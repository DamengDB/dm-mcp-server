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
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from dm_mcp.core.db import (
    TokenModel,
    close_db,
    create_tables,
    get_async_session,
    init_db,
)
from dm_mcp.core.exceptions.auth_errors import InvalidTokenError, TokenExpiredError
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.services.base_service import BaseService
from dm_mcp.settings import Settings
from dm_mcp.settings.token_auth_config import TokenAuthConfig, TokenConfig

logger = logging.getLogger(__name__)


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

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.token_auth_config: TokenAuthConfig = settings.token_auth
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        # Token 验证缓存：token -> (TokenConfig, cached_at)
        self._token_cache: Dict[str, Tuple[TokenConfig, datetime]] = {}
        self._cache_ttl = timedelta(seconds=300)  # 5分钟缓存 TTL
        # 延迟更新队列：用于异步更新 last_used_at
        self._pending_updates: List[str] = []
        self._update_lock = asyncio.Lock()

    async def startup(self) -> None:
        """服务启动：初始化数据库，启动清理任务"""
        # 初始化数据库
        init_db(self.settings.database)
        await create_tables()
        logger.info(f"Token 数据库已初始化: {self.settings.database.db_type}")

        # 启动清理任务
        if self.token_auth_config.auto_cleanup:
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
                        f"Token expired at {cached_config.expires_at.isoformat()}"
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
                    raise InvalidTokenError(f"Token not found: {token[:8]}...")

                # 转换为 TokenConfig
                token_config = self._model_to_config(token_model)

                # 检查过期
                if token_config.expires_at < now:
                    raise TokenExpiredError(
                        f"Token expired at {token_config.expires_at.isoformat()}"
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

    async def list_tokens(self, user_id: Optional[str] = None) -> List[TokenConfig]:
        """
        列出 Token

        Args:
            user_id: 用户 ID，如果提供则只返回该用户创建的 Token；如果为 None 则返回所有 Token

        Returns:
            Token 列表
        """
        async with get_async_session() as session:
            query = select(TokenModel)
            if user_id is not None:
                query = query.where(TokenModel.user_id == user_id)
            result = await session.execute(query)
            token_models = result.scalars().all()
            return [self._model_to_config(model) for model in token_models]

    async def get_token(self, token: str) -> Optional[TokenConfig]:
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

    async def create_token(
        self,
        user_id: str,
        datasource_id: uuid.UUID,
        expires_in: Optional[int] = None,
        description: Optional[str] = None,
        ip_whitelist: Optional[List[str]] = None,
        ip_blacklist: Optional[List[str]] = None,
    ) -> TokenConfig:
        """
        创建 Token

        Args:
            user_id: 用户 ID（从 AuthContext 获取）
            datasource_id: 绑定的数据源 UUID
            expires_in: 有效期（秒），默认使用配置中的默认值
            description: 描述信息
            ip_whitelist: IP 白名单列表（可选，支持单个 IP 或 CIDR）
            ip_blacklist: IP 黑名单列表（可选，支持单个 IP 或 CIDR）

        Returns:
            创建的 TokenConfig
        """
        async with self._lock:
            # 生成随机 Token（Base64 编码）
            token_bytes = secrets.token_bytes(32)  # 32 字节 = 256 位
            token = base64.urlsafe_b64encode(token_bytes).decode("utf-8").rstrip("=")

            # 计算过期时间
            expires_in = expires_in or self.token_auth_config.default_expires_in
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=expires_in)

            # 构建 metadata，包含 IP 名单
            metadata: Dict[str, Any] = {}
            if ip_whitelist is not None:
                metadata["ip_whitelist"] = ip_whitelist
            if ip_blacklist is not None:
                metadata["ip_blacklist"] = ip_blacklist

            # 创建 TokenModel
            token_model = TokenModel(
                token=token,
                user_id=user_id,
                datasource_id=datasource_id,
                created_at=now,
                last_used_at=now,
                expires_at=expires_at,
                description=description,
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
        token: str,
        datasource_id: Optional[uuid.UUID] = None,
        expires_at: Optional[datetime] = None,
        description: Optional[str] = None,
        ip_whitelist: Optional[List[str]] = None,
        ip_blacklist: Optional[List[str]] = None,
    ) -> TokenConfig:
        """
        更新 Token

        Args:
            token: Token 值
            datasource_id: 绑定的数据源 UUID（可选）
            expires_at: 过期时间（可选）
            description: 描述信息（可选）
            ip_whitelist: IP 白名单列表（可选，支持单个 IP 或 CIDR）
            ip_blacklist: IP 黑名单列表（可选，支持单个 IP 或 CIDR）

        Returns:
            更新后的 TokenConfig

        Raises:
            ValueError: Token 不存在
        """
        async with self._lock:
            async with get_async_session() as session:
                result = await session.execute(
                    select(TokenModel).where(TokenModel.token == token)
                )
                token_model = result.scalar_one_or_none()

                if token_model is None:
                    raise ValueError(f"Token not found: {token[:8]}...")

                # 更新字段
                if datasource_id is not None:
                    token_model.datasource_id = datasource_id
                if expires_at is not None:
                    # 确保 expires_at 是 aware datetime
                    token_model.expires_at = self._ensure_aware_datetime_required(
                        expires_at
                    )
                if description is not None:
                    token_model.description = description

                # 更新 IP 名单（存储在 metadata 中）
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

                # get_async_session 会在退出时自动提交
                # 不需要手动刷新，对象已经是最新的
                token_config = self._model_to_config(token_model)

            logger.info(f"已更新 Token: {token[:8]}...")

            # 清除缓存（更新后需要重新验证）
            if token in self._token_cache:
                del self._token_cache[token]

            return token_config

    async def delete_token(self, token: str) -> None:
        """
        删除 Token

        Args:
            token: Token 值

        Raises:
            ValueError: Token 不存在
        """
        async with self._lock:
            async with get_async_session() as session:
                result = await session.execute(
                    delete(TokenModel)
                    .where(TokenModel.token == token)
                    .returning(TokenModel.token)
                )
                deleted_token = result.scalar_one_or_none()

                if deleted_token is None:
                    raise ValueError(f"Token not found: {token[:8]}...")

                # get_async_session 会在退出时自动提交

            logger.info(f"已删除 Token: {token[:8]}...")

            # 清除缓存
            if token in self._token_cache:
                del self._token_cache[token]

    # ============================================================
    # IP 地址验证
    # ============================================================

    @staticmethod
    def _is_ip_allowed(
        ip: str, whitelist: Optional[List[str]], blacklist: Optional[List[str]]
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
    def _ensure_aware_datetime(dt: Optional[datetime]) -> Optional[datetime]:
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

        return TokenConfig(
            token=model.token,
            user_id=model.user_id,
            datasource_id=model.datasource_id,
            created_at=self._ensure_aware_datetime_required(model.created_at),
            expires_at=self._ensure_aware_datetime_required(model.expires_at),
            last_used_at=self._ensure_aware_datetime(model.last_used_at),
            description=model.description,
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
                await asyncio.sleep(self.token_auth_config.cleanup_interval)
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
                    .returning(TokenModel.token)
                )
                deleted_tokens = result.scalars().all()
                removed_count = len(list(deleted_tokens))

                # get_async_session 会在退出时自动提交
                if removed_count > 0:
                    logger.info(f"已清理 {removed_count} 个过期 Token")

            return removed_count

    async def _update_last_used_async(self, token: str, used_at: datetime) -> None:
        """异步更新 Token 的最后使用时间（不阻塞验证流程）"""
        try:
            # 避免频繁写入，如果已经在更新队列中，跳过
            async with self._update_lock:
                if token in self._pending_updates:
                    return
                self._pending_updates.append(token)

            # 稍微延迟，批量处理
            await asyncio.sleep(1)

            # 从数据库获取最新的 token_model
            async with get_async_session() as session:
                result = await session.execute(
                    select(TokenModel).where(TokenModel.token == token)
                )
                token_model = result.scalar_one_or_none()

                if token_model:
                    # 确保 expires_at 是 aware datetime 以便比较
                    expires_at = self._ensure_aware_datetime(token_model.expires_at)
                    now = datetime.now(timezone.utc)

                    if expires_at and expires_at > now:
                        # 只在未过期时更新
                        token_model.last_used_at = used_at
                        # get_async_session 会在退出时自动提交

                        # 转换为 TokenConfig 并更新缓存
                        token_config = self._model_to_config(token_model)
                        if token in self._token_cache:
                            self._token_cache[token] = (
                                token_config,
                                datetime.now(timezone.utc),
                            )

            # 从待更新队列移除
            async with self._update_lock:
                if token in self._pending_updates:
                    self._pending_updates.remove(token)
        except Exception as e:
            logger.warning(
                f"异步更新 Token last_used_at 失败: {token[:8]}..., error: {e}"
            )
            # 确保从待更新队列移除
            async with self._update_lock:
                if token in self._pending_updates:
                    self._pending_updates.remove(token)


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
            dependencies=[],
            priority=10,  # 优先级高，早于其他需要认证的服务启动
        )

    def create(self, settings, **deps) -> TokenService:
        return TokenService(settings)
