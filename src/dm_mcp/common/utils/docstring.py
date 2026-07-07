"""Docstring 解析工具模块

提供函数解析和 docstring 描述的公共辅助函数，
消除 tool.py、resource.py、prompt.py 中的重复代码。
"""

import inspect
from typing import Any, Callable


def resolve_function(fn: Callable[..., Any]) -> Callable[..., Any]:
    """解析函数对象，处理类实例和 staticmethod 的情况

    Args:
        fn: 可能是类实例、staticmethod 或普通函数的 callable

    Returns:
        解析后的实际函数对象
    """
    if not inspect.isroutine(fn) and hasattr(fn, "__call__"):
        fn = fn.__call__
    if isinstance(fn, staticmethod):
        fn = fn.__func__
    return fn


def split_description(raw_doc: str) -> tuple[str, str]:
    """从 docstring 中提取短描述和长描述

    Args:
        raw_doc: 原始 docstring 字符串

    Returns:
        (short_desc, long_desc) 元组
    """
    if raw_doc:
        lines = raw_doc.strip().split("\n")
        short_desc = lines[0].strip()
        long_desc = raw_doc.strip()
    else:
        short_desc = "未提供描述"
        long_desc = ""
    return short_desc, long_desc
