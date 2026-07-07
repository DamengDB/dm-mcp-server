"""ExceptionHandlerMiddleware 扩展测试"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dm_mcp.core.exceptions import DmMCPError
from dm_mcp.infra.middleware.error_handler import ExceptionHandlerMiddleware


class TestExceptionHandlerMiddlewareExtended:
    """扩展异常场景"""

    @pytest.fixture
    def middleware(self):
        return ExceptionHandlerMiddleware(app=MagicMock())

    @pytest.fixture
    def mock_request(self):
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/v1/test"
        request.method = "GET"
        return request

    @pytest.mark.asyncio
    async def test_dispatch_timeout_error_returns_500(self, middleware, mock_request):
        async def call_next(_request):
            raise TimeoutError("upstream timeout")

        response = await middleware.dispatch(mock_request, call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = json.loads(response.body.decode())
        assert body["success"] is False
        assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"


class TestExceptionHandlerErrorResponse:
    """错误响应格式"""

    @pytest.fixture
    def middleware(self):
        return ExceptionHandlerMiddleware(app=MagicMock())

    def test_json_error_format(self, middleware):
        error = DmMCPError(
            message="业务错误",
            error_code="BUSINESS_ERROR",
            status_code=422,
            details={"field": "name"},
        )

        response = middleware._create_error_response(error)
        body = json.loads(response.body.decode())

        assert body["success"] is False
        assert body["error"]["code"] == "BUSINESS_ERROR"
        assert body["error"]["details"]["field"] == "name"
        assert response.status_code == 422
