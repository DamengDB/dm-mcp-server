"""主页控制器测试模块"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse

from dm_mcp.server.controllers.home_controller import HomeController


class TestHomeController:
    """主页控制器测试类"""

    @pytest.fixture
    def mock_settings_with_frontend_url(self):
        """创建带前端URL的Mock设置"""
        settings = MagicMock()
        settings.server.frontend_url = "https://frontend.example.com"
        settings.server.static_path = "/static"
        return settings

    @pytest.fixture
    def mock_settings_without_frontend_url(self, tmp_path):
        """创建不带前端URL的Mock设置"""
        settings = MagicMock()
        settings.server.frontend_url = None
        # 创建临时静态目录和index.html
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html>Test</html>")
        settings.server.static_path = str(static_dir)
        return settings

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        return request

    @pytest.fixture
    def controller_with_frontend(self, mock_settings_with_frontend_url):
        """创建带前端URL的控制器"""
        return HomeController(settings=mock_settings_with_frontend_url)

    @pytest.fixture
    def controller_without_frontend(self, mock_settings_without_frontend_url):
        """创建不带前端URL的控制器"""
        return HomeController(settings=mock_settings_without_frontend_url)

    @pytest.mark.asyncio
    async def test_handle_home_page_with_frontend_url(
        self, controller_with_frontend, mock_request
    ):
        """测试带前端URL的主页请求"""
        response = await controller_with_frontend.handle_home_page(mock_request)

        assert isinstance(response, RedirectResponse)
        assert response.status_code == 307  # 临时重定向
        assert response.headers["location"] == "https://frontend.example.com"

    @pytest.mark.asyncio
    async def test_handle_home_page_without_frontend_url(
        self, controller_without_frontend, mock_request
    ):
        """测试不带前端URL的主页请求"""
        response = await controller_without_frontend.handle_home_page(mock_request)

        assert isinstance(response, FileResponse)
        # 验证文件路径
        expected_path = os.path.join(
            controller_without_frontend.settings.server.static_path, "index.html"
        )
        assert response.path == expected_path

    @pytest.mark.asyncio
    async def test_handle_home_page_empty_frontend_url(
        self, mock_settings_without_frontend_url, mock_request
    ):
        """测试前端URL为空字符串的主页请求"""
        mock_settings_without_frontend_url.server.frontend_url = ""
        controller = HomeController(settings=mock_settings_without_frontend_url)

        response = await controller.handle_home_page(mock_request)

        # 空字符串应该被视为没有前端URL，返回静态文件
        assert isinstance(response, FileResponse)
