"""OwnedQuery 单元测试

验证统一查询构建器的权限过滤和访问检查逻辑。
"""

import pytest
from sqlalchemy import select
from unittest.mock import MagicMock

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions.auth_errors import AuthorizationError
from dm_mcp.infra.persistence.query import OwnedQuery
from dm_mcp.infra.persistence.models import DataSourceModel


class TestOwnedQueryFilter:
    """测试 OwnedQuery.filter()"""

    def test_filter_adds_owner_condition_for_user(self):
        """普通用户应注入 owner_id 过滤条件"""
        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            stmt = select(DataSourceModel)
            result = OwnedQuery.filter(stmt, DataSourceModel)
            assert result is not stmt
            str_result = str(result)
            assert "owner_id" in str_result

    def test_filter_adds_owner_condition_for_admin(self):
        """admin 也应注入 owner_id 过滤条件，不享有特权"""
        with AuthContext.as_current(
            AuthContext(user_id="admin", auth_type="basic_auth")
        ):
            stmt = select(DataSourceModel)
            result = OwnedQuery.filter(stmt, DataSourceModel)
            assert result is not stmt
            str_result = str(result)
            assert "owner_id" in str_result

    def test_filter_adds_owner_condition_for_anonymous(self):
        """匿名用户应注入 owner_id 过滤条件"""
        stmt = select(DataSourceModel)
        result = OwnedQuery.filter(stmt, DataSourceModel)
        assert result is not stmt
        str_result = str(result)
        assert "owner_id" in str_result


class TestOwnedQueryCheckAccess:
    """测试 OwnedQuery.check_access()"""

    def test_public_resource_accessible_to_all(self):
        """owner_id 为 None 的公共资源所有人可访问"""
        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            model = MagicMock()
            model.owner_id = None
            model.name = "test"
            OwnedQuery.check_access(model)

    def test_owner_can_access_own_resource(self):
        """所有者可以访问自己的资源"""
        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            model = MagicMock()
            model.owner_id = "user_a"
            model.name = "test"
            OwnedQuery.check_access(model)

    def test_non_owner_cannot_access_private_resource(self):
        """非所有者不能访问他人的私有资源"""
        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            model = MagicMock()
            model.owner_id = "user_b"
            model.name = "test"
            with pytest.raises(AuthorizationError) as exc_info:
                OwnedQuery.check_access(model)
            assert "无权访问" in str(exc_info.value)

    def test_admin_cannot_access_others_private_resource(self):
        """admin 也不能访问他人的私有资源，遵循同样的 owner_id 隔离"""
        with AuthContext.as_current(
            AuthContext(user_id="admin", auth_type="basic_auth")
        ):
            model = MagicMock()
            model.owner_id = "user_b"
            model.name = "test"
            with pytest.raises(AuthorizationError):
                OwnedQuery.check_access(model)

    def test_anonymous_cannot_access_private_resource(self):
        """匿名用户不能访问私有资源"""
        model = MagicMock()
        model.owner_id = "user_b"
        model.name = "test"
        with pytest.raises(AuthorizationError):
            OwnedQuery.check_access(model)
