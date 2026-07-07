"""全局异常处理中间件测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dm_mcp.core.exceptions import DmMCPError
from dm_mcp.infra.middleware.error_handler import ExceptionHandlerMiddleware


class TestExceptionHandlerMiddleware:
    """全局异常处理中间件测试类"""

    @pytest.fixture
    def mock_app(self):
        """创建Mock应用"""
        app = MagicMock()
        return app

    @pytest.fixture
    def middleware(self, mock_app):
        """创建异常处理中间件"""
        return ExceptionHandlerMiddleware(app=mock_app)

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/v1/test"
        request.method = "GET"
        return request

    @pytest.fixture
    def mock_response(self):
        """创建Mock响应"""
        response = MagicMock(spec=Response)
        response.status_code = 200
        return response

    @pytest.fixture
    def mock_call_next_success(self, mock_response):
        """创建成功调用的call_next"""
        return AsyncMock(return_value=mock_response)

    @pytest.mark.asyncio
    async def test_dispatch_success(
        self, middleware, mock_request, mock_call_next_success
    ):
        """测试正常请求处理"""
        response = await middleware.dispatch(mock_request, mock_call_next_success)

        assert response == mock_call_next_success.return_value
        mock_call_next_success.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_dispatch_dm_mcp_error(self, middleware, mock_request):
        """测试处理DmMCPError异常"""
        error = DmMCPError(
            message="业务错误",
            error_code="BUSINESS_ERROR",
            status_code=400,
            details={"field": "value"},
        )

        async def call_next(request):
            raise error

        response = await middleware.dispatch(mock_request, call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "BUSINESS_ERROR"
        assert data["error"]["message"] == "业务错误"
        assert data["error"]["details"] == {"field": "value"}

    @pytest.mark.asyncio
    async def test_dispatch_generic_exception(self, middleware, mock_request):
        """测试处理通用异常"""

        async def call_next(request):
            raise ValueError("意外的错误")

        response = await middleware.dispatch(mock_request, call_next)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert data["error"]["message"] == "服务器内部错误"

    @pytest.mark.asyncio
    async def test_create_error_response(self, middleware):
        """测试创建错误响应"""
        error = DmMCPError(
            message="测试错误",
            error_code="TEST_ERROR",
            status_code=404,
            details={"key": "value"},
        )

        response = middleware._create_error_response(error)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "TEST_ERROR"
        assert data["error"]["message"] == "测试错误"
        assert data["error"]["details"] == {"key": "value"}
        # 验证UTF-8编码
        assert "charset=utf-8" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_dispatch_different_error_codes(self, middleware, mock_request):
        """测试不同错误码的处理"""
        error_codes = [
            ("AUTH_ERROR", 401),
            ("VALIDATION_ERROR", 400),
            ("NOT_FOUND", 404),
            ("INTERNAL_ERROR", 500),
        ]

        for error_code, status_code in error_codes:
            error = DmMCPError(
                message=f"错误: {error_code}",
                error_code=error_code,
                status_code=status_code,
            )

            async def call_next(request):
                raise error

            response = await middleware.dispatch(mock_request, call_next)

            assert isinstance(response, JSONResponse)
            assert response.status_code == status_code
            body = response.body.decode()
            import json

            data = json.loads(body)
            assert data["error"]["code"] == error_code
