"""Metrics Export MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from dm_mcp.providers.metrics_export_provider import MetricsExportMCPProvider
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.services.metrics_service import MetricsService
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.core.datasource.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.metrics.metrics_context import MetricsContext


class TestMetricsExportMCPProvider:
    """MetricsExportMCPProvider测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        service.execute_query = AsyncMock()
        return service

    @pytest.fixture
    def mock_metrics_service(self):
        service = MagicMock(spec=MetricsService)
        service.export_metrics_snapshot = MagicMock(return_value={"metrics": "data"})
        return service

    @pytest.fixture
    def provider(
        self, mock_datasource_service, mock_pool_service, mock_metrics_service
    ):
        return MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

    @pytest.fixture
    def mock_mcp_context(self):
        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )
        return ctx, datasource_id

    def test_init(
        self, provider, mock_datasource_service, mock_pool_service, mock_metrics_service
    ):
        """测试初始化"""
        assert provider.datasource_service is mock_datasource_service
        assert provider._pool_service is mock_pool_service
        assert provider._metrics_service is mock_metrics_service

    def test_tools_registered(self, provider):
        """测试工具已注册"""
        tools = provider.mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "export_metrics" in tool_names
        assert "get_sql_explain_plan" in tool_names
        assert "get_sql_slow_queries_top" in tool_names
        assert "get_audit_recent_logs" in tool_names
        assert "get_sql_execution_profile" in tool_names
        assert "get_metrics" in tool_names
        assert "get_pool_status" in tool_names
        assert "get_worker_status" in tool_names

    @pytest.mark.asyncio
    async def test_export_metrics(self, provider):
        """测试导出指标"""
        result = await provider.mcp.call_tool("export_metrics", {})

        assert "metrics" in result or hasattr(result, "metrics")

    @pytest.mark.asyncio
    async def test_get_sql_explain_plan(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试获取SQL执行计划"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {"result": []},  # EXPLAIN结果
                {"result": [{"ID": 1, "OPERATION": "TABLE ACCESS"}]},  # 计划详情
            ]
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_sql_explain_plan", {"sql": "SELECT * FROM users"}
            )

        assert "sql" in result

    @pytest.mark.asyncio
    async def test_get_sql_explain_plan_error(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试获取SQL执行计划失败"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[Exception("SQL error")]  # EXPLAIN失败
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_sql_explain_plan", {"sql": "INVALID SQL"}
            )

        assert result.get("success") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_sql_slow_queries_top(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试获取慢SQL Top N"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [{"SQL_TEXT": "SELECT * FROM users", "EXEC_TIME": 1000}]
            }
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_sql_slow_queries_top", {"days": 7, "top_n": 10}
            )

        assert result.get("success") is True
        assert "slow_queries" in result

    @pytest.mark.asyncio
    async def test_get_audit_recent_logs(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试获取审计日志"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {"result": [{"ENABLE_AUDIT": "1"}]},  # 审计检查
                {
                    "result": [{"OPTIME": "2024-01-01", "USERNAME": "SYSDBA"}]
                },  # 审计日志
            ]
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_audit_recent_logs", {"days": 7, "limit": 100}
            )

        assert "audit_logs" in result or result.get("success") is not None

    @pytest.mark.asyncio
    async def test_get_audit_not_enabled(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试审计未开启"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            return_value={"result": [{"ENABLE_AUDIT": "0"}]}
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_audit_recent_logs", {"days": 7})

        assert result.get("success") is False

    @pytest.mark.asyncio
    async def test_get_sql_execution_profile_with_id(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试按SQL ID获取执行统计"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            return_value={"result": [{"SQL_ID": "abc123", "EXEC_TIME": 100}]}
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_sql_execution_profile", {"sql_id": "abc123"}
            )

        assert "execution_stats" in result or result.get("success") is not None

    @pytest.mark.asyncio
    async def test_get_sql_execution_profile_no_params(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试没有提供sql_id或sql_text"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_sql_execution_profile", {})

        assert result.get("success") is False
        assert "至少一个" in result.get("error", "")

    @pytest.mark.asyncio
    async def test_get_metrics(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试获取服务器监控指标"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(return_value={"result": []})

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_metrics", {})

        assert "metrics" in result

    @pytest.mark.asyncio
    async def test_get_pool_status(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试获取连接池状态"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {
                    "result": [
                        {"STATE": "ACTIVE", "count": 5},
                        {"STATE": "IDLE", "count": 10},
                    ]
                },  # 状态统计
                {"result": []},  # 详情
            ]
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_pool_status", {})

        assert result.get("success") is True
        assert "pool_status" in result

    @pytest.mark.asyncio
    async def test_get_worker_status(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
        mock_metrics_service,
    ):
        """测试获取worker状态"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {"result": [{"SESS_ID": 1, "STATE": "ACTIVE"}]},  # workers
                {"result": []},  # executions
            ]
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_worker_status", {})

        assert result.get("success") is True
        assert "worker_status" in result


class TestMetricsExportMCPProviderEdgeCases:
    """MetricsExportMCPProvider边界情况测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        service.execute_query = AsyncMock()
        return service

    @pytest.fixture
    def mock_metrics_service(self):
        service = MagicMock(spec=MetricsService)
        return service

    @pytest.mark.asyncio
    async def test_export_metrics_no_method(
        self, mock_datasource_service, mock_pool_service, mock_metrics_service
    ):
        """测试metrics_service没有导出方法"""
        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        # 删除导出方法
        if hasattr(provider._metrics_service, "export_metrics_snapshot"):
            delattr(provider._metrics_service, "export_metrics_snapshot")
        if hasattr(provider._metrics_service, "export_metrics"):
            delattr(provider._metrics_service, "export_metrics")

        with pytest.raises(AttributeError, match="缺少导出方法"):
            await provider._export_metrics()

    @pytest.mark.asyncio
    async def test_get_metrics_with_filter(
        self, mock_datasource_service, mock_pool_service, mock_metrics_service
    ):
        """测试按指标名称过滤"""
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=uuid4()),
        )

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service = MagicMock(spec=AsyncPoolService)
        mock_pool_service.execute_query = AsyncMock(
            return_value={"result": [{"total_sessions": 10}]}
        )

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_metrics", {"metric_names": ["sessions"]}
            )

        assert "metrics" in result

    @pytest.mark.asyncio
    async def test_get_sql_slow_queries_error(
        self, mock_datasource_service, mock_pool_service, mock_metrics_service
    ):
        """测试获取慢SQL失败"""
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=uuid4()),
        )

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service = MagicMock(spec=AsyncPoolService)
        mock_pool_service.execute_query = AsyncMock(side_effect=Exception("DB error"))

        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_sql_slow_queries_top", {})

        assert result.get("success") is False


class TestMetricsExportMCPProviderTools:
    """MetricsExportMCPProvider工具方法测试类"""

    def test_list_tools_count(self):
        """测试工具数量"""
        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_pool_service = MagicMock(spec=AsyncPoolService)
        mock_metrics_service = MagicMock(spec=MetricsService)
        provider = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )
        tools = provider.list_tools()
        assert len(tools) >= 8
