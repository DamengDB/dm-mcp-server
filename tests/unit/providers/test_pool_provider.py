"""Query/Pool/Metrics Provider 测试模块"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_mcp.providers.metrics_export_provider import MetricsExportMCPProvider
from dm_mcp.providers.pool_ops_provider import PoolOpsMCPProvider
from dm_mcp.providers.query_exec_provider import QueryExecMCPProvider


class TestProviders:
    @pytest.fixture
    def mock_pool_service(self):
        svc = MagicMock()
        svc.execute_query = AsyncMock(return_value={"result": "data"})
        svc.pool_status = MagicMock(return_value={"status": "ok"})
        return svc

    @pytest.fixture
    def mock_metrics_service(self):
        svc = MagicMock()
        svc.export = MagicMock(return_value=(b"metrics_data", "text/plain"))
        return svc

    @pytest.fixture
    def mock_datasource_service(self):
        svc = MagicMock()
        svc.get_datasource = AsyncMock(
            return_value=MagicMock(name="test_ds", enabled=True)
        )
        return svc

    def test_query_exec_provider_registers_tool(
        self, mock_pool_service, mock_datasource_service
    ):
        with patch("dm_mcp.providers.query_exec_provider.SqlGuard"):
            p = QueryExecMCPProvider(mock_datasource_service, mock_pool_service)
        tools = [t.name for t in p.list_tools()]
        assert "exec_query" in tools

    def test_pool_ops_provider_registers_tool(
        self, mock_pool_service, mock_datasource_service
    ):
        p = PoolOpsMCPProvider(mock_datasource_service, mock_pool_service)
        tools = [t.name for t in p.list_tools()]
        assert len(tools) >= 1

    def test_metrics_export_provider_registers_tool(
        self, mock_metrics_service, mock_pool_service, mock_datasource_service
    ):
        p = MetricsExportMCPProvider(
            mock_datasource_service, mock_pool_service, mock_metrics_service
        )
        tools = [t.name for t in p.list_tools()]
        assert len(tools) >= 1
