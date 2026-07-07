"""MCPContext 单元测试"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.persistence.datasource_context import DatasourceContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext
from dm_mcp.core.mcp.context import MCPContext


@pytest.fixture(autouse=True)
def reset_mcp_context():
    """在每个测试前重置 MCPContext 类变量"""
    MCPContext._extra_getters = {}
    yield
    MCPContext._extra_getters = {}


class TestMCPContextDefault:
    """MCPContext 默认值测试"""

    def test_default_values(self):
        """测试默认值"""
        ctx = MCPContext()
        assert ctx.auth is None
        assert ctx.metrics is None
        assert ctx.datasource is None
        assert ctx.extra == {}

    def test_with_all_contexts(self):
        """测试传入所有上下文"""
        auth = AuthContext(user_id="test_user")
        metrics = MetricsContext()
        ds_id = uuid.uuid4()
        datasource = DatasourceContext(datasource_id=ds_id)

        ctx = MCPContext(auth=auth, metrics=metrics, datasource=datasource)

        assert ctx.auth == auth
        assert ctx.metrics == metrics
        assert ctx.datasource == datasource


class TestMCPContextCurrent:
    """MCPContext.current() 测试"""

    def test_current_no_context(self):
        """测试无上下文时返回默认值"""
        with (
            patch("dm_mcp.core.mcp.context.AuthContext.get") as mock_auth,
            patch("dm_mcp.core.mcp.context.MetricsContext.get") as mock_metrics,
            patch("dm_mcp.core.mcp.context.DatasourceContext.get") as mock_ds,
        ):

            # 所有上下文都抛出 ValueError
            mock_auth.side_effect = ValueError("No auth context")
            mock_metrics.side_effect = ValueError("No metrics context")
            mock_ds.side_effect = ValueError("No datasource")

            ctx = MCPContext.current()

            # 应该返回默认值 None
            assert ctx.auth is None
            assert ctx.metrics is None
            assert ctx.datasource is None
            assert ctx.extra == {}

    def test_current_with_auth_context(self):
        """测试有认证上下文时正确获取"""
        auth_context = AuthContext(user_id="test_user", auth_type="token")

        with (
            patch("dm_mcp.core.mcp.context.AuthContext.get", return_value=auth_context),
            patch("dm_mcp.core.mcp.context.MetricsContext.get") as mock_metrics,
            patch("dm_mcp.core.mcp.context.DatasourceContext.get") as mock_ds,
        ):

            mock_metrics.side_effect = ValueError("No metrics context")
            mock_ds.side_effect = ValueError("No datasource")

            ctx = MCPContext.current()

            assert ctx.auth == auth_context
            assert ctx.auth.user_id == "test_user"
            assert ctx.metrics is None
            assert ctx.datasource is None

    def test_current_with_all_contexts(self):
        """测试所有上下文都存在时正确获取"""
        auth_context = AuthContext(user_id="test_user")
        metrics_context = MetricsContext(metadata={"user": "test"})
        ds_id = uuid.uuid4()
        ds_context = DatasourceContext(datasource_id=ds_id)

        with (
            patch("dm_mcp.core.mcp.context.AuthContext.get", return_value=auth_context),
            patch(
                "dm_mcp.core.mcp.context.MetricsContext.get",
                return_value=metrics_context,
            ),
            patch(
                "dm_mcp.core.mcp.context.DatasourceContext.get", return_value=ds_context
            ),
        ):

            ctx = MCPContext.current()

            assert ctx.auth == auth_context
            assert ctx.metrics == metrics_context
            assert ctx.datasource == ds_context


class TestMCPContextRegisterExtra:
    """MCPContext.register_extra() 测试"""

    def test_register_extra(self):
        """测试注册扩展上下文"""
        extra_getter = MagicMock(return_value="extra_value")

        MCPContext.register_extra("tenant", extra_getter)

        assert "tenant" in MCPContext._extra_getters
        assert MCPContext._extra_getters["tenant"] == extra_getter

    def test_register_multiple_extra(self):
        """测试注册多个扩展上下文"""
        getter1 = MagicMock(return_value="value1")
        getter2 = MagicMock(return_value="value2")

        MCPContext.register_extra("tenant", getter1)
        MCPContext.register_extra("trace", getter2)

        assert len(MCPContext._extra_getters) == 2
        assert MCPContext._extra_getters["tenant"] == getter1
        assert MCPContext._extra_getters["trace"] == getter2

    def test_register_extra_override(self):
        """测试覆盖已注册的扩展上下文"""
        getter1 = MagicMock(return_value="old")
        getter2 = MagicMock(return_value="new")

        MCPContext.register_extra("tenant", getter1)
        MCPContext.register_extra("tenant", getter2)

        # 新的覆盖旧的
        assert MCPContext._extra_getters["tenant"] == getter2


class TestMCPContextCurrentWithExtra:
    """MCPContext.current() 扩展上下文测试"""

    def test_current_with_extra_context(self):
        """测试获取扩展上下文"""
        auth_context = AuthContext(user_id="test")
        extra_data = {"tenant_id": "tenant1", "trace_id": "trace1"}

        def mock_tenant_getter():
            return extra_data

        MCPContext.register_extra("tenant", mock_tenant_getter)

        with (
            patch("dm_mcp.core.mcp.context.AuthContext.get", return_value=auth_context),
            patch("dm_mcp.core.mcp.context.MetricsContext.get") as mock_metrics,
            patch("dm_mcp.core.mcp.context.DatasourceContext.get") as mock_ds,
        ):

            mock_metrics.side_effect = ValueError("No metrics")
            mock_ds.side_effect = ValueError("No datasource")

            ctx = MCPContext.current()

            assert "tenant" in ctx.extra
            assert ctx.extra["tenant"] == extra_data

    def test_current_extra_getter_exception(self):
        """测试扩展上下文 getter 抛出异常时忽略"""
        auth_context = AuthContext(user_id="test")

        def failing_getter():
            raise RuntimeError("Getter failed")

        MCPContext.register_extra("fail", failing_getter)

        with (
            patch("dm_mcp.core.mcp.context.AuthContext.get", return_value=auth_context),
            patch("dm_mcp.core.mcp.context.MetricsContext.get") as mock_metrics,
            patch("dm_mcp.core.mcp.context.DatasourceContext.get") as mock_ds,
        ):

            mock_metrics.side_effect = ValueError("No metrics")
            mock_ds.side_effect = ValueError("No datasource")

            # 不应该抛出异常
            ctx = MCPContext.current()

            # fail 由于异常被忽略
            assert "fail" not in ctx.extra


class TestMCPContextGet:
    """MCPContext.get() 测试"""

    def test_get_auth(self):
        """测试获取 auth 上下文"""
        auth = AuthContext(user_id="test")
        ctx = MCPContext(auth=auth)

        assert ctx.get("auth") == auth

    def test_get_metrics(self):
        """测试获取 metrics 上下文"""
        metrics = MetricsContext()
        ctx = MCPContext(metrics=metrics)

        assert ctx.get("metrics") == metrics

    def test_get_datasource(self):
        """测试获取 datasource 上下文"""
        ds_id = uuid.uuid4()
        datasource = DatasourceContext(datasource_id=ds_id)
        ctx = MCPContext(datasource=datasource)

        assert ctx.get("datasource") == datasource

    def test_get_extra(self):
        """测试获取 extra 上下文"""
        ctx = MCPContext(extra={"tenant": "test_tenant"})

        assert ctx.get("tenant") == "test_tenant"

    def test_get_with_default(self):
        """测试获取不存在的上下文时返回默认值"""
        ctx = MCPContext()

        assert ctx.get("nonexistent") is None
        assert ctx.get("nonexistent", "default") == "default"

    def test_get_auth_returns_none(self):
        """测试 auth 为 None 时返回 None 而非 default"""
        ctx = MCPContext(auth=None)

        result = ctx.get("auth")
        assert result is None


class TestMCPContextAsCurrent:
    """MCPContext.as_current() 测试"""

    def test_as_current_context_manager(self):
        """测试上下文管理器功能"""
        auth = AuthContext(user_id="test_user")
        metrics = MetricsContext()
        ds_id = uuid.uuid4()
        datasource = DatasourceContext(datasource_id=ds_id)

        ctx = MCPContext(auth=auth, metrics=metrics, datasource=datasource)

        with MCPContext.as_current(ctx):
            # 在上下文中可以获取
            current = MCPContext.current()
            assert current.auth == auth
            assert current.metrics == metrics
            assert current.datasource == datasource

    def test_as_current_with_partial_context(self):
        """测试部分上下文（只有 auth）"""
        auth = AuthContext(user_id="test")
        ctx = MCPContext(auth=auth)

        with MCPContext.as_current(ctx):
            current = MCPContext.current()
            assert current.auth == auth
            # metrics 和 datasource 未设置

    def test_as_current_restores_previous(self):
        """测试退出后恢复之前的上下文"""
        # 先设置一个上下文
        old_auth = AuthContext(user_id="old_user")
        old_ctx = MCPContext(auth=old_auth)

        with MCPContext.as_current(old_ctx):
            assert MCPContext.current().auth.user_id == "old_user"

            # 在内部设置新上下文
            new_auth = AuthContext(user_id="new_user")
            new_ctx = MCPContext(auth=new_auth)

            with MCPContext.as_current(new_ctx):
                assert MCPContext.current().auth.user_id == "new_user"

            # 退出内层后应该恢复外层的上下文
            assert MCPContext.current().auth.user_id == "old_user"

        # 完全退出后，contextvars 恢复原值（无设置），current() 仍能返回默认值（各子 Context.get 不抛异常）
        # 因为 MetricsContext.get() 会返回空实例而不是抛异常，所以 MCPContext.current() 能正常返回
        ctx = MCPContext.current()
        assert ctx is not None


@pytest.mark.asyncio
class TestMCPContextBuildForStdio:
    """MCPContext.build_for_stdio() 测试"""

    async def test_build_for_stdio_default(self):
        """测试 stdio 模式构建默认上下文"""
        mock_settings = MagicMock()
        mock_settings.pool.default_source = "primary"

        ctx = await MCPContext.build_for_stdio(mock_settings)

        assert ctx.auth.user_id == "anonymous"
        assert ctx.auth.auth_type == "anonymous"
        assert ctx.metrics is not None
        assert ctx.datasource is not None

    async def test_build_for_stdio_with_datasource_service(self):
        """测试带数据源服务的 stdio 构建"""
        mock_settings = MagicMock()
        mock_settings.pool.default_source = "test_source"

        mock_datasource_service = AsyncMock()
        mock_datasource = MagicMock()
        mock_datasource.id = uuid.uuid4()
        mock_datasource_service.get_datasource = AsyncMock(return_value=mock_datasource)
        mock_datasource_service.get_default_datasource = AsyncMock(
            return_value="db_default"
        )

        ctx = await MCPContext.build_for_stdio(
            mock_settings, datasource_service=mock_datasource_service
        )

        assert ctx.auth.user_id == "anonymous"
        assert ctx.datasource.datasource_id == mock_datasource.id

        # 验证调用了正确的方法
        mock_datasource_service.get_default_datasource.assert_called_once()

    async def test_build_for_stdio_datasource_not_found(self):
        """测试数据源未找到时使用默认 UUID"""
        mock_settings = MagicMock()
        mock_settings.pool.default_source = "nonexistent"

        mock_datasource_service = AsyncMock()
        mock_datasource_service.get_default_datasource = AsyncMock(
            return_value="primary"
        )
        mock_datasource_service.get_datasource = AsyncMock(return_value=None)

        ctx = await MCPContext.build_for_stdio(
            mock_settings, datasource_service=mock_datasource_service
        )

        # 应该生成了 UUID
        assert ctx.datasource.datasource_id is not None


@pytest.mark.asyncio
class TestMCPContextBuildForHttp:
    """MCPContext.build_for_http() 测试"""

    async def test_build_for_http_auth_user(self):
        """测试带认证用户的 HTTP 上下文构建"""
        mock_settings = MagicMock()
        mock_settings.pool.default_source = "primary"

        # 创建带 auth_context 的用户对象
        auth = AuthContext(user_id="http_user", auth_type="token", token="abc")
        mock_user = MagicMock()
        mock_user.auth_context = auth
        mock_user.datasource_ids = []  # 未绑定数据源
        mock_user.default_datasource_id = None

        ctx = await MCPContext.build_for_http(mock_user, mock_settings)

        assert ctx.auth.user_id == "http_user"
        assert ctx.auth.auth_type == "token"
        assert ctx.metrics is not None
        assert ctx.datasource is not None

    async def test_build_for_http_no_auth_user(self):
        """测试无认证用户的 HTTP 上下文构建（匿名）"""
        mock_settings = MagicMock()
        mock_settings.pool.default_source = "primary"

        ctx = await MCPContext.build_for_http(None, mock_settings)

        assert ctx.auth.user_id == "anonymous"
        assert ctx.auth.auth_type == "anonymous"

    async def test_build_for_http_with_datasource_bound(self):
        """测试 Token 绑定数据源的 HTTP 上下文"""
        mock_settings = MagicMock()
        mock_settings.pool.default_source = "primary"

        bound_ds_id = str(uuid.uuid4())
        auth = AuthContext(user_id="token_user", auth_type="token", token="abc")
        mock_user = MagicMock()
        mock_user.auth_context = auth
        mock_user.datasource_ids = [bound_ds_id]
        mock_user.default_datasource_id = bound_ds_id

        mock_ds = MagicMock()
        mock_ds.id = uuid.UUID(bound_ds_id)
        mock_ds.enabled = True
        mock_datasource_service = MagicMock()
        mock_datasource_service.get_datasource = AsyncMock(return_value=mock_ds)

        ctx = await MCPContext.build_for_http(
            mock_user, mock_settings, mock_datasource_service
        )

        assert ctx.datasource.datasource_id == uuid.UUID(bound_ds_id)


class TestMCPContextModelBehavior:
    """MCPContext 作为 Pydantic Model 的行为测试"""

    def test_model_fields(self):
        """测试模型字段定义"""
        ctx = MCPContext.model_fields
        assert "auth" in ctx
        assert "metrics" in ctx
        assert "datasource" in ctx
        assert "extra" in ctx

    def test_model_dump(self):
        """测试模型序列化为字典"""
        auth = AuthContext(user_id="test")
        ctx = MCPContext(auth=auth)

        data = ctx.model_dump()

        assert "auth" in data
        assert data["auth"]["user_id"] == "test"

    def test_model_validate(self):
        """测试模型从字典创建"""
        data = {"auth": {"user_id": "from_dict"}}
        ctx = MCPContext.model_validate(data)

        assert ctx.auth.user_id == "from_dict"
