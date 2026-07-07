"""元数据实体定义

数据库系统目录视图的查询结果 → MCP 层友好结构。
映射逻辑内聚在实体类方法中，不单独拆分 mapper。
"""

from typing import Any

from pydantic import BaseModel, Field


class ConstraintEntity(BaseModel):
    """表约束实体（聚合后）

    聚合来源：DBA_CONSTRAINTS + DBA_CONS_COLUMNS + ALL_TAB_COLUMNS(NOT NULL)
    """

    name: str | None = None
    type: str
    status: str | None = None
    columns: list[str] = Field(default_factory=list)
    ref_owner: str | None = None
    ref_constraint: str | None = None
    ref_table: str | None = None
    ref_columns: list[str] = Field(default_factory=list)

    @classmethod
    def from_db_rows(cls, rows: list[dict[str, Any]]) -> list["ConstraintEntity"]:
        """从数据库原始行聚合（一行一约束列 → 一实体一约束）

        Args:
            rows: DBA_CONSTRAINTS + DBA_CONS_COLUMNS 查询原始行

        Returns:
            按约束名聚合后的 ConstraintEntity 列表
        """
        groups: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = row.get("CONSTRAINT_NAME")
            if not name:
                continue
            if name not in groups:
                groups[name] = {
                    "name": name,
                    "type": cls._map_type(row.get("CONSTRAINT_TYPE", "")),
                    "status": row.get("STATUS"),
                    "columns": [],
                    "ref_owner": row.get("REF_OWNER"),
                    "ref_constraint": row.get("REF_CONSTRAINT_NAME"),
                    "ref_table": row.get("REF_TABLE_NAME"),
                    "ref_columns": [],
                }
            col = row.get("COLUMN_NAME")
            if col:
                groups[name]["columns"].append(col)
            ref_col = row.get("REF_COLUMN_NAME")
            if ref_col:
                groups[name]["ref_columns"].append(ref_col)
        return [cls.model_validate(g) for g in groups.values()]

    @classmethod
    def from_not_null_columns(
        cls, rows: list[dict[str, Any]]
    ) -> list["ConstraintEntity"]:
        """从 ALL_TAB_COLUMNS 原始行提取 NOT NULL 约束

        匿名同类型约束按 (type, status) 分组合并，status 不同则不合并。

        Args:
            rows: ALL_TAB_COLUMNS 中 NULLABLE = 'N' 的原始行

        Returns:
            合并后的 NOT_NULL ConstraintEntity 列表
        """
        groups: dict[tuple, dict[str, Any]] = {}
        for row in rows:
            col = row.get("COLUMN_NAME")
            if not col:
                continue
            key = ("NOT_NULL", "ENABLED")
            if key not in groups:
                groups[key] = {
                    "type": key[0],
                    "status": key[1],
                    "columns": [],
                }
            groups[key]["columns"].append(col)
        return [cls.model_validate(g) for g in groups.values()]

    @staticmethod
    def _map_type(raw: str) -> str:
        mapping = {
            "P": "PRIMARY_KEY",
            "R": "FOREIGN_KEY",
            "U": "UNIQUE",
            "C": "CHECK",
        }
        return mapping.get(raw, raw)
