"""使用 Mock 模拟 MCP SDK 回调执行的测试

这个测试文件直接模拟 MCP Service 的回调处理器行为，
以覆盖异常处理分支。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import AnyUrl


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPDKCallbackMockExecution:
    """使用 Mock 模拟 MCP SDK 回调执行"""

    @pytest_asyncio.fixture
    async def mcp_service_instance(self, mock_settings):
        """创建 MCP 服务实例"""
        from dm_mcp.services.mcp_service import MCPService

        mock_metrics = MagicMock()
        mock_metrics.startup = AsyncMock()
        mock_metrics.shutdown = AsyncMock()

        mock_datasource = MagicMock()
        mock_datasource.startup = AsyncMock()
        mock_datasource.shutdown = AsyncMock()

        mock_logging = MagicMock()
        mock_logging.startup = AsyncMock()
        mock_logging.shutdown = AsyncMock()

        service = MCPService(
            mock_settings.server,
            mock_metrics,
            mock_datasource,
            mock_logging,
        )

        yield service

    async def test_list_resources_with_exception_in_middleware(
        self, mcp_service_instance, mock_mcp_provider
    ):
        """测试资源列表中间件异常处理 (行501-503)"""

        # 模拟中间件抛出异常
        async def raise_exception(*args, **kwargs):
            raise RuntimeError("Simulated list resources error")

        # 替换 middleaware_stack.on_list_resources
        original_on_list_resources = (
            mcp_service_instance.middleaware_stack.on_list_resources
        )
        mcp_service_instance.middleaware_stack.on_list_resources = raise_exception

        try:
            # 调用 list_resources（模拟回调中的逻辑）
            result = await mcp_service_instance.list_resources()
            # 应该返回空列表，因为异常被捕获了
            assert result == []
        finally:
            # 恢复原始方法
            mcp_service_instance.middleaware_stack.on_list_resources = (
                original_on_list_resources
            )

    async def test_list_resource_templates_with_exception(
        self, mcp_service_instance, mock_mcp_provider
    ):
        """测试资源模板列表异常处理 (行517-519)"""

        async def raise_exception(*args, **kwargs):
            raise RuntimeError("Simulated list templates error")

        original = mcp_service_instance.middleaware_stack.on_list_resource_templates
        mcp_service_instance.middleaware_stack.on_list_resource_templates = (
            raise_exception
        )

        try:
            result = await mcp_service_instance.list_resource_templates()
            assert result == []
        finally:
            mcp_service_instance.middleaware_stack.on_list_resource_templates = original

    async def test_read_resource_with_exception(
        self, mcp_service_instance, mock_mcp_provider
    ):
        """测试读取资源异常处理 (行531-537)

        由于 middleaware 的替换在 read_resource 中不会直接生效，
        我们测试直接的异常处理路径。
        """
        # 直接向 provider 添加会抛出异常的 read_resource
        provider = MagicMock()
        provider.read_resource = AsyncMock(side_effect=RuntimeError("DB Error"))

        mock_resource = MagicMock()
        mock_resource.uri = "test://error"
        provider.list_resources.return_value = [mock_resource]
        provider.list_resource_templates.return_value = []

        mcp_service_instance.add_mcp_provider(provider)

        uri = AnyUrl("test://error")
        result = await mcp_service_instance.read_resource(uri)

        # 验证异常被捕获并返回错误 JSON
        assert "error" in result

    async def test_list_tools_with_exception(
        self, mcp_service_instance, mock_mcp_provider
    ):
        """测试工具列表异常处理 (行546-548)"""

        async def raise_exception(*args, **kwargs):
            raise RuntimeError("Simulated list tools error")

        original = mcp_service_instance.middleaware_stack.on_list_tools
        mcp_service_instance.middleaware_stack.on_list_tools = raise_exception

        try:
            result = await mcp_service_instance.list_tools()
            assert result == []
        finally:
            mcp_service_instance.middleaware_stack.on_list_tools = original

    async def test_call_tool_with_exception(
        self, mcp_service_instance, mock_mcp_provider
    ):
        """测试工具调用异常处理 (行561-573)"""
        # 添加一个会抛出异常的 provider
        tool = MagicMock()
        tool.name = "error_tool"

        provider = MagicMock()
        provider.list_tools.return_value = [tool]
        provider.call_tool = AsyncMock(side_effect=RuntimeError("Tool execution error"))
        provider.list_resources.return_value = []
        provider.list_resource_templates.return_value = []
        provider.list_prompts.return_value = []
        provider.mcp = MagicMock()
        provider.mcp.tools_map = {"error_tool": tool}

        mcp_service_instance.providers.append(provider)

        # 清除缓存
        for attr in ["_tools", "_providers_tool_map"]:
            if hasattr(mcp_service_instance, attr):
                try:
                    delattr(mcp_service_instance, attr)
                except AttributeError:
                    pass

        result = await mcp_service_instance.call_tool("error_tool", {})

        # 应该返回错误 JSON
        assert "error" in result

    async def test_list_prompts_with_exception(
        self, mcp_service_instance, mock_mcp_provider
    ):
        """测试提示列表异常处理 (行585-587)"""

        async def raise_exception(*args, **kwargs):
            raise RuntimeError("Simulated list prompts error")

        original = mcp_service_instance.middleaware_stack.on_list_prompts
        mcp_service_instance.middleaware_stack.on_list_prompts = raise_exception

        try:
            result = await mcp_service_instance.list_prompts()
            assert result == []
        finally:
            mcp_service_instance.middleaware_stack.on_list_prompts = original

    async def test_get_prompt_with_exception(
        self, mcp_service_instance, mock_mcp_provider
    ):
        """测试获取提示异常处理 (行601-612)"""
        # 添加一个会抛出异常的 provider
        prompt = MagicMock()
        prompt.name = "error_prompt"

        provider = MagicMock()
        provider.list_prompts.return_value = [prompt]
        provider.get_prompt = AsyncMock(side_effect=RuntimeError("Prompt error"))
        provider.list_tools.return_value = []
        provider.list_resources.return_value = []
        provider.list_resource_templates.return_value = []
        provider.mcp = MagicMock()
        provider.mcp.prompts_map = {"error_prompt": prompt}

        mcp_service_instance.providers.append(provider)

        # 清除缓存
        for attr in ["_prompts", "_providers_prompt_map"]:
            if hasattr(mcp_service_instance, attr):
                try:
                    delattr(mcp_service_instance, attr)
                except AttributeError:
                    pass

        result = await mcp_service_instance.get_prompt("error_prompt", {})

        # 应该返回错误结果
        assert result is not None
        assert hasattr(result, "messages")


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServiceExceptionHandlingDirect:
    """直接测试 MCP Service 方法的异常处理"""

    async def test_read_resource_exception_returns_json_error(self, mock_settings):
        """测试 read_resource 异常返回 JSON 错误"""
        from dm_mcp.services.mcp_service import MCPService

        mock_metrics = MagicMock()
        mock_metrics.startup = AsyncMock()
        mock_metrics.shutdown = AsyncMock()

        mock_datasource = MagicMock()
        mock_datasource.startup = AsyncMock()
        mock_datasource.shutdown = AsyncMock()

        mock_logging = MagicMock()
        mock_logging.startup = AsyncMock()
        mock_logging.shutdown = AsyncMock()

        service = MCPService(
            mock_settings.server,
            mock_metrics,
            mock_datasource,
            mock_logging,
        )

        # 创建一个会抛出异常的 provider
        provider = MagicMock()

        # 设置 read_resource 抛出异常
        provider.read_resource = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        mock_resource = MagicMock()
        mock_resource.uri = "test://error"
        provider.list_resources.return_value = [mock_resource]
        provider.list_resource_templates.return_value = []

        service.add_mcp_provider(provider)

        # 调用 read_resource
        uri = AnyUrl("test://error")
        result = await service.read_resource(uri)

        # 验证返回错误 JSON
        assert "error" in result
        assert "RESOURCE_READ_ERROR" in result

    async def test_get_prompt_exception_returns_error_result(self, mock_settings):
        """测试 get_prompt 异常返回错误结果"""
        from dm_mcp.services.mcp_service import MCPService

        mock_metrics = MagicMock()
        mock_metrics.startup = AsyncMock()
        mock_metrics.shutdown = AsyncMock()

        mock_datasource = MagicMock()
        mock_datasource.startup = AsyncMock()
        mock_datasource.shutdown = AsyncMock()

        mock_logging = MagicMock()
        mock_logging.startup = AsyncMock()
        mock_logging.shutdown = AsyncMock()

        service = MCPService(
            mock_settings.server,
            mock_metrics,
            mock_datasource,
            mock_logging,
        )

        # 创建一个会抛出异常的 provider
        provider = MagicMock()
        provider.get_prompt = AsyncMock(side_effect=Exception("Prompt error"))

        mock_prompt = MagicMock()
        mock_prompt.name = "error_prompt"
        provider.list_prompts.return_value = [mock_prompt]
        provider.list_tools.return_value = []
        provider.list_resources.return_value = []
        provider.list_resource_templates.return_value = []

        service.add_mcp_provider(provider)

        # 清除缓存
        if hasattr(service, "_prompts"):
            del service._prompts
        if hasattr(service, "_providers_prompt_map"):
            del service._providers_prompt_map

        # 调用 get_prompt
        result = await service.get_prompt("error_prompt")

        # 验证返回错误结果
        assert result is not None
        assert hasattr(result, "messages")
        # 检查是否包含错误信息
        text_content = result.messages[0].content
        assert "error" in text_content.text or "PROMPT_GET_ERROR" in text_content.text
