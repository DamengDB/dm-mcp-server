"""服务相关异常测试"""

import pytest
from dm_mcp.core.exceptions.base_error import DmMCPError
from dm_mcp.core.exceptions.service_errors import (
    ServiceError,
    ServiceNotFoundError,
    ServiceCircularDependencyError,
)


class TestServiceError:
    """ServiceError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = ServiceError("Service error")
        assert error.message == "Service error"
        assert error.error_code == "SERVICE_ERROR"
        assert error.status_code == 500

    def test_with_service_name(self):
        """测试带服务名称"""
        error = ServiceError("Service failed", service_name="my_service")
        assert error.details["service"] == "my_service"

    def test_custom_error_code(self):
        """测试自定义错误码"""
        error = ServiceError("error", error_code="CUSTOM_SERVICE_ERROR")
        assert error.error_code == "CUSTOM_SERVICE_ERROR"

    def test_custom_status_code(self):
        """测试自定义状态码"""
        error = ServiceError("error", status_code=503)
        assert error.status_code == 503

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(ServiceError, DmMCPError)


class TestServiceNotFoundError:
    """ServiceNotFoundError 异常测试类"""

    def test_with_service_name(self):
        """测试带服务名称"""
        error = ServiceNotFoundError("user_service")
        assert "user_service" in error.message
        assert error.error_code == "SERVICE_NOT_FOUND"
        assert error.status_code == 404
        assert error.details["service"] == "user_service"

    def test_status_code_404(self):
        """测试状态码为 404"""
        error = ServiceNotFoundError("test")
        assert error.status_code == 404

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(ServiceNotFoundError, ServiceError)


class TestServiceCircularDependencyError:
    """ServiceCircularDependencyError 异常测试类"""

    def test_with_service_name_only(self):
        """测试只带服务名称"""
        error = ServiceCircularDependencyError("service_a")
        assert "service_a" in error.message
        assert "circular dependency" in error.message.lower()
        assert error.error_code == "SERVICE_CIRCULAR_DEPENDENCY"
        assert error.status_code == 503
        assert error.details["service"] == "service_a"

    def test_with_path(self):
        """测试带路径"""
        error = ServiceCircularDependencyError(
            "service_a", path="service_b -> service_c -> service_a"
        )
        assert "path" in error.message.lower() or "service_b" in error.message

    def test_status_code_503(self):
        """测试状态码为 503"""
        error = ServiceCircularDependencyError("test")
        assert error.status_code == 503

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(ServiceCircularDependencyError, ServiceError)
