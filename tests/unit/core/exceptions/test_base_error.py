"""基础异常类测试"""

import pytest
from dm_mcp.core.exceptions import DmMCPError


class TestDmMCPError:
    """DmMCPError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = DmMCPError("test message")
        assert error.message == "test message"
        assert error.error_code == "DMCP_UNKNOWN_ERROR"
        assert error.status_code == 500
        assert error.details == {}

    def test_custom_values(self):
        """测试自定义值"""
        error = DmMCPError(
            message="custom",
            error_code="CUSTOM_ERROR",
            status_code=400,
            details={"key": "value"},
        )
        assert error.message == "custom"
        assert error.error_code == "CUSTOM_ERROR"
        assert error.status_code == 400
        assert error.details == {"key": "value"}

    def test_to_dict(self):
        """测试转换为字典"""
        error = DmMCPError("test", "ERR", 400, {"a": 1})
        d = error.to_dict()
        assert d["error"] == "ERR"
        assert d["message"] == "test"
        assert d["status_code"] == 400
        assert d["details"]["a"] == 1

    def test_inheritance(self):
        """测试异常继承"""
        assert issubclass(DmMCPError, Exception)

    def test_str_representation(self):
        """测试字符串表示"""
        error = DmMCPError("test message")
        assert str(error) == "test message"

    def test_details_default_to_empty_dict(self):
        """测试 details 默认值为空字典"""
        error = DmMCPError("test")
        assert error.details == {}
        assert isinstance(error.details, dict)

    def test_message_in_exception_args(self):
        """测试消息在异常参数中"""
        error = DmMCPError("test message")
        assert "test message" in str(error)
