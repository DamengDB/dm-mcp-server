"""指标控制器测试模块"""

from unittest.mock import MagicMock

import pytest
from starlette.authentication import AuthCredentials, BaseUser
from starlette.requests import Request
from starlette.responses import Response

from dm_mcp.server.controllers.metrics_controller import MetricsController


class TestMetricsController:
    """指标控制器测试类"""

    @pytest.fixture
    def mock_metrics_service(self):
        """创建Mock指标服务"""
        service = MagicMock()
        service.export = MagicMock(return_value=("metric_data", "text/plain"))
        return service

    @pytest.fixture
    def controller(self, mock_metrics_service):
        """创建指标控制器"""
        return MetricsController(metrics_service=mock_metrics_service)

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        request.user = BaseUser()
        request.auth = AuthCredentials(scopes=["authenticated"])
        return request

    @pytest.mark.asyncio
    async def test_handle_metrics_request(
        self, controller, mock_request, mock_metrics_service
    ):
        """测试处理指标请求"""
        response = await controller.handle_metrics_request(mock_request)

        assert isinstance(response, Response)
        assert response.body == b"metric_data"
        assert response.media_type == "text/plain"
        mock_metrics_service.export.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_metrics_request_different_content_type(
        self, controller, mock_request, mock_metrics_service
    ):
        """测试不同内容类型的指标请求"""
        mock_metrics_service.export.return_value = (
            "prometheus_data",
            "text/plain; version=0.0.4",
        )

        response = await controller.handle_metrics_request(mock_request)

        assert isinstance(response, Response)
        assert response.body == b"prometheus_data"
        assert response.media_type == "text/plain; version=0.0.4"
