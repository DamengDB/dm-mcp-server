"""Token认证中间件测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions.auth_errors import AuthorizationError
from dm_mcp.domain.mcp.entities.tool import ToolDefinition
from dm_mcp.domain.mcp.middleware.token_auth import (
    AUTH_TYPE_TOKEN,
    SOURCE_AUTO,
    TokenAuthMCPMiddleware,
)


class TestTokenAuthMCPMiddleware:
    """Token认证中间件测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        """创建Mock数据源服务"""
        service = MagicMock()
        service.get_datasource = AsyncMock(return_value=None)
        return service

    @pytest.fixture
    def mock_mcp_service(self):
        """创建Mock MCP服务"""
        service = MagicMock()
        service.get_tool_definition = MagicMock(return_value=None)
        return service

    @pytest.fixture
    def middleware(self, mock_datasource_service, mock_mcp_service):
        """创建Token认证中间件"""
        return TokenAuthMCPMiddleware(
            datasource_service=mock_datasource_service,
            mcp_service=mock_mcp_service,
        )

    @pytest.fixture
    def mock_call_next(self):
        """创建Mock的call_next函数"""
        return AsyncMock(return_value="result")

    @pytest.fixture
    def mock_tool_function(self):
        """创建Mock工具函数"""

        async def tool_func(*args, **kwargs):
            return "result"

        return tool_func

    @pytest.mark.asyncio
    async def test_tool_no_token_auth_required(
        self, middleware, mock_call_next, mock_tool_function
    ):
        """测试不需要Token认证的工具"""
        # 工具不需要token认证
        tool_def = ToolDefinition(
            fn=mock_tool_function,
            name="test_tool",
            short_description="Test tool",
            long_description="Test tool",
            input_schema={"type": "object"},
            output_schema=None,
            requires_token_auth=False,
        )
        middleware.mcp_service.get_tool_definition.return_value = tool_def

        result = await middleware.on_call_tool(mock_call_next, "test_tool", {})
        assert result == "result"
        mock_call_next.assert_called_once_with("test_tool", {})

    @pytest.mark.asyncio
    async def test_tool_not_found(self, middleware, mock_call_next):
        """测试工具未找到时直接通过"""
        middleware.mcp_service.get_tool_definition.return_value = None

        result = await middleware.on_call_tool(mock_call_next, "nonexistent_tool", {})
        assert result == "result"

    @pytest.mark.asyncio
    async def test_tool_requires_auth_no_context(
        self, middleware, mock_call_next, mock_tool_function
    ):
        """测试需要认证但无认证上下文"""
        tool_def = ToolDefinition(
            fn=mock_tool_function,
            name="test_tool",
            short_description="Test tool",
            long_description="Test tool",
            input_schema={"type": "object"},
            output_schema=None,
            requires_token_auth=True,
        )
        middleware.mcp_service.get_tool_definition.return_value = tool_def

        with pytest.raises(AuthorizationError) as exc_info:
            await middleware.on_call_tool(mock_call_next, "test_tool", {})

        assert "token" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_tool_requires_auth_anonymous_type(
        self, middleware, mock_call_next, mock_tool_function
    ):
        """测试需要认证但认证类型为anonymous（stdio模式）"""
        tool_def = ToolDefinition(
            fn=mock_tool_function,
            name="test_tool",
            short_description="Test tool",
            long_description="Test tool",
            input_schema={"type": "object"},
            output_schema=None,
            requires_token_auth=True,
        )
        middleware.mcp_service.get_tool_definition.return_value = tool_def

        auth_context = AuthContext(
            user_id="anonymous", auth_type="anonymous", token=None
        )
        with AuthContext.as_current(auth_context):
            # anonymous类型应该跳过验证
            result = await middleware.on_call_tool(mock_call_next, "test_tool", {})
            assert result == "result"

    @pytest.mark.asyncio
    async def test_tool_requires_auth_with_valid_token(
        self, middleware, mock_call_next, mock_tool_function
    ):
        """测试需要认证且有有效 Token 时正常通过"""
        tool_def = ToolDefinition(
            fn=mock_tool_function,
            name="test_tool",
            short_description="Test tool",
            long_description="Test tool",
            input_schema={"type": "object"},
            output_schema=None,
            requires_token_auth=True,
        )
        middleware.mcp_service.get_tool_definition.return_value = tool_def

        auth_context = AuthContext(
            user_id="user123",
            auth_type=AUTH_TYPE_TOKEN,
            token="valid-token",
        )
        with AuthContext.as_current(auth_context):
            result = await middleware.on_call_tool(
                mock_call_next, "test_tool", {"source": SOURCE_AUTO}
            )
            assert result == "result"
            mock_call_next.assert_called_once_with("test_tool", {"source": SOURCE_AUTO})
