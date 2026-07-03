from typing import Any, Dict, Optional

from dm_mcp.providers.base_datasource_provider import BaseDataSourceMCPProvider
from dm_mcp.services import AsyncPoolService, DataSourceService


class QueryExecMCPProvider(BaseDataSourceMCPProvider):
    """执行类工具 Provider：仅负责 SQL 执行（不依赖 DataSourceService）。"""

    def __init__(
        self, datasource_service: DataSourceService, pool_service: AsyncPoolService
    ):
        super().__init__(datasource_service)
        self._pool_service = pool_service
        self._register_routes()

    async def _exec_query(
        self,
        sql: str,
        params: Optional[Any] = None,
        max_rows: int = 200,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        执行 SQL 查询（受控执行入口）
        """
        source = await self._get_current_datasource_name()
        return await self._pool_service.execute_query(
            sql=sql,
            source=source,
            params=params,
            max_rows=max_rows,
            timeout=timeout,
        )

    def _register_routes(self) -> None:
        @self.mcp.tool(requires_token_auth=True)
        async def exec_query(
            sql: str,
            params: Optional[Any] = None,
            max_rows: int = 200,
            timeout: Optional[float] = None,
        ):
            """
            执行任意 SQL（SELECT/INSERT/UPDATE/DELETE 等），不做风险拦截。
            适用场景：需执行写操作或复杂 SQL；只读场景建议用 exec_readonly_query 更安全。

            Args:
                sql: 要执行的 SQL 语句。
                params: 绑定参数（列表或映射，格式由驱动决定）。
                max_rows: 最大返回行数，默认 200。
                timeout: 超时秒数，None 用默认。

            Returns:
                Dict[str, Any]: 含 result（结果集）, summary（耗时/行数等，可选）。
            """
            return await self._exec_query(
                sql=sql,
                params=params,
                max_rows=max_rows,
                timeout=timeout,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def analyze_sql_risk(sql: str, mode: str = "readonly"):
            """
            分析 SQL 的风险等级（只分析不执行）。

            注意：实际的风控拦截由 SqlGuardMCPMiddleware 负责，这里仅提供分析结果。
            """
            from dm_mcp.core.sql_guard import SqlGuard  # 延迟导入避免循环

            guard = SqlGuard()
            report = guard.analyze(sql, mode=mode)
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

        @self.mcp.tool(requires_token_auth=True)
        async def exec_readonly_query(
            sql: str, schema: Optional[str] = None, max_rows: int = 200
        ):
            """
            执行只读 SELECT 查询，执行前强制安全检查。
            适用场景：只读场景首选；非 SELECT 或含 FOR UPDATE/锁表 会被拒绝返回 allowed=False。

            Args:
                sql: 要执行的 SQL（仅支持 SELECT）。
                schema: 默认 schema 名称（可选）。
                max_rows: 最大返回行数，默认 200。

            Returns:
                Dict[str, Any]: 成功时含 result；被阻止时含 allowed=False, reason, risk_report。
            """
            # 只负责执行查询，实际的 readonly 风险控制交由 SqlGuardMCPMiddleware 处理
            source = await self._get_current_datasource_name()
            result = await self._pool_service.execute_query(
                sql=sql,
                source=source,
                schema=schema,
                max_rows=max_rows,
                read_only=True,  # 强制只读
            )

            return {
                "allowed": True,
                "result": result.get("result", []),
                "summary": result.get("summary", ""),
            }
