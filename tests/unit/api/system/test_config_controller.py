"""配置控制器测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from dm_mcp.api.system.config import ConfigController


class TestConfigController:
    """配置控制器测试类"""

    @pytest.fixture
    def mock_settings(self):
        """创建Mock设置"""
        settings = MagicMock()
        return settings

    @pytest.fixture
    def mock_auth_config_service(self):
        """创建Mock认证配置服务"""
        service = MagicMock()
        service.oauth_enabled = True
        service.token_auth_enabled = False
        service.list_providers = AsyncMock(return_value=[])
        return service

    @pytest.fixture
    def mock_basic_auth_service(self):
        """创建Mock BasicAuth服务"""
        service = MagicMock()
        service.is_initialized = AsyncMock(return_value=True)
        return service

    @pytest.fixture
    def controller_with_service(self, mock_settings, mock_basic_auth_service, mock_auth_config_service):
        """创建带BasicAuth服务的配置控制器"""
        return ConfigController(
            settings=mock_settings, basic_auth_service=mock_basic_auth_service, auth_config_service=mock_auth_config_service
        )

    @pytest.fixture
    def controller_without_service(self, mock_settings, mock_auth_config_service):
        """创建不带BasicAuth服务的配置控制器"""
        return ConfigController(settings=mock_settings, basic_auth_service=None, auth_config_service=mock_auth_config_service)

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        return request

    @pytest.mark.asyncio
    async def test_handle_config_with_basic_auth_service(
        self, controller_with_service, mock_request
    ):
        """测试处理配置请求（带BasicAuth服务）"""
        response = await controller_with_service.handle_config(mock_request)

        import json

        body = response.body.decode()
        data = json.loads(body)

        assert data["data"]["oauth_enabled"] is True
        assert data["data"]["token_auth_enabled"] is False
        assert data["data"]["initialized"] is True

    @pytest.mark.asyncio
    async def test_handle_config_without_basic_auth_service(
        self, controller_without_service, mock_request
    ):
        """测试处理配置请求（不带BasicAuth服务）"""
        response = await controller_without_service.handle_config(mock_request)

        import json

        body = response.body.decode()
        data = json.loads(body)

        assert data["data"]["oauth_enabled"] is True
        assert data["data"]["token_auth_enabled"] is False
        assert data["data"]["initialized"] is False  # 没有服务时默认为False

    @pytest.mark.asyncio
    async def test_handle_config_not_initialized(self, mock_settings, mock_request, mock_auth_config_service):
        """测试未初始化状态"""
        mock_basic_auth_service = MagicMock()
        mock_basic_auth_service.is_initialized = AsyncMock(return_value=False)
        controller = ConfigController(
            settings=mock_settings, basic_auth_service=mock_basic_auth_service, auth_config_service=mock_auth_config_service
        )

        response = await controller.handle_config(mock_request)

        import json

        body = response.body.decode()
        data = json.loads(body)

        assert data["data"]["initialized"] is False

    @pytest.mark.asyncio
    async def test_handle_config_oauth_disabled(self, mock_settings, mock_request, mock_auth_config_service):
        """测试OAuth禁用状态"""
        mock_auth_config_service.oauth_enabled = False
        controller = ConfigController(settings=mock_settings, basic_auth_service=None, auth_config_service=mock_auth_config_service)

        response = await controller.handle_config(mock_request)

        import json

        body = response.body.decode()
        data = json.loads(body)

        assert data["data"]["oauth_enabled"] is False

    @pytest.mark.asyncio
    async def test_handle_config_token_auth_enabled(self, mock_settings, mock_request, mock_auth_config_service):
        """测试Token认证启用状态"""
        mock_auth_config_service.token_auth_enabled = True
        controller = ConfigController(settings=mock_settings, basic_auth_service=None, auth_config_service=mock_auth_config_service)

        response = await controller.handle_config(mock_request)

        import json

        body = response.body.decode()
        data = json.loads(body)

        assert data["data"]["token_auth_enabled"] is True
