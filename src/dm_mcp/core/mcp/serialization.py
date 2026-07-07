"""MCP 数据序列化模块

负责 Python 对象与 JSON 字符串之间的转换，支持 datetime、Decimal、timedelta、bytes 等数据库类型。

职责边界：
- 做：数据类型的序列化/反序列化
- 不做：envelope 结构包装（那是 ResponseFormatter 的职责）
"""

import json
from typing import Any

from dm_mcp.common.utils.encoding import ExtendedJSONEncoder


class DataSerializer:
    """MCP 数据序列化器

    所有 MCP 实体（Tool、Resource、Prompt）的数据序列化统一入口。
    内部使用 ExtendedJSONEncoder 处理数据库特殊类型。
    """

    @staticmethod
    def serialize(
        obj: Any,
        *,
        ensure_ascii: bool = False,
        indent: int | None = None,
    ) -> str:
        """将 Python 对象序列化为 JSON 字符串。

        Args:
            obj: 要序列化的对象（通常为 dict / list）
            ensure_ascii: 是否转义非 ASCII 字符（默认 False，支持中文直接输出）
            indent: 缩进空格数（默认 None，即紧凑格式；常用 2 用于调试展示）

        Returns:
            JSON 字符串
        """
        return json.dumps(
            obj,
            cls=ExtendedJSONEncoder,
            ensure_ascii=ensure_ascii,
            indent=indent,
        )

    @staticmethod
    def deserialize(text: str) -> Any:
        """将 JSON 字符串反序列化为 Python 对象。

        Args:
            text: JSON 字符串

        Returns:
            反序列化后的 Python 对象
        """
        return json.loads(text)
