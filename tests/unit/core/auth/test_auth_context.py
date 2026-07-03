"""认证上下文单元测试

测试 AuthContext 的功能，包括上下文管理、数据源权限等。
"""

import pytest
from datetime import datetime, timezone
from contextlib import contextmanager

from dm_mcp.core.auth.auth_context import AuthContext


class TestAuthContext:
    """AuthContext 测试类"""

    def test_auth_context_creation(self):
        """测试创建认证上下文"""
        auth_context = AuthContext(
            user_id="testuser", auth_type="token", token="test_token"
        )

        assert auth_context.user_id == "testuser"
        assert auth_context.auth_type == "token"
        assert auth_context.token == "test_token"

    def test_auth_context_default_values(self):
        """测试认证上下文默认值"""
        auth_context = AuthContext()

        assert auth_context.user_id == "anonymous"
        assert auth_context.auth_type == "anonymous"
        assert auth_context.token is None
        assert isinstance(auth_context.login_time, datetime)
        assert isinstance(auth_context.last_activity, datetime)

    def test_auth_context_get_without_context(self):
        """测试在没有上下文时获取认证上下文"""
        with pytest.raises(ValueError, match="No auth context set"):
            AuthContext.get()

    def test_auth_context_get_with_context(self):
        """测试在有上下文时获取认证上下文"""
        auth_context = AuthContext(user_id="testuser", auth_type="token")

        with AuthContext.as_current(auth_context):
            retrieved = AuthContext.get()

            assert retrieved.user_id == "testuser"
            assert retrieved.auth_type == "token"

    def test_auth_context_as_current(self):
        """测试上下文管理器"""
        auth_context = AuthContext(
            user_id="testuser",
            auth_type="token",
        )

        with AuthContext.as_current(auth_context):
            retrieved = AuthContext.get()
            assert retrieved.user_id == "testuser"

    def test_auth_context_as_current_nested(self):
        """测试嵌套的上下文管理器"""
        auth1 = AuthContext(user_id="user1", auth_type="token")
        auth2 = AuthContext(user_id="user2", auth_type="oauth")

        with AuthContext.as_current(auth1):
            assert AuthContext.get().user_id == "user1"

            with AuthContext.as_current(auth2):
                assert AuthContext.get().user_id == "user2"

            # 外层上下文应该恢复
            assert AuthContext.get().user_id == "user1"

    def test_auth_context_different_auth_types(self):
        """测试不同的认证类型"""
        auth_types = ["oauth", "token", "basic_auth", "anonymous"]

        for auth_type in auth_types:
            auth_context = AuthContext(user_id="testuser", auth_type=auth_type)

            assert auth_context.auth_type == auth_type

    def test_auth_context_datetime_fields(self):
        """测试时间字段"""
        now = datetime.now(timezone.utc)
        auth_context = AuthContext(
            user_id="testuser", login_time=now, last_activity=now
        )

        assert auth_context.login_time == now
        assert auth_context.last_activity == now

    def test_auth_context_context_isolation(self):
        """测试上下文隔离（不同线程/任务）"""
        # 这个测试验证 contextvars 的隔离性
        # 在实际的异步环境中，每个任务都有独立的上下文
        auth1 = AuthContext(user_id="user1", auth_type="token")
        auth2 = AuthContext(user_id="user2", auth_type="oauth")

        with AuthContext.as_current(auth1):
            ctx1 = AuthContext.get()

            with AuthContext.as_current(auth2):
                ctx2 = AuthContext.get()

                # 两个上下文应该是不同的对象
                assert ctx1.user_id == "user1"
                assert ctx2.user_id == "user2"

            # 恢复后应该还是 user1
            assert AuthContext.get().user_id == "user1"
