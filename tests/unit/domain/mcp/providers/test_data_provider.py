"""Data MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

from dm_mcp.domain.mcp.providers.data import DataMCPProvider
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.infra.persistence.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext
from dm_mcp.core.exceptions import MCPExecutionError


class TestDataMCPProvider:
    """DataMCPProvider测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def provider(self, mock_datasource_service):
        return DataMCPProvider(mock_datasource_service)

    @pytest.fixture
    def mock_mcp_context(self):
        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )
        return ctx, datasource_id

    def test_init(self, provider, mock_datasource_service):
        """测试初始化"""
        assert provider.datasource_service is mock_datasource_service

    def test_tools_registered(self, provider):
        """测试工具已注册"""
        tools = provider.mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "get_table_data_size" in tool_names
        assert "get_table_basic_info" in tool_names
        assert "analyze_columns" in tool_names

    @pytest.mark.asyncio
    async def test_get_table_data_size(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试获取表空间占用"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "模式名": "TEST_SCHEMA",
                        "表名": "TEST_TABLE",
                        "数据占用页数": 100,
                        "索引占用页数": 20,
                        "数据占用MB": 0.78,
                        "索引占用MB": 0.16,
                    }
                ]
            }
        )

        provider = DataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_data_size",
                {"schema_name": "TEST_SCHEMA", "table_name": "TEST_TABLE"},
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_table_data_size_error(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试获取表空间占用失败"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=Exception("DB error")
        )

        provider = DataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            with pytest.raises(Exception, match="DB error"):
                await provider.mcp.call_tool(
                    "get_table_data_size",
                    {"schema_name": "TEST_SCHEMA", "table_name": "TEST_TABLE"},
                )

    @pytest.mark.asyncio
    async def test_get_table_basic_info(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试获取表基础统计信息"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=[
                {"result": []},  # GATHER_TABLE_STATS
                {
                    "result": [
                        {
                            "OWNER": "TEST_SCHEMA",
                            "TABLE_NAME": "TEST_TABLE",
                            "NUM_ROWS": 1000,
                            "BLOCKS": 50,
                        }
                    ]
                },  # 查询结果
            ]
        )

        provider = DataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_basic_info",
                {"schema_name": "TEST_SCHEMA", "table_name": "TEST_TABLE"},
            )

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_table_basic_info_gather_stats_error(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试收集统计信息失败"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=Exception("Stats error")
        )

        provider = DataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            with pytest.raises(Exception, match="Stats error"):
                await provider.mcp.call_tool(
                    "get_table_basic_info",
                    {"schema_name": "TEST_SCHEMA", "table_name": "TEST_TABLE"},
                )

    @pytest.mark.asyncio
    async def test_analyze_columns(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试分析列统计特征"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=[
                {
                    "result": [
                        {"COLUMN_NAME": "ID", "DATA_TYPE": "INT"},
                        {"COLUMN_NAME": "NAME", "DATA_TYPE": "VARCHAR"},
                    ]
                },  # 列信息
                {"result": [{"TOTAL_ROWS": 100, "NULL_COUNT": 0, "DISTINCT_COUNT": 100}]},  # ID stats
                {"result": [{"VALUE": 1, "OCCUR_COUNT": 1}]},  # ID top
                {"result": [{"TOTAL_ROWS": 100, "NULL_COUNT": 5, "DISTINCT_COUNT": 80}]},  # NAME stats
                {"result": [{"VALUE": "Alice", "OCCUR_COUNT": 3}]},  # NAME top
            ]
        )

        provider = DataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "analyze_columns",
                {"schema_name": "TEST_SCHEMA", "table_name": "TEST_TABLE", "top_n": 1},
            )

        assert result is not None
        assert len(result.get("columns", [])) == 2

    @pytest.mark.asyncio
    async def test_analyze_columns_no_columns(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试分析列时表无列"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": []}
        )

        provider = DataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "analyze_columns",
                {"schema_name": "TEST_SCHEMA", "table_name": "TEST_TABLE"},
            )

        assert result is not None
        assert result.get("columns") == []

    @pytest.mark.asyncio
    async def test_analyze_columns_error(
        self,
        mock_mcp_context,
        mock_datasource_service,
    ):
        """测试分析列失败"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=Exception("DB error")
        )

        provider = DataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            with pytest.raises(Exception, match="DB error"):
                await provider.mcp.call_tool(
                    "analyze_columns",
                    {"schema_name": "TEST_SCHEMA", "table_name": "TEST_TABLE"},
                )


class TestDataMCPProviderTools:
    """DataMCPProvider工具方法测试类"""

    def test_list_tools_count(self):
        """测试工具数量"""
        mock_datasource_service = MagicMock(spec=DataSourceService)
        provider = DataMCPProvider(mock_datasource_service)
        tools = provider.list_tools()
        assert len(tools) == 3
