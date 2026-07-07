"""OAuth认证控制器模块

提供OAuth认证相关的API端点，包括登录、回调等。
"""

from urllib.parse import urljoin, urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.common import messages
from dm_mcp.api.base import BaseController
from dm_mcp.domain.auth.services.oauth import OAuthService
from dm_mcp.domain.auth.services.auth_config import AuthConfigService
from dm_mcp.infra.config import Settings


class AuthController(BaseController):
    """OAuth认证控制器

    处理OAuth认证流程，包括登录请求、回调处理和提供者列表查询。
    """

    def __init__(
        self,
        settings: Settings,
        oauth_services: OAuthService,
        auth_config_service: AuthConfigService = None,
    ) -> None:
        self.settings = settings
        self.oauth_service = oauth_services
        self.auth_config_service = auth_config_service

    async def handle_oauth_login(self, request: Request):
        """处理OAuth登录请求"""
        provider = request.path_params["provider"]

        # 使用 frontend_url 构建回调地址（确保 OAuth 回调走前端→代理→后端）
        if self.settings.server.frontend_url:
            callback_path = f"api/v1/auth/{provider}/callback"
            callback_uri = urljoin(self.settings.server.frontend_url.rstrip("/") + "/", callback_path)
        else:
            callback_uri = request.url_for("api:oauth_callback", provider=provider)

        # 认证结束后前端跳转至指定页面 url
        next_url = request.query_params.get("next")

        if next_url:
            if not self.is_safe_url(next_url):
                return self.error(messages.MSG_AUTH_NEXT_URL_INVALID, status_code=400)

        response = await self.oauth_service.handle_login(
            provider, request, callback_uri
        )

        if next_url:
            response.set_cookie(key="next", value=next_url, max_age=300, httponly=True)

        return response

    async def handle_oauth_callback(self, request: Request):
        provider = request.path_params["provider"]

        # 认证结束后前端跳转至指定页面 url
        next_url = request.cookies.get("next")

        # 前端只允许指定跳转的相对路径，完整的跳转路由有后台拼接完成，确保不被劫持
        if next_url:
            base_url = self.settings.server.frontend_url or ""
            next_url = urljoin(base_url, next_url).rstrip("/")

        response = await self.oauth_service.handle_callback(request, provider, next_url)

        if next_url:
            response.delete_cookie(key="next")
            response.set_cookie(
                "auth_handshake", "valid", max_age=20, httponly=False, samesite="lax"
            )

        return response

    async def handle_oauth_providers(self, request: Request) -> JSONResponse:
        """获取已启用且可见的 OAuth 提供商列表"""
        providers = await self.auth_config_service.list_providers(
            include_secrets=False
        )
        visible_providers = [
            p["name"]
            for p in providers
            if p.get("enabled") and p.get("visible")
        ]
        return self.success(data=visible_providers)


    def is_safe_url(
        self, target: str, allowed_hosts: set | None = None, require_https: bool = False
    ) -> bool:
        """验证 URL 是否安全"""
        if not target:
            return False

        if "\r" in target or "\n" in target:
            return False

        try:
            url_info = urlparse(target)
        except Exception:
            return False

        if url_info.scheme:
            if url_info.scheme not in ("http", "https"):
                return False

            if allowed_hosts and url_info.netloc:
                hostname = url_info.hostname
                if hostname not in allowed_hosts:
                    return False

            if require_https and url_info.scheme != "https":
                return False

            return True

        if url_info.netloc == "" and url_info.scheme == "":
            return target.startswith("/") and not target.startswith("//")

        return False
