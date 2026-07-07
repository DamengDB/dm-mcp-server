"""Query/Pool/Metrics Provider 测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dm_mcp.domain.mcp.providers.data import DataMCPProvider
from dm_mcp.domain.mcp.providers.inspection import InspectionMCPProvider
from dm_mcp.domain.mcp.providers.query_exec import QueryExecMCPProvider


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
        p = QueryExecMCPProvider(mock_datasource_service)
        tools = [t.name for t in p.list_tools()]
        assert "exec_query" in tools

    def test_inspection_provider_registers_tool(
        self, mock_pool_service, mock_datasource_service
    ):
        p = InspectionMCPProvider(mock_datasource_service)
        tools = [t.name for t in p.list_tools()]
        assert len(tools) >= 1
