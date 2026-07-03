"""BasicAuth 服务：管理 admin 用户密码和认证"""

import base64
import logging
from datetime import datetime, timezone
from typing import Optional

from passlib.context import CryptContext
from sqlalchemy import select

from dm_mcp.core.db import AdminUserModel, get_async_session
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.services.base_service import BaseService
from dm_mcp.services.jwt_service import JwtService
from dm_mcp.settings import Settings

logger = logging.getLogger(__name__)

# 密码上下文（使用 PBKDF2 SHA256）
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Admin 用户名（固定）
ADMIN_USERNAME = "admin"


class BasicAuthService(BaseService):
    """BasicAuth 服务：管理 admin 用户密码和认证"""

    def __init__(self, settings: Settings, jwt_service: JwtService) -> None:
        self.settings = settings
        self.jwt_service = jwt_service

    async def is_initialized(self) -> bool:
        """检查 admin 密码是否已初始化"""
        async with get_async_session() as session:
            result = await session.execute(
                select(AdminUserModel).where(AdminUserModel.username == ADMIN_USERNAME)
            )
            admin_user = result.scalar_one_or_none()
            return admin_user is not None

    async def init_password(self, password: str) -> None:
        """
        初始化 admin 密码（仅在未初始化时可用）

        Args:
            password: 密码（最少6位）

        Raises:
            ValueError: 密码不符合要求或已初始化
        """
        # 验证密码长度
        if len(password) < 6:
            raise ValueError("密码长度不能少于6位")

        # 检查是否已初始化
        if await self.is_initialized():
            raise ValueError("admin 密码已初始化，无法重复初始化")

        # 生成密码哈希
        password_hash = pwd_context.hash(password)

        # 保存到数据库
        now = datetime.now(timezone.utc)
        admin_user = AdminUserModel(
            username=ADMIN_USERNAME,
            password_hash=password_hash,
            created_at=now,
            updated_at=now,
        )

        async with get_async_session() as session:
            session.add(admin_user)
            # get_async_session 会在退出时自动提交

        logger.info("admin 密码已初始化")

    async def change_password(self, old_password: str, new_password: str) -> None:
        """
        修改 admin 密码

        Args:
            old_password: 旧密码
            new_password: 新密码（最少6位）

        Raises:
            ValueError: 密码不符合要求或旧密码错误
        """
        # 验证新密码长度
        if len(new_password) < 6:
            raise ValueError("新密码长度不能少于6位")

        # 获取 admin 用户
        async with get_async_session() as session:
            result = await session.execute(
                select(AdminUserModel).where(AdminUserModel.username == ADMIN_USERNAME)
            )
            admin_user = result.scalar_one_or_none()

            if admin_user is None:
                raise ValueError("admin 用户不存在，请先初始化密码")

            # 验证旧密码
            if not pwd_context.verify(old_password, admin_user.password_hash):
                raise ValueError("旧密码错误")

            # 更新密码哈希
            admin_user.password_hash = pwd_context.hash(new_password)
            admin_user.updated_at = datetime.now(timezone.utc)
            # get_async_session 会在退出时自动提交

        logger.info("admin 密码已更新")

    async def verify_password(self, password: str) -> bool:
        """
        验证密码

        Args:
            password: 密码

        Returns:
            True 如果密码正确，False 否则
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(AdminUserModel).where(AdminUserModel.username == ADMIN_USERNAME)
            )
            admin_user = result.scalar_one_or_none()

            if admin_user is None:
                return False

            return pwd_context.verify(password, admin_user.password_hash)

    def create_jwt_token(self) -> str:
        """
        为 admin 用户创建 JWT token

        Returns:
            JWT token 字符串
        """
        # 构造 user_info（兼容 OAuth 的格式）
        user_info = {
            "sub": ADMIN_USERNAME,  # subject（用户标识）
            "username": ADMIN_USERNAME,
            "auth_type": "basic_auth",
        }

        # 使用 JwtService 生成 token
        return self.jwt_service.create_token(user_info)

    @staticmethod
    def decode_basic_auth(auth_header: str) -> tuple[str, str] | None:
        """
        解码 Basic Auth header

        Args:
            auth_header: Authorization header 的值（格式：Basic base64(username:password)）

        Returns:
            (username, password) 元组，如果格式错误返回 None
        """
        try:
            if not auth_header.startswith("Basic "):
                return None

            # 移除 "Basic " 前缀
            encoded = auth_header[6:]

            # Base64 解码
            decoded = base64.b64decode(encoded).decode("utf-8")

            # 分割用户名和密码
            if ":" not in decoded:
                return None

            username, password = decoded.split(":", 1)
            return username, password
        except Exception:
            return None


class BasicAuthServiceFactory(ServiceFactory):
    """BasicAuth 服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="basic_auth_service",
            service_type=BasicAuthService,
            description="BasicAuth 服务（admin 密码管理和认证）",
            author="DM MCP Team",
            dependencies=["jwt_service"],
            priority=20,  # 优先级较高，但在 JwtService 之后
        )

    def create(self, settings, **deps) -> BasicAuthService:
        return BasicAuthService(settings, deps["jwt_service"])
