"""序列化工具模块

提供通用的数据序列化辅助函数，用于将数据库模型、复杂对象转换为 JSON 可序列化的字典。
"""

from datetime import datetime
from typing import Any


def jsonable_value(v: Any) -> Any:
    """递归将 datetime 转为 ISO 字符串，处理嵌套 dict/list。"""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [jsonable_value(item) for item in v]
    return v


def jsonable_row(row: dict[str, Any]) -> dict[str, Any]:
    """将字典中的每个值通过 jsonable_value 转换。"""
    return {k: jsonable_value(v) for k, v in row.items()}
