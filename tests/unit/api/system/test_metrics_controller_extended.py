"""MetricsController 扩展测试"""

import json
from unittest.mock import MagicMock

import pytest
from starlette.authentication import AuthCredentials, BaseUser
from starlette.requests import Request
from starlette.responses import Response

from dm_mcp.api.system.metrics import MetricsController


class TestMetricsControllerExtended:
    """MetricsController 扩展测试"""

    @pytest.fixture
    def mock_metrics_service(self):
        service = MagicMock()
        service.export = MagicMock(
            return_value=("# HELP test_counter\ntest_counter 42", "text/plain")
        )
        return service

    @pytest.fixture
    def controller(self, mock_metrics_service):
        return MetricsController(metrics_service=mock_metrics_service)

    @pytest.fixture
    def mock_request(self):
        request = MagicMock(spec=Request)
        request.user = BaseUser()
        request.auth = AuthCredentials(scopes=["authenticated"])
        request.headers = {"Accept": "text/plain"}
        return request

    @pytest.mark.asyncio
    async def test_handle_metrics_request_prometheus_text(
        self, controller, mock_request, mock_metrics_service
    ):
        response = await controller.handle_metrics_request(mock_request)

        assert isinstance(response, Response)
        assert response.body == b"# HELP test_counter\ntest_counter 42"
        assert response.media_type == "text/plain"
        mock_metrics_service.export.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_metrics_request_custom_content_type(
        self, controller, mock_request, mock_metrics_service
    ):
        mock_metrics_service.export.return_value = (
            '{"metrics":[]}',
            "application/json",
        )

        response = await controller.handle_metrics_request(mock_request)

        assert response.media_type == "application/json"
        assert json.loads(response.body) == {"metrics": []}


class TestMetricsControllerPrometheusFormat:
    """Prometheus 格式边界"""

    @pytest.mark.asyncio
    async def test_export_empty_metrics(self):
        service = MagicMock()
        service.export = MagicMock(return_value=("", "text/plain; version=0.0.4"))
        controller = MetricsController(service)
        request = MagicMock(spec=Request)
        request.user = BaseUser()
        request.auth = AuthCredentials(scopes=["authenticated"])

        response = await controller.handle_metrics_request(request)

        assert response.body == b""
        assert "text/plain" in response.media_type
