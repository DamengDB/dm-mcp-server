"""MCP注册表测试模块"""

from unittest.mock import MagicMock

import pytest

from dm_mcp.core.mcp.router import MCPRouter
from dm_mcp.core.service import ServiceRegistry
from dm_mcp.domain.mcp.registry import MCPFunctionRegistry


class TestMCPFunctionRegistry:
    """MCP函数注册表测试类"""

    @pytest.fixture
    def mock_router(self):
        """创建Mock路由器"""
        router = MagicMock(spec=MCPRouter)
        router.tool = MagicMock(return_value=lambda f: f)
        router.resource = MagicMock(return_value=lambda f: f)
        router.prompt = MagicMock(return_value=lambda f: f)
        return router

    @pytest.fixture
    def mock_registry(self):
        """创建Mock服务注册表"""
        registry = MagicMock(spec=ServiceRegistry)
        registry.get_service = MagicMock(return_value=MagicMock())
        return registry

    @pytest.fixture
    def mcp_registry(self, mock_router, mock_registry):
        """创建MCP注册表"""
        return MCPFunctionRegistry(router=mock_router, registry=mock_registry)

    def test_init(self, mcp_registry, mock_router, mock_registry):
        """测试初始化"""
        assert mcp_registry.router == mock_router
        assert mcp_registry._registry == mock_registry

    def test_router_property(self, mcp_registry, mock_router):
        """测试路由器属性"""
        assert mcp_registry.router == mock_router

    def test_tool_decorator(self, mcp_registry, mock_router):
        """测试工具装饰器"""

        @mcp_registry.tool(name="test_tool", description="测试工具")
        def test_function():
            pass

        mock_router.tool.assert_called_once_with(
            name="test_tool", description="测试工具"
        )

    def test_resource_decorator(self, mcp_registry, mock_router):
        """测试资源装饰器"""

        @mcp_registry.resource(uri="test://resource")
        def test_resource():
            pass

        mock_router.resource.assert_called_once_with(uri="test://resource")

    def test_prompt_decorator(self, mcp_registry, mock_router):
        """测试提示词装饰器"""

        @mcp_registry.prompt(name="test_prompt")
        def test_prompt():
            pass

        mock_router.prompt.assert_called_once_with(name="test_prompt")

    def test_get_service(self, mcp_registry, mock_registry):
        """测试获取服务"""
        service = mcp_registry.get_service("test_service")

        mock_registry.get_service.assert_called_once_with("test_service")
        assert service is not None

    def test_auth_property(self, mcp_registry):
        """测试认证上下文属性"""
        # 这个属性依赖于AuthContext.get()，如果没有上下文会抛出异常
        # 使用getattr测试属性存在，但不访问它
        # 因为@property装饰器，hasattr会尝试访问属性，导致异常
        # 所以我们需要直接测试属性访问时的异常
        with pytest.raises(ValueError, match="未设置认证上下文"):
            _ = mcp_registry.auth

        # 验证属性确实存在（通过检查是否有getter方法）
        assert hasattr(type(mcp_registry), "auth")
        assert isinstance(type(mcp_registry).auth, property)

    def test_metrics_property(self, mcp_registry):
        """测试指标上下文属性"""
        # 这个属性依赖于MetricsContext.get()，主要测试属性存在
        assert hasattr(mcp_registry, "metrics")

    def test_tool_with_requires_token_auth(self, mcp_registry, mock_router):
        """测试需要Token认证的工具"""

        @mcp_registry.tool(requires_token_auth=True)
        def test_function():
            pass

        mock_router.tool.assert_called_once_with(requires_token_auth=True)

    def test_tool_with_exclude_args(self, mcp_registry, mock_router):
        """测试排除参数的工具"""

        @mcp_registry.tool(exclude_args=["internal"])
        def test_function(internal: str, public: str):
            pass

        mock_router.tool.assert_called_once_with(exclude_args=["internal"])
