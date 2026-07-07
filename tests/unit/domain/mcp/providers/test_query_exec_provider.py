"""QueryExec MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from dm_mcp.domain.mcp.providers.query_exec import QueryExecMCPProvider
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.datasource.services.pool import AsyncPoolService
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.infra.persistence.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext
from dm_mcp.core.exceptions import MCPExecutionError


class TestQueryExecMCPProvider:
    """QueryExecMCPProvider测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        """创建Mock DataSourceService"""
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        """创建Mock AsyncPoolService"""
        service = MagicMock(spec=AsyncPoolService)
        service.execute_query = AsyncMock()
        return service

    @pytest.fixture
    def provider(self, mock_datasource_service):
        """创建QueryExecMCPProvider实例"""
        return QueryExecMCPProvider(mock_datasource_service)

    @pytest.fixture
    def mock_mcp_context(self):
        """创建Mock MCPContext并设置为当前上下文"""
        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )
        return ctx, datasource_id

    def test_init(self, provider, mock_datasource_service, mock_pool_service):
        """测试初始化"""
        assert provider.datasource_service is mock_datasource_service
        assert hasattr(provider, "mcp")

    @pytest.mark.asyncio
    async def test_exec_query_basic(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试_exec_query基本功能"""
        ctx, datasource_id = mock_mcp_context

        # Mock datasource_service返回数据源名称
        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        # Mock execute_query返回结果
        mock_datasource_service.execute_query = AsyncMock(
            return_value={
                "result": [{"id": 1, "name": "test"}],
                "summary": "1 row affected",
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider._exec(sql="SELECT * FROM users")

        assert isinstance(result, list)
        assert result[0]["id"] == 1
        mock_datasource_service.get_datasource_by_id.assert_called_once_with(
            datasource_id
        )
        mock_datasource_service.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_exec_query_with_params(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试_exec_query带参数"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [], "summary": "0 rows"}
        )

        with MCPContext.as_current(ctx):
            result = await provider._exec(
                sql="SELECT * FROM users WHERE ID = ?",
                params=(1,),
                max_rows=100,
                timeout=30.0,
            )

        mock_datasource_service.execute_query.assert_called_once()
        call_kwargs = mock_datasource_service.execute_query.call_args.kwargs
        assert call_kwargs["params"] == (1,)
        assert call_kwargs["max_rows"] == 100
        assert call_kwargs["timeout"] == 30.0

    def test_tools_registered(self, provider):
        """测试工具已注册"""
        tools = provider.mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "exec_query" in tool_names
        assert "analyze_sql_risk" in tool_names
        assert "exec_readonly_query" in tool_names

    @pytest.mark.asyncio
    async def test_analyze_sql_risk_select(self, provider, mock_mcp_context):
        """测试analyze_sql_risk - SELECT语句"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        with MCPContext.as_current(ctx):
            with patch.object(provider, "datasource_service") as mock_ds_svc:
                mock_ds_svc.get_datasource_by_id = AsyncMock(
                    return_value=mock_datasource
                )
                with patch("dm_mcp.domain.mcp.sql_guard.SqlGuard") as MockGuard:
                    mock_guard = MockGuard.return_value
                    mock_report = MagicMock()
                    mock_report.normalized_sql = "SELECT * FROM users"
                    mock_report.statement_type = "SELECT"
                    mock_report.is_select = True
                    mock_report.has_for_update = False
                    mock_report.has_lock_table = False
                    mock_report.write_tokens = []
                    mock_report.tx_tokens = []
                    mock_report.calls = []
                    mock_report.unknown_calls = []
                    mock_report.risky_calls = []
                    mock_report.risk_level.value = "ALLOW"
                    mock_report.reason = "Safe query"
                    mock_report.details = {}

                    mock_guard.analyze.return_value = mock_report

                    result = await provider.mcp.call_tool(
                        "analyze_sql_risk", {"sql": "SELECT * FROM USERS"}
                    )

                    assert result["statement_type"] == "SELECT"
                    assert result["is_select"] is True
                    assert result["risk_level"] == "ALLOW"

    @pytest.mark.asyncio
    async def test_analyze_sql_risk_delete(self, provider, mock_mcp_context):
        """测试analyze_sql_risk - DELETE语句"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        with MCPContext.as_current(ctx):
            with patch.object(provider, "datasource_service") as mock_ds_svc:
                mock_ds_svc.get_datasource_by_id = AsyncMock(
                    return_value=mock_datasource
                )
                with patch("dm_mcp.domain.mcp.sql_guard.SqlGuard") as MockGuard:
                    mock_guard = MockGuard.return_value
                    mock_report = MagicMock()
                    mock_report.normalized_sql = "DELETE FROM USERS"
                    mock_report.statement_type = "DELETE"
                    mock_report.is_select = False
                    mock_report.has_for_update = False
                    mock_report.has_lock_table = False
                    mock_report.write_tokens = ["DELETE"]
                    mock_report.tx_tokens = []
                    mock_report.calls = []
                    mock_report.unknown_calls = []
                    mock_report.risky_calls = []
                    mock_report.risk_level.value = "ALLOW"
                    mock_report.reason = "Write operation"
                    mock_report.details = {}

                    mock_guard.analyze.return_value = mock_report

                    result = await provider.mcp.call_tool(
                        "analyze_sql_risk", {"sql": "DELETE FROM USERS WHERE ID = 1"}
                    )

                    assert result["statement_type"] == "DELETE"
                    assert result["is_select"] is False

    @pytest.mark.asyncio
    async def test_analyze_sql_risk_with_mode(self, provider, mock_mcp_context):
        """测试analyze_sql_risk带mode参数"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        with MCPContext.as_current(ctx):
            with patch.object(provider, "datasource_service") as mock_ds_svc:
                mock_ds_svc.get_datasource_by_id = AsyncMock(
                    return_value=mock_datasource
                )
                with patch("dm_mcp.domain.mcp.sql_guard.SqlGuard") as MockGuard:
                    mock_guard = MockGuard.return_value
                    mock_guard.analyze = MagicMock()

                    await provider.mcp.call_tool(
                        "analyze_sql_risk", {"sql": "SELECT 1", "mode": "normal"}
                    )

                    mock_guard.analyze.assert_called_once_with(
                        "SELECT 1", mode="normal"
                    )

    @pytest.mark.asyncio
    async def test_exec_readonly_query_allowed(
        self, provider, mock_mcp_context
    ):
        """测试exec_readonly_query - 允许执行"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        with MCPContext.as_current(ctx):
            with patch.object(provider, "datasource_service") as mock_ds_svc:
                mock_ds_svc.get_datasource_by_id = AsyncMock(
                    return_value=mock_datasource
                )
                mock_ds_svc.execute_query = AsyncMock(
                    return_value={"result": [{"ID": 1}], "summary": "1 row"}
                )

                result = await provider.mcp.call_tool(
                    "exec_readonly_query", {"sql": "SELECT * FROM USERS"}
                )

                assert result == {"columns": ["ID"], "records": [[1]]}

    @pytest.mark.asyncio
    async def test_exec_readonly_query_blocked(self, provider, mock_mcp_context):
        """测试exec_readonly_query - execute_query异常"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        with MCPContext.as_current(ctx):
            with patch.object(provider, "datasource_service") as mock_ds_svc:
                mock_ds_svc.get_datasource_by_id = AsyncMock(
                    return_value=mock_datasource
                )
                mock_ds_svc.execute_query = AsyncMock(
                    side_effect=Exception("readonly blocked")
                )

                with pytest.raises(Exception, match="readonly blocked"):
                    await provider.mcp.call_tool(
                        "exec_readonly_query",
                        {"sql": "SELECT * FROM USERS LOCK IN SHARE MODE"},
                    )

    @pytest.mark.asyncio
    async def test_exec_readonly_query_non_select(self, provider, mock_mcp_context):
        """测试exec_readonly_query - 非SELECT被SqlGuard BLOCK"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        with MCPContext.as_current(ctx):
            with patch.object(provider, "datasource_service") as mock_ds_svc:
                mock_ds_svc.get_datasource_by_id = AsyncMock(
                    return_value=mock_datasource
                )

                with pytest.raises(MCPExecutionError):
                    await provider.mcp.call_tool(
                        "exec_readonly_query", {"sql": "UPDATE USERS SET NAME = 'test'"}
                    )

    def test_list_tools(self, provider):
        """测试列出所有工具"""
        tools = provider.list_tools()
        assert len(tools) >= 3  # 至少3个工具

    @pytest.mark.asyncio
    async def test_call_tool(self, provider, mock_mcp_context):
        """测试通过call_tool调用工具"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        # 通过mcp router调用
        with MCPContext.as_current(ctx):
            with patch("dm_mcp.domain.mcp.sql_guard.SqlGuard") as MockGuard:
                mock_guard = MockGuard.return_value
                mock_report = MagicMock()
                mock_report.normalized_sql = "SELECT 1"
                mock_report.statement_type = "SELECT"
                mock_report.is_select = True
                mock_report.has_for_update = False
                mock_report.has_lock_table = False
                mock_report.write_tokens = []
                mock_report.tx_tokens = []
                mock_report.calls = []
                mock_report.unknown_calls = []
                mock_report.risky_calls = []
                mock_report.risk_level.value = "ALLOW"
                mock_report.reason = "Test"
                mock_report.details = {}
                mock_guard.analyze.return_value = mock_report

                result = await provider.mcp.call_tool(
                    "analyze_sql_risk", {"sql": "SELECT 1"}
                )

        assert "statement_type" in result


class TestQueryExecMCPProviderEdgeCases:
    """QueryExecMCPProvider边界情况测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        service.execute_query = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_exec_query_datasource_not_found(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试数据源不存在时的错误处理"""
        provider = QueryExecMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=None)

        with MCPContext.as_current(ctx):
            with pytest.raises(ValueError, match="数据源未找到"):
                await provider._exec(sql="SELECT 1")

    @pytest.mark.asyncio
    async def test_exec_query_max_rows_default(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试 exec_query 工具默认 max_rows"""
        provider = QueryExecMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        with MCPContext.as_current(ctx):
            await provider.mcp.call_tool("exec_query", {"sql": "SELECT 1"})

        call_kwargs = mock_datasource_service.execute_query.call_args.kwargs
        assert call_kwargs["max_rows"] == 200  # 工具层面默认值

    @pytest.mark.asyncio
    async def test_analyze_sql_risk_with_complex_sql(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试复杂SQL分析"""
        provider = QueryExecMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        complex_sql = """
            SELECT u.ID, u.NAME, o.ORDER_ID
            FROM users u
            LEFT JOIN orders o ON u.ID = o.USER_ID
            WHERE u.STATUS = 'active'
            ORDER BY u.CREATED_AT DESC
            LIMIT 100
        """

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        with MCPContext.as_current(ctx):
            with patch("dm_mcp.domain.mcp.sql_guard.SqlGuard") as MockGuard:
                mock_guard = MockGuard.return_value
                mock_report = MagicMock()
                mock_report.normalized_sql = "SELECT..."
                mock_report.statement_type = "SELECT"
                mock_report.is_select = True
                mock_report.has_for_update = False
                mock_report.has_lock_table = False
                mock_report.write_tokens = []
                mock_report.tx_tokens = []
                mock_report.calls = []
                mock_report.unknown_calls = []
                mock_report.risky_calls = []
                mock_report.risk_level.value = "ALLOW"
                mock_report.reason = "Safe"
                mock_report.details = {}
                mock_guard.analyze.return_value = mock_report

                result = await provider.mcp.call_tool(
                    "analyze_sql_risk", {"sql": complex_sql, "mode": "readonly"}
                )

                assert result["statement_type"] == "SELECT"
                assert result["is_select"] is True
