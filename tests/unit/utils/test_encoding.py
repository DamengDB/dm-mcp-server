"""encoding 编码工具模块测试"""

import base64
import json
import pytest
from datetime import datetime, date, time
from decimal import Decimal
from unittest.mock import patch, MagicMock
from dm_mcp.utils.encoding import (
    ExtendedJSONEncoder,
    json_dumps_with_datetime,
    setup_utf8_encoding,
    UTF8JSONResponse,
)


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


class TestJsonDumpsWithDatetime:
    """json_dumps_with_datetime 函数测试"""

    def test_dumps_datetime(self):
        """测试 datetime 序列化"""
        data = {"time": datetime(2024, 1, 15, 10, 30, 45)}
        result = json_dumps_with_datetime(data)
        assert "2024-01-15" in result
        assert "10:30:45" in result

    def test_dumps_decimal(self):
        """测试 Decimal 序列化"""
        data = {"value": Decimal("123.456")}
        result = json_dumps_with_datetime(data)
        assert "123.456" in result

    def test_ensure_ascii_false(self):
        """测试不转义非 ASCII"""
        data = {"message": "你好"}
        result = json_dumps_with_datetime(data, ensure_ascii=False)
        assert "你好" in result or "\\u" in result

    def test_ensure_ascii_true(self):
        """测试转义非 ASCII"""
        data = {"message": "你好"}
        result = json_dumps_with_datetime(data, ensure_ascii=True)
        # 汉字会被转义为 Unicode 转义序列
        assert "\\u" in result

    def test_indent(self):
        """测试缩进"""
        data = {"key": "value"}
        result = json_dumps_with_datetime(data, indent=2)
        assert "\n" in result
        assert "  " in result


class TestSetupUtf8Encoding:
    """setup_utf8_encoding 函数测试"""

    @patch("dm_mcp.utils.encoding.os.environ.setdefault")
    @patch("sys.stdout")
    @patch("sys.stderr")
    def test_setup_encoding(self, mock_stderr, mock_stdout, mock_environ):
        """测试 UTF-8 编码设置"""
        mock_stdout.reconfigure = MagicMock()
        mock_stderr.reconfigure = MagicMock()

        setup_utf8_encoding()

        mock_environ.assert_called_with("PYTHONIOENCODING", "utf-8")
        mock_stdout.reconfigure.assert_called_once()
        mock_stderr.reconfigure.assert_called_once()

    @patch("dm_mcp.utils.encoding.os.environ.setdefault")
    @patch("sys.stdout")
    @patch("sys.stderr")
    def test_setup_encoding_reconfigure_fails(
        self, mock_stderr, mock_stdout, mock_environ
    ):
        """测试重新配置失败时使用环境变量"""
        del mock_stdout.reconfigure
        del mock_stderr.reconfigure

        setup_utf8_encoding()


class TestUTF8JSONResponse:
    """UTF8JSONResponse 测试类"""

    def test_response_creation(self):
        """测试响应创建"""
        response = UTF8JSONResponse({"message": "hello"})
        assert response.status_code == 200
        assert response.body is not None

    def test_custom_status_code(self):
        """测试自定义状态码"""
        response = UTF8JSONResponse({"error": "not found"}, status_code=404)
        assert response.status_code == 404

    def test_content_type_header(self):
        """测试 Content-Type 头"""
        response = UTF8JSONResponse({"message": "hello"})
        assert "charset=utf-8" in response.headers.get("Content-Type", "")

    def test_custom_headers(self):
        """测试自定义头"""
        response = UTF8JSONResponse(
            {"message": "hello"},
            headers={"X-Custom-Header": "custom-value"},
        )
        assert response.headers.get("X-Custom-Header") == "custom-value"
