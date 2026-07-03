import logging
from typing import Any, Dict, List, Optional

from dm_mcp.core.mcp.middleware import BaseMCPMiddleware, NextCallable
from dm_mcp.core.sql_guard import RiskLevel, SqlGuard
from dm_mcp.utils import json_dumps_with_datetime

logger = logging.getLogger(__name__)


class SqlGuardMCPMiddleware(BaseMCPMiddleware):
    """
    基于 SqlGuard 的 MCP 中间件。

    只在指定的工具上生效，用于对“对外暴露的任意 SQL 执行工具”做安全控制，
    不影响各 Provider 内部的固定 SQL。
    """

    def __init__(self, protected_tools: Optional[List[str]] = None) -> None:
        """
        Args:
            protected_tools: 需要启用 SQL 风险控制的工具名列表。
                例如: ["exec_readonly_query"]
        """
        super().__init__()
        self._sql_guard = SqlGuard()
        self.protected_tools = set(protected_tools or ["exec_readonly_query"])

    async def on_call_tool(
        self, call_next: NextCallable, name: str, arguments: Dict[str, Any]
    ) -> str:
        # 只拦选定工具，其余工具直接透传
        if name not in self.protected_tools:
            return await call_next(name, arguments)

        sql = arguments.get("sql")
        if not isinstance(sql, str):
            # 没有 SQL 文本，直接透传，由业务自行报错
            return await call_next(name, arguments)

        mode = arguments.get("mode", "readonly")

        try:
            report = self._sql_guard.analyze(sql, mode=mode)
        except Exception as exc:  # noqa: BLE001
            logger.error("SqlGuard 分析异常: %s", exc)
            # 分析失败时，不阻断业务执行，直接透传
            return await call_next(name, arguments)

        if report.risk_level == RiskLevel.BLOCK:
            # 统一返回一个 JSON 文本，保持与普通工具结果兼容
            result = {
                "allowed": False,
                "reason": report.reason,
                "risk_report": {
                    "risk_level": report.risk_level.value,
                    "statement_type": report.statement_type,
                    "is_select": report.is_select,
                    "has_for_update": report.has_for_update,
                    "has_lock_table": report.has_lock_table,
                    "write_tokens": report.write_tokens,
                    "tx_tokens": report.tx_tokens,
                    "risky_calls": report.risky_calls,
                    "unknown_calls": report.unknown_calls,
                    "calls": report.calls,
                    "details": report.details,
                },
                "suggestion": "建议重写为纯 SELECT 语句，或改用专用工具执行写操作 / 过程调用。",
            }
            return json_dumps_with_datetime(result)

        # 其余风险等级只打日志，不阻断
        if report.risk_level != RiskLevel.LOW:
            logger.warning(
                "SQL 语句存在中等/高风险但允许执行: %s, risk_level=%s",
                report.reason,
                report.risk_level.value,
            )

        return await call_next(name, arguments)
