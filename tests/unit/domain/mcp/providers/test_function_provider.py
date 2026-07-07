"""Function Provider测试模块"""

import pytest

from dm_mcp.domain.mcp.providers.function import FunctionMCPProvider


class TestFunctionMCPProvider:
    """Function Provider测试类"""

    @pytest.fixture
    def provider(self):
        """创建Function Provider实例"""
        return FunctionMCPProvider()

    def test_init(self, provider):
        """测试初始化"""
        assert provider is not None
        assert hasattr(provider, "mcp")

    def test_mcp_router_exists(self, provider):
        """测试MCP router存在"""
        assert provider.mcp is not None

    def test_provider_inherits_base(self, provider):
        """测试Provider继承自BaseMCPProvider"""
        from dm_mcp.core.mcp import BaseMCPProvider

        assert isinstance(provider, BaseMCPProvider)

    def test_provider_can_register_tools(self, provider):
        """测试Provider可以注册工具"""
        # Function Provider主要用于通过装饰器注册工具
        # 这里我们验证router存在，可以用于注册
        assert hasattr(provider.mcp, "tool")
        assert callable(provider.mcp.tool)

    def test_provider_can_register_resources(self, provider):
        """测试Provider可以注册资源"""
        assert hasattr(provider.mcp, "resource")
        assert callable(provider.mcp.resource)

    def test_provider_can_register_prompts(self, provider):
        """测试Provider可以注册提示词"""
        assert hasattr(provider.mcp, "prompt")
        assert callable(provider.mcp.prompt)
