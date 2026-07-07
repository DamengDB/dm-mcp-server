from typing import Annotated, Any

from pydantic import Field
from dm_mcp.core.exceptions import MCPExecutionError
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.mcp.mappers import query_exec_mapper as _mapper
from dm_mcp.domain.mcp.providers.base import BaseDataSourceMCPProvider


class QueryExecMCPProvider(BaseDataSourceMCPProvider):
    """执行类工具 Provider：负责 SQL 执行（通过 DataSourceService）。"""

    def __init__(self, datasource_service: DataSourceService):
        super().__init__(datasource_service)
        self._sql_guard = None
        self._register_routes()

    def _get_sql_guard(self):
        """延迟初始化 SqlGuard"""
        if self._sql_guard is None:
            from dm_mcp.domain.mcp.sql_guard import SqlGuard
            self._sql_guard = SqlGuard()
        return self._sql_guard

    def _register_routes(self) -> None:
        @self.mcp.tool(group="query", requires_token_auth=True)
        async def exec_query(
            sql: Annotated[str, Field(description="要执行的 SQL 语句")],
            params: Annotated[Any | None, Field(description="绑定参数（列表或映射，格式由驱动决定）")] = None,
            max_rows: Annotated[int, Field(description="最大返回行数，默认 200")] = 200,
            timeout: Annotated[float | None, Field(description="超时秒数，None 用默认")] = None,
        ):
            """
            执行任意 SQL（SELECT/INSERT/UPDATE/DELETE 等），不做风险拦截。
            需执行写操作或复杂 SQL；只读场景建议用 exec_readonly_query 更安全。
            """
            rows = await self._exec(
                sql=sql,
                params=params,
                max_rows=max_rows,
                timeout=timeout,
            )
            return _mapper.query_result(rows)

        @self.mcp.tool(group="query", requires_token_auth=True)
        async def analyze_sql_risk(
            sql: Annotated[str, Field(description="要分析的 SQL 语句")],
            mode: Annotated[str, Field(description="分析模式：readonly 或 dml，默认 readonly")] = "readonly",
        ):
            """分析 SQL 的风险等级（只分析不执行）。"""
            guard = self._get_sql_guard()
            report = guard.analyze(sql, mode=mode)
            return _mapper.sql_risk_report(report)

        @self.mcp.tool(group="query", requires_token_auth=True)
        async def exec_readonly_query(
            sql: Annotated[str, Field(description="要执行的 SQL（仅支持 SELECT）")],
            max_rows: Annotated[int, Field(description="最大返回行数，默认 200")] = 200,
        ):
            """
            执行只读 SELECT 查询，执行前强制安全检查。
            只读场景首选；非 SELECT 或含 FOR UPDATE/锁表 会被拒绝。
            """
            guard = self._get_sql_guard()
            report = guard.analyze(sql, mode="readonly")
            if report.risk_level.value == "BLOCK":
                raise MCPExecutionError("SQL_BLOCKED", report.reason)

            rows = await self._exec(
                sql=sql,
                max_rows=max_rows,
                read_only=True,
            )
            return _mapper.query_result(rows)
