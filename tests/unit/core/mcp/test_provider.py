"""MCP Provider 单元测试

测试 BaseMCPProvider 基类的功能。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from dm_mcp.core.mcp.provider import BaseMCPProvider
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext


class MockMCPProvider(BaseMCPProvider):
    """Mock MCP Provider 用于测试"""

    pass


class TestBaseMCPProvider:
    """BaseMCPProvider 测试类"""

    def test_provider_initialization(self):
        """测试 Provider 初始化"""
        provider = MockMCPProvider()

        assert provider is not None
        assert provider.mcp is not None

    def test_auth_property_with_context(self):
        """测试 auth 属性（有上下文）"""
        provider = MockMCPProvider()
        auth_context = AuthContext(
            user_id="testuser", auth_type="token", token="test_token"
        )

        with AuthContext.as_current(auth_context):
            auth = provider.auth
            assert auth is not None
            assert auth.user_id == "testuser"
            assert auth.auth_type == "token"

    def test_auth_property_without_context(self):
        """测试 auth 属性（无上下文）"""
        provider = MockMCPProvider()

        with pytest.raises(ValueError, match="未设置认证上下文"):
            _ = provider.auth

    def test_metrics_property(self):
        """测试 metrics 属性"""
        provider = MockMCPProvider()

        metrics = provider.metrics
        assert metrics is not None
        assert isinstance(metrics, MetricsContext)

    @pytest.mark.asyncio
    async def test_list_prompts(self):
        """测试列出提示词"""
        provider = MockMCPProvider()

        # Mock MCPRouter 的 list_prompts 方法
        provider.mcp.list_prompts = MagicMock(return_value=[])

        prompts = provider.list_prompts()

        assert isinstance(prompts, list)
        provider.mcp.list_prompts.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_prompt(self):
        """测试获取提示词"""
        provider = MockMCPProvider()

        mock_result = MagicMock()
        provider.mcp.get_prompt = AsyncMock(return_value=mock_result)

        result = await provider.get_prompt("test_prompt", {"arg1": "value1"})

        assert result == mock_result
        provider.mcp.get_prompt.assert_called_once_with(
            "test_prompt", {"arg1": "value1"}
        )

    @pytest.mark.asyncio
    async def test_get_prompt_without_arguments(self):
        """测试获取提示词（无参数）"""
        provider = MockMCPProvider()

        mock_result = MagicMock()
        provider.mcp.get_prompt = AsyncMock(return_value=mock_result)

        result = await provider.get_prompt("test_prompt")

        assert result == mock_result
        provider.mcp.get_prompt.assert_called_once_with("test_prompt", None)

    def test_list_resources(self):
        """测试列出静态资源"""
        provider = MockMCPProvider()

        provider.mcp.list_resources = MagicMock(return_value=[])

        resources = provider.list_resources()

        assert isinstance(resources, list)
        provider.mcp.list_resources.assert_called_once()

    def test_list_resource_templates(self):
        """测试列出资源模板"""
        provider = MockMCPProvider()

        provider.mcp.list_resource_templates = MagicMock(return_value=[])

        templates = provider.list_resource_templates()

        assert isinstance(templates, list)
        provider.mcp.list_resource_templates.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_resource(self):
        """测试读取资源"""
        provider = MockMCPProvider()

        provider.mcp.read_resource = AsyncMock(return_value="resource content")

        result = await provider.read_resource("resource://test")

        assert result == "resource content"
        provider.mcp.read_resource.assert_called_once_with("resource://test")

    def test_list_tools(self):
        """测试列出工具"""
        provider = MockMCPProvider()

        provider.mcp.list_tools = MagicMock(return_value=[])

        tools = provider.list_tools()

        assert isinstance(tools, list)
        provider.mcp.list_tools.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool(self):
        """测试调用工具"""
        provider = MockMCPProvider()

        provider.mcp.call_tool = AsyncMock(return_value={"result": "success"})

        result = await provider.call_tool("test_tool", {"param1": "value1"})

        assert result == {"result": "success"}
        provider.mcp.call_tool.assert_called_once_with(
            "test_tool", {"param1": "value1"}
        )
