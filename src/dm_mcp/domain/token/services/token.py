import asyncio
import base64
import ipaddress
import json
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dm_mcp.common import messages
from dm_mcp.infra.persistence import (
    TokenModel,
    bootstrap_schema,
    close_db,
    get_async_session,
    init_db,
)
from dm_mcp.infra.persistence.models import generate_short_id
from dm_mcp.core.exceptions.auth_errors import AuthorizationError, InvalidTokenError, TokenExpiredError
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.domain.token.events import TokenRevoked
from dm_mcp.infra.messaging.event import EventService
from dm_mcp.domain.auth.services.auth_config import AuthConfigService
from dm_mcp.infra.config import Settings
from dm_mcp.infra.config.token_auth_config import TokenConfig

from dm_mcp.core.service import BaseService

logger = logging.getLogger(__name__)

# MCP Token 前缀，用于在 Bearer 认证中区分 JWT
TOKEN_PREFIX = "sk-dmmcp-"


class TokenService(BaseService):
    """Token 管理服务

    管理 API Token 的创建、验证和维护。

    主要功能：
    - Token 持久化（SQLite 数据库）
    - Token 验证（存在性、有效期）
    - Token 维护（清理过期、更新最后使用时间）
    - Token CRUD 操作（创建、查询、更新、删除）
    - Token 缓存机制（提升验证性能）
    """

    def __init__(self, settings: Settings, event_service: EventService, auth_config_service: AuthConfigService) -> None:
        self.settings = settings
        self._event_service = event_service
        self._auth_config_service = auth_config_service
        self._cleanup_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        # Token 验证缓存：token -> (TokenConfig, cached_at)
        self._token_cache: dict[str, tuple[TokenConfig, datetime]] = {}
        self._cache_ttl = timedelta(seconds=300)  # 5分钟缓存 TTL
        # 延迟更新队列：用于异步更新 last_used_at（有界，防内存泄露）
        self._pending_updates: list[str] = []
        self._max_pending_updates: int = 100  # 队列上限，超出的直接丢弃
        self._update_lock = asyncio.Lock()

    async def startup(self) -> None:
        """服务启动：初始化数据库，启动清理任务"""
        # 初始化数据库
        init_db(self.settings.database)
        await bootstrap_schema(self.settings.database)
        logger.info(f"Token 数据库已初始化: {self.settings.database.db_type}")

        # 启动清理任务
        if self._auth_config_service.token_auth_auto_cleanup:
            self._cleanup_task = asyncio.create_task(
                self._cleanup_expired_tokens_loop()
            )
            logger.info("已启动 Token 自动清理任务")

    async def shutdown(self) -> None:
        """服务关闭：停止清理任务，关闭数据库连接"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("已停止 Token 自动清理任务")

        # 关闭数据库连接
        await close_db()
        logger.info("数据库连接已关闭")

    # ============================================================
    # Token 验证
    # ============================================================

    async def validate_token(self, token: str) -> TokenConfig:
        """
        验证 Token（带缓存）

        Args:
            token: Token 值

        Returns:
            TokenConfig 如果有效

        Raises:
            InvalidTokenError: Token 不存在
            TokenExpiredError: Token 已过期
        """
        now = datetime.now(timezone.utc)

        # 先检查缓存
        if token in self._token_cache:
            cached_config, cached_at = self._token_cache[token]

            # 检查缓存是否过期（基于 TTL）
            if now - cached_at < self._cache_ttl:
                # 即使缓存未过期，也要检查 Token 本身是否过期
                if cached_config.expires_at < now:
                    # Token 已过期，清除缓存
                    del self._token_cache[token]
                    raise TokenExpiredError(
                        messages.MSG_AUTH_TOKEN_EXPIRED_AT.format(
                            expired_at=cached_config.expires_at.isoformat()
                        )
                    )
                # 缓存有效且 Token 未过期，直接返回
                # 异步更新 last_used_at（不阻塞验证流程）
                asyncio.create_task(self._update_last_used_async(token, now))
                return cached_config
            else:
                # 缓存过期，清除
                del self._token_cache[token]

        # 缓存未命中，从数据库读取
        async with self._lock:
            async with get_async_session() as session:
                result = await session.execute(
                    select(TokenModel).where(TokenModel.token == token)
                )
                token_model = result.scalar_one_or_none()

                if token_model is None:
                    raise InvalidTokenError(
                        messages.MSG_AUTH_TOKEN_NOT_FOUND.format(
                            token_hint=f"{token[:8]}..."
                        )
                    )

                # 转换为 TokenConfig
                token_config = self._model_to_config(token_model)

                # 检查过期
                if token_config.expires_at < now:
                    raise TokenExpiredError(
                        messages.MSG_AUTH_TOKEN_EXPIRED_AT.format(
                            expired_at=token_config.expires_at.isoformat()
                        )
                    )

                # 更新最后使用时间
                token_config.last_used_at = now
                token_model.last_used_at = now
                # get_async_session 会在退出时自动提交

                # 更新缓存
                self._token_cache[token] = (token_config, now)

                return token_config

    # ============================================================
    # Token CRUD 操作
    # ============================================================

    async def list_tokens(self, user_id: str | None = None) -> list[TokenConfig]:
        """
        列出 Token

        Args:
            user_id: 用户 ID，如果提供则只返回该用户创建的 Token；
                    如果为 None 则从当前认证上下文获取用户 ID。

        Returns:
            Token 列表
        """
        effective_user_id = user_id or self.current_user_id
        async with get_async_session() as session:
            query = select(TokenModel)
            if effective_user_id is not None:
                query = query.where(TokenModel.user_id == effective_user_id)
            result = await session.execute(query)
            token_models = result.scalars().all()
            return [self._model_to_config(model) for model in token_models]

    async def get_token(self, token: str) -> TokenConfig | None:
        """获取单个 Token 配置

        Args:
            token: Token 值

        Returns:
            Token 配置，如果不存在返回 None
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(TokenModel).where(TokenModel.token == token)
            )
            token_model = result.scalar_one_or_none()
            if token_model is None:
                return None
            return self._model_to_config(token_model)

    async def get_by_token_id(self, token_id: str) -> TokenConfig | None:
        """根据 token_id 获取 Token 配置（管理用接口入口）

        Args:
            token_id: 管理短码（12 字符 base62）

        Returns:
            Token 配置，如果不存在返回 None

        Raises:
            AuthorizationError: 当前用户无权访问该 Token
        """
        user_id = self.current_user_id
        async with get_async_session() as session:
            result = await session.execute(
                select(TokenModel).where(TokenModel.token_id == token_id)
            )
            token_model = result.scalar_one_or_none()
            if token_model is None:
                return None
            if token_model.user_id != user_id:
                raise AuthorizationError(
                    f"无权访问 Token: {token_id}",
                    error_code="ACCESS_DENIED",
                )
            return self._model_to_config(token_model)

    async def create_token(
        self,
        user_id: str,
        datasource_ids: list[str],
        default_datasource_id: str,
        name: str,
        expires_in: int | None = None,
        ip_whitelist: list[str] | None = None,
        ip_blacklist: list[str] | None = None,
        ssh_host_ids: list[str] | None = None,
    ) -> TokenConfig:
        """
        创建 Token

        Args:
            user_id: 用户 ID（从 AuthContext 获取）
            datasource_ids: 允许访问的数据源 UUID 列表
            default_datasource_id: 默认数据源 UUID
            name: Token 名称（必填，非空）
            expires_in: 有效期（秒），默认使用配置中的默认值
            ip_whitelist: IP 白名单列表（可选，支持单个 IP 或 CIDR）
            ip_blacklist: IP 黑名单列表（可选，支持单个 IP 或 CIDR）
            ssh_host_ids: 允许访问的 SSH 主机 UUID 列表（可选）

        Returns:
            创建的 TokenConfig

        Raises:
            ValueError: name 为空字符串，或数据源列表校验失败时
        """
        if not name or not name.strip():
            raise ValueError(messages.MSG_TOKEN_NAME_REQUIRED)

        # 校验数据源列表
        if not datasource_ids:
            raise ValueError("数据源列表不能为空")
        if default_datasource_id not in datasource_ids:
            raise ValueError(
                f"默认数据源不在允许列表中"
            )

        ssh_host_ids = ssh_host_ids or []

        async with self._lock:
            # 生成随机 Token（Base64 编码），并添加 MCP Token 前缀
            token_bytes = secrets.token_bytes(32)  # 32 字节 = 256 位
            raw_token = (
                base64.urlsafe_b64encode(token_bytes).decode("utf-8").rstrip("=")
            )
            token = f"{TOKEN_PREFIX}{raw_token}"

            # 计算过期时间
            expires_in = expires_in or self._auth_config_service.token_auth_default_expires_in
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=expires_in)

            # 构建 metadata，包含 IP 名单
            metadata: dict[str, Any] = {}
            if ip_whitelist is not None:
                metadata["ip_whitelist"] = ip_whitelist
            if ip_blacklist is not None:
                metadata["ip_blacklist"] = ip_blacklist

            # 创建 TokenModel
            token_model = TokenModel(
                token=token,
                token_id=generate_short_id(),
                user_id=user_id,
                datasource_ids=json.dumps([str(ds_id) for ds_id in datasource_ids]),
                default_datasource_id=default_datasource_id,
                ssh_host_ids=json.dumps([str(hid) for hid in ssh_host_ids]),
                created_at=now,
                last_used_at=now,
                expires_at=expires_at,
                name=name,
                token_metadata=json.dumps(metadata, ensure_ascii=False),
            )

            # 保存到数据库（get_async_session 会在退出时自动提交）
            async with get_async_session() as session:
                session.add(token_model)

            logger.info(f"已创建 Token: {token[:8]}... (user={user_id})")

            # 转换为 TokenConfig
            token_config = self._model_to_config(token_model)

            # 清除相关缓存（如果有）
            if token_config.token in self._token_cache:
                del self._token_cache[token_config.token]

            return token_config

    async def update_token(
        self,
        token_id: str,
        datasource_ids: list[str] | None = None,
        default_datasource_id: str | None = None,
        expires_at: datetime | None = None,
        name: str | None = None,
        ip_whitelist: list[str] | None = None,
        ip_blacklist: list[str] | None = None,
        ssh_host_ids: list[str] | None = None,
    ) -> TokenConfig:
        """
        更新 Token

        Args:
            token_id: Token 管理短码（12 字符 base62）
            datasource_ids: 允许访问的数据源 UUID 列表（可选）
            default_datasource_id: 默认数据源 UUID（可选）
            expires_at: 过期时间（可选）
            name: Token 名称（可选；传入时不能为空字符串）
            ip_whitelist: IP 白名单列表（可选，支持单个 IP 或 CIDR）
            ip_blacklist: IP 黑名单列表（可选，支持单个 IP 或 CIDR）
            ssh_host_ids: 允许访问的 SSH 主机 UUID 列表（可选）

        Returns:
            更新后的 TokenConfig

        Raises:
            ValueError: Token 不存在，或数据源列表校验失败时
            AuthorizationError: 当前用户无权修改该 Token
        """
        user_id = self.current_user_id
        async with self._lock:
            async with get_async_session() as session:
                result = await session.execute(
                    select(TokenModel).where(TokenModel.token_id == token_id)
                )
                token_model = result.scalar_one_or_none()

                if token_model is None:
                    raise ValueError(
                        messages.MSG_TOKEN_NOT_FOUND_BY_ID.format(token_id=token_id)
                    )
                if token_model.user_id != user_id:
                    raise AuthorizationError(
                        f"无权访问 Token: {token_id}",
                        error_code="ACCESS_DENIED",
                    )

                # 更新数据源列表
                if datasource_ids is not None:
                    if not datasource_ids:
                        raise ValueError("数据源列表不能为空")
                    token_model.datasource_ids = json.dumps(
                        [str(ds_id) for ds_id in datasource_ids]
                    )

                # 更新默认数据源
                if default_datasource_id is not None:
                    # 校验默认数据源在新的（或当前的）列表中
                    effective_ids = datasource_ids
                    if effective_ids is None:
                        # 未更新列表，使用当前值
                        effective_ids = [
                            uuid.UUID(ds_id)
                            for ds_id in json.loads(token_model.datasource_ids or "[]")
                        ]
                    if default_datasource_id not in effective_ids:
                        raise ValueError(
                            "默认数据源不在允许列表中"
                        )
                    token_model.default_datasource_id = default_datasource_id

                if expires_at is not None:
                    # 确保 expires_at 是 aware datetime
                    token_model.expires_at = self._ensure_aware_datetime_required(
                        expires_at
                    )
                if name is not None:
                    if not name.strip():
                        raise ValueError(messages.MSG_TOKEN_NAME_REQUIRED)
                    token_model.name = name

                # 更新 metadata（IP 名单）
                if ip_whitelist is not None or ip_blacklist is not None:
                    metadata = (
                        json.loads(token_model.token_metadata)
                        if token_model.token_metadata
                        else {}
                    )
                    if ip_whitelist is not None:
                        metadata["ip_whitelist"] = ip_whitelist
                    if ip_blacklist is not None:
                        metadata["ip_blacklist"] = ip_blacklist
                    token_model.token_metadata = json.dumps(
                        metadata, ensure_ascii=False
                    )

                # 更新 SSH 主机列表
                if ssh_host_ids is not None:
                    token_model.ssh_host_ids = json.dumps(
                        [str(hid) for hid in ssh_host_ids]
                    )

                # get_async_session 会在退出时自动提交
                # 不需要手动刷新，对象已经是最新的
                token_config = self._model_to_config(token_model)
                cached_token = token_model.token

            logger.info(f"已更新 Token: token_id={token_id}")

            # 清除缓存（更新后需要重新验证），缓存以明文 token 为 key
            if cached_token in self._token_cache:
                del self._token_cache[cached_token]

            return token_config

    async def delete_token(self, token_id: str) -> None:
        """
        删除 Token

        Args:
            token_id: Token 管理短码（12 字符 base62）

        Raises:
            ValueError: Token 不存在
            AuthorizationError: 当前用户无权删除该 Token
        """
        user_id = self.current_user_id
        async with self._lock:
            async with get_async_session() as session:
                # 先查询再删除，以校验所有权
                result = await session.execute(
                    select(TokenModel).where(TokenModel.token_id == token_id)
                )
                token_model = result.scalar_one_or_none()

                if token_model is None:
                    raise ValueError(
                        messages.MSG_TOKEN_NOT_FOUND_BY_ID.format(token_id=token_id)
                    )
                if token_model.user_id != user_id:
                    raise AuthorizationError(
                        f"无权访问 Token: {token_id}",
                        error_code="ACCESS_DENIED",
                    )

                deleted_token = token_model.token
                deleted_user_id = token_model.user_id
                await session.delete(token_model)

            logger.info(f"已删除 Token: token_id={token_id}")

            # 清除缓存（缓存以明文 token 为 key）
            if deleted_token in self._token_cache:
                del self._token_cache[deleted_token]

        # 锁外发布事件,避免订阅者反向调用 token_service 造成死锁
        await self._event_service.publish(
            TokenRevoked(token=deleted_token, reason="deleted", user_id=deleted_user_id)
        )

    # ============================================================
    # IP 地址验证
    # ============================================================

    @staticmethod
    def _is_ip_allowed(
        ip: str, whitelist: list[str] | None, blacklist: list[str] | None
    ) -> bool:
        """检查 IP 是否允许访问

        Args:
            ip: 客户端 IP 地址
            whitelist: IP 白名单列表（支持单个 IP 或 CIDR）
            blacklist: IP 黑名单列表（支持单个 IP 或 CIDR）

        Returns:
            bool: True 表示允许访问，False 表示拒绝访问
        """
        # 黑名单优先检查
        if blacklist:
            for pattern in blacklist:
                if TokenService._ip_matches(ip, pattern):
                    logger.debug(f"IP {ip} 匹配黑名单规则: {pattern}")
                    return False

        # 白名单检查
        if whitelist:
            for pattern in whitelist:
                if TokenService._ip_matches(ip, pattern):
                    logger.debug(f"IP {ip} 匹配白名单规则: {pattern}")
                    return True
            # 有白名单但不在列表中，拒绝访问
            logger.debug(f"IP {ip} 不在白名单中")
            return False

        # 既没有白名单也没有黑名单，允许访问（向后兼容）
        return True

    @staticmethod
    def _ip_matches(ip: str, pattern: str) -> bool:
        """判断 IP 是否匹配模式（单个 IP 或 CIDR 网段）

        Args:
            ip: 客户端 IP 地址
            pattern: 匹配模式（单个 IP 或 CIDR，如 "192.168.1.1" 或 "192.168.1.0/24"）

        Returns:
            bool: True 表示匹配，False 表示不匹配
        """
        try:
            ip_obj = ipaddress.ip_address(ip)
            if "/" in pattern:
                # CIDR 网段匹配
                network = ipaddress.ip_network(pattern, strict=False)
                return ip_obj in network
            else:
                # 单个 IP 匹配
                pattern_ip = ipaddress.ip_address(pattern)
                return ip_obj == pattern_ip
        except ValueError as e:
            # IP 格式错误，记录警告但不影响其他规则检查
            logger.warning(f"IP 匹配模式格式错误: {pattern}, IP: {ip}, 错误: {e}")
            return False
        except Exception as e:
            logger.warning(f"IP 匹配检查异常: {pattern}, IP: {ip}, 错误: {e}")
            return False

    # ============================================================
    # 模型转换
    # ============================================================

    @staticmethod
    def _ensure_aware_datetime(dt: datetime | None) -> datetime | None:
        """
        确保 datetime 对象是 aware（带时区信息）

        如果 datetime 是 naive（没有时区信息），则假设它是 UTC 并转换为 aware datetime
        如果 datetime 是 aware，则直接返回

        Args:
            dt: datetime 对象（可能是 None）

        Returns:
            aware datetime 对象或 None
        """
        if dt is None:
            return None
        if dt.tzinfo is None:
            # naive datetime，假设是 UTC 并转换为 aware
            return dt.replace(tzinfo=timezone.utc)
        # 已经是 aware datetime，直接返回
        return dt

    @staticmethod
    def _ensure_aware_datetime_required(dt: datetime) -> datetime:
        """
        确保 datetime 对象是 aware（带时区信息），用于不能为 None 的字段

        如果 datetime 是 naive（没有时区信息），则假设它是 UTC 并转换为 aware datetime
        如果 datetime 是 aware，则直接返回

        Args:
            dt: datetime 对象（不能为 None）

        Returns:
            aware datetime 对象
        """
        if dt.tzinfo is None:
            # naive datetime，假设是 UTC 并转换为 aware
            return dt.replace(tzinfo=timezone.utc)
        # 已经是 aware datetime，直接返回
        return dt

    def _model_to_config(self, model: TokenModel) -> TokenConfig:
        """将 TokenModel 转换为 TokenConfig"""
        metadata = json.loads(model.token_metadata) if model.token_metadata else {}
        # 从 metadata 中提取 IP 名单（如果有）
        ip_whitelist = metadata.get("ip_whitelist")
        ip_blacklist = metadata.get("ip_blacklist")

        # 解析 datasource_ids JSON 字符串
        datasource_ids: list[str] = []
        if model.datasource_ids:
            try:
                datasource_ids = json.loads(model.datasource_ids)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    f"Token {model.token[:8]}... 的数据源列表解析失败: {model.datasource_ids}"
                )

        # 解析 ssh_host_ids JSON 字符串
        ssh_host_ids: list[str] = []
        if model.ssh_host_ids:
            try:
                ssh_host_ids = json.loads(model.ssh_host_ids)
            except (json.JSONDecodeError, ValueError):
                logger.warning(
                    f"Token {model.token[:8]}... 的 SSH 主机列表解析失败: {model.ssh_host_ids}"
                )

        return TokenConfig(
            token=model.token,
            token_id=model.token_id,
            user_id=model.user_id,
            datasource_ids=datasource_ids,
            default_datasource_id=str(model.default_datasource_id) if model.default_datasource_id else None,
            ssh_host_ids=ssh_host_ids,
            created_at=self._ensure_aware_datetime_required(model.created_at),
            expires_at=self._ensure_aware_datetime_required(model.expires_at),
            last_used_at=self._ensure_aware_datetime(model.last_used_at),
            name=model.name,
            metadata=metadata,
            ip_whitelist=ip_whitelist,
            ip_blacklist=ip_blacklist,
        )

    # ============================================================
    # 清理过期 Token
    # ============================================================

    async def _cleanup_expired_tokens_loop(self) -> None:
        """定期清理过期 Token 的后台任务"""
        while True:
            try:
                await asyncio.sleep(self._auth_config_service.token_auth_cleanup_interval)
                await self.cleanup_expired_tokens()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"清理过期 Token 失败: {e}", exc_info=True)

    async def cleanup_expired_tokens(self) -> int:
        """
        清理过期的 Token

        Returns:
            清理的 Token 数量
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            async with get_async_session() as session:
                # 使用索引优化查询
                result = await session.execute(
                    delete(TokenModel)
                    .where(TokenModel.expires_at < now)
                    .returning(TokenModel.token, TokenModel.user_id)
                )
                deleted_rows = list(result.all())
                removed_count = len(deleted_rows)

                # get_async_session 会在退出时自动提交
                if removed_count > 0:
                    logger.info(f"已清理 {removed_count} 个过期 Token")

        # 锁外按单 token 发布,订阅者按单 token 处理派生数据
        for deleted_token, deleted_user_id in deleted_rows:
            await self._event_service.publish(
                TokenRevoked(
                    token=deleted_token,
                    reason="expired",
                    user_id=deleted_user_id,
                )
            )

        return removed_count

    async def _update_last_used_async(self, token: str, used_at: datetime) -> None:
        """异步更新 Token 的最后使用时间（不阻塞验证流程）

        采用批量聚合策略：token 先入队，延迟 1 秒后由第一个醒来的 task
        一次性批量 UPDATE，减少数据库往返次数。
        """
        try:
            # 避免频繁写入，如果已经在更新队列中，跳过；队列满则丢弃
            async with self._update_lock:
                if token in self._pending_updates:
                    return
                if len(self._pending_updates) >= self._max_pending_updates:
                    return  # 队列已满，直接丢弃本次更新（非关键字段）
                self._pending_updates.append(token)

            # 稍微延迟，聚合同一时间段内的其他 token
            await asyncio.sleep(1)

            # 批量 flush：由第一个醒来的 task 把队列中所有 token 一次性更新
            async with self._update_lock:
                if not self._pending_updates:
                    return
                batch = list(self._pending_updates)
                self._pending_updates.clear()

            # 批量 UPDATE：一次 SQL 更新所有聚合到的 token
            async with get_async_session() as session:
                now = datetime.now(timezone.utc)
                await session.execute(
                    update(TokenModel)
                    .where(TokenModel.token.in_(batch))
                    .values(last_used_at=now)
                )

            # 同步更新内存缓存中的 last_used_at
            for t in batch:
                if t in self._token_cache:
                    config, cached_at = self._token_cache[t]
                    config.last_used_at = now
                    self._token_cache[t] = (config, cached_at)

        except Exception as e:
            logger.warning(
                f"异步更新 Token last_used_at 失败: {token[:8]}..., error: {e}"
            )


# =========================================================
# Factory
# =========================================================
class TokenServiceFactory(ServiceFactory):
    """Token 管理服务工厂

    负责创建和配置 TokenService 实例。
    """

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="token_service",
            service_type=TokenService,
            description="Token 管理服务（SQLite 持久化 + CRUD + 验证）",
            author="DM MCP Team",
            dependencies=["event_service", "auth_config_service"],
            priority=10,  # 优先级高，早于其他需要认证的服务启动
        )

    def create(self, settings, event_service, auth_config_service, **deps) -> TokenService:
        return TokenService(settings, event_service, auth_config_service)
