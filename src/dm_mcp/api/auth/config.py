"""认证配置控制器模块

提供认证配置的查询和修改 API：
- 全局认证配置查询/修改（OAuth 开关、Token Auth 开关、JWT 过期时间等）
- OAuth Provider 配置管理

GET /auth-config              — 返回所有认证配置
PUT /auth-config              — 更新认证配置（admin only）
GET /auth-config/providers    — 列出所有 provider 配置
GET /auth-config/providers/{slot} — 获取单个 provider 配置
PUT /auth-config/providers/{slot} — 更新 provider 配置（admin only）
POST /auth-config/providers/{slot}/enable  — 启用 provider（admin only）
POST /auth-config/providers/{slot}/disable — 禁用 provider（admin only）
POST /auth-config/providers/{slot}/test    — 测试 provider 连通性（admin only）
"""

import logging

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.domain.auth.services.auth_config import (
    AuthConfigService,
    OAuthGlobalConfig,
    OAuthProviderConfig,
)
from dm_mcp.domain.auth.services.oauth import OAuthService

from dm_mcp.api.base import BaseController

logger = logging.getLogger(__name__)

VALID_SLOTS = {"google", "microsoft", "github", "oidc"}


class PutAuthConfigRequest(BaseModel):
    """PUT /auth-config 请求体"""

    enabled: bool | None = None
    cookie_secure: bool | None = None
    state_ttl_seconds: int | None = Field(None, ge=60, le=86400)
    token_auth_enabled: bool | None = None
    token_auth_cleanup_interval: int | None = Field(None, ge=60)
    token_auth_auto_cleanup: bool | None = None
    token_auth_default_expires_in: int | None = Field(None, ge=60)
    jwt_token_expire_seconds: int | None = Field(None, ge=1)


class PutProviderRequest(BaseModel):
    """PUT /auth-config/providers/{slot} 请求体"""

    name: str | None = None
    display_name: str | None = None
    enabled: bool | None = None
    visible: bool | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] | None = None
    discovery_url: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None


