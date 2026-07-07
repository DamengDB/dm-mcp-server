"""DPC Cluster MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from dm_mcp.domain.mcp.providers.cluster import DpcClusterMCPProvider
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.datasource.services.pool import AsyncPoolService
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.infra.persistence.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext


class TestDpcClusterMCPProvider:
    """DpcClusterMCPProvider测试类"""

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
        return DpcClusterMCPProvider(mock_datasource_service)

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

        assert "get_dpc_sp_instances" in tool_names
        assert "get_dpc_instances" in tool_names
        assert "get_dpc_raft_list" in tool_names
        assert "get_dpc_instance_raft_topology" in tool_names
        assert "get_dpc_esession_detail" in tool_names
        assert "get_dpc_esession_summary" in tool_names
        assert "get_dpc_stask_threads_by_exec_id" in tool_names
        assert "get_dpc_stask_threads_top" in tool_names
        assert "get_dpc_sql_node_history_by_exec_id" in tool_names
        assert "get_dpc_sql_node_top" in tool_names

    @pytest.mark.asyncio
    async def test_get_dpc_sp_instances(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取SP实例列表"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"INST_ID": 1}]}
        )

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_dpc_sp_instances", {})

        assert "mode" in result
        assert result["mode"] == "SP"
        assert "instances" in result

    @pytest.mark.asyncio
    async def test_get_dpc_instances(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取DPC实例列表"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_dpc_instances", {})

        assert "instances" in result
        assert "count" in result

    @pytest.mark.asyncio
    async def test_get_dpc_raft_list(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取RAFT列表"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={
                "result": [{"RAFT_ID": 1, "DPC_MODE": "AUTO", "NAME": "raft1"}]
            }
        )

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_dpc_raft_list", {})

        assert "rafts" in result
        assert result["count"] == 1

    @pytest.mark.asyncio
    async def test_get_dpc_instance_raft_topology(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取实例RAFT拓扑"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_dpc_instance_raft_topology", {})

        assert "topology" in result

    @pytest.mark.asyncio
    async def test_get_dpc_esession_detail(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取ESESSION详情"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_dpc_esession_detail", {})

        assert "esessions" in result

    @pytest.mark.asyncio
    async def test_get_dpc_esession_summary(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取ESESSION汇总"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"SRC_SITEID": 1, "esess_cnt": 10}]}
        )

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_dpc_esession_summary", {})

        assert "summary" in result

    @pytest.mark.asyncio
    async def test_get_dpc_stask_threads_by_exec_id(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试按exec_id获取STASK线程"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_dpc_stask_threads_by_exec_id", {"exec_id": 123}
            )

        assert result["exec_id"] == 123
        assert "threads" in result

    @pytest.mark.asyncio
    async def test_get_dpc_stask_threads_top(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取Top STASK线程"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"EXEC_ID": 1, "TIME_USED": 1000}]}
        )

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_dpc_stask_threads_top", {"top_n": 10}
            )

        assert result["top_n"] == 10
        assert "threads" in result

    @pytest.mark.asyncio
    async def test_get_dpc_sql_node_history_by_exec_id(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试按exec_id获取SQL节点历史"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_dpc_sql_node_history_by_exec_id", {"exec_id": 456}
            )

        assert result["exec_id"] == 456
        assert "nodes" in result

    @pytest.mark.asyncio
    async def test_get_dpc_sql_node_top(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取Top SQL节点"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"TYPE$": "SELECT", "samples": 100}]}
        )

        provider = DpcClusterMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_dpc_sql_node_top", {"top_n": 20})

        assert result["top_n"] == 20


class TestDpcClusterMCPProviderEdgeCases:
    """DpcClusterMCPProvider边界情况测试类"""

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
    async def test_datasource_not_found(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试数据源不存在"""
        provider = DpcClusterMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=None)

        with MCPContext.as_current(ctx):
            with pytest.raises(ValueError, match="数据源未找到"):
                await provider._get_dpc_source()

    @pytest.mark.asyncio
    async def test_not_dmdpc_deploy_type(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试非DMDPC部署类型"""
        provider = DpcClusterMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource = MagicMock()
        mock_datasource.deploy_type = "single"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        with MCPContext.as_current(ctx):
            with pytest.raises(ValueError, match="deploy_type"):
                await provider._get_dpc_source()

    @pytest.mark.asyncio
    async def test_stask_threads_top_invalid_top_n(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试top_n无效值"""
        provider = DpcClusterMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        with MCPContext.as_current(ctx):
            with pytest.raises(ValueError, match="top_n 必须为正数"):
                await provider.mcp.call_tool("get_dpc_stask_threads_top", {"top_n": -1})

    @pytest.mark.asyncio
    async def test_exec_id_required(self, mock_datasource_service, mock_pool_service):
        """测试exec_id为必填参数"""
        provider = DpcClusterMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource.deploy_type = "dmdpc"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        with MCPContext.as_current(ctx):
            # exec_id 为 None 时应该直接抛出异常
            with pytest.raises(ValueError, match="exec_id 不能为空"):
                await provider._tool_get_dpc_stask_threads_by_exec_id(exec_id=None)


class TestDpcClusterMCPProviderHelpers:
    """DpcClusterMCPProvider辅助方法测试类"""

    def test_list_tools(self):
        """测试列出所有工具"""
        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_pool_service = MagicMock(spec=AsyncPoolService)
        provider = DpcClusterMCPProvider(mock_datasource_service)
        tools = provider.list_tools()
        assert len(tools) >= 10
