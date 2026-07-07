"""MCP Mappers — 负责原始数据解析与 MCP 输出格式化。"""

from .data_mapper import (
    analyze_columns,
    table_basic_info,
    table_data_size,
)
from .inspection_mapper import (
    explain_plan,
)
from .metadata_mapper import (
    database_resource,
    dump_column,
    dump_constraint,
    ensure_dict_rows,
    parse_schema_info,
    parse_schemas,
    parse_table_columns,
    parse_table_constraints,
    parse_table_indexes,
    parse_table_info,
    parse_tables,
    parse_view_columns,
    parse_view_info,
    parse_views,
    schema_resource,
    table_constraints_list,
    table_describe,
    table_indexes_list,
    table_resource,
    truncate_definition,
    view_definition,
    view_describe,
    view_resource,
)
from .query_exec_mapper import sql_risk_report

__all__ = [
    # data
    "analyze_columns",
    "table_basic_info",
    "table_data_size",
    # inspection
    "explain_plan",
    # metadata
    "database_resource",
    "dump_column",
    "dump_constraint",
    "ensure_dict_rows",
    "parse_schema_info",
    "parse_schemas",
    "parse_table_columns",
    "parse_table_constraints",
    "parse_table_indexes",
    "parse_table_info",
    "parse_tables",
    "parse_view_columns",
    "parse_view_info",
    "parse_views",
    "schema_resource",
    "table_constraints_list",
    "table_describe",
    "table_indexes_list",
    "table_resource",
    "truncate_definition",
    "view_definition",
    "view_describe",
    "view_resource",
    # query_exec
    "sql_risk_report",
]
