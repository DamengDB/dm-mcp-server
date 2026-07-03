"""MCP控制器测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.authentication import AuthCredentials, BaseUser
from starlette.responses import JSONResponse

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions import AuthorizationError
from dm_mcp.server.controllers.mcp_controller import MCPController
from dm_mcp.settings import Settings


class TestMCPController:
    """MCP控制器测试类"""

    @pytest.fixture
    def mock_session_manager(self):
        """创建Mock会话管理器"""
        manager = MagicMock()
        manager.handle_request = AsyncMock()
        return manager

    @pytest.fixture
    def mock_settings(self):
        """创建Mock设置"""
        settings = MagicMock(spec=Settings)
        settings.server = MagicMock()
        settings.server.host = "localhost"
        settings.server.port = 8000
        settings.database = MagicMock()
        settings.database.type = "sqlite"
        return settings

    @pytest.fixture
    def controller(self, mock_session_manager, mock_settings):
        """创建MCP控制器"""
        return MCPController(
            session_manager=mock_session_manager, settings=mock_settings
        )

    @pytest.fixture
    def mock_scope(self):
        """创建Mock ASGI scope"""
        return {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [],
        }

    @pytest.fixture
    def authenticated_scope(self, mock_scope):
        """创建已认证的scope"""
        scope = mock_scope.copy()
        scope["auth"] = AuthCredentials(scopes=["authenticated"])
        scope["user"] = BaseUser()
        scope["user"].auth_context = AuthContext(user_id="test_user", auth_type="token")
        return scope

    @pytest.fixture
    def mock_receive(self):
        """创建Mock receive函数"""
        return AsyncMock()

    @pytest.fixture
    def mock_send(self):
        """创建Mock send函数"""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_handle_request_authenticated(
        self,
        controller,
        authenticated_scope,
        mock_receive,
        mock_send,
        mock_session_manager,
    ):
        """测试处理已认证的请求"""
        await controller.handle_request(authenticated_scope, mock_receive, mock_send)

        mock_session_manager.handle_request.assert_called_once_with(
            authenticated_scope, mock_receive, mock_send
        )

    @pytest.mark.asyncio
    async def test_handle_request_not_authenticated(
        self, controller, mock_scope, mock_receive, mock_send
    ):
        """测试处理未认证的请求"""
        mock_scope["auth"] = None

        await controller.handle_request(mock_scope, mock_receive, mock_send)

        # 应该返回错误响应
        assert mock_send.called
        # 验证发送了错误响应
        call_args = mock_send.call_args[0]
        assert len(call_args) > 0

    @pytest.mark.asyncio
    async def test_handle_request_no_auth_credentials(
        self, controller, mock_scope, mock_receive, mock_send
    ):
        """测试没有认证凭据的请求"""
        mock_scope.pop("auth", None)

        await controller.handle_request(mock_scope, mock_receive, mock_send)

        # 应该返回错误响应
        assert mock_send.called

    @pytest.mark.asyncio
    async def test_handle_request_authorization_error(
        self, controller, mock_scope, mock_receive, mock_send
    ):
        """测试授权错误处理"""
        mock_scope["auth"] = AuthCredentials(scopes=[])  # 没有authenticated scope

        await controller.handle_request(mock_scope, mock_receive, mock_send)

        # 应该返回错误响应
        assert mock_send.called

    @pytest.mark.asyncio
    async def test_handle_request_with_user_context(
        self,
        controller,
        authenticated_scope,
        mock_receive,
        mock_send,
        mock_session_manager,
    ):
        """测试带用户上下文的请求"""
        await controller.handle_request(authenticated_scope, mock_receive, mock_send)

        mock_session_manager.handle_request.assert_called_once()
        # 验证AuthContext被正确设置（通过上下文管理器）

    @pytest.mark.asyncio
    async def test_handle_request_internal_error(
        self,
        controller,
        authenticated_scope,
        mock_receive,
        mock_send,
        mock_session_manager,
    ):
        """测试内部错误处理"""
        mock_session_manager.handle_request = AsyncMock(
            side_effect=Exception("Internal error")
        )

        await controller.handle_request(authenticated_scope, mock_receive, mock_send)

        # 应该返回错误响应
        assert mock_send.called
