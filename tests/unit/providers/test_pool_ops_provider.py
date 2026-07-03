"""Pool Ops MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from dm_mcp.providers.pool_ops_provider import PoolOpsMCPProvider
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.core.datasource.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.metrics.metrics_context import MetricsContext


class TestPoolOpsMCPProvider:
    """PoolOpsMCPProvider测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        return service

    @pytest.fixture
    def provider(self, mock_datasource_service, mock_pool_service):
        return PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)

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
        assert provider._pool_service is mock_pool_service

    def test_tools_registered(self, provider):
        """测试工具已注册"""
        tools = provider.mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "pool_status" in tool_names
        assert "test_connection" in tool_names
        assert "get_connection_metrics" in tool_names

    @pytest.mark.asyncio
    async def test_pool_status(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取连接池状态"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.get_pool_status = AsyncMock(
            return_value={"total": 10, "active": 5, "idle": 5}
        )

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("pool_status", {})

        assert "total" in result or "status" in result

    @pytest.mark.asyncio
    async def test_test_connection_success(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试连接成功"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.test_connection = AsyncMock(
            return_value={"ok": True, "result": 1}
        )

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("test_connection", {"timeout": 5.0})

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_connection_metrics_returns_dict(
        self, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取连接池监控指标返回字典"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.get_connection_metrics = AsyncMock(
            return_value={
                "total_connections": 10,
            }
        )

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)

        with MCPContext.as_current(ctx):
            result = await provider._get_connection_metrics()

        assert isinstance(result, dict)


class TestPoolOpsMCPProviderEdgeCases:
    """PoolOpsMCPProvider边界情况测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        return service

    @pytest.mark.asyncio
    async def test_pool_status_returns_dict(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试获取连接池状态返回字典"""
        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)

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
        mock_pool_service.get_pool_status = AsyncMock(return_value={"total": 10})

        with MCPContext.as_current(ctx):
            result = await provider._get_pool_status()
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_connection_metrics_empty(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试获取空连接指标"""
        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)

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
        mock_pool_service.get_connection_metrics = AsyncMock(return_value={})

        with MCPContext.as_current(ctx):
            result = await provider._get_connection_metrics()
            assert isinstance(result, dict)

    def test_list_tools_count(self):
        """测试工具数量"""
        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_pool_service = MagicMock(spec=AsyncPoolService)
        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        tools = provider.list_tools()
        assert len(tools) >= 3


class TestPoolOpsMCPProviderMethods:
    """测试 PoolOpsMCPProvider 业务方法"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        return service

    def _create_context(self):
        """创建测试上下文"""
        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )
        return ctx, datasource_id

    @pytest.mark.asyncio
    async def test_get_pool_status_with_get_pool_status_method(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试使用 get_pool_status 方法"""
        mock_pool_service.get_pool_status = AsyncMock(
            return_value={"total": 10, "active": 5}
        )
        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, _ = self._create_context()

        with MCPContext.as_current(ctx):
            result = await provider._get_pool_status()
        assert result == {"total": 10, "active": 5}

    @pytest.mark.asyncio
    async def test_get_pool_status_with_pool_status_method(
        self, mock_datasource_service
    ):
        """测试使用 pool_status 方法"""
        mock_pool_service = MagicMock(
            spec=[]
        )  # Empty spec to avoid hasattr returning True
        mock_pool_service.pool_status = AsyncMock(
            return_value={"total": 20, "active": 10}
        )
        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, _ = self._create_context()

        with MCPContext.as_current(ctx):
            result = await provider._get_pool_status()
        assert result == {"total": 20, "active": 10}

    @pytest.mark.asyncio
    async def test_get_pool_status_with_status_method(self, mock_datasource_service):
        """测试使用 status 方法"""
        mock_pool_service = MagicMock()
        mock_pool_service.get_pool_status = MagicMock(
            return_value={"total": 10, "active": 5}
        )
        mock_pool_service.pool_status = MagicMock(
            return_value={"total": 20, "active": 10}
        )
        del mock_pool_service.get_pool_status
        del mock_pool_service.pool_status
        mock_pool_service.status = AsyncMock(return_value={"total": 30, "active": 15})
        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, _ = self._create_context()

        with MCPContext.as_current(ctx):
            result = await provider._get_pool_status()
        assert result == {"total": 30, "active": 15}

    @pytest.mark.asyncio
    async def test_get_pool_status_no_method_raises_error(
        self, mock_datasource_service
    ):
        """测试没有可用方法时抛出异常"""
        mock_pool_service = MagicMock()
        mock_pool_service.get_pool_status = MagicMock(return_value={})
        mock_pool_service.pool_status = MagicMock(return_value={})
        mock_pool_service.status = MagicMock(return_value={})
        del mock_pool_service.get_pool_status
        del mock_pool_service.pool_status
        del mock_pool_service.status
        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, _ = self._create_context()

        with MCPContext.as_current(ctx):
            with pytest.raises(AttributeError, match="缺少 pool 状态查询方法"):
                await provider._get_pool_status()

    @pytest.mark.asyncio
    async def test_test_connection_success(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试连接测试成功"""
        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(return_value={"result": [[1]]})

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, datasource_id = self._create_context()
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.list_data_sources = AsyncMock(
            return_value=[mock_datasource]
        )

        with MCPContext.as_current(ctx):
            result = await provider._test_connection(timeout=3.0)

        assert result["ok"] is True
        assert "result" in result

    @pytest.mark.asyncio
    async def test_test_connection_failure(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试连接测试失败"""
        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, datasource_id = self._create_context()
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.list_data_sources = AsyncMock(
            return_value=[mock_datasource]
        )

        with MCPContext.as_current(ctx):
            result = await provider._test_connection(timeout=3.0)

        assert result["ok"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_get_connection_metrics_success(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试获取连接指标成功"""
        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {
                    "result": [
                        {
                            "total_connections": 100,
                            "active_connections": 50,
                            "idle_connections": 50,
                        }
                    ]
                },
                {
                    "result": [
                        {
                            "healthy_connections": 90,
                            "unhealthy_connections": 10,
                            "connection_timeout_count": 2,
                            "connection_error_count": 1,
                        }
                    ]
                },
            ]
        )

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, datasource_id = self._create_context()
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.list_data_sources = AsyncMock(
            return_value=[mock_datasource]
        )

        with MCPContext.as_current(ctx):
            result = await provider._get_connection_metrics()

        assert result["success"] is True
        assert "connection_metrics" in result

    @pytest.mark.asyncio
    async def test_get_connection_metrics_empty_result(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试获取连接指标空结果"""
        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[{"result": []}, {"result": []}]
        )

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, datasource_id = self._create_context()
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.list_data_sources = AsyncMock(
            return_value=[mock_datasource]
        )

        with MCPContext.as_current(ctx):
            result = await provider._get_connection_metrics()

        assert "connection_metrics" in result

    @pytest.mark.asyncio
    async def test_get_connection_metrics_exception(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试获取连接指标异常"""
        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_pool_service.execute_query = AsyncMock(
            side_effect=Exception("Database error")
        )

        provider = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        ctx, datasource_id = self._create_context()
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.list_data_sources = AsyncMock(
            return_value=[mock_datasource]
        )

        with MCPContext.as_current(ctx):
            result = await provider._get_connection_metrics()

        assert result["success"] is False
        assert "error" in result
