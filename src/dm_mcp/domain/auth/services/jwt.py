"""JWT 服务：统一管理 JWT token 的生成和验证"""

import logging
from datetime import datetime, timezone
from typing import Any

from authlib.jose import jwt
from authlib.jose.errors import ExpiredTokenError, JoseError

from dm_mcp.common import messages
from dm_mcp.core.exceptions.auth_errors import InvalidTokenError, TokenExpiredError
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.core.service import BaseService
from dm_mcp.domain.auth.services.auth_config import AuthConfigService

logger = logging.getLogger(__name__)


class JwtService(BaseService):
    """JWT 服务：统一管理 JWT token 的生成和验证"""

    def __init__(self, auth_config_service: AuthConfigService, app_secret: str) -> None:
        self._auth_config_service = auth_config_service
        self._app_secret = app_secret

    @property
    def app_secret(self) -> str:
        """应用主密钥（用于外部服务需要相同密钥的场景，如 OAuth state 加密）"""
        return self._app_secret

    @property
    def token_expire_seconds(self) -> int:
        """JWT token 过期时间（秒）"""
        return self._auth_config_service.jwt_token_expire_seconds

    def create_token(
        self, user_info: dict[str, Any], expires_in: int | None = None
    ) -> str:
        """
        创建 JWT token

        Args:
            user_info: 用户信息字典（必须包含 "sub" 字段作为用户 ID）
            expires_in: 过期时间（秒），如果为 None 则使用配置中的默认值

        Returns:
            JWT token 字符串
        """
        # 复制 user_info 避免修改原始字典
        payload = user_info.copy()

        # 添加友好的用户名字段，前端显示用户名时会优先使用
        # 优先级: name > preferred_username > email > sub
        username = (
            payload.get("name")
            or payload.get("preferred_username")
            or payload.get("email")
            or payload.get("sub")
        )
        if username:
            payload["username"] = username

        # 添加过期时间
        expires_in = expires_in or self._auth_config_service.jwt_token_expire_seconds
        now = datetime.now(timezone.utc)
        payload["exp"] = int(now.timestamp() + expires_in)
        payload["iat"] = int(now.timestamp())

        # 生成 JWT token
        header = {"alg": "HS256"}
        token = jwt.encode(header, payload, self._app_secret)

        # 兼容 bytes 和 str 返回类型
        if isinstance(token, bytes):
            return token.decode("utf-8")
        return token

    def decode_token(self, token: str) -> dict[str, Any]:
        """
        解码并验证 JWT token

        Args:
            token: JWT token 字符串

        Returns:
            解码后的 claims 字典

        Raises:
            TokenExpiredError: Token 已过期
            InvalidTokenError: Token 无效或验证失败
        """
        try:
            claims = jwt.decode(token, self._app_secret)
            claims.validate()
            # 将 Claims 对象转换为字典
            return dict(claims)
        except ExpiredTokenError as e:
            raise TokenExpiredError() from e
        except JoseError as e:
            raise InvalidTokenError(messages.MSG_AUTH_TOKEN_VALIDATION_FAILED) from e

    def parse_jwt_payload(
        self, token: str, verify_signature: bool = False
    ) -> dict[str, Any]:
        """
        解析 JWT token 的 payload（不验证签名）

        用于解析第三方签发的 JWT（如 OAuth 提供商的 id_token），
        这些 token 不是用我们的密钥签名的，所以不需要验证签名。

        Args:
            token: JWT token 字符串
            verify_signature: 是否验证签名（默认 False）

        Returns:
            解码后的 payload 字典

        Raises:
            InvalidTokenError: Token 格式无效或解析失败
        """
        try:
            if verify_signature:
                # 如果需要验证签名，使用 decode_token 方法
                return self.decode_token(token)

            # 不验证签名，只解析 payload
            # authlib.jose 的 jwt.decode 需要密钥，但我们可以提供一个假的密钥
            # 然后跳过验证步骤，或者直接手动解析 payload 部分
            # 对于 id_token，我们只需要读取 payload 中的用户信息
            import base64
            import json

            # JWT 格式：header.payload.signature
            parts = token.split(".")
            if len(parts) < 2:
                raise InvalidTokenError(messages.MSG_JWT_PAYLOAD_MISSING)

            # 解析 payload（第二部分）
            payload_part = parts[1]
            # 添加 base64 padding（如果需要）
            payload_part += "=" * (4 - len(payload_part) % 4)

            try:
                decoded_bytes = base64.urlsafe_b64decode(payload_part)
                payload = json.loads(decoded_bytes.decode("utf-8"))
                return payload
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
                raise InvalidTokenError(
                    messages.MSG_JWT_PAYLOAD_DECODE_FAILED.format(error=str(e))
                ) from e

        except InvalidTokenError:
            raise
        except Exception as e:
            logger.debug(f"Unexpected error parsing JWT: {e}", exc_info=True)
            raise InvalidTokenError(messages.MSG_JWT_TOKEN_FORMAT_INVALID.format(error=str(e))) from e


class JwtServiceFactory(ServiceFactory):
    """JWT 服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="jwt_service",
            service_type=JwtService,
            description="JWT 服务（token 生成和验证）",
            author="DM MCP Team",
            dependencies=["auth_config_service"],
            priority=15,  # 优先级较高，早于 OAuth 和 BasicAuth 服务
        )

    def create(self, settings, auth_config_service, **deps) -> JwtService:
        return JwtService(
            auth_config_service=auth_config_service,
            app_secret=settings.app_secret.get_secret_value(),
        )
