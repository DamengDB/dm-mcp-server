"""编码工具模块

提供自定义 JSON 编码器，支持 datetime、timedelta、Decimal 等数据库类型的序列化。
"""

import base64
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any


def _timedelta_to_iso8601_duration(td: timedelta) -> str:
    """将 timedelta 转为 ISO 8601 duration 字符串（PnDTnHnMnS）

    说明：部分 Python 版本未提供 ``timedelta.isoformat``，此处自行拼装，
    供 JSON 序列化及 MCP 工具（如 analyze_columns）消费
    """
    if td == timedelta(0):
        return "PT0S"
    negative = td < timedelta(0)
    if negative:
        td = -td
    sign = "-" if negative else ""
    days = td.days
    secs = td.seconds
    usec = td.microseconds
    hours, r1 = divmod(secs, 3600)
    minutes, seconds = divmod(r1, 60)
    day_part = f"{days}D" if days else ""
    time_parts: list[str] = []
    if hours:
        time_parts.append(f"{hours}H")
    if minutes:
        time_parts.append(f"{minutes}M")
    if usec:
        sec_total = seconds + usec / 1_000_000
        frac = f"{sec_total:.6f}".rstrip("0").rstrip(".")
        time_parts.append(f"{frac}S")
    elif seconds:
        time_parts.append(f"{seconds}S")
    elif not time_parts and not day_part:
        time_parts.append("0S")
    if day_part and time_parts:
        return f"{sign}P{day_part}T{''.join(time_parts)}"
    if day_part:
        return f"{sign}P{day_part}"
    return f"{sign}PT{''.join(time_parts)}"


class ExtendedJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器

    支持datetime、date、time、timedelta、Decimal等数据库类型的序列化，
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
        # bug 131940 ：日-时类 INTERVAL 在 Python 驱动中映射为 timedelta，须可 JSON 序列化（如 analyze_columns）
        elif isinstance(o, timedelta):
            return _timedelta_to_iso8601_duration(o)
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


