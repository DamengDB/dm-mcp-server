"""Metadata Mapper — 负责元数据类数据的解析与格式化输出。"""

from typing import Any, cast

from dm_mcp.core.mcp.format import to_table
from dm_mcp.domain.mcp.entities import (
    ColumnEntity,
    ConstraintEntity,
    SchemaEntity,
    TableEntity,
)


# ============================================================
# Row helpers
# ============================================================

def ensure_dict_rows(
    rows: list[Any] | None, columns: list[str]
) -> list[dict[str, Any]] | None:
    """当驱动返回 list[list] 时，按列顺序转为 list[dict]。"""
    if rows is None:
        return None
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return cast(list[dict[str, Any]], rows)
    return [dict(zip(columns, row)) for row in rows]


# ============================================================
# Parse：原始 SQL 结果 → 结构化数据
# ============================================================

def parse_schemas(rows: list[Any]) -> list[SchemaEntity]:
    """将原始行解析为 SchemaEntity 列表。"""
    dict_rows = ensure_dict_rows(rows, ["SCHEMA_NAME", "OWNER_NAME", "CREATED_TIME"])
    return [
        SchemaEntity(
            name=r["SCHEMA_NAME"],
            owner=r.get("OWNER_NAME"),
            created_time=r.get("CREATED_TIME"),
        )
        for r in (dict_rows or [])
    ]


def parse_schema_info(rows: list[Any]) -> dict[str, Any]:
    """将原始行解析为 schema 信息字典。"""
    dict_rows = ensure_dict_rows(rows, ["SCHEMA_NAME", "OWNER", "CREATED_TIME"])
    return dict_rows[0] if dict_rows else {}


def parse_tables(
    rows: list[Any], include_comments: bool
) -> list[TableEntity]:
    """将原始行解析为 TableEntity 列表（TABLE 类型）。"""
    columns = ["SCHEMA_NAME", "OBJECT_NAME", "OBJECT_TYPE"]
    if include_comments:
        columns.append("TABLE_COMMENT")
    dict_rows = ensure_dict_rows(rows, columns)
    return [
        TableEntity(
            schema_name=r["SCHEMA_NAME"],
            table_name=r["OBJECT_NAME"],
            table_type="TABLE",
            comment=r.get("TABLE_COMMENT") or None,
        )
        for r in (dict_rows or [])
    ]


def parse_table_info(rows: list[Any]) -> dict[str, Any]:
    """将原始行解析为表信息字典。"""
    dict_rows = ensure_dict_rows(rows, ["SCHEMA_NAME", "TABLE_NAME"])
    return dict_rows[0] if dict_rows else {}


def parse_table_columns(rows: list[Any]) -> list[ColumnEntity]:
    """将原始行解析为 ColumnEntity 列表（表列）。"""
    dict_rows = ensure_dict_rows(
        rows,
        [
            "SCHEMA_NAME",
            "TABLE_NAME",
            "COLUMN_ID",
            "COLUMN_NAME",
            "DATA_TYPE",
            "DATA_LENGTH",
            "DATA_PRECISION",
            "DATA_SCALE",
            "NULLABLE",
            "DEFAULT_VALUE",
            "COLUMN_COMMENT",
        ],
    )
    return [
        ColumnEntity(
            schema_name=r["SCHEMA_NAME"],
            table_name=r["TABLE_NAME"],
            column_name=r["COLUMN_NAME"],
            column_id=r["COLUMN_ID"],
            data_type=r["DATA_TYPE"],
            data_length=r.get("DATA_LENGTH"),
            data_precision=r.get("DATA_PRECISION"),
            data_scale=r.get("DATA_SCALE"),
            nullable=(r.get("NULLABLE") == "Y"),
            default_value=r.get("DEFAULT_VALUE"),
            comment=r.get("COLUMN_COMMENT") or "",
        )
        for r in (dict_rows or [])
    ]


def parse_views(rows: list[Any], include_comments: bool) -> list[TableEntity]:
    """将原始行解析为 TableEntity 列表（VIEW 类型）。"""
    columns = ["SCHEMA_NAME", "OBJECT_NAME", "OBJECT_TYPE"]
    if include_comments:
        columns.append("VIEW_COMMENT")
    dict_rows = ensure_dict_rows(rows, columns)
    return [
        TableEntity(
            schema_name=r["SCHEMA_NAME"],
            table_name=r["OBJECT_NAME"],
            table_type="VIEW",
            comment=r.get("VIEW_COMMENT") or None,
        )
        for r in (dict_rows or [])
    ]


