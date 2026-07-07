"""Inspection MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from dm_mcp.domain.mcp.providers.inspection import InspectionMCPProvider
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.datasource.services.pool import AsyncPoolService
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.infra.persistence.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext
from dm_mcp.core.exceptions import MCPExecutionError


class TestValidateExplainSql:
    """get_sql_explain_plan SQL 入参校验"""

    def test_allows_optimizer_hint(self):
        InspectionMCPProvider._validate_explain_sql(
            "SELECT /*+ USE_HASH(e, d) */ e.id FROM t e INNER JOIN t2 d ON e.id = d.id"
        )

    def test_allows_block_and_line_comments(self):
        InspectionMCPProvider._validate_explain_sql(
            "SELECT e.id -- employee id\nFROM t e /* filter */\nWHERE e.id = 1"
        )

    def test_rejects_semicolon(self):
        with pytest.raises(MCPExecutionError) as exc:
            InspectionMCPProvider._validate_explain_sql("SELECT 1; SELECT 2")
        assert exc.value.error_code == "EXPLAIN_REJECTED"
        assert "分号" in exc.value.message

    def test_rejects_unclosed_block_comment(self):
        with pytest.raises(MCPExecutionError) as exc:
            InspectionMCPProvider._validate_explain_sql("SELECT /*+ USE_HASH(a) FROM t")
        assert exc.value.error_code == "EXPLAIN_REJECTED"


class TestInspectionMCPProvider:
    """InspectionMCPProvider测试类"""

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
    def provider(self, mock_datasource_service, mock_pool_service):
        return InspectionMCPProvider(mock_datasource_service)

    @pytest.fixture
    def mock_mcp_context(self):
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

    def test_tools_registered(self, provider):
        """测试工具已注册"""
        tools = provider.mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "get_sql_explain_plan" in tool_names
        assert "find_long_active_sessions" in tool_names
        assert "find_sql_resource_hotspots" in tool_names
        assert "find_long_waiting_threads" in tool_names
        assert "get_blocking_chain" in tool_names
        assert "get_session_context" in tool_names
        assert "get_sql_execution_stats" in tool_names
        assert "get_buffer_pool_stats" in tool_names

    @pytest.mark.asyncio
    async def test_get_sql_explain_plan(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试获取SQL执行计划"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        with patch(
            "dm_mcp.domain.mcp.providers.inspection.InspectionMCPProvider._collect_explain_trace",
            new_callable=AsyncMock,
            return_value={
                "explain_text": "1   #NSET2: [1, 1, 0]",
                "exec_id": 1,
                "sql_stat": {"LOGICAL_READS": 10, "EXEC_TIME_MS": 2},
                "et_rows": [],
            },
        ):
            provider = InspectionMCPProvider(mock_datasource_service)

            with MCPContext.as_current(ctx):
                result = await provider.mcp.call_tool(
                    "get_sql_explain_plan", {"sql": "SELECT * FROM users"}
                )

        assert result["exec_id"] == 1
        assert "origin_plan" in result
        assert result["statistics"]["statement"]["logical_reads"] == 10

    @pytest.mark.asyncio
    async def test_get_sql_explain_plan_with_schema(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试带 schema 时 _exec 透传 schema 至 execute_query"""
        ctx, _ = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"1": 1}]},
        )
        mock_collect = AsyncMock(
            return_value={
                "explain_text": "plan",
                "exec_id": 2,
                "sql_stat": {"LOGICAL_READS": 1},
                "et_rows": [],
            }
        )
        with patch(
            "dm_mcp.domain.mcp.providers.inspection.InspectionMCPProvider._collect_explain_trace",
            mock_collect,
        ):
            provider = InspectionMCPProvider(mock_datasource_service)

            with MCPContext.as_current(ctx):
                result = await provider.mcp.call_tool(
                    "get_sql_explain_plan",
                    {"sql": "SELECT * FROM users", "schema": "DSTEST"},
                )

        assert "origin_plan" in result
        mock_collect.assert_awaited_once()
        assert mock_collect.await_args.kwargs["schema"] == "DSTEST"

    @pytest.mark.asyncio
    async def test_get_sql_explain_plan_error(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试获取SQL执行计划失败"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        with patch(
            "dm_mcp.domain.mcp.providers.inspection.InspectionMCPProvider._collect_explain_trace",
            new_callable=AsyncMock,
            side_effect=Exception("SQL error"),
        ):
            provider = InspectionMCPProvider(mock_datasource_service)

            with MCPContext.as_current(ctx):
                with pytest.raises(Exception, match="SQL error"):
                    await provider.mcp.call_tool(
                        "get_sql_explain_plan", {"sql": "SELECT * FROM users"}
                    )

    @pytest.mark.asyncio
    async def test_find_long_active_sessions(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试检索长活跃会话"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={
                "result": [{"SESS_ID": 1, "SQL_TEXT": "SELECT * FROM users"}]
            }
        )

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "find_long_active_sessions", {"threshold_ms": 1000}
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_find_sql_resource_hotspots(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试检索 SQL 资源热点"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={
                "result": [{"SQL_ID": 1, "SQL_TEXT": "SELECT * FROM users"}]
            }
        )

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "find_sql_resource_hotspots", {"top_n": 10}
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_sql_execution_stats(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试按 SQL ID 获取执行统计"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"SQL_ID": 123, "EXEC_TIME": 100}]}
        )

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_sql_execution_stats", {"sql_id": 123}
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_blocking_chain(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试获取阻塞链"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"TRX_ID": 1, "WAIT_FOR_ID": 2}]}
        )

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_blocking_chain", {})

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_buffer_pool_stats(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试获取缓冲池统计"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_buffer_pool_stats", {})

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_session_context(
        self,
        mock_mcp_context,
        mock_datasource_service,
        mock_pool_service,
    ):
        """测试获取会话上下文"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"SESS_ID": 1, "STATE": "ACTIVE"}]}
        )

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_session_context", {"session_id": 1}
            )

        assert result is not None


class TestInspectionMCPProviderEdgeCases:
    """InspectionMCPProvider边界情况测试类"""

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
    async def test_find_long_waiting_threads(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试检索长等待线程"""
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
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"THREAD_ID": 1, "WAIT_TIME": 5000}]}
        )

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "find_long_waiting_threads", {"threshold_ms": 1000}
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_find_long_active_sessions_error(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试检索长活跃会话失败"""
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
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=Exception("DB error")
        )

        provider = InspectionMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            with pytest.raises(Exception, match="DB error"):
                await provider.mcp.call_tool(
                    "find_long_active_sessions", {"threshold_ms": 1000}
                )


class TestInspectionMCPProviderTools:
    """InspectionMCPProvider工具方法测试类"""

    def test_list_tools_count(self):
        """测试工具数量"""
        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_pool_service = MagicMock(spec=AsyncPoolService)
        provider = InspectionMCPProvider(mock_datasource_service)
        tools = provider.list_tools()
        assert len(tools) >= 13
