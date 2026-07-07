"""Data Mapper — 负责表数据分析类数据的格式化输出。"""

from typing import Any


def table_data_size(schema_name: str, table_name: str, rows: list[dict]) -> dict[str, Any]:
    """格式化表空间占用输出。"""
    return rows[0] if rows else {}


def table_basic_info(schema_name: str, table_name: str, rows: list[dict]) -> dict[str, Any]:
    """格式化表基础统计信息输出。"""
    return rows[0] if rows else {}


def analyze_columns(
    schema_name: str,
    table_name: str,
    top_n: int,
    analyzed_columns: list[dict],
) -> dict[str, Any]:
    """格式化列分析结果输出。"""
    return {
        "schema_name": schema_name,
        "table_name": table_name,
        "top_n": top_n,
        "columns": analyzed_columns,
    }
