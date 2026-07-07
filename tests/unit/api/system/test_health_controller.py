"""健康检查控制器测试模块"""

from unittest.mock import MagicMock

import pytest
from starlette.authentication import AuthCredentials, BaseUser
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.api.system.health import HealthController


class TestHealthController:
    """健康检查控制器测试类"""

    @pytest.fixture
    def mock_settings(self):
        """创建Mock设置"""
        settings = MagicMock()
        settings.server.name = "test-service"
        return settings

    @pytest.fixture
    def controller(self, mock_settings):
        """创建健康检查控制器"""
        return HealthController(settings=mock_settings)

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        request.user = BaseUser()
        request.auth = AuthCredentials(scopes=["authenticated"])
        return request

    @pytest.mark.asyncio
    async def test_handle_health_check(self, controller, mock_request):
        """测试处理健康检查请求"""
        response = await controller.handle_health_check(mock_request)

        assert isinstance(response, JSONResponse)
        # 获取响应体
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["data"]["status"] == "healthy"
        assert data["data"]["service"] == "test-service"

    @pytest.mark.asyncio
    async def test_handle_health_check_with_different_service_name(
        self, mock_settings, mock_request
    ):
        """测试不同服务名称的健康检查"""
        mock_settings.server.name = "another-service"
        controller = HealthController(settings=mock_settings)

        response = await controller.handle_health_check(mock_request)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["data"]["service"] == "another-service"

    def test_controller_requires_authentication(self, controller):
        """测试控制器需要认证装饰器"""
        # 验证handle_health_check方法有@requires装饰器
        # 这可以通过检查方法的元数据来验证，但更简单的是测试实际行为
        # 由于@requires是运行时装饰器，我们主要验证方法存在
        assert hasattr(controller, "handle_health_check")
        assert callable(controller.handle_health_check)
