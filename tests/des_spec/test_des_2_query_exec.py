from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from dm_mcp.providers.query_exec_provider import QueryExecMCPProvider
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.metrics_service import MetricsService
from dm_mcp.core.sql_guard import RiskLevel, SqlGuard
from dm_mcp.settings.pool_config import DmPoolConfig


class _RiskReport:
    def __init__(
        self,
        *,
        normalized_sql: str = "",
        statement_type: str = "SELECT",
        is_select: bool = True,
        has_for_update: bool = False,
        has_lock_table: bool = False,
        write_tokens=None,
        tx_tokens=None,
        calls=None,
        unknown_calls=None,
        risky_calls=None,
        risk_level: RiskLevel = RiskLevel.LOW,
        reason: str = "",
        details: Dict[str, Any] | None = None,
    ) -> None:
        self.normalized_sql = normalized_sql
        self.statement_type = statement_type
        self.is_select = is_select
        self.has_for_update = has_for_update
        self.has_lock_table = has_lock_table
        self.write_tokens = write_tokens or []
        self.tx_tokens = tx_tokens or []
        self.calls = calls or []
        self.unknown_calls = unknown_calls or []
        self.risky_calls = risky_calls or []
        self.risk_level = risk_level
        self.reason = reason
        self.details = details or {}


@pytest.fixture
def mock_pool_service(mock_datasource_service, mock_metrics_service):
    pool_cfg = DmPoolConfig(enabled=False)
    service = AsyncPoolService(pool_cfg, mock_datasource_service, mock_metrics_service)
    service.execute_query = AsyncMock()
    return service


@pytest.fixture
def query_exec_provider(mock_datasource_service, mock_pool_service):
    provider = QueryExecMCPProvider(mock_datasource_service, mock_pool_service)
    # 避免依赖 MCPContext / DataSourceService
    provider._get_current_datasource_name = AsyncMock(return_value="primary")
    return provider


@pytest.mark.asyncio
async def test_des_2_tc_01_tools_registered(query_exec_provider: QueryExecMCPProvider):
    """[DM_MCP-des-2] DES-2-TC-01 QueryExec Provider 工具注册完整。"""
    tools = query_exec_provider.list_tools()
    names = {t.name for t in tools}
    assert "exec_query" in names
    assert "analyze_sql_risk" in names
    assert "exec_readonly_query" in names


@pytest.mark.asyncio
async def test_des_2_tc_02_exec_query_routes_to_pool(
    query_exec_provider, mock_pool_service
):
    """[DM_MCP-des-2] DES-2-TC-02 exec_query 将请求路由到 AsyncPoolService。"""
    # fastmcp/mcp-sdk 模型下，调用由 MCPService 完成；此处直接走 Provider 内部受控入口
    result = await query_exec_provider._exec_query(
        sql="SELECT 1", params={"x": 1}, max_rows=100, timeout=1.5
    )

    mock_pool_service.execute_query.assert_awaited_once()
    args, kwargs = mock_pool_service.execute_query.await_args
    assert kwargs["sql"] == "SELECT 1"
    assert kwargs["source"] == "primary"
    assert kwargs["params"] == {"x": 1}
    assert kwargs["max_rows"] == 100
    assert kwargs["timeout"] == 1.5
    # 返回值直接来自 execute_query
    assert result is mock_pool_service.execute_query.return_value


@pytest.mark.asyncio
async def test_des_2_tc_03_analyze_sql_risk_returns_report(query_exec_provider):
    """[DM_MCP-des-2] DES-2-TC-03 analyze_sql_risk 返回结构化风险报告。"""
    report = _RiskReport(
        normalized_sql="select 1",
        statement_type="SELECT",
        is_select=True,
        risk_level=RiskLevel.LOW,
        reason="ok",
    )
    query_exec_provider._sql_guard.analyze = MagicMock(return_value=report)

    tool_def = query_exec_provider.mcp.tools_map["analyze_sql_risk"]
    result = await tool_def.fn(sql="SELECT 1", mode="readonly")
    # 工具返回的报告应当与 SqlGuard 分析结果保持一致
    assert result["normalized_sql"] == report.normalized_sql
    assert result["statement_type"] == report.statement_type
    assert result["is_select"] is report.is_select
    assert result["risk_level"] == report.risk_level.value


@pytest.mark.asyncio
async def test_des_2_tc_04_exec_readonly_query_block_high_risk(query_exec_provider):
    """[DM_MCP-des-2] DES-2-TC-04 高风险 SQL 在 exec_readonly_query 中被阻止。"""
    report = _RiskReport(
        normalized_sql="delete from t",
        statement_type="DELETE",
        is_select=False,
        risk_level=RiskLevel.BLOCK,
        reason="dangerous",
        write_tokens=["DELETE"],
    )
    query_exec_provider._sql_guard.analyze = MagicMock(return_value=report)

    tool_def = query_exec_provider.mcp.tools_map["exec_readonly_query"]
    result = await tool_def.fn(sql="DELETE FROM t", schema=None, max_rows=10)

    assert result["allowed"] is False
    assert "risk_report" in result
    assert result["risk_report"]["risk_level"] == RiskLevel.BLOCK.value
    assert "DELETE" in result["risk_report"]["write_tokens"]
    # 被阻止时不应真正执行查询
    query_exec_provider._pool_service.execute_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_des_2_tc_05_exec_readonly_query_reject_non_select(query_exec_provider):
    """[DM_MCP-des-2] DES-2-TC-05 非 SELECT 语句在只读工具中被拒绝。"""
    report = _RiskReport(
        normalized_sql="update t set x=1",
        statement_type="UPDATE",
        is_select=False,
        risk_level=RiskLevel.MEDIUM,
        reason="write",
    )
    query_exec_provider._sql_guard.analyze = MagicMock(return_value=report)

    tool_def = query_exec_provider.mcp.tools_map["exec_readonly_query"]
    result = await tool_def.fn(sql="UPDATE t SET x=1", schema=None, max_rows=10)

    assert result["allowed"] is False
    assert "只读查询只允许SELECT语句" in result["reason"]
    query_exec_provider._pool_service.execute_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_des_2_tc_06_exec_readonly_query_success(
    query_exec_provider, mock_pool_service
):
    """[DM_MCP-des-2] DES-2-TC-06 安全 SELECT 在只读工具中正常执行。"""
    report = _RiskReport(
        normalized_sql="select * from t",
        statement_type="SELECT",
        is_select=True,
        risk_level=RiskLevel.LOW,
        reason="ok",
    )
    query_exec_provider._sql_guard.analyze = MagicMock(return_value=report)

    mock_pool_service.execute_query.return_value = {
        "result": [{"id": 1}],
        "summary": "1 row",
    }

    tool_def = query_exec_provider.mcp.tools_map["exec_readonly_query"]
    result = await tool_def.fn(sql="SELECT * FROM T", schema="TEST", max_rows=5)

    assert result["allowed"] is True
    assert result["risk_report"]["risk_level"] == RiskLevel.LOW.value
    assert result["result"] == [{"id": 1}]
    assert result["summary"] == "1 row"

    mock_pool_service.execute_query.assert_awaited_once()
    _, kwargs = mock_pool_service.execute_query.await_args
    assert kwargs["sql"] == "SELECT * FROM T"
    assert kwargs["schema"] == "TEST"
    assert kwargs["read_only"] is True
    assert kwargs["max_rows"] == 5
