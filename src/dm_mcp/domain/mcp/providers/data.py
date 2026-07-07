
from typing import Annotated, Any
from pydantic import Field
from dm_mcp.core.exceptions import MCPExecutionError
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.datasource.services.pool import _validate_identifier
from dm_mcp.domain.mcp.mappers import data_mapper as _mapper
from dm_mcp.domain.mcp.providers.base import BaseDataSourceMCPProvider
from dm_mcp.domain.mcp.providers.sql import data_sql as _sql

# bug 132011：analyze_columns 的 top_n 允许上限，避免超大整数传入 SQL FETCH FIRST 导致驱动异常退出
MAX_ANALYZE_COLUMNS_TOP_N = 10000

# bug 132101 ：analyze_columns 曾将用户可控的 schema/table 及字典列名直接拼入动态 SQL，存在注入（如 table_name 含空格与注释截断后续语句）。
# 引入版本：自本仓库提供 analyze_columns MCP 工具起至本修复提交前；修复版本：dm-mcp-server 以 pyproject.toml 的 project.version 为准（发布时与发行说明一致）。
# 标识符合法性仅调用连接池侧同一实现 pool._validate_identifier，不在此重复规则。


def _require_pool_sql_identifier(name: str) -> None:
    """将连接池的标识符校验映射为 MCP 预期错误（与建池时 schema 校验同源）。"""
    try:
        _validate_identifier(name)
    except ValueError as e:
        raise MCPExecutionError("INVALID_PARAMETER", str(e)) from e


class DataMCPProvider(BaseDataSourceMCPProvider):
    """表数据分析工具 Provider。"""

    def __init__(
        self,
        datasource_service: DataSourceService,
    ) -> None:
        super().__init__(datasource_service)
        self._register_routes()

    def _register_routes(self) -> None:
        """注册 MCP Tool 路由"""

        @self.mcp.tool(group="data", requires_token_auth=True)
        async def get_table_data_size(
            schema_name: Annotated[str, Field(description="表所属 schema")],
            table_name: Annotated[str, Field(description="表名")],
        ):
            """
            返回表的数据与索引空间占用（数据页数、索引页数、MB 等）。
            容量评估、大表识别、存储优化。
            """
            return await self._tool_get_table_data_size(
                schema_name=schema_name, table_name=table_name
            )

        @self.mcp.tool(group="data", requires_token_auth=True)
        async def get_table_basic_info(
            schema_name: Annotated[str, Field(description="表所属 schema")],
            table_name: Annotated[str, Field(description="表名")],
        ):
            """
            返回表的统计信息（行数、块数、平均行长、是否分区等）；调用前自动 GATHER_TABLE_STATS。
            优化器统计、执行计划分析、表规模评估。
            """
            return await self._tool_get_table_basic_info(
                schema_name=schema_name, table_name=table_name
            )

        @self.mcp.tool(group="data", requires_token_auth=True)
        async def analyze_columns(
            schema_name: Annotated[str, Field(description="表所属 schema")],
            table_name: Annotated[str, Field(description="表名")],
            top_n: Annotated[int, Field(description="每列 Top N 取值数量，默认 10", ge=1, le=MAX_ANALYZE_COLUMNS_TOP_N)] = 10,
        ):
            """
            分析表各列的统计特征（空值数、不重复值数、最大/最小值、Top N 取值频次）。
            数据质量分析、索引设计、理解列分布。
            """
            return await self._tool_analyze_columns(
                schema_name=schema_name, table_name=table_name, top_n=top_n
            )

    # ============================================================
    # 数据分析 Tools
    # ============================================================

    async def _tool_get_table_data_size(
        self,
        schema_name: str,
        table_name: str,
    ) -> dict[str, Any]:
        """获取指定表的数据与索引空间占用情况"""
        rows = await self._exec(
            sql=_sql.get_table_data_size(),
            params=[table_name, schema_name],
            max_rows=1,
        )
        return _mapper.table_data_size(schema_name, table_name, rows)

    async def _tool_get_table_basic_info(
        self,
        schema_name: str,
        table_name: str,
    ) -> dict[str, Any]:
        """获取指定表的基础统计信息与存储信息"""
        # 先收集统计信息
        await self._exec(
            sql=_sql.gather_table_stats(),
            params=[schema_name, table_name],
            max_rows=1,
        )

        # 再查询最新统计信息
        rows = await self._exec(
            sql=_sql.get_table_basic_info(),
            params=[schema_name, table_name],
            max_rows=1,
        )
        return _mapper.table_basic_info(schema_name, table_name, rows)

    async def _tool_analyze_columns(
        self,
        schema_name: str,
        table_name: str,
        top_n: int = 10,
    ) -> dict[str, Any]:
        """分析表中所有列的统计特征（行数、空值、不重复值、最大/最小值及 Top N 频次）"""
        # bug 132011：对 top_n 做范围校验，超大值须在访问数据库前拒绝并返回「数据溢出」，防止 MCP 进程异常退出
        if isinstance(top_n, bool) or not isinstance(top_n, int):
            raise MCPExecutionError(
                "INVALID_PARAMETER",
                "参数 top_n 须为正整数",
            )
        if top_n < 1:
            raise MCPExecutionError(
                "INVALID_PARAMETER",
                "参数 top_n 须为正整数",
            )
        if top_n > MAX_ANALYZE_COLUMNS_TOP_N:
            raise MCPExecutionError(
                "VALUE_OVERFLOW",
                "数据溢出",
            )

        _require_pool_sql_identifier(schema_name)
        _require_pool_sql_identifier(table_name)

        # 先从数据字典获取该表的所有列及数据类型
        columns = await self._exec(
            sql=_sql.get_columns(),
            params=[schema_name, table_name],
            max_rows=500,
        )

        if not columns:
            return _mapper.analyze_columns(
                schema_name, table_name, top_n, []
            )

        # 逐列统计
        qualified_table = f"{schema_name}.{table_name}"
        analyzed_columns: list[dict[str, Any]] = []

        for col in columns:
            col_name = col.get("COLUMN_NAME")
            data_type = col.get("DATA_TYPE")
            if not col_name:
                continue
            _require_pool_sql_identifier(col_name)

            stats_rows = await self._exec(
                sql=_sql.analyze_column_stats(col_name, qualified_table),
                max_rows=1,
            )
            top_rows = await self._exec(
                sql=_sql.analyze_column_top(col_name, qualified_table),
                params=[top_n],
                max_rows=top_n,
            )

            analyzed_columns.append(
                {
                    "column_name": col_name,
                    "data_type": data_type,
                    "basic_stats": stats_rows[0] if stats_rows else None,
                    "top_values": top_rows,
                }
            )

        return _mapper.analyze_columns(
            schema_name, table_name, top_n, analyzed_columns
        )
