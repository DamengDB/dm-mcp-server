"""dmAsync 连接池服务模块

纯连接池管理服务，不接触数据源配置和权限。
职责：
- 维护 name -> Pool 映射
- 按需创建/删除/关闭连接池
- 提供 Pool 状态查询
"""

import asyncio
import logging
import re
import time
from typing import Any, TypeVar

from dmAsync.connection import connect
from dmAsync.pool import Pool

_T = TypeVar("_T")

_SQL_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_#$]*$")


def _validate_identifier(name: str) -> None:
    """校验 schema/table/column 等 SQL 标识符合法性（防注入）"""
    if not _SQL_IDENTIFIER_RE.match(name):
        raise ValueError(messages.MSG_DB_ILLEGAL_SQL_IDENTIFIER.format(name=name))

from collections.abc import Awaitable, Callable

from dm_mcp.common import messages
from dm_mcp.infra.persistence import DataSourceModel
from dm_mcp.core.events import EventSubscription
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.domain.datasource.events import (
    DataSourceCreated,
    DataSourceDeleted,
    DataSourceUpdated,
)
from dm_mcp.core.service import BaseService
from dm_mcp.domain.system.services.metrics import MetricsService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# bug 131823
#
# 上游在 override_min（池扩容）分支错误地 ``connect(self._dsn, ...)``，首个位置参数
# 被解析为 host，导致 user/password 未传入；并发下还易触发 dmPython 连接异常。
# 此处改为与 minsize 分支一致的关键字参数，并用进程级 Lock 串行化 connect。
# ---------------------------------------------------------------------------
_POOL_FILL_PATCHED_ATTR = "_dmmcp_pool_fill_free_patched"
_connect_serialize_lock = asyncio.Lock()


def _apply_dm_async_pool_fill_hotfix() -> None:
    """幂等：替换 ``dmAsync.pool.Pool._fill_free_pool``。"""
    if getattr(Pool, _POOL_FILL_PATCHED_ATTR, False):
        return

    async def _fill_free_pool_fixed(self: Any, override_min: bool) -> None:
        n, free = 0, len(self._free)
        while n < free:
            conn = self._free[-1]
            conn.get_closed()
            if conn.closed:
                self._free.pop()
            elif -1 < self._recycle < self._loop.time() - conn.last_usage:
                await conn.close()
                self._free.pop()
            else:
                self._free.rotate()
            n += 1

        while self.size < self.minsize:
            self._acquiring += 1
            try:
                async with _connect_serialize_lock:
                    conn = await connect(
                        dsn=self._dsn,
                        host=self._host,
                        user=self._user,
                        password=self._password,
                        port=self._port,
                        **self._conn_kwargs,
                    )
                if self._on_connect is not None:
                    await self._on_connect(conn)
                self._free.append(conn)
                self._cond.notify()
            finally:
                self._acquiring -= 1
        if self._free:
            return

        if override_min and (not self.maxsize or self.size < self.maxsize):
            self._acquiring += 1
            try:
                async with _connect_serialize_lock:
                    conn = await connect(
                        dsn=self._dsn,
                        host=self._host,
                        user=self._user,
                        password=self._password,
                        port=self._port,
                        **self._conn_kwargs,
                    )
                if self._on_connect is not None:
                    await self._on_connect(conn)
                self._free.append(conn)
                self._cond.notify()
            finally:
                self._acquiring -= 1

    Pool._fill_free_pool = _fill_free_pool_fixed  # type: ignore[method-assign]
    setattr(Pool, _POOL_FILL_PATCHED_ATTR, True)
    logger.debug("dmAsync Pool._fill_free_pool 补丁已启用")


_apply_dm_async_pool_fill_hotfix()


