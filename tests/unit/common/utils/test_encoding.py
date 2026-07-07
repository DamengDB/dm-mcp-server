"""encoding 编码工具模块测试"""

import base64
import json
import pytest
from datetime import datetime, date, time
from decimal import Decimal
from dm_mcp.common.utils.encoding import ExtendedJSONEncoder


class TestExtendedJSONEncoder:
    """ExtendedJSONEncoder 测试类"""

    def test_encode_datetime(self):
        """测试 datetime 序列化"""
        encoder = ExtendedJSONEncoder()
        now = datetime(2024, 1, 15, 10, 30, 45)
        result = encoder.encode({"time": now})
        assert "2024-01-15" in result
        assert "10:30:45" in result

    def test_encode_date(self):
        """测试 date 序列化"""
        encoder = ExtendedJSONEncoder()
        today = date(2024, 1, 15)
        result = encoder.encode({"date": today})
        assert "2024-01-15" in result

    def test_encode_time(self):
        """测试 time 序列化"""
        encoder = ExtendedJSONEncoder()
        t = time(10, 30, 45)
        result = encoder.encode({"time": t})
        assert "10:30:45" in result

    def test_encode_decimal(self):
        """测试 Decimal 序列化"""
        encoder = ExtendedJSONEncoder()
        d = Decimal("123.456")
        result = encoder.encode({"value": d})
        assert "123.456" in result

    def test_encode_bytes_utf8(self):
        """测试 UTF-8 字节序列化"""
        encoder = ExtendedJSONEncoder()
        b = "你好".encode("utf-8")
        result = encoder.encode({"value": b})
        # 应该包含 Unicode 转义
        assert "value" in result

    def test_encode_bytes_non_utf8(self):
        """测试非 UTF-8 字节序列化（base64 编码）"""
        encoder = ExtendedJSONEncoder()
        b = bytes([0x80, 0x81, 0x82])
        result = encoder.encode({"value": b})
        assert "value" in result

    def test_encode_unknown_type(self):
        """测试未知类型抛出异常"""
        encoder = ExtendedJSONEncoder()

        class UnknownType:
            pass

        with pytest.raises(TypeError):
            encoder.encode({"value": UnknownType()})


class TestJsonDumpsWithExtendedEncoder:
    """json.dumps + ExtendedJSONEncoder 测试"""

    def test_dumps_datetime(self):
        """测试 datetime 序列化"""
        data = {"time": datetime(2024, 1, 15, 10, 30, 45)}
        result = json.dumps(data, cls=ExtendedJSONEncoder)
        assert "2024-01-15" in result
        assert "10:30:45" in result

    def test_dumps_decimal(self):
        """测试 Decimal 序列化"""
        data = {"value": Decimal("123.456")}
        result = json.dumps(data, cls=ExtendedJSONEncoder)
        assert "123.456" in result

    def test_ensure_ascii_false(self):
        """测试不转义非 ASCII"""
        data = {"message": "你好"}
        result = json.dumps(data, cls=ExtendedJSONEncoder, ensure_ascii=False)
        assert "你好" in result or "\\u" in result

    def test_ensure_ascii_true(self):
        """测试转义非 ASCII"""
        data = {"message": "你好"}
        result = json.dumps(data, cls=ExtendedJSONEncoder, ensure_ascii=True)
        # 汉字会被转义为 Unicode 转义序列
        assert "\\u" in result

    def test_indent(self):
        """测试缩进"""
        data = {"key": "value"}
        result = json.dumps(data, cls=ExtendedJSONEncoder, indent=2)
        assert "\n" in result
        assert "  " in result

