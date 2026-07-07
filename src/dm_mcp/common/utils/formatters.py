"""表格格式转换工具模块

提供 JSON 数据转 CSV、Markdown 表格等格式。
"""

import csv
import io
import json
from typing import Any

from .encoding import ExtendedJSONEncoder


def _csv_cell(v: Any) -> str:
    """将值转换为 CSV 安全的字符串。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return json.dumps(v, cls=ExtendedJSONEncoder, ensure_ascii=False)
    return str(v)


def json_to_csv(data: list[dict[str, Any]], *, bom: bool = True) -> str:
    """将 JSON 列表转换为 CSV 字符串

    Args:
        data: 字典列表，每个字典代表一行数据
        bom: 是否添加 UTF-8 BOM，便于 Excel 正确识别中文（默认 True）

    Returns:
        CSV 格式字符串
    """
    if not data:
        return ""

    headers = list(data[0].keys())
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    writer.writerow(headers)
    for row in data:
        writer.writerow([_csv_cell(row.get(h)) for h in headers])

    result = output.getvalue()
    if bom:
        result = "﻿" + result
    return result


def _md_cell(v: Any) -> str:
    """将值转换为 Markdown 表格安全的字符串。"""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    text = str(v)
    text = text.replace("|", "\\|")
    text = text.replace("\n", "<br>")
    text = text.replace("\r", "")
    return text


def json_to_markdown(data: list[dict[str, Any]]) -> str:
    """将 JSON 列表转换为 Markdown 表格字符串

    Args:
        data: 字典列表，每个字典代表一行数据

    Returns:
        Markdown 表格格式字符串
    """
    if not data:
        return ""

    headers = list(data[0].keys())
    lines: list[str] = []

    lines.append("| " + " | ".join(_md_cell(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in data:
        lines.append("| " + " | ".join(_md_cell(row.get(h)) for h in headers) + " |")

    return "\n".join(lines) + "\n"
