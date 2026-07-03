from typing import Any
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from dm_mcp.providers.query_exec_provider import QueryExecMCPProvider
from dm_mcp.server.routes import get_routes
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.services.mcp_service import MCPService
from dm_mcp.settings import Settings
from dm_mcp.settings.pool_config import DmPoolConfig
from dm_mcp.settings.server_config import ServerConfig
from dm_mcp.services import DataSourceService, MetricsService


class _DummyGlobalContext:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.basic_auth_service = MagicMock()
        self.metrics_service = MagicMock(spec=MetricsService)
        self.datasource_service = MagicMock(spec=DataSourceService)
        self.pool_service = MagicMock()
        self.token_service = MagicMock()
        self.oauth_service = MagicMock()


def test_des_6_tc_01_mcp_mount_path_with_base_url(mock_settings):
    """[DM_MCP-des-6] DES-6-TC-01 MCP HTTP 路由路径符合 /dm-mcp/mcp 约定。"""
    # 配置 base_url
    mock_settings.server.base_url = "/dm-mcp"
    ctx = _DummyGlobalContext(mock_settings)
    session_manager = MagicMock()
    routes = get_routes(ctx, session_manager)

    mcp_mount_paths = {r.path for r in routes if getattr(r, "name", "") == "mcp"}  # type: ignore[attr-defined]
    assert "/dm-mcp/mcp" in mcp_mount_paths


@pytest.fixture
def mock_pool_service_for_des6(mock_datasource_service, mock_metrics_service):
    """为 des-6 构造 AsyncPoolService，但不真正连接数据库。"""
    pool_cfg = DmPoolConfig(enabled=False)
    service = AsyncPoolService(pool_cfg, mock_datasource_service, mock_metrics_service)
    service.execute_query = AsyncMock()
    return service


@pytest.fixture
def query_exec_provider_for_des6(
    mock_datasource_service, mock_pool_service_for_des6
) -> QueryExecMCPProvider:
    """使用真实 QueryExecMCPProvider，但依赖注入 mock 的 AsyncPoolService。"""
    provider = QueryExecMCPProvider(mock_datasource_service, mock_pool_service_for_des6)
    # 避免依赖 MCPContext / DataSourceService，直接指定当前数据源名
    provider._get_current_datasource_name = AsyncMock(return_value="primary")
    return provider


@pytest.mark.asyncio
async def test_des_6_tc_03_minimal_flow_list_and_call_tool(
    mock_metrics_service,
    mock_datasource_service,
    mock_logging_service,
    mock_pool_service_for_des6,
    query_exec_provider_for_des6,
):
    """[DM_MCP-des-6] DES-6-TC-03 最小闭环：通过 MCPService 列出并调用真实 SQL Provider 的只读查询工具。"""
    server_cfg = ServerConfig(name="test-mcp")
    mcp_service = MCPService(
        server_cfg,
        mock_metrics_service,
        mock_datasource_service,
        mock_logging_service,
    )

    # 注册真实的 QueryExecMCPProvider
    mcp_service.add_mcp_provider(query_exec_provider_for_des6)

    # 1) 列出工具，确认 exec_readonly_query 已注册
    tools = await mcp_service.list_tools()
    assert any(t.name == "exec_readonly_query" for t in tools)

    # 2) 模拟一个安全的只读查询场景
    #    - 通过 stub _sql_guard.analyze 返回低风险、SELECT 语句
    report = SimpleNamespace(
        normalized_sql="select 1",
        statement_type="SELECT",
        is_select=True,
        has_for_update=False,
        has_lock_table=False,
        write_tokens=[],
        tx_tokens=[],
        calls=[],
        unknown_calls=[],
        risky_calls=[],
        risk_level=SimpleNamespace(value="LOW"),
        reason="ok",
        details={},
    )
    query_exec_provider_for_des6._sql_guard.analyze = MagicMock(return_value=report)  # type: ignore[attr-defined]

    #    - AsyncPoolService.execute_query 返回固定结构的结果
    mock_pool_service_for_des6.execute_query.return_value = {
        "result": [{"id": 1}],
        "summary": "1 row",
    }

    # 3) 通过 MCPService.call_tool 触发完整协议链路
    result_str = await mcp_service.call_tool(
        "exec_readonly_query",
        {"sql": "SELECT * FROM T", "schema": "TEST", "max_rows": 5},
    )

    import json

    payload = json.loads(result_str)
    # 工具返回的业务结果应符合只读查询成功场景
    assert payload["allowed"] is True
    assert payload["risk_report"]["risk_level"] == "LOW"
    assert payload["result"] == [{"id": 1}]
    assert payload["summary"] == "1 row"

    # AsyncPoolService.execute_query 被正确调用一次，参数符合预期
    mock_pool_service_for_des6.execute_query.assert_awaited_once()
    _, kwargs = mock_pool_service_for_des6.execute_query.await_args
    assert kwargs["sql"] == "SELECT * FROM T"
    assert kwargs["schema"] == "TEST"
    assert kwargs["read_only"] is True
    assert kwargs["max_rows"] == 5
