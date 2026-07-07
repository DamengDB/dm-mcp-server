"""DataSerializer 单元测试

覆盖 datetime、Decimal、timedelta、bytes、中文等场景的序列化与反序列化。
"""

import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from dm_mcp.core.mcp.serialization import DataSerializer


class TestDataSerializerSerialize:
    """serialize 方法测试"""

    def test_plain_dict(self):
        """普通 dict 序列化"""
        result = DataSerializer.serialize({"key": "value"})
        assert json.loads(result) == {"key": "value"}

    def test_list_of_dicts(self):
        """list[dict] 序列化"""
        result = DataSerializer.serialize([{"a": 1}, {"a": 2}])
        assert json.loads(result) == [{"a": 1}, {"a": 2}]

    def test_datetime_serialization(self):
        """datetime 序列化为 ISO 格式"""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = DataSerializer.serialize({"ts": dt})
        assert json.loads(result) == {"ts": "2024-01-15T10:30:45"}

    def test_date_serialization(self):
        """date 序列化为 ISO 格式"""
        d = date(2024, 6, 1)
        result = DataSerializer.serialize({"d": d})
        assert json.loads(result) == {"d": "2024-06-01"}

    def test_time_serialization(self):
        """time 序列化为 ISO 格式"""
        t = time(14, 30, 0)
        result = DataSerializer.serialize({"t": t})
        assert json.loads(result) == {"t": "14:30:00"}

    def test_timedelta_serialization(self):
        """timedelta 序列化为 ISO 8601 duration"""
        td = timedelta(days=1, hours=2, minutes=3, seconds=4)
        result = DataSerializer.serialize({"td": td})
        assert json.loads(result) == {"td": "P1DT2H3M4S"}

    def test_decimal_serialization(self):
        """Decimal 序列化为 float"""
        d = Decimal("3.14159")
        result = DataSerializer.serialize({"pi": d})
        assert json.loads(result) == {"pi": 3.14159}

    def test_bytes_utf8_serialization(self):
        """UTF-8 bytes 解码为字符串"""
        b = "hello".encode("utf-8")
        result = DataSerializer.serialize({"data": b})
        assert json.loads(result) == {"data": "hello"}

    def test_bytes_base64_serialization(self):
        """非 UTF-8 bytes 使用 base64 编码"""
        b = b"\x89PNG\r\n\x1a\n"  # PNG 文件头
        result = DataSerializer.serialize({"data": b})
        loaded = json.loads(result)
        assert loaded["data"] == "iVBORw0KGgo="  # base64 编码后的 PNG 头

    def test_chinese_not_escaped(self):
        """中文默认不转义（ensure_ascii=False）"""
        result = DataSerializer.serialize({"msg": "你好"})
        assert "你好" in result
        assert "\\u" not in result

    def test_ensure_ascii_true(self):
        """ensure_ascii=True 时中文转义"""
        result = DataSerializer.serialize({"msg": "你好"}, ensure_ascii=True)
        assert "\\u4f60" in result  # 你 的 Unicode 转义

    def test_indent_none(self):
        """默认无缩进（紧凑格式）"""
        result = DataSerializer.serialize({"a": 1})
        assert result == '{"a": 1}'

    def test_indent_2(self):
        """indent=2 时格式化缩进"""
        result = DataSerializer.serialize({"a": 1}, indent=2)
        assert result == '{\n  "a": 1\n}'


class TestDataSerializerDeserialize:
    """deserialize 方法测试"""

    def test_simple_dict(self):
        """简单 dict 反序列化"""
        result = DataSerializer.deserialize('{"key": "value"}')
        assert result == {"key": "value"}

    def test_list(self):
        """list 反序列化"""
        result = DataSerializer.deserialize('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_nested_structure(self):
        """嵌套结构反序列化"""
        result = DataSerializer.deserialize('{"a": {"b": [1, 2]}}')
        assert result == {"a": {"b": [1, 2]}}

    def test_invalid_json_raises(self):
        """非法 JSON 抛出异常"""
        with pytest.raises(json.JSONDecodeError):
            DataSerializer.deserialize("not json")


class TestDataSerializerRoundTrip:
    """序列化-反序列化往返测试"""

    def test_round_trip_plain(self):
        """普通 dict 往返"""
        original = {"name": "test", "value": 42}
        serialized = DataSerializer.serialize(original)
        deserialized = DataSerializer.deserialize(serialized)
        assert deserialized == original

    def test_round_trip_with_special_types(self):
        """含特殊类型的往返（datetime/Decimal 序列化后变 str/float）"""
        original = {"ts": datetime(2024, 1, 1, 0, 0, 0), "val": Decimal("1.5")}
        serialized = DataSerializer.serialize(original)
        deserialized = DataSerializer.deserialize(serialized)
        assert deserialized == {"ts": "2024-01-01T00:00:00", "val": 1.5}