def parse_view_info(basic_rows: list[Any], def_rows: list[Any]) -> dict[str, Any]:
    """合并视图基本信息和定义行，解析为统一字典。"""
    dict_rows = ensure_dict_rows(
        basic_rows, ["SCHEMA_NAME", "VIEW_NAME", "OBJECT_TYPE", "VIEW_COMMENT"]
    )
    if not dict_rows:
        return {}

    view_info = dict_rows[0]
    view_info["COMMENT"] = view_info.get("VIEW_COMMENT")
    if def_rows:
        def_dict_rows = ensure_dict_rows(def_rows, ["DEFINITION"])
        if def_dict_rows:
            view_info["DEFINITION"] = def_dict_rows[0].get("DEFINITION") or ""
        elif isinstance(def_rows[0], dict):
            view_info["DEFINITION"] = def_rows[0].get("DEFINITION", "")
        else:
            row0 = def_rows[0]
            view_info["DEFINITION"] = row0[0] if row0 else ""
    else:
        view_info["DEFINITION"] = ""
    return view_info


def parse_view_columns(rows: list[Any]) -> list[ColumnEntity]:
    """将原始行解析为 ColumnEntity 列表（视图列）。"""
    dict_rows = ensure_dict_rows(
        rows,
        [
            "SCHEMA_NAME",
            "VIEW_NAME",
            "COLUMN_ID",
            "COLUMN_NAME",
            "DATA_TYPE",
            "DATA_LENGTH",
            "DATA_PRECISION",
            "DATA_SCALE",
            "NULLABLE",
            "DEFAULT_VALUE",
        ],
    )
    return [
        ColumnEntity(
            schema_name=r["SCHEMA_NAME"],
            table_name=r["VIEW_NAME"],
            column_name=r["COLUMN_NAME"],
            column_id=r["COLUMN_ID"],
            data_type=r["DATA_TYPE"],
            data_length=r.get("DATA_LENGTH"),
            data_precision=r.get("DATA_PRECISION"),
            data_scale=r.get("DATA_SCALE"),
            nullable=(r.get("NULLABLE") == "Y"),
            default_value=r.get("DEFAULT_VALUE"),
        )
        for r in (dict_rows or [])
    ]


def parse_table_indexes(rows: list[Any]) -> list[dict[str, Any]]:
    """将原始行解析为索引字典列表（按 INDEX_NAME 聚合复合索引）。"""
    dict_rows = ensure_dict_rows(
        rows,
        [
            "SCHEMA_NAME",
            "TABLE_NAME",
            "INDEX_NAME",
            "UNIQUENESS",
            "INDEX_TYPE",
            "COLUMN_POSITION",
            "COLUMN_NAME",
            "SORT_ORDER",
        ],
    )
    grouped: dict[str, dict[str, Any]] = {}
    for r in (dict_rows or []):
        index_name = str(r.get("INDEX_NAME") or "")
        if not index_name:
            continue
        if index_name not in grouped:
            grouped[index_name] = {
                "SCHEMA_NAME": r.get("SCHEMA_NAME"),
                "TABLE_NAME": r.get("TABLE_NAME"),
                "INDEX_NAME": index_name,
                "UNIQUENESS": r.get("UNIQUENESS"),
                "INDEX_TYPE": r.get("INDEX_TYPE"),
                "IS_UNIQUE": r.get("UNIQUENESS"),
                "COLUMNS": [],
            }
        grouped[index_name]["COLUMNS"].append(
            {
                "COLUMN_POSITION": r.get("COLUMN_POSITION"),
                "COLUMN_NAME": r.get("COLUMN_NAME"),
                "SORT_ORDER": r.get("SORT_ORDER"),
            }
        )

    result = list(grouped.values())
    for index in result:
        index["COLUMNS"].sort(
            key=lambda c: (
                int(c.get("COLUMN_POSITION"))
                if str(c.get("COLUMN_POSITION", "")).isdigit()
                else 10**9
            )
        )
    return result


def parse_table_constraints(
    constraint_rows: list[Any], not_null_rows: list[Any], limit: int = 10000
) -> list[ConstraintEntity]:
    """合并 DBA_CONSTRAINTS 和 NOT NULL 查询结果，解析为 ConstraintEntity 列表。"""
    dict_rows = ensure_dict_rows(
        constraint_rows,
        [
            "SCHEMA_NAME",
            "TABLE_NAME",
            "CONSTRAINT_NAME",
            "CONSTRAINT_TYPE",
            "STATUS",
            "COLUMN_NAME",
            "COLUMN_POSITION",
            "REF_OWNER",
            "REF_CONSTRAINT_NAME",
            "REF_TABLE_NAME",
            "REF_COLUMN_NAME",
        ],
    )
    constraints = ConstraintEntity.from_db_rows(dict_rows[:limit] if dict_rows else [])

    nn_dict_rows = ensure_dict_rows(not_null_rows, ["COLUMN_NAME", "NULLABLE"])
    nn_constraints = ConstraintEntity.from_not_null_columns(
        nn_dict_rows if nn_dict_rows else []
    )

    return (constraints + nn_constraints)[:limit]


