"""传输层相关异常测试"""

import pytest
from dm_mcp.core.exceptions import (
    DmMCPError,
    TransportError,
    TransportConfigError,
)


class TestTransportError:
    """TransportError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = TransportError("Transport error")
        assert error.message == "Transport error"
        assert error.error_code == "TRANSPORT_ERROR"
        assert error.status_code == 500

    def test_custom_message(self):
        """测试自定义消息"""
        error = TransportError("Connection reset")
        assert error.message == "Connection reset"

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(TransportError, DmMCPError)


class TestTransportConfigError:
    """TransportConfigError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = TransportConfigError("Config error")
        assert error.message == "Config error"
        assert error.error_code == "TRANSPORT_CONFIG_ERROR"
        assert error.status_code == 500

    def test_custom_message(self):
        """测试自定义消息"""
        error = TransportConfigError("Invalid port")
        assert error.message == "Invalid port"

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(TransportConfigError, TransportError)