class AuthConfigController(BaseController):
    """认证配置控制器

    处理所有认证配置的查询和修改，写操作要求 admin 权限。
    """

    def __init__(
        self,
        auth_config_service: AuthConfigService,
        oauth_service: OAuthService,
    ) -> None:
        self._auth_config_service = auth_config_service
        self._oauth_service = oauth_service

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    def _check_admin(self, request: Request) -> JSONResponse | None:
        """检查是否为 admin，非 admin 返回 403 响应"""
        if not self.is_admin(request):
            return self.error(
                "需要管理员权限",
                code="FORBIDDEN",
                status_code=403,
            )
        return None

    def _check_slot(self, slot: str) -> JSONResponse | None:
        """检查 slot 是否有效"""
        if slot not in VALID_SLOTS:
            return self.error(
                f"无效的 provider slot: '{slot}'，必须是 {sorted(VALID_SLOTS)} 之一",
                code="INVALID_SLOT",
                status_code=400,
            )
        return None

    def _audit_log(self, actor: str, action: str, target: str) -> None:
        """记录审计日志"""
        logger.info(f"actor={actor}, action={action}, target={target}")

    # ------------------------------------------------------------------
    # 全局认证配置
    # ------------------------------------------------------------------

    async def handle_get(self, request: Request) -> JSONResponse:
        """GET /auth-config — 获取所有认证配置"""
        config = await self._auth_config_service.get_config()
        return self.success(data=config)

    async def handle_put(self, request: Request) -> JSONResponse:
        """PUT /auth-config — 更新认证配置"""
        if resp := self._check_admin(request):
            return resp

        try:
            body = await request.json()
            req = PutAuthConfigRequest(**body)
        except ValidationError as e:
            return self.error(
                self.format_validation_error(e),
                code="VALIDATION_ERROR",
                status_code=400,
            )
        except Exception as e:
            return self.error(str(e), code="BAD_REQUEST", status_code=400)

        # 只更新非 None 的字段
        updates = {}
        for field in req.model_fields:
            value = getattr(req, field)
            if value is not None:
                updates[field] = value

        if not updates:
            return self.error("请求体为空，未提供任何配置项", code="EMPTY_BODY", status_code=400)

        updated = await self._auth_config_service.update_config(updates)
        return self.success(data=updated)

    # ------------------------------------------------------------------
    # Provider 列表和详情
    # ------------------------------------------------------------------

    async def handle_list_providers(self, request: Request) -> JSONResponse:
        """GET /auth-config/providers — 列出所有 provider 配置（secret 掩码）"""
        providers = await self._auth_config_service.list_providers(
            include_secrets=False
        )
        return self.success(data=providers)

    async def handle_get_provider(self, request: Request) -> JSONResponse:
        """GET /auth-config/providers/{slot} — 获取单个 provider 配置"""
        slot = request.path_params["slot"]
        if resp := self._check_slot(slot):
            return resp

        provider = await self._auth_config_service.get_provider(
            slot, include_secrets=False
        )
        if provider is None:
            return self.error(
                f"Provider '{slot}' 不存在",
                code="NOT_FOUND",
                status_code=404,
            )

        return self.success(data=provider)

    # ------------------------------------------------------------------
    # Provider 更新
    # ------------------------------------------------------------------

    async def handle_put_provider(self, request: Request) -> JSONResponse:
        """PUT /auth-config/providers/{slot} — 更新 provider 配置"""
        if resp := self._check_admin(request):
            return resp

        slot = request.path_params["slot"]
        if resp := self._check_slot(slot):
            return resp

        try:
            body = await request.json()
            req = PutProviderRequest(**body)
        except ValidationError as e:
            return self.error(
                self.format_validation_error(e),
                code="VALIDATION_ERROR",
                status_code=400,
            )
        except Exception as e:
            return self.error(f"无效的请求体: {e}", status_code=400)

        # 获取当前配置用于合并
        current = await self._auth_config_service.get_provider(
            slot, include_secrets=True
        )
        if current is None:
            return self.error(
                f"Provider '{slot}' 不存在",
                code="NOT_FOUND",
                status_code=404,
            )

        # builtin 的 name 锁定为 slot
        name = current.get("name", slot)
        if not current.get("is_builtin") and req.name is not None:
            name = req.name

        config = OAuthProviderConfig(
            slot=slot,
            name=name,
            display_name=req.display_name
            if req.display_name is not None
            else current.get("display_name"),
            enabled=req.enabled if req.enabled is not None else current.get("enabled", False),
            visible=req.visible if req.visible is not None else current.get("visible", True),
            client_id=req.client_id if req.client_id is not None else current.get("client_id", ""),
            client_secret=req.client_secret or "",
            scopes=req.scopes if req.scopes is not None else current.get("scopes", []),
            discovery_url=req.discovery_url
            if req.discovery_url is not None
            else current.get("discovery_url"),
            authorization_endpoint=req.authorization_endpoint
            if req.authorization_endpoint is not None
            else current.get("authorization_endpoint"),
            token_endpoint=req.token_endpoint
            if req.token_endpoint is not None
            else current.get("token_endpoint"),
            userinfo_endpoint=req.userinfo_endpoint
            if req.userinfo_endpoint is not None
            else current.get("userinfo_endpoint"),
            jwks_uri=req.jwks_uri if req.jwks_uri is not None else current.get("jwks_uri"),
        )

        try:
            updated = await self._auth_config_service.update_provider(slot, config)
        except ValueError as e:
            return self.error(str(e), status_code=400)

        # 重新加载 providers
        await self._oauth_service.reload_providers()

        actor = self.get_current_user_id(request)
        self._audit_log(actor, "update_oauth_provider", f"oauth.provider.{slot}")

        return self.success(data=updated)

    async def handle_enable_provider(self, request: Request) -> JSONResponse:
        """POST /auth-config/providers/{slot}/enable — 启用 provider"""
        if resp := self._check_admin(request):
            return resp

        slot = request.path_params["slot"]
        if resp := self._check_slot(slot):
            return resp

        updated = await self._auth_config_service.enable_provider(slot)
        await self._oauth_service.reload_providers()

        actor = self.get_current_user_id(request)
        self._audit_log(actor, "enable_oauth_provider", f"oauth.provider.{slot}")

        return self.success(data=updated)

    async def handle_disable_provider(self, request: Request) -> JSONResponse:
        """POST /auth-config/providers/{slot}/disable — 禁用 provider"""
        if resp := self._check_admin(request):
            return resp

        slot = request.path_params["slot"]
        if resp := self._check_slot(slot):
            return resp

        updated = await self._auth_config_service.disable_provider(slot)
        await self._oauth_service.reload_providers()

        actor = self.get_current_user_id(request)
        self._audit_log(actor, "disable_oauth_provider", f"oauth.provider.{slot}")

        return self.success(data=updated)

    # ------------------------------------------------------------------
    # Provider 连通性测试
    # ------------------------------------------------------------------

    async def handle_test_provider(self, request: Request) -> JSONResponse:
        """POST /auth-config/providers/{slot}/test — 测试 provider 连通性"""
        if resp := self._check_admin(request):
            return resp

        slot = request.path_params["slot"]
        if resp := self._check_slot(slot):
            return resp

        provider = await self._auth_config_service.get_provider(
            slot, include_secrets=False
        )
        if provider is None:
            return self.error(
                f"Provider '{slot}' 不存在",
                code="NOT_FOUND",
                status_code=404,
            )

        # 获取 discovery_url 或端点配置
        discovery_url = provider.get("discovery_url")
        authorization_endpoint = provider.get("authorization_endpoint")
        token_endpoint = provider.get("token_endpoint")

        if discovery_url:
            return self.success(
                data={
                    "slot": slot,
                    "name": provider.get("name"),
                    "discovery_url": discovery_url,
                    "status": "configured",
                    "message": "已配置 discovery URL，建议到实际 OAuth 流程中验证",
                }
            )

        if authorization_endpoint and token_endpoint:
            return self.success(
                data={
                    "slot": slot,
                    "name": provider.get("name"),
                    "authorization_endpoint": authorization_endpoint,
                    "token_endpoint": token_endpoint,
                    "status": "configured",
                    "message": "已配置手动端点，建议到实际 OAuth 流程中验证",
                }
            )

        return self.success(
            data={
                "slot": slot,
                "name": provider.get("name"),
                "status": "incomplete",
                "message": "缺少 discovery_url 或 authorization_endpoint + token_endpoint",
            }
        )
