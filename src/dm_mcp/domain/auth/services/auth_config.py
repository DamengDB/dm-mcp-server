"""认证配置服务模块

统一管理所有认证相关的运行时配置：
- OAuth 提供商配置（client_id, client_secret, scope, 端点等）
- OAuth 全局开关（enabled, cookie_secure, state_ttl_seconds）
- Token Auth 配置（enabled, cleanup_interval, auto_cleanup, default_expires_in）
- JWT 配置（token_expire_seconds）
- Fernet 加密/解密 client_secret
- secret 掩码处理（API 返回时仅展示后 4 位）
- 启动时自动 seed 4 个 OAuth 固定槽位
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from dm_mcp.infra.persistence import AppSettingsModel, OAuthProviderModel, get_async_session
from dm_mcp.infra.persistence.models import OAuthProviderModel as _OAuthProviderModel
from dm_mcp.infra.security.crypto import FernetCrypto
from dm_mcp.core.service import ServiceFactory, ServiceMetadata

from dm_mcp.core.service import BaseService

logger = logging.getLogger(__name__)

# 4 个固定槽位定义
OAUTH_SLOTS = ["google", "microsoft", "github", "oidc"]

# 内置 provider 的默认 scope（JSON 字符串）
DEFAULT_SCOPES = {
    "google": '["openid", "email", "profile"]',
    "microsoft": '["openid", "profile", "email", "User.Read"]',
    "github": '["openid", "email", "profile"]',
    "oidc": '["openid", "email", "profile"]',
}

# OAuth 全局配置 key（复用 app_settings 表）
OAUTH_GLOBAL_CONFIG_KEYS = {
    "enabled": "oauth.enabled",
    "cookie_secure": "oauth.cookie_secure",
    "state_ttl_seconds": "oauth.state_ttl_seconds",
}

# Token Auth 配置 key
TOKEN_AUTH_CONFIG_KEYS = {
    "token_auth_enabled": "token_auth.enabled",
    "token_auth_cleanup_interval": "token_auth.cleanup_interval",
    "token_auth_auto_cleanup": "token_auth.auto_cleanup",
    "token_auth_default_expires_in": "token_auth.default_expires_in",
}

# JWT 配置 key
JWT_CONFIG_KEYS = {
    "jwt_token_expire_seconds": "jwt.token_expire_seconds",
}

# 所有 key-value 配置项的合并字典
ALL_KV_CONFIG_KEYS = {**OAUTH_GLOBAL_CONFIG_KEYS, **TOKEN_AUTH_CONFIG_KEYS, **JWT_CONFIG_KEYS}

# 默认值
KV_DEFAULTS = {
    "enabled": False,
    "cookie_secure": False,
    "state_ttl_seconds": 600,
    "token_auth_enabled": True,
    "token_auth_cleanup_interval": 3600,
    "token_auth_auto_cleanup": True,
    "token_auth_default_expires_in": 604800,
    "jwt_token_expire_seconds": 3600,
}


class OAuthProviderConfig(BaseModel):
    """OAuth 提供商配置 schema（service 层使用）"""

    slot: str
    name: str
    display_name: str | None = None
    is_builtin: bool = True
    enabled: bool = False
    visible: bool = True
    client_id: str = ""
    client_secret: str = ""  # 仅在写入时使用；读取时由 service 控制是否填充
    scopes: list[str] = ["openid", "email", "profile"]
    discovery_url: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None


class OAuthGlobalConfig(BaseModel):
    """OAuth 全局配置 schema"""

    enabled: bool = False
    cookie_secure: bool = False
    state_ttl_seconds: int = 600


class AuthConfigService(BaseService):
    """认证配置服务

    统一管理所有认证相关的运行时配置（DB 化）。
    """

    def __init__(self, crypto: FernetCrypto) -> None:
        self._crypto = crypto
        self._config: dict[str, Any] = dict(KV_DEFAULTS)

    async def startup(self) -> None:
        """启动时加载配置并确保 OAuth 槽位已 seed"""
        await self._load_from_db()
        await self.ensure_slots_seeded()
        logger.info("认证配置服务已启动，配置已加载，OAuth 槽位已就绪")

    # ------------------------------------------------------------------
    # Key-value 配置加载/更新
    # ------------------------------------------------------------------

    async def _load_from_db(self) -> None:
        """从数据库加载所有 key-value 配置到内存缓存"""
        async with get_async_session() as session:
            for field, key in ALL_KV_CONFIG_KEYS.items():
                result = await session.execute(
                    select(AppSettingsModel).where(AppSettingsModel.key == key)
                )
                row = result.scalar_one_or_none()
                if row is not None:
                    self._config[field] = self._parse_value(field, row.value)

    async def get_config(self) -> dict[str, Any]:
        """获取所有 key-value 认证配置"""
        return dict(self._config)

    async def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        """更新配置并持久化到数据库，同时更新内存热生效

        Args:
            updates: 要更新的配置字典，key 为 ALL_KV_CONFIG_KEYS 中的 field 名

        Returns:
            更新后的完整配置字典

        Raises:
            ValueError: 当包含无效的配置项时
        """
        for key in updates:
            if key not in ALL_KV_CONFIG_KEYS:
                raise ValueError(f"无效的配置项: {key}")
            self._config[key] = updates[key]

        async with get_async_session() as session:
            for key, value in updates.items():
                db_key = ALL_KV_CONFIG_KEYS[key]
                result = await session.execute(
                    select(AppSettingsModel).where(AppSettingsModel.key == db_key)
                )
                row = result.scalar_one_or_none()
                str_value = str(value).lower() if isinstance(value, bool) else str(value)
                if row is not None:
                    row.value = str_value
                else:
                    session.add(AppSettingsModel(key=db_key, value=str_value))

        logger.info(f"认证配置已更新: {updates}")
        return dict(self._config)

    # ------------------------------------------------------------------
    # OAuth 全局配置（兼容旧接口）
    # ------------------------------------------------------------------

    async def get_oauth_global_config(self) -> OAuthGlobalConfig:
        """读取全局 OAuth 配置"""
        return OAuthGlobalConfig(
            enabled=self._config["enabled"],
            cookie_secure=self._config["cookie_secure"],
            state_ttl_seconds=self._config["state_ttl_seconds"],
        )

    async def update_oauth_global_config(self, config: OAuthGlobalConfig) -> OAuthGlobalConfig:
        """更新全局 OAuth 配置"""
        updates = {
            "enabled": config.enabled,
            "cookie_secure": config.cookie_secure,
            "state_ttl_seconds": config.state_ttl_seconds,
        }
        await self.update_config(updates)
        return config

    # ------------------------------------------------------------------
    # Token Auth / JWT 属性访问（内存缓存，同步）
    # ------------------------------------------------------------------

    @property
    def token_auth_enabled(self) -> bool:
        return self._config["token_auth_enabled"]

    @property
    def token_auth_cleanup_interval(self) -> int:
        return self._config["token_auth_cleanup_interval"]

    @property
    def token_auth_auto_cleanup(self) -> bool:
        return self._config["token_auth_auto_cleanup"]

    @property
    def token_auth_default_expires_in(self) -> int:
        return self._config["token_auth_default_expires_in"]

    @property
    def jwt_token_expire_seconds(self) -> int:
        return self._config["jwt_token_expire_seconds"]

    @property
    def oauth_enabled(self) -> bool:
        return self._config["enabled"]

    @property
    def oauth_cookie_secure(self) -> bool:
        return self._config["cookie_secure"]

    @property
    def oauth_state_ttl_seconds(self) -> int:
        return self._config["state_ttl_seconds"]

    # ------------------------------------------------------------------
    # OAuth Provider CRUD
    # ------------------------------------------------------------------

    async def ensure_slots_seeded(self) -> None:
        """检查并补全 4 个固定槽位"""
        async with get_async_session() as session:
            result = await session.execute(select(OAuthProviderModel))
            rows = list(result.scalars().all())
            by_slot = {m.slot: m for m in rows}
            by_name = {m.name: m for m in rows}

            for slot in OAUTH_SLOTS:
                if slot in by_slot:
                    continue
                if slot in by_name:
                    other = by_name[slot]
                    logger.warning(
                        "跳过 OAuth 槽位 '%s' 的自动创建：name=%s 已被 slot=%s 占用",
                        slot,
                        slot,
                        other.slot,
                    )
                    continue
                model = OAuthProviderModel(
                    slot=slot,
                    name=slot,
                    is_builtin=slot != "oidc",
                    enabled=False,
                    visible=True,
                    client_id="",
                    client_secret_enc="",
                    scopes=DEFAULT_SCOPES.get(slot, DEFAULT_SCOPES["oidc"]),
                )
                session.add(model)
                by_slot[slot] = model
                by_name[slot] = model
                logger.info(f"OAuth provider 槽位 '{slot}' 已自动创建")

    async def list_providers(self, *, include_secrets: bool = False) -> list[dict[str, Any]]:
        """列出所有 provider 配置"""
        async with get_async_session() as session:
            result = await session.execute(
                select(OAuthProviderModel).order_by(OAuthProviderModel.slot)
            )
            models = result.scalars().all()
            return [self._model_to_dict(m, include_secrets=include_secrets) for m in models]

    async def get_provider(self, slot: str, *, include_secrets: bool = False) -> dict[str, Any] | None:
        """获取单个 provider 配置"""
        async with get_async_session() as session:
            result = await session.execute(
                select(OAuthProviderModel).where(OAuthProviderModel.slot == slot)
            )
            model = result.scalar_one_or_none()
            if model is None:
                return None
            return self._model_to_dict(model, include_secrets=include_secrets)

    async def update_provider(self, slot: str, config: OAuthProviderConfig) -> dict[str, Any]:
        """更新 provider 配置"""
        async with get_async_session() as session:
            result = await session.execute(
                select(OAuthProviderModel).where(OAuthProviderModel.slot == slot)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise ValueError(f"OAuth provider 槽位 '{slot}' 不存在")

            if model.is_builtin and config.name != slot:
                pass
            elif not model.is_builtin:
                model.name = config.name or model.name

            model.display_name = config.display_name if config.display_name is not None else model.display_name
            model.enabled = config.enabled
            model.visible = config.visible

            if config.client_id is not None:
                model.client_id = config.client_id

            if config.client_secret and config.client_secret.strip():
                model.client_secret_enc = self._crypto.encrypt(config.client_secret)

            if config.scopes is not None:
                model.scopes = json.dumps(config.scopes)

            if not model.is_builtin:
                model.discovery_url = config.discovery_url
                model.authorization_endpoint = config.authorization_endpoint
                model.token_endpoint = config.token_endpoint
                model.userinfo_endpoint = config.userinfo_endpoint
                model.jwks_uri = config.jwks_uri

            model.updated_at = datetime.now(timezone.utc)

        logger.info(f"OAuth provider '{slot}' 配置已更新")
        return await self.get_provider(slot, include_secrets=False)

    async def enable_provider(self, slot: str) -> dict[str, Any]:
        """启用 provider"""
        return await self.update_provider(
            slot, OAuthProviderConfig(slot=slot, name=slot, enabled=True)
        )

    async def disable_provider(self, slot: str) -> dict[str, Any]:
        """禁用 provider"""
        return await self.update_provider(
            slot, OAuthProviderConfig(slot=slot, name=slot, enabled=False)
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _model_to_dict(self, model: OAuthProviderModel, *, include_secrets: bool = False) -> dict[str, Any]:
        """将 ORM 模型转换为字典"""
        result = model.to_dict(include_secret=False)
        result["scopes"] = json.loads(model.scopes) if model.scopes else []

        if include_secrets and model.client_secret_enc:
            try:
                result["client_secret"] = self._crypto.decrypt(model.client_secret_enc)
            except ValueError:
                result["client_secret"] = ""
        else:
            result["client_secret"] = self._mask_secret(model.client_secret_enc)

        return result

    @staticmethod
    def _mask_secret(secret_enc: str) -> str:
        """掩码加密后的 secret"""
        if not secret_enc:
            return ""
        suffix = secret_enc[-4:] if len(secret_enc) >= 4 else secret_enc
        return f"sk_***{suffix}"

    def _encrypt_secret(self, plaintext: str) -> str:
        """加密 secret"""
        return self._crypto.encrypt(plaintext)

    def _decrypt_secret(self, ciphertext: str) -> str:
        """解密 secret"""
        return self._crypto.decrypt(ciphertext)

    @staticmethod
    def _parse_value(field: str, raw: str) -> Any:
        """将 app_settings 中的字符串值解析为对应 Python 类型"""
        if field in ("enabled", "cookie_secure", "token_auth_enabled", "token_auth_auto_cleanup"):
            return raw.lower() in ("true", "1", "yes", "on")
        if field in ("state_ttl_seconds", "token_auth_cleanup_interval", "token_auth_default_expires_in", "jwt_token_expire_seconds"):
            try:
                return int(raw)
            except ValueError:
                return KV_DEFAULTS.get(field, 0)
        return raw


class AuthConfigServiceFactory(ServiceFactory):
    """认证配置服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="auth_config_service",
            service_type=AuthConfigService,
            description="认证配置管理服务（OAuth + Token Auth + JWT）",
            author="DM MCP Team",
            dependencies=["datasource_service"],
            priority=70,  # DataSourceService (60) 之后，确保数据库已初始化
        )

    def create(self, settings, **deps) -> AuthConfigService:
        from dm_mcp.common.utils.crypto import to_fernet_key

        app_secret = settings.app_secret.get_secret_value()
        if not app_secret:
            raise ValueError("APP_SECRET 是必填项，用于加密 OAuth client_secret。")
        crypto = FernetCrypto(to_fernet_key(app_secret))
        return AuthConfigService(crypto)
