"""用户模型单元测试

测试 MCPUser 的功能。
"""

import pytest

from dm_mcp.core.auth.user import MCPUser
from dm_mcp.core.auth.auth_context import AuthContext


class TestMCPUser:
    """MCPUser 测试类"""

    def test_user_initialization(self):
        """测试用户初始化"""
        auth_context = AuthContext(user_id="testuser", auth_type="token")

        user = MCPUser(auth_context)

        assert user.auth_context == auth_context
        assert user.is_authenticated is True

    def test_user_is_authenticated(self):
        """测试用户认证状态"""
        auth_context = AuthContext(user_id="testuser")
        user = MCPUser(auth_context)

        # MCPUser 始终返回 True
        assert user.is_authenticated is True

    def test_user_with_different_auth_types(self):
        """测试不同认证类型的用户"""
        auth_types = ["oauth", "token", "basic_auth", "anonymous"]

        for auth_type in auth_types:
            auth_context = AuthContext(user_id="testuser", auth_type=auth_type)
            user = MCPUser(auth_context)

            assert user.is_authenticated is True
            assert user.auth_context.auth_type == auth_type

    def test_user_auth_context_access(self):
        """测试访问用户认证上下文"""
        auth_context = AuthContext(
            user_id="testuser",
            auth_type="token",
            token="test_token",
        )

        user = MCPUser(auth_context)

        assert user.auth_context.user_id == "testuser"
        assert user.auth_context.token == "test_token"
        assert user.auth_context.auth_type == "token"

    def test_user_inherits_base_user(self):
        """测试用户继承自 BaseUser"""
        from starlette.authentication import BaseUser

        auth_context = AuthContext(user_id="testuser")
        user = MCPUser(auth_context)

        assert isinstance(user, BaseUser)
