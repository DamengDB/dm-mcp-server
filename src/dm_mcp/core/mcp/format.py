"""MCP Provider 辅助工具

提供 `to_table` 和 `McpResponseBuilder`，供 Provider 内部自主决定输出数据结构。
Service 层不再做自动转换或 Envelope 包装。
"""

from __future__ import annotations


def to_table(rows: list[dict]) -> dict:
    """将 list[dict] 转换为 columns+records 格式"""
    if not rows:
        return {"columns": [], "records": []}
    columns = list(rows[0].keys())
    records = [[r.get(c) for c in columns] for r in rows]
    return {"columns": columns, "records": records}


class McpResponseBuilder:
    """Provider 可显式使用此构建器决定输出格式"""

    @staticmethod
    def table(rows: list[dict], summary: dict | None = None) -> dict:
        return {"_mcp_response_type": "table", "value": to_table(rows), "summary": summary}

    @staticmethod
    def data(data: dict, summary: dict | None = None) -> dict:
        return {"_mcp_response_type": "data", "value": data, "summary": summary}

    @staticmethod
    def error(code: str, message: str) -> dict:
        return {"_mcp_response_type": "error", "code": code, "message": message}
