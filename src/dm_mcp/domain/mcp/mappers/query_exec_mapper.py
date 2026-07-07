"""QueryExec Mapper — 负责 SQL 执行类数据的格式化输出。"""

from typing import Any

from dm_mcp.core.mcp.format import to_table


def query_result(rows: list[Any]) -> dict[str, Any]:
    """格式化查询结果输出为 table 格式。"""
    return to_table(rows)


def sql_risk_report(report) -> dict[str, Any]:
    """格式化 SQL 风险分析报告输出。"""
    return {
        "normalized_sql": report.normalized_sql,
        "statement_type": report.statement_type,
        "is_select": report.is_select,
        "has_for_update": report.has_for_update,
        "has_lock_table": report.has_lock_table,
        "write_tokens": report.write_tokens,
        "tx_tokens": report.tx_tokens,
        "calls": report.calls,
        "unknown_calls": report.unknown_calls,
        "risky_calls": report.risky_calls,
        "risk_level": report.risk_level.value,
        "reason": report.reason,
        "details": report.details,
    }
