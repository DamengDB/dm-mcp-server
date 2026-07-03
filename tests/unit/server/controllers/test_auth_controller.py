"""OAuth认证控制器测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from dm_mcp.server.controllers.auth_controller import AuthController


class TestAuthController:
    """OAuth认证控制器测试类"""

    @pytest.fixture
    def mock_settings(self):
        """创建Mock设置"""
        settings = MagicMock()
        settings.server.frontend_url = "http://localhost:3000"
        return settings

    @pytest.fixture
    def mock_oauth_service(self):
        """创建Mock OAuth服务"""
        service = MagicMock()
        service.handle_login = AsyncMock(
            return_value=RedirectResponse(url="http://oauth-provider.com")
        )
        service.handle_callback = AsyncMock(
            return_value=RedirectResponse(url="http://localhost:3000")
        )
        service.get_providers = MagicMock(return_value=["github", "google"])
        return service

    @pytest.fixture
    def controller(self, mock_settings, mock_oauth_service):
        """创建OAuth认证控制器"""
        return AuthController(settings=mock_settings, oauth_services=mock_oauth_service)

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        request.path_params = {}
        request.query_params = {}
        request.url = MagicMock()
        request.url_for = MagicMock(
            return_value="http://localhost:8000/api/v1/auth/github/callback"
        )
        request.cookies = {}
        return request

    @pytest.mark.asyncio
    async def test_handle_oauth_login_success(self, controller, mock_request):
        """测试OAuth登录成功"""
        mock_request.path_params["provider"] = "github"
        mock_request.query_params = {}

        response = await controller.handle_oauth_login(mock_request)

        assert isinstance(response, RedirectResponse)
        controller.oauth_service.handle_login.assert_called_once()
        call_args = controller.oauth_service.handle_login.call_args
        assert call_args[0][0] == "github"
        assert call_args[0][1] == mock_request

    @pytest.mark.asyncio
    async def test_handle_oauth_login_with_next_url(self, controller, mock_request):
        """测试OAuth登录带next参数"""
        mock_request.path_params["provider"] = "github"
        mock_request.query_params = {"next": "/dashboard"}

        response = await controller.handle_oauth_login(mock_request)

        assert isinstance(response, RedirectResponse)
        # 验证设置了cookie
        assert hasattr(response, "set_cookie")

    @pytest.mark.asyncio
    async def test_handle_oauth_login_with_unsafe_next_url(
        self, controller, mock_request
    ):
        """测试OAuth登录带不安全的next URL"""
        mock_request.path_params["provider"] = "github"
        mock_request.query_params = {"next": "javascript:alert(1)"}

        response = await controller.handle_oauth_login(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["message"] == "Invalid next URL"
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_handle_oauth_callback_success(self, controller, mock_request):
        """测试OAuth回调成功"""
        mock_request.path_params["provider"] = "github"
        mock_request.cookies = {}

        response = await controller.handle_oauth_callback(mock_request)

        assert isinstance(response, RedirectResponse)
        controller.oauth_service.handle_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_oauth_callback_with_next_url(self, controller, mock_request):
        """测试OAuth回调带next URL"""
        mock_request.path_params["provider"] = "github"
        mock_request.cookies = {"next": "/dashboard"}

        response = await controller.handle_oauth_callback(mock_request)

        assert isinstance(response, RedirectResponse)
        controller.oauth_service.handle_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_oauth_providers(self, controller, mock_request):
        """测试获取OAuth提供者列表"""
        response = await controller.handle_oauth_providers(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data == ["github", "google"]
        controller.oauth_service.get_providers.assert_called_once()

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("/dashboard", True),  # 相对路径
            ("/api/v1/datasources", True),  # 相对路径
            ("http://localhost:3000/dashboard", True),  # 允许的绝对路径
            ("https://localhost:3000/dashboard", True),  # HTTPS
            ("javascript:alert(1)", False),  # JavaScript协议
            ("//evil.com", False),  # 双斜杠绕过
            ("", False),  # 空字符串
            ("/dashboard\r\n", False),  # CRLF注入
        ],
    )
    def test_is_safe_url(self, controller, url, expected):
        """测试URL安全检查"""
        result = controller.is_safe_url(url)
        assert result == expected

    def test_is_safe_url_evil_domain(self, controller):
        """测试不安全的域名（需要allowed_hosts参数）"""
        # 默认情况下，没有allowed_hosts限制时，http://evil.com会被认为是安全的
        # 只有在指定了allowed_hosts时才会被拒绝
        result = controller.is_safe_url("http://evil.com", allowed_hosts={"localhost"})
        assert result is False

    def test_is_safe_url_with_allowed_hosts(self, controller):
        """测试带允许主机列表的URL检查"""
        allowed_hosts = {"localhost", "example.com"}
        assert (
            controller.is_safe_url(
                "http://localhost:3000/dashboard", allowed_hosts=allowed_hosts
            )
            is True
        )
        assert (
            controller.is_safe_url(
                "http://example.com/dashboard", allowed_hosts=allowed_hosts
            )
            is True
        )
        assert (
            controller.is_safe_url(
                "http://evil.com/dashboard", allowed_hosts=allowed_hosts
            )
            is False
        )

    def test_is_safe_url_require_https(self, controller):
        """测试要求HTTPS的URL检查"""
        assert (
            controller.is_safe_url("https://example.com/dashboard", require_https=True)
            is True
        )
        assert (
            controller.is_safe_url("http://example.com/dashboard", require_https=True)
            is False
        )
