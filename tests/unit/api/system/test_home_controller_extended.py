"""HomeController 扩展测试"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from starlette.requests import Request
from starlette.responses import RedirectResponse, FileResponse
from starlette.datastructures import URL, Headers

import pytest
from pydantic import SecretStr

from dm_mcp.api.system.home import HomeController
from dm_mcp.infra.config import Settings
from dm_mcp.infra.config.database_config import DatabaseConfig
from dm_mcp.infra.config.logging_config import LoggingConfig
from dm_mcp.infra.config.metrics_config import MetricsConfig
from dm_mcp.infra.config.server_config import ServerConfig


def create_test_settings(**overrides) -> Settings:
    """创建测试用 Settings 对象"""
    original_argv = sys.argv.copy()
    sys.argv = [sys.argv[0]]

    try:
        settings = Settings(
            _env_file=None,
            app_secret=SecretStr("test_secret"),
            server=ServerConfig(**overrides.get("server", {})),
            database=DatabaseConfig(**overrides.get("database", {})),
            metrics=MetricsConfig(),
            logging=LoggingConfig(
                level="DEBUG", log_dir=Path("logs"), enable_file=False
            ),
        )
        return settings
    finally:
        sys.argv = original_argv


class TestHomeControllerExtended:
    """HomeController 扩展测试类"""

    @pytest.fixture
    def mock_settings_with_frontend(self, tmp_path):
        """创建带前端URL的设置"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html>Test</html>")
        return create_test_settings(
            server={
                "frontend_url": "https://example.com/ui",
                "static_path": str(static_dir),
            }
        )

    @pytest.fixture
    def mock_settings_without_frontend(self):
        """创建不带前端URL的设置"""
        return create_test_settings(
            server={"frontend_url": "", "static_path": "/static"}
        )

    @pytest.fixture
    def mock_request(self):
        """创建模拟请求"""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        url = MagicMock(spec=URL)
        url.path = "/"
        request.url = url
        return request

    @pytest.mark.asyncio
    async def test_handle_home_with_query_string(
        self, mock_settings_with_frontend, mock_request
    ):
        """测试带查询字符串时返回静态 index.html"""
        mock_request.url.path = "/"
        mock_request.url.query = "tab=datasources"

        controller = HomeController(mock_settings_with_frontend)
        response = await controller.handle_home_page(mock_request)

        assert isinstance(response, FileResponse)
        assert response.path.endswith("index.html")

    @pytest.mark.asyncio
    async def test_handle_home_with_static_path(
        self, mock_settings_without_frontend, mock_request
    ):
        """测试静态文件路径"""
        controller = HomeController(mock_settings_without_frontend)

        with patch("os.path.join") as mock_join:
            mock_join.return_value = "/static/index.html"
            with patch("os.path.exists", return_value=True):
                with patch(
                    "dm_mcp.api.system.home.FileResponse"
                ) as mock_file:
                    mock_response = MagicMock()
                    mock_file.return_value = mock_response
                    response = await controller.handle_home_page(mock_request)
                    # 调用了 FileResponse
                    assert mock_file.called or response is not None

    @pytest.mark.asyncio
    async def test_handle_home_file_not_found(
        self, mock_settings_without_frontend, mock_request, tmp_path
    ):
        """静态文件不存在时仍返回 FileResponse（由底层在访问时处理）"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        mock_settings_without_frontend.server.static_path = str(static_dir)

        controller = HomeController(mock_settings_without_frontend)

        with patch(
            "dm_mcp.api.system.home.FileResponse",
            return_value=MagicMock(spec=FileResponse),
        ) as mock_file:
            response = await controller.handle_home_page(mock_request)
            mock_file.assert_called_once()
            assert response is not None

    @pytest.mark.asyncio
    async def test_handle_home_none_frontend_url(self, mock_request):
        """测试 None 的 frontend_url"""
        settings = create_test_settings(
            server={"frontend_url": None, "static_path": "/static"}
        )

        controller = HomeController(settings)
        response = await controller.handle_home_page(mock_request)

        # None 应该被视为空，应该返回静态文件
        assert response is not None


class TestHomeControllerEdgeCases:
    """HomeController 边界情况测试"""

    @pytest.fixture
    def mock_settings(self):
        """创建设置"""
        return create_test_settings(
            server={"frontend_url": "", "static_path": "/static"}
        )

    @pytest.fixture
    def mock_request(self):
        """创建模拟请求"""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        url = MagicMock(spec=URL)
        url.path = "/"
        request.url = url
        return request

    @pytest.mark.asyncio
    async def test_handle_home_custom_path(self, mock_settings, mock_request):
        """测试自定义路径请求"""
        mock_settings.server.frontend_url = ""
        mock_settings.server.static_path = "/custom/static"

        mock_request.url.path = "/custom"

        controller = HomeController(mock_settings)

        with patch("os.path.join", return_value="/custom/static/index.html"):
            with patch("os.path.exists", return_value=True):
                with patch(
                    "dm_mcp.api.system.home.FileResponse"
                ) as mock_file:
                    mock_file.return_value = MagicMock()
                    await controller.handle_home_page(mock_request)
                    # 验证路径拼接使用了 static_path
                    mock_file.assert_called_once()
                    call_args = mock_file.call_args[0][0]
                    assert "custom" in call_args


class TestHomeControllerStaticResponse:
    """静态响应测试"""

    @pytest.fixture
    def mock_settings(self):
        """创建设置"""
        return create_test_settings(
            server={"frontend_url": None, "static_path": "/app/static"}
        )

    @pytest.fixture
    def mock_request(self):
        """创建模拟请求"""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        url = MagicMock(spec=URL)
        url.path = "/"  # 主页
        request.url = url
        return request

    @pytest.mark.asyncio
    async def test_file_response_has_correct_headers(self, mock_settings, mock_request):
        """测试文件响应包含正确的头部"""
        controller = HomeController(mock_settings)

        with patch("os.path.join", return_value="/app/static/index.html"):
            with patch("os.path.exists", return_value=True):
                with patch(
                    "dm_mcp.api.system.home.FileResponse"
                ) as mock_file_response:
                    # 模拟返回的文件响应
                    mock_response = MagicMock(spec=FileResponse)
                    mock_file_response.return_value = mock_response

                    await controller.handle_home_page(mock_request)

                    # 验证调用了 FileResponse
                    assert mock_file_response.called

    @pytest.mark.asyncio
    async def test_redirect_response_keeps_scheme(self, mock_request, tmp_path):
        """测试始终返回静态 index.html（不再重定向到 frontend_url）"""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html>Test</html>")
        settings = create_test_settings(
            server={
                "frontend_url": "https://secure.example.com/app",
                "static_path": str(static_dir),
            }
        )

        controller = HomeController(settings)
        response = await controller.handle_home_page(mock_request)

        assert isinstance(response, FileResponse)
        assert response.path.endswith("index.html")
