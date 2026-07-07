"""元数据库结构兼容性校验

启动时对比 SQLAlchemy 模型与数据库实际结构，发现缺表/缺列则失败。
不执行任何自动迁移或结构修补。
"""

from __future__ import annotations

from dm_mcp.common import messages
from dm_mcp.infra.config.server_config import ServerConfig

from .models import Base


class SchemaIncompatibleError(RuntimeError):
    """元数据库结构与当前版本模型不兼容"""

    code = "SCHEMA_INCOMPATIBLE"

    def __init__(
        self,
        issues: list[str],
        *,
        schema_hint: str,
        version: str | None = None,
    ) -> None:
        self.issues = issues
        self.schema_hint = schema_hint
        self.version = version or ServerConfig.version
        super().__init__(self.format_message())

    def format_message(self) -> str:
        issue_lines = "\n".join(
            messages.MSG_SCHEMA_INCOMPATIBLE_ISSUE.format(issue=issue)
            for issue in self.issues
        )
        return messages.MSG_SCHEMA_INCOMPATIBLE.format(
            version=self.version,
            issues=issue_lines,
            schema_hint=self.schema_hint,
        )


def collect_schema_issues(inspector) -> list[str]:
    """对比模型元数据与数据库 inspector，返回不兼容项列表。"""
    issues: list[str] = []

    for table in Base.metadata.sorted_tables:
        table_name = table.name
        if not inspector.has_table(table_name):
            issues.append(
                messages.MSG_SCHEMA_INCOMPATIBLE_MISSING_TABLE.format(
                    table_name=table_name
                )
            )
            continue

        db_column_names = {
            col["name"].lower() for col in inspector.get_columns(table_name)
        }
        for column in table.columns:
            col_name = column.name
            if col_name.lower() not in db_column_names:
                issues.append(
                    messages.MSG_SCHEMA_INCOMPATIBLE_MISSING_COLUMN.format(
                        table_name=table_name,
                        column_name=col_name,
                    )
                )

    return issues


def verify_schema_compatible_sync(sync_conn, *, schema_hint: str) -> None:
    """在 run_sync 中执行的同步结构校验。"""
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    issues = collect_schema_issues(inspector)
    if issues:
        raise SchemaIncompatibleError(issues, schema_hint=schema_hint)
