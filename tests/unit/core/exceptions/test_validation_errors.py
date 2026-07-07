"""验证相关异常测试"""

import pytest
from dm_mcp.core.exceptions import (
    DmMCPError,
    ValidationError,
    InvalidParameterError,
    MissingParameterError,
)


class TestValidationError:
    """ValidationError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = ValidationError()
        assert error.message == "验证失败"
        assert error.error_code == "VALIDATION_ERROR"
        assert error.status_code == 400

    def test_custom_message(self):
        """测试自定义消息"""
        error = ValidationError("Invalid input")
        assert error.message == "Invalid input"

    def test_with_errors_list(self):
        """测试带错误列表"""
        errors = [{"field": "name", "message": "Required"}]
        error = ValidationError(errors=errors)
        assert error.details["errors"] == errors

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(ValidationError, DmMCPError)


class TestInvalidParameterError:
    """InvalidParameterError 异常测试类"""

    def test_with_parameter(self):
        """测试带参数名"""
        error = InvalidParameterError("username")
        assert "username" in error.message
        assert error.error_code == "INVALID_PARAMETER"
        assert error.status_code == 400
        assert error.details["parameter"] == "username"

    def test_with_reason(self):
        """测试带原因"""
        error = InvalidParameterError("email", reason="invalid format")
        assert "email" in error.message
        assert "invalid format" in error.message

    def test_with_both_parameter_and_reason(self):
        """测试带参数名和原因"""
        error = InvalidParameterError("password", reason="too weak")
        assert error.details["parameter"] == "password"
        assert error.details.get("reason") is None  # reason 在消息中，不在 details

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(InvalidParameterError, ValidationError)


class TestMissingParameterError:
    """MissingParameterError 异常测试类"""

    def test_with_parameter(self):
        """测试带参数名"""
        error = MissingParameterError("email")
        assert "email" in error.message
        assert "缺少" in error.message
        assert error.error_code == "MISSING_PARAMETER"
        assert error.status_code == 400
        assert error.details["parameter"] == "email"

    def test_status_code_400(self):
        """测试状态码为 400"""
        error = MissingParameterError("test")
        assert error.status_code == 400

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(MissingParameterError, ValidationError)
