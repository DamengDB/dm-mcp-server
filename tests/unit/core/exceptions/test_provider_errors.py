"""Provider相关异常测试"""

import pytest
from dm_mcp.core.exceptions import (
    DmMCPError,
    MCPProviderError,
    MCPProviderLoadError,
    MCPProviderNotFoundError,
    MCPProviderDependencyError,
)


class TestMCPProviderError:
    """MCPProviderError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = MCPProviderError("Provider error")
        assert error.message == "Provider error"
        assert error.error_code == "PROVIDER_ERROR"
        assert error.status_code == 500

    def test_with_provider_name(self):
        """测试带 provider 名称"""
        error = MCPProviderError("Load failed", provider_name="demo_provider")
        assert error.details["provider_name"] == "demo_provider"

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(MCPProviderError, DmMCPError)


class TestMCPProviderLoadError:
    """MCPProviderLoadError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = MCPProviderLoadError("Load failed")
        assert error.message == "Load failed"
        assert error.error_code == "PROVIDER_LOAD_ERROR"
        assert error.status_code == 500

    def test_with_provider_name(self):
        """测试带 provider 名称"""
        error = MCPProviderLoadError("Init failed", provider_name="my_provider")
        assert error.details["provider_name"] == "my_provider"

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(MCPProviderLoadError, MCPProviderError)


class TestMCPProviderNotFoundError:
    """MCPProviderNotFoundError 异常测试类"""

    def test_with_provider_name(self):
        """测试带 provider 名称"""
        error = MCPProviderNotFoundError("demo_provider")
        assert "demo_provider" in error.message
        assert error.error_code == "PROVIDER_NOT_FOUND"
        assert error.status_code == 404
        assert error.details["provider_name"] == "demo_provider"

    def test_status_code_404(self):
        """测试状态码为 404"""
        error = MCPProviderNotFoundError("test")
        assert error.status_code == 404

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(MCPProviderNotFoundError, MCPProviderError)


class TestMCPProviderDependencyError:
    """MCPProviderDependencyError 异常测试类"""

    def test_with_dependencies(self):
        """测试带依赖列表"""
        error = MCPProviderDependencyError("my_provider", ["dep_a", "dep_b"])
        assert "my_provider" in error.message
        assert error.error_code == "PROVIDER_DEPENDENCY_ERROR"
        assert error.details["missing_dependencies"] == ["dep_a", "dep_b"]

    def test_single_dependency(self):
        """测试单依赖"""
        error = MCPProviderDependencyError("provider", ["jwt_service"])
        assert error.details["missing_dependencies"] == ["jwt_service"]

    def test_provider_name_attribute(self):
        """测试 provider_name 属性（向后兼容）"""
        error = MCPProviderDependencyError("test_provider", ["dep1"])
        assert error.provider_name == "test_provider"

    def test_missing_dependencies_attribute(self):
        """测试 missing_dependencies 属性（向后兼容）"""
        error = MCPProviderDependencyError("test_provider", ["a", "b", "c"])
        assert error.missing_dependencies == ["a", "b", "c"]

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(MCPProviderDependencyError, MCPProviderError)