# =========================================================
# AsyncPoolService
# =========================================================
class AsyncPoolService(BaseService):
    """dmAsync 连接池服务（纯池管理，无配置/权限耦合）"""

    def __init__(
        self,
        metrics_service: MetricsService,
    ) -> None:
        self.metrics_service = metrics_service

        # data_source_name -> Pool
        self._pools: dict[str, Pool] = {}

        # init 防重入
        self._init_lock = asyncio.Lock()
        self._initialized = False

        # 全局锁，保护 _creation_locks 字典的原子访问
        self._global_lock = asyncio.Lock()
        # 按数据源名称的创建锁，防止并行创建同一个连接池
        self._creation_locks: dict[str, asyncio.Lock] = {}

        # 同一 dmAsync Pool 上串行执行 SQL（dmPython 多协程并发下偶发异常）
        self._pool_execute_locks: dict[int, asyncio.Lock] = {}

    # ---------------------------
    # 生命周期
    # ---------------------------
    async def startup(self) -> None:
        await self.init_pools()

    async def shutdown(self) -> None:
        for name, pool in list(self._pools.items()):
            try:
                pool.close()
                await pool.wait_closed()
            except Exception as e:
                logger.warning(f"关闭连接池失败: {name}, err={e}")
        self._pools.clear()
        self._initialized = False

    async def init_pools(self) -> None:
        async with self._init_lock:
            if self._initialized:
                return
            logger.info("dmAsync 连接池服务已启动，连接池按需创建")
            self._initialized = True

    # ---------------------------
    # 核心：获取或创建 Pool
    # ---------------------------
    async def get_or_create_pool(self, ds: DataSourceModel) -> Pool:
        """获取已有 Pool，或根据配置现场创建

        Args:
            ds: 数据源配置

        Returns:
            Pool 对象

        Raises:
            Exception: 建池失败时抛出
        """
        # 快速路径：已有池，直接返回
        pool = self._pools.get(ds.name)
        if pool is not None:
            logger.debug(f"数据源 [{ds.name}] 连接池已存在，直接复用, pool_id={id(pool)}, pool_count={len(self._pools)}")
            return pool

        logger.debug(f"数据源 [{ds.name}] 连接池不存在，准备创建..., 当前池数={len(self._pools)}")

        # 获取该数据源的创建锁（必须用全局锁保证字典访问的原子性）
        async with self._global_lock:
            if ds.name not in self._creation_locks:
                self._creation_locks[ds.name] = asyncio.Lock()
            lock = self._creation_locks[ds.name]

        # 加锁创建连接池，防止并行创建导致的竞态条件
        async with lock:
            # 双重检查，防止其他协程已经创建完成
            pool = self._pools.get(ds.name)
            if pool is not None:
                logger.debug(f"其他协程已创建数据源 [{ds.name}] 连接池, pool_id={id(pool)}")
                return pool

            logger.info(f"开始创建数据源 [{ds.name}] 连接池...")
            pool = await self._init_single_pool(ds)
            self._pools[ds.name] = pool
            logger.info(f"数据源 [{ds.name}] 连接池已创建, pool_id={id(pool)}")
            return pool

    async def _init_single_pool(self, ds: DataSourceModel) -> Pool:
        password = ds.password or ""

        if not password:
            logger.error(
                f"[CRITICAL] 创建连接池时发现密码为空！数据源: {ds.name}, "
                f"user={ds.user}, host={ds.host}, port={ds.port}"
            )
        else:
            logger.debug(f"创建连接池，数据源: {ds.name}, user={ds.user}, password_len={len(password)}")

        conn_kwargs: dict[str, Any] = {
            "user": ds.user,
            "password": password,
            "port": ds.port,
            "local_code": 1,
        }

        if ds.dsn:
            dsn = ds.dsn
            host = None
        else:
            dsn = None
            host = ds.host

        try:
            pool = await asyncio.wait_for(
                Pool.from_pool_fill(
                    dsn=dsn,
                    host=host,
                    minsize=ds.minsize,
                    maxsize=ds.maxsize,
                    timeout=ds.timeout,
                    on_connect=self._default_on_connect,
                    pool_recycle=ds.timeout,
                    **conn_kwargs,
                ),
                timeout=max(ds.timeout + 5.0, 30.0),
            )
        except asyncio.TimeoutError:
            raise ValueError(
                messages.MSG_DATASOURCE_CONNECTION_TIMEOUT.format(name=ds.name)
            ) from None
        except Exception:
            raise

        logger.info(
            f"单实例数据源 [{ds.name}] 连接池已创建："
            f"min={ds.minsize}, max={ds.maxsize}, read_only={ds.read_only}"
        )
        return pool

    async def _default_on_connect(self, conn):
        try:
            conn.autoCommit = True
        except Exception as e:
            logger.warning(f"on_connect 执行异常: {e}")

    # ---------------------------
    # 对外能力
    # ---------------------------
    def has_pool(self, name: str) -> bool:
        return name in self._pools

    def list_pool_names(self) -> list[str]:
        return list(self._pools.keys())

    async def pool_status(self) -> dict[str, Any]:
        """获取已创建连接池的运行时状态"""
        current_time = int(time.time() * 1000)
        status_info: dict[str, Any] = {}

        for name, pool in self._pools.items():
            size = getattr(pool, "size", 0)
            freesize = getattr(pool, "freesize", 0)
            minsize = getattr(pool, "minsize", 0)
            maxsize = getattr(pool, "maxsize", 0)
            active_connections = max(0, int(size) - int(freesize))
            usage_rate = (
                (active_connections / max(1, int(size))) * 100 if size > 0 else 0
            )

            status_info[name] = {
                "status": "active",
                "size": size,
                "freesize": freesize,
                "minsize": minsize,
                "maxsize": maxsize,
                "active_connections": active_connections,
                "usage_rate": round(usage_rate, 2),
                "health_status": self._determine_pool_health(
                    usage_rate, active_connections > 0
                ),
                "last_check_time": current_time,
                "error_count": 0,
            }

        return {"status": status_info}

    def _determine_pool_health(self, usage_rate: float, has_errors: bool) -> str:
        if has_errors or usage_rate > 95:
            return "critical"
        if usage_rate > 80:
            return "warning"
        return "healthy"

    # ---------------------------
    # 动态管理
    # ---------------------------
    async def add_pool(self, ds: DataSourceModel) -> None:
        if ds.name in self._pools:
            raise ValueError(messages.MSG_DATASOURCE_NAME_EXISTS.format(name=ds.name))
        await self.get_or_create_pool(ds)

    async def remove_pool(self, name: str, timeout: float = 30.0) -> None:
        if name not in self._pools:
            raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND.format(name=name))

        pool = self._pools.get(name)
        if pool:
            pool_id = id(pool)
            await self._graceful_close_pool(pool, name, timeout)
            del self._pools[name]

        # 清理创建锁
        if name in self._creation_locks:
            del self._creation_locks[name]

        logger.info(f"已动态删除连接池: {name}")

    async def reload_pool(self, ds: DataSourceModel, timeout: float = 30.0) -> None:
        if ds.name in self._pools:
            await self.remove_pool(ds.name, timeout)
        await self.add_pool(ds)
        logger.info(f"已重载连接池: {ds.name}")

    async def reload_all_pools(
        self, datasources: list[DataSourceModel]
    ) -> dict[str, Any]:
        """批量重载连接池

        Args:
            datasources: 数据源配置列表

        Returns:
            dict: 含 closed, created, errors
        """
        closed: list[str] = []
        created: list[str] = []
        errors: list[dict[str, str]] = []

        for ds in datasources:
            if not ds.enabled:
                continue
            try:
                if self.has_pool(ds.name):
                    await self.reload_pool(ds)
                    closed.append(ds.name)
                    created.append(ds.name)
                else:
                    await self.add_pool(ds)
                    created.append(ds.name)
            except Exception as e:
                errors.append({"name": ds.name, "error": str(e)})

        return {"closed": closed, "created": created, "errors": errors}

    async def execute(
        self,
        pool: Pool,
        sql: str,
        params: dict[str, Any] | None = None,
        schema: str | None = None,
    ) -> list[Any]:
        """使用给定 Pool 执行 SQL 查询

        Args:
            pool: 连接池对象
            sql: SQL 语句
            params: 绑定参数
            schema: 默认 schema 名称

        Returns:
            查询结果列表
        """
        pid = id(pool)
        async with self._global_lock:
            if pid not in self._pool_execute_locks:
                self._pool_execute_locks[pid] = asyncio.Lock()
            lock = self._pool_execute_locks[pid]
        async with lock:
            async with pool.acquire() as conn:
                cur = await conn.cursor()
                try:
                    if schema:
                        _validate_identifier(schema)
                        await cur.execute(f"SET SCHEMA {schema}")

                    if params:
                        await cur.execute(sql, params)
                    else:
                        await cur.execute(sql)

                    description = getattr(cur, "description", None)
                    if description:
                        rows = await cur.fetchall()
                        rows = self._normalize_rows_to_dicts(rows, description)
                    else:
                        rows = []

                    return self.convert_bytes_for_json(rows)
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass

    async def run_in_session(
        self,
        pool: Pool,
        callback: Callable[[Any], Awaitable[_T]],
    ) -> _T:
        """在连接池上单连接、串行执行回调（供 explain trace 等多步会话操作）。"""
        pid = id(pool)
        async with self._global_lock:
            if pid not in self._pool_execute_locks:
                self._pool_execute_locks[pid] = asyncio.Lock()
            lock = self._pool_execute_locks[pid]
        async with lock:
            async with pool.acquire() as conn:
                return await callback(conn)

    def convert_bytes_for_json(self, obj: Any) -> Any:
        return self._convert_bytes_for_json(obj)

    async def test_connection(self, ds: DataSourceModel) -> dict[str, Any]:
        try:
            pool = await self._init_single_pool(ds)
            async with pool.acquire() as conn:
                cur = await conn.cursor()
                try:
                    await cur.execute("SELECT 1")
                    rows = await cur.fetchall()
                    success = len(rows) > 0
                finally:
                    try:
                        cur.close()
                    except Exception:
                        pass
            pool.close()
            await pool.wait_closed()
            return {"success": success, "message": "连接测试成功"}
        except Exception as e:
            logger.error(f"连接测试失败: {ds.name}, err={e}")
            return {"success": False, "message": f"连接测试失败: {str(e)}"}

    def _normalize_rows_to_dicts(
        self, rows: list[Any], description: Any | None
    ) -> list[Any]:
        if not rows or isinstance(rows[0], dict):
            return rows
        col_names: list[Any] | None = None
        try:
            if description:
                col_names = [desc[0] for desc in description]
        except Exception:
            col_names = None
        if not col_names:
            return rows
        mapped_rows: list[Any] = []
        for row in rows:
            if isinstance(row, dict):
                mapped_rows.append(row)
                continue
            try:
                mapped_rows.append(
                    {col_names[i]: row[i] for i in range(len(col_names))}
                )
            except Exception:
                mapped_rows.append(row)
        return mapped_rows

    def _convert_bytes_for_json(self, obj: Any) -> Any:
        if isinstance(obj, bytes):
            try:
                return obj.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                import base64
                return base64.b64encode(obj).decode("ascii")
        elif isinstance(obj, (list, tuple)):
            return [self._convert_bytes_for_json(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._convert_bytes_for_json(v) for k, v in obj.items()}
        else:
            return obj

    async def _graceful_close_pool(
        self, pool: Pool, name: str, timeout: float = 30.0
    ) -> None:
        start_time = time.time()
        wait_interval = 0.5

        while True:
            size = getattr(pool, "size", 0)
            freesize = getattr(pool, "freesize", 0)
            active = max(0, int(size) - int(freesize))

            if active == 0:
                logger.info(f"连接池 {name} 无活跃连接，安全关闭")
                break

            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(
                    f"连接池 {name} 等待超时({timeout}s)，仍有 {active} 个活跃连接，强制关闭"
                )
                break

            logger.debug(
                f"连接池 {name} 有 {active} 个活跃连接，等待中... ({elapsed:.1f}s/{timeout}s)"
            )
            await asyncio.sleep(wait_interval)

        try:
            pool.close()
            await asyncio.wait_for(pool.wait_closed(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.warning(f"关闭连接池超时: {name}")
        except Exception as e:
            logger.warning(f"关闭连接池失败: {name}, err={e}")

    # ---------------------------
    # 事件订阅（DataSource 联动）
    # ---------------------------
    @staticmethod
    def _event_to_model(event: DataSourceCreated | DataSourceUpdated) -> DataSourceModel:
        """从事件数据构造 DataSourceModel"""
        return DataSourceModel(
            id=event.datasource_id,
            name=event.name,
            enabled=event.enabled,
            deploy_type=event.deploy_type,
            read_only=event.read_only,
            dsn=event.dsn,
            host=event.host,
            port=event.port,
            user=event.user,
            password=event.password,
            minsize=event.minsize,
            maxsize=event.maxsize,
            timeout=event.timeout,
            weight=event.weight,
            owner_id=event.owner_id,
        )

    async def on_datasource_created(self, event: DataSourceCreated) -> None:
        if event.enabled:
            await self.add_pool(self._event_to_model(event))

    async def on_datasource_deleted(self, event: DataSourceDeleted) -> None:
        if self.has_pool(event.name):
            await self.remove_pool(event.name)

    async def on_datasource_updated(self, event: DataSourceUpdated) -> None:
        logger.info(
            f"[事件] DataSourceUpdated: old_name={event.old_name}, "
            f"new_name={event.name}, enabled={event.enabled}, "
            f"current_pools={self.list_pool_names()}"
        )
        old_name = event.old_name
        model = self._event_to_model(event)
        had_pool = self.has_pool(old_name)
        renamed = old_name != event.name

        if renamed and had_pool:
            # rename 时先直接改 key，避免 graceful_close 在 connect 阻塞时卡死事件循环
            pool = self._pools.pop(old_name)
            self._pools[event.name] = pool
            # 检查配置是否变化：若变化则用 terminate 强制关闭（同步、不阻塞）后重建
            config_changed = (
                pool._host != model.host
                or pool._port != model.port
                or pool._user != model.user
                or pool._password != model.password
                or (getattr(pool, "_dsn", None) or "") != (model.dsn or "")
            )
            if config_changed:
                pool.terminate()
                del self._pools[event.name]
                had_pool = False
            else:
                had_pool = True

        if event.enabled:
            if had_pool:
                await self.reload_pool(model)
            else:
                await self.add_pool(model)
        else:
            if had_pool:
                await self.remove_pool(event.name)
        logger.info(
            f"[事件] DataSourceUpdated 处理完成: pools={self.list_pool_names()}"
        )


# =========================================================
# Factory
# =========================================================
class AsyncPoolServiceFactory(ServiceFactory):
    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="async_pool_service",
            service_type=AsyncPoolService,
            description="dmAsync 异步连接池服务（纯池管理）",
            author="DM MCP Team",
            dependencies=["metrics_service"],
            event_subscriptions=[
                EventSubscription(
                    event_type=DataSourceCreated,
                    handler_method="on_datasource_created",
                    priority=50,
                ),
                EventSubscription(
                    event_type=DataSourceUpdated,
                    handler_method="on_datasource_updated",
                    priority=50,
                ),
                EventSubscription(
                    event_type=DataSourceDeleted,
                    handler_method="on_datasource_deleted",
                    priority=50,
                ),
            ],
            priority=50,
        )

    def create(self, settings, **deps) -> AsyncPoolService:
        return AsyncPoolService(deps["metrics_service"])