# ============================================================
# Column / Entity helpers
# ============================================================

def dump_column(column_entity, exclude: set[str] | None = None) -> dict[str, Any]:
    """将 ColumnEntity 序列化为字典，自动清理空 comment。"""
    dumped = column_entity.model_dump(exclude_none=True, exclude=exclude)
    if dumped.get("comment") == "":
        dumped.pop("comment", None)
    return dumped


def dump_constraint(constraint_entity: ConstraintEntity) -> dict[str, Any]:
    """将 ConstraintEntity 序列化为字典。"""
    return constraint_entity.model_dump(exclude_none=True)


# ============================================================
# Resources
# ============================================================

def table_resource(
    schema: str,
    table: str,
    table_info: dict[str, Any],
    visible_columns: list[dict],
    indexes: list[dict],
) -> dict[str, Any]:
    """格式化表资源（概览）输出。"""
    return {
        "schema": schema,
        "table": table,
        "table_info": table_info,
        "columns_preview": to_table(visible_columns),
        "indexes_preview": indexes,
    }


def schema_resource(
    schema: str,
    schema_info: dict[str, Any],
    visible_tables: list[dict],
    visible_views: list[dict],
) -> dict[str, Any]:
    """格式化 Schema 资源（概览）输出。"""
    return {
        "schema": schema,
        "schema_info": schema_info,
        "tables": to_table(visible_tables),
        "views": to_table(visible_views),
    }


def view_resource(
    schema: str,
    view: str,
    view_info: dict[str, Any],
    definition_preview: str,
    visible_columns: list[dict],
) -> dict[str, Any]:
    """格式化视图资源（概览）输出。"""
    return {
        "schema": schema,
        "view": view,
        "view_info": view_info,
        "definition_preview": definition_preview,
        "columns_preview": to_table(visible_columns),
    }


def database_resource(
    db: str, schema_count: int, table_count: int, view_count: int
) -> dict[str, Any]:
    """格式化数据库资源（概览）输出。"""
    return {
        "db": db,
        "schema_count": schema_count,
        "table_count": table_count,
        "view_count": view_count,
    }


# ============================================================
# Tools
# ============================================================

def table_describe(
    schema: str | None,
    table: str,
    table_comment: str | None,
    visible_cols: list[dict],
    constraints: list[ConstraintEntity],
) -> dict[str, Any]:
    """格式化表描述（明细）输出。"""
    result: dict[str, Any] = {
        "schema": schema,
        "table": table,
        "columns": to_table(visible_cols),
        "constraints": [dump_constraint(c) for c in constraints],
    }
    if table_comment:
        result["comment"] = table_comment
    return result


def view_describe(
    schema: str | None,
    view: str,
    view_info: dict[str, Any],
    visible_columns: list[dict],
) -> dict[str, Any]:
    """格式化视图描述（明细）输出。"""
    cleaned_view_info = (
        {k: v for k, v in view_info.items() if k != "DEFINITION"}
        if isinstance(view_info, dict)
        else {}
    )
    return {
        "schema": schema,
        "view": view,
        "view_info": cleaned_view_info,
        "columns": to_table(visible_columns),
    }


def view_definition(
    schema: str | None,
    view: str,
    comment: str | None,
    definition: str | None,
) -> dict[str, Any]:
    """格式化视图定义（DDL）输出。"""
    return {
        "schema": schema,
        "view": view,
        "comment": comment,
        "definition": definition,
    }


def table_indexes_list(indexes: list[dict]) -> list[dict[str, Any]]:
    """格式化索引列表输出。"""
    return [
        {
            "name": r["INDEX_NAME"],
            "type": (
                "UNIQUE"
                if r.get("IS_UNIQUE") == "UNIQUE"
                else r.get("INDEX_TYPE", "NORMAL")
            ),
            "columns": [
                {
                    "name": c.get("COLUMN_NAME"),
                    "sort_order": c.get("SORT_ORDER"),
                }
                for c in r.get("COLUMNS", [])
            ],
        }
        for r in indexes
    ]


def table_constraints_list(constraints: list[ConstraintEntity]) -> list[dict[str, Any]]:
    """格式化约束列表输出。"""
    return [dump_constraint(c) for c in constraints]


# ============================================================
# Text helpers
# ============================================================

def truncate_definition(definition: str, max_length: int = 2000) -> str:
    """截断长文本定义，用于资源预览。"""
    if len(definition) > max_length:
        return definition[:max_length] + "..."
    return definition
