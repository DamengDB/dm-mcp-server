"""配置控制器模块

提供系统配置信息API端点。
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.api.base import BaseController
from dm_mcp.domain.auth.services.auth_config import AuthConfigService
from dm_mcp.domain.auth.services.basic_auth import BasicAuthService
from dm_mcp.infra.config import Settings


class ConfigController(BaseController):
    """配置信息控制器

    提供系统配置信息查询功能，包括OAuth、Token认证状态等。
    """

    def __init__(
        self,
        settings: Settings,
        basic_auth_service: BasicAuthService | None = None,
        auth_config_service: AuthConfigService | None = None,
    ) -> None:
        self.settings = settings
        self.basic_auth_service = basic_auth_service
        self.auth_config_service = auth_config_service

    async def handle_config(self, request: Request) -> JSONResponse:
        """返回系统配置信息"""
        initialized = False
        if self.basic_auth_service:
            initialized = await self.basic_auth_service.is_initialized()

        # 从 AuthConfigService 获取 OAuth 状态
        oauth_enabled = False
        oauth_providers = []
        if self.auth_config_service:
            oauth_enabled = self.auth_config_service.oauth_enabled
            all_providers = await self.auth_config_service.list_providers(
                include_secrets=False
            )
            # 仅返回 enabled && visible 的 provider
            oauth_providers = [
                {
                    "slot": p["slot"],
                    "name": p["name"],
                    "display_name": p.get("display_name") or p["name"].capitalize(),
                }
                for p in all_providers
                if p.get("enabled") and p.get("visible")
            ]

        return self.success(
            data={
                "oauth_enabled": oauth_enabled,
                "oauth_providers": oauth_providers,
                "token_auth_enabled": self.auth_config_service.token_auth_enabled if self.auth_config_service else False,
                "initialized": initialized,
            }
        )
