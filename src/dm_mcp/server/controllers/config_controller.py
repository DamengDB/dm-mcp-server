"""配置控制器模块

提供系统配置信息API端点。
"""

from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.services.basic_auth_service import BasicAuthService
from dm_mcp.settings import Settings


class ConfigController(object):
    """配置信息控制器

    提供系统配置信息查询功能，包括OAuth、Token认证状态等。
    """

    def __init__(
        self, settings: Settings, basic_auth_service: BasicAuthService | None = None
    ) -> None:
        """初始化配置控制器

        Args:
            settings: 服务器设置
            basic_auth_service: BasicAuth服务实例（可选）
        """
        self.settings = settings
        self.basic_auth_service = basic_auth_service

    async def handle_config(self, request: Request) -> JSONResponse:
        """返回系统配置信息

        返回系统配置信息，包括：
        - oauth_enabled: 是否启用OAuth认证
        - token_auth_enabled: 是否启用Token认证
        - initialized: admin密码是否已初始化

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含配置信息的JSON响应
        """
        initialized = False
        if self.basic_auth_service:
            initialized = await self.basic_auth_service.is_initialized()

        return JSONResponse(
            {
                "oauth_enabled": self.settings.oauth.enabled,
                "token_auth_enabled": self.settings.token_auth.enabled,
                "initialized": initialized,
            }
        )
