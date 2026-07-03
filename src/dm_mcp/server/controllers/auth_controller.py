"""OAuth认证控制器模块

提供OAuth认证相关的API端点，包括登录、回调等。
"""

from urllib.parse import urljoin, urlparse

from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.services import OAuthService
from dm_mcp.settings import Settings


class AuthController(object):
    """OAuth认证控制器

    处理OAuth认证流程，包括登录请求、回调处理和提供者列表查询。
    """

    def __init__(self, settings: Settings, oauth_services: OAuthService) -> None:
        """初始化OAuth认证控制器

        Args:
            settings: 服务器设置
            oauth_services: OAuth服务实例
        """
        self.settings = settings
        self.oauth_service = oauth_services

    async def handle_oauth_login(self, request: Request):
        """处理OAuth登录请求

        根据provider参数启动OAuth登录流程，支持通过next参数指定回调后的跳转URL。

        Args:
            request: HTTP请求对象，包含provider路径参数和可选的next查询参数

        Returns:
            Response: OAuth登录响应（重定向到OAuth提供者）

        Raises:
            JSONResponse: 当next URL不安全时返回错误响应
        """
        provider = request.path_params["provider"]
        callback_uri = request.url_for("api:oauth_callback", provider=provider)

        # 认证结束后前端跳转至指定页面 url
        next_url = request.query_params.get("next")

        if next_url:
            if not self.is_safe_url(next_url):
                return JSONResponse({"message": "Invalid next URL"}, status_code=400)

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
        provider_names = self.oauth_service.get_providers()
        return JSONResponse(provider_names)

    def is_safe_url(
        self, target: str, allowed_hosts: set | None = None, require_https: bool = False
    ) -> bool:
        """
        验证 URL 是否安全
        :param target: 待验证的目标 URL (即 ?next=... 的值)
        :param allowed_hosts: 允许跳转的域名白名单 (例如 {'localhost', 'my-frontend.com'})
        :param require_https: 是否强制 HTTPS
        """
        # 1. 基础非空检查
        if not target:
            return False

        # 2. 防止控制字符注入 (CRLF 注入等)
        if "\r" in target or "\n" in target:
            return False

        # 3. 解析 URL
        try:
            url_info = urlparse(target)
        except Exception:
            return False

        # --- 场景 A: 绝对路径 (http://...) ---
        if url_info.scheme:
            # 必须是 http 或 https
            if url_info.scheme not in ("http", "https"):
                return False

            # 如果配置了 allow_hosts，则必须在白名单内
            if allowed_hosts and url_info.netloc:
                # 去掉端口号对比域名 (比如 localhost:3000 -> localhost)
                hostname = url_info.hostname
                if hostname not in allowed_hosts:
                    return False

            # 强制 HTTPS 检查 (生产环境建议开启)
            if require_https and url_info.scheme != "https":
                return False

            return True

        # --- 场景 B: 相对路径 (/dashboard) ---
        # 关键防御：防止 //evil.com 绕过
        # url_info.netloc 为空意味着它被识别为相对路径，但我们必须手动检查开头
        if url_info.netloc == "" and url_info.scheme == "":
            # 必须以 / 开头，但绝不能以 // 开头
            return target.startswith("/") and not target.startswith("//")

        return False
