"""SSH 命令执行服务

内部维护连接缓存（按 host_id），自动管理连接的生命周期：
- 按需创建：首次执行时建立连接
- 空闲复用：短时间内重复执行复用同一连接
- 超时回收：空闲超过 TTL 后自动关闭，释放资源
- 优雅关闭：服务 shutdown 时批量关闭所有连接
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncssh

from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.core.service import BaseService
from dm_mcp.domain.ssh.services.host import SSHHostService

logger = logging.getLogger(__name__)


@dataclass
class SSHResult:
    """单次命令执行结果"""

    success: bool
    stdout: str
    stderr: str
    exit_code: int | None
    error: str | None
    duration_ms: int


@dataclass
class _ConnectionEntry:
    """内部连接缓存条目"""

    conn: asyncssh.SSHClientConnection
    last_used_at: datetime
    in_use: bool = False


class SSHExecutionService(BaseService):
    """SSH 命令执行服务

    面向内部调用方的高级接口，屏蔽连接生命周期细节。
    调用方只需知道「在哪个主机上执行什么命令」。
    """

    def __init__(
        self,
        ssh_host_service: SSHHostService,
        idle_ttl: float = 60.0,
        max_connections: int = 50,
        cleanup_interval: float = 30.0,
    ) -> None:
        self._host_service = ssh_host_service
        self._idle_ttl = idle_ttl
        self._max_connections = max_connections
        self._cleanup_interval = cleanup_interval

        self._connection_cache: dict[str, _ConnectionEntry] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._cache_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task | None = None

    # ============================================================
    # 服务生命周期
    # ============================================================

    async def startup(self) -> None:
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            f"SSH 执行服务已启动 (idle_ttl={self._idle_ttl}s, "
            f"max_connections={self._max_connections})"
        )

    async def shutdown(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._cache_lock:
            for host_id, entry in list(self._connection_cache.items()):
                try:
                    entry.conn.close()
                    await entry.conn.wait_closed()
                    logger.debug(f"已关闭 SSH 连接: {host_id}")
                except Exception as e:
                    logger.warning(f"关闭 SSH 连接失败 {host_id}: {e}")
            self._connection_cache.clear()

        logger.info("SSH 执行服务已关闭")

    # ============================================================
    # 公开接口
    # ============================================================

    async def execute(
        self,
        host_id: str,
        command: str,
        timeout: float = 30.0,
    ) -> SSHResult:
        """在指定主机执行单条命令

        Args:
            host_id: SSH 主机 UUID
            command: 要执行的命令
            timeout: 执行超时（秒）

        Returns:
            SSHResult: 执行结果
        """
        start = datetime.now(timezone.utc)
        lock = self._get_host_lock(host_id)

        async with lock:
            try:
                conn = await self._get_or_create_connection(host_id)
                result = await conn.run(command, timeout=timeout)

                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                await self._touch(host_id)

                return SSHResult(
                    success=result.exit_status == 0,
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    exit_code=result.exit_status,
                    error=None,
                    duration_ms=duration,
                )
            except asyncio.TimeoutError:
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                # 超时后断开连接，避免残留
                await self._remove_connection(host_id)
                return SSHResult(
                    success=False,
                    stdout="",
                    stderr="",
                    exit_code=None,
                    error=f"命令执行超时（{timeout}s）",
                    duration_ms=duration,
                )
            except Exception as e:
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                # 连接异常时清理缓存，下次重建
                await self._remove_connection(host_id)
                return SSHResult(
                    success=False,
                    stdout="",
                    stderr="",
                    exit_code=None,
                    error=f"SSH 执行失败: {e}",
                    duration_ms=duration,
                )

    async def execute_script(
        self,
        host_id: str,
        script: str,
        timeout: float = 60.0,
    ) -> SSHResult:
        """在指定主机执行多行脚本

        通过 stdin 传入脚本内容执行。
        """
        start = datetime.now(timezone.utc)
        lock = self._get_host_lock(host_id)

        async with lock:
            try:
                conn = await self._get_or_create_connection(host_id)
                result = await conn.run(
                    script, timeout=timeout, stdin=script.encode()
                )

                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                await self._touch(host_id)

                return SSHResult(
                    success=result.exit_status == 0,
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                    exit_code=result.exit_status,
                    error=None,
                    duration_ms=duration,
                )
            except asyncio.TimeoutError:
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                await self._remove_connection(host_id)
                return SSHResult(
                    success=False,
                    stdout="",
                    stderr="",
                    exit_code=None,
                    error=f"脚本执行超时（{timeout}s）",
                    duration_ms=duration,
                )
            except Exception as e:
                duration = int(
                    (datetime.now(timezone.utc) - start).total_seconds() * 1000
                )
                await self._remove_connection(host_id)
                return SSHResult(
                    success=False,
                    stdout="",
                    stderr="",
                    exit_code=None,
                    error=f"SSH 脚本执行失败: {e}",
                    duration_ms=duration,
                )

    async def execute_multi(
        self,
        host_ids: list[str],
        command: str,
        timeout: float = 30.0,
    ) -> dict[str, SSHResult]:
        """在多台主机并行执行同一命令

        Args:
            host_ids: SSH 主机 UUID 列表
            command: 要执行的命令
            timeout: 每台主机的超时（秒）

        Returns:
            dict[str, SSHResult]: host_id -> 执行结果
        """
        coros = [self.execute(hid, command, timeout) for hid in host_ids]
        results = await asyncio.gather(*coros, return_exceptions=True)

        return {
            hid: (
                result
                if isinstance(result, SSHResult)
                else SSHResult(
                    success=False,
                    stdout="",
                    stderr="",
                    exit_code=None,
                    error=str(result),
                    duration_ms=0,
                )
            )
            for hid, result in zip(host_ids, results)
        }

    # ============================================================
    # 连接管理（内部）
    # ============================================================

    def _get_host_lock(self, host_id: str) -> asyncio.Lock:
        """获取指定 host 的执行锁（同一 host 串行）"""
        if host_id not in self._host_locks:
            self._host_locks[host_id] = asyncio.Lock()
        return self._host_locks[host_id]

    async def _get_or_create_connection(
        self, host_id: str
    ) -> asyncssh.SSHClientConnection:
        """获取连接：缓存命中则复用，否则新建"""
        async with self._cache_lock:
            entry = self._connection_cache.get(host_id)
            if entry is not None:
                # 检查连接是否仍活跃
                if not entry.conn.is_closed():
                    entry.in_use = True
                    return entry.conn
                # 已断开，移除
                del self._connection_cache[host_id]

            # 检查全局连接数上限
            if len(self._connection_cache) >= self._max_connections:
                # 关闭最老的空闲连接
                await self._evict_oldest()

        # 锁外创建连接（避免阻塞其他 host）
        config = await self._host_service.get_host_config(host_id)
        if not config:
            raise ValueError(f"SSH 主机不存在: {host_id}")

        conn_kwargs: dict[str, Any] = {
            "host": config.host,
            "port": config.port,
            "username": config.username,
            "known_hosts": None,  # 暂不校验 known_hosts
        }

        if config.key_based:
            # 免密模式：依赖 OS 级 ssh-agent 或 ~/.ssh 默认密钥
            pass
        elif config.password:
            conn_kwargs["password"] = config.password

        conn = await asyncssh.connect(**conn_kwargs)

        async with self._cache_lock:
            self._connection_cache[host_id] = _ConnectionEntry(
                conn=conn,
                last_used_at=datetime.now(timezone.utc),
                in_use=True,
            )

        logger.debug(f"已创建 SSH 连接: {config.host}:{config.port} ({host_id})")
        return conn

    async def _touch(self, host_id: str) -> None:
        """更新连接最后使用时间"""
        async with self._cache_lock:
            entry = self._connection_cache.get(host_id)
            if entry is not None:
                entry.last_used_at = datetime.now(timezone.utc)
                entry.in_use = False

    async def _remove_connection(self, host_id: str) -> None:
        """移除并关闭指定连接"""
        async with self._cache_lock:
            entry = self._connection_cache.pop(host_id, None)
        if entry is not None:
            try:
                entry.conn.close()
                await entry.conn.wait_closed()
            except Exception:
                pass

    async def _evict_oldest(self) -> None:
        """驱逐最老的空闲连接（在 cache_lock 内调用）"""
        now = datetime.now(timezone.utc)
        candidates = [
            (hid, entry)
            for hid, entry in self._connection_cache.items()
            if not entry.in_use
        ]
        if not candidates:
            # 全部 busy，强制移除最老的
            candidates = list(self._connection_cache.items())

        candidates.sort(key=lambda x: x[1].last_used_at)
        for hid, entry in candidates[:1]:
            del self._connection_cache[hid]
            try:
                entry.conn.close()
                await entry.conn.wait_closed()
            except Exception:
                pass
            logger.debug(f"已驱逐 SSH 连接: {hid}")
            break

    async def _cleanup_loop(self) -> None:
        """后台清理任务：定期关闭 idle 超时的连接"""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_idle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSH 连接清理任务异常: {e}")

    async def _cleanup_idle(self) -> None:
        """关闭超过 idle_ttl 的空闲连接"""
        now = datetime.now(timezone.utc)
        to_close: list[_ConnectionEntry] = []

        async with self._cache_lock:
            for host_id, entry in list(self._connection_cache.items()):
                if entry.in_use:
                    continue
                idle_seconds = (now - entry.last_used_at).total_seconds()
                if idle_seconds > self._idle_ttl:
                    to_close.append(entry)
                    del self._connection_cache[host_id]

        for entry in to_close:
            try:
                entry.conn.close()
                await entry.conn.wait_closed()
            except Exception:
                pass

        if to_close:
            logger.debug(f"已清理 {len(to_close)} 个 idle SSH 连接")


# =========================================================
# Factory
# =========================================================
class SSHExecutionServiceFactory(ServiceFactory):
    """SSH 命令执行服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="ssh_execution_service",
            service_type=SSHExecutionService,
            description="SSH 命令执行服务（连接缓存 + 生命周期管理）",
            dependencies=["ssh_host_service"],
            priority=13,
        )

    def create(self, settings, ssh_host_service, **deps) -> SSHExecutionService:
        return SSHExecutionService(ssh_host_service)
