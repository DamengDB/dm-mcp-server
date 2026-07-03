"""UTF-8编码工具模块

提供统一的UTF-8编码支持，确保系统正确处理中文等非ASCII字符。
包括自定义JSON编码器、UTF-8响应类等。
"""

import base64
import json
import os
import sys
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict

from starlette.responses import JSONResponse


class ExtendedJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器

    支持datetime、date、time、Decimal等数据库类型的序列化，
    确保JSON导出不会失败。用于序列化包含数据库类型的数据。

    Examples:
        >>> encoder = ExtendedJSONEncoder()
        >>> encoder.encode({"date": datetime.now()})
        '{"date": "2024-01-01T12:00:00"}'
    """

    def default(self, o: Any) -> Any:
        """处理不可序列化的对象

        Args:
            o: 要序列化的对象

        Returns:
            Any: 序列化后的值

        Raises:
            TypeError: 当对象类型不支持时
        """
        if isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, date):
            return o.isoformat()
        elif isinstance(o, time):
            return o.isoformat()
        elif isinstance(o, Decimal):
            return float(o)
        elif isinstance(o, bytes):
            # 尝试解码为 UTF-8 字符串，如果失败则使用 base64 编码
            try:
                return o.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):
                # 无法解码为 UTF-8，使用 base64 编码
                return base64.b64encode(o).decode("ascii")
        # 处理其他不可序列化的类型
        return super().default(o)


def json_dumps_with_datetime(
    obj: Any, ensure_ascii: bool = False, indent: int | None = None
) -> str:
    """序列化 JSON，支持 datetime 等数据库类型

    Args:
        obj: 要序列化的对象
        ensure_ascii: 是否转义非 ASCII 字符
        indent: JSON 缩进空格数

    Returns:
        序列化后的 JSON 字符串
    """
    return json.dumps(
        obj, cls=ExtendedJSONEncoder, ensure_ascii=ensure_ascii, indent=indent
    )


def setup_utf8_encoding():
    """设置系统使用 UTF-8 编码

    在程序启动时调用此函数，确保：
    1. 设置环境变量 PYTHONIOENCODING=utf-8
    2. 配置标准输入输出流使用 UTF-8 编码
    """
    # 设置环境变量
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    # 配置标准流的编码
    if hasattr(sys.stdout, "reconfigure"):
        try:
            # type: ignore[attr-defined] - reconfigure 在 Python 3.7+ 可用，但类型存根可能未更新
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (ValueError, AttributeError):
            # 如果重新配置失败，使用环境变量
            pass


class UTF8JSONResponse(JSONResponse):
    """UTF-8编码的JSON响应类

    确保所有JSON响应使用UTF-8编码，正确支持中文等非ASCII字符。
    默认JSONResponse已经支持UTF-8，此类的目的是显式设置Content-Type，
    并处理包含datetime等特殊类型的内容。

    Examples:
        >>> response = UTF8JSONResponse({"message": "你好"})
        >>> response.headers["Content-Type"]
        'application/json; charset=utf-8'
    """

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Dict[str, str] | None = None,
        media_type: str = "application/json; charset=utf-8",
        **kwargs,
    ) -> None:
        """初始化UTF-8 JSON响应

        Args:
            content: 响应内容（将自动序列化为JSON字符串）
            status_code: HTTP状态码（默认200）
            headers: 响应头（可选）
            media_type: 媒体类型（默认"application/json; charset=utf-8"）
            **kwargs: 其他参数传递给基类
        """
        # 确保使用 UTF-8 编码序列化 JSON
        if content is not None:
            # 将内容序列化为 JSON 字符串（确保使用 UTF-8，支持 datetime 等类型）
            encoded_content = json_dumps_with_datetime(
                content,
                ensure_ascii=False,  # 不转义非 ASCII 字符（如中文）
                indent=None,
            )
        else:
            encoded_content = None

        # 设置默认 headers（如果未提供）
        if headers is None:
            headers = {}

        # 确保 Content-Type 包含 charset
        if "content-type" not in {k.lower() for k in headers.keys()}:
            headers["Content-Type"] = media_type

        super().__init__(
            content=encoded_content,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            **kwargs,
        )
