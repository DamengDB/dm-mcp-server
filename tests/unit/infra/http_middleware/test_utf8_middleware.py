"""UTF-8编码中间件测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dm_mcp.infra.middleware.utf8 import UTF8ResponseMiddleware


class TestUTF8ResponseMiddleware:
    """UTF-8编码中间件测试类"""

    @pytest.fixture
    def mock_app(self):
        """创建Mock应用"""
        app = MagicMock()
        return app

    @pytest.fixture
    def middleware(self, mock_app):
        """创建UTF-8中间件"""
        return UTF8ResponseMiddleware(app=mock_app)

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        return request

    @pytest.fixture
    def mock_response_json(self):
        """创建Mock JSON响应"""
        response = MagicMock(spec=JSONResponse)
        response.headers = MagicMock()
        response.headers.get.return_value = "application/json"
        return response

    @pytest.fixture
    def mock_response_text(self):
        """创建Mock文本响应"""
        response = MagicMock(spec=Response)
        response.headers = MagicMock()
        response.headers.get.return_value = "text/plain"
        return response

    @pytest.fixture
    def mock_response_xml(self):
        """创建Mock XML响应"""
        response = MagicMock(spec=Response)
        response.headers = MagicMock()
        response.headers.get.return_value = "application/xml"
        return response

    @pytest.fixture
    def mock_call_next(self, mock_response_json):
        """创建Mock call_next函数"""
        return AsyncMock(return_value=mock_response_json)

    @pytest.mark.asyncio
    async def test_dispatch_json_without_charset(
        self, middleware, mock_request, mock_response_json
    ):
        """测试JSON响应未指定字符集时添加UTF-8"""
        mock_response_json.headers.get.return_value = "application/json"
        mock_response_json.headers = {"content-type": "application/json"}

        async def call_next(request):
            return mock_response_json

        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["content-type"] == "application/json; charset=utf-8"

    @pytest.mark.asyncio
    async def test_dispatch_json_with_charset(
        self, middleware, mock_request, mock_response_json
    ):
        """测试JSON响应已指定字符集时不修改"""
        mock_response_json.headers = {"content-type": "application/json; charset=utf-8"}

        async def call_next(request):
            return mock_response_json

        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["content-type"] == "application/json; charset=utf-8"

    @pytest.mark.asyncio
    async def test_dispatch_text_without_charset(
        self, middleware, mock_request, mock_response_text
    ):
        """测试文本响应未指定字符集时添加UTF-8"""
        mock_response_text.headers = {"content-type": "text/plain"}

        async def call_next(request):
            return mock_response_text

        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    @pytest.mark.asyncio
    async def test_dispatch_xml_without_charset(
        self, middleware, mock_request, mock_response_xml
    ):
        """测试XML响应未指定字符集时添加UTF-8"""
        mock_response_xml.headers = {"content-type": "application/xml"}

        async def call_next(request):
            return mock_response_xml

        response = await middleware.dispatch(mock_request, call_next)

        assert response.headers["content-type"] == "application/xml; charset=utf-8"

    @pytest.mark.asyncio
    async def test_dispatch_javascript_without_charset(self, middleware, mock_request):
        """测试JavaScript响应未指定字符集时添加UTF-8"""
        response = MagicMock(spec=Response)
        response.headers = {"content-type": "application/javascript"}

        async def call_next(request):
            return response

        result = await middleware.dispatch(mock_request, call_next)

        assert result.headers["content-type"] == "application/javascript; charset=utf-8"

    @pytest.mark.asyncio
    async def test_dispatch_binary_content(self, middleware, mock_request):
        """测试二进制内容不添加字符集"""
        response = MagicMock(spec=Response)
        response.headers = {"content-type": "image/png"}

        async def call_next(request):
            return response

        result = await middleware.dispatch(mock_request, call_next)

        # 二进制内容不应该添加charset
        assert "charset" not in result.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_dispatch_no_content_type(self, middleware, mock_request):
        """测试没有Content-Type的响应"""
        response = MagicMock(spec=Response)
        response.headers = MagicMock()
        response.headers.get.return_value = ""

        async def call_next(request):
            return response

        result = await middleware.dispatch(mock_request, call_next)

        # 没有Content-Type时不修改
        result.headers.get.assert_called()
