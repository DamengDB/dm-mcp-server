"""MCP Service 集成测试

测试 MCP 服务的完整工作流程，包括 Provider 注册、工具调用、资源访问等。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import AnyUrl


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServiceWorkflow:
    """MCP 服务工作流测试类"""

    @pytest_asyncio.fixture
    async def mcp_service_instance(self, mock_settings):
        """创建 MCP 服务实例"""
        from tests.integration.conftest import make_mcp_service

        yield make_mcp_service(mock_settings.server)

    @pytest_asyncio.fixture
    def mock_provider(self):
        """创建 Mock Provider（tools_map / _static_resources / prompts_map 与合并视图一致）"""
        provider = MagicMock()
        provider.name = "test_provider"

        mock_tool = MagicMock()
        mock_tool.name = "calculate_sum"
        mock_tool.description = "Calculate sum of two numbers"
        mock_tool_def = MagicMock()
        mock_tool_def.short_description = "Calculate sum of two numbers"
        mock_tool_def.long_description = "Calculate sum of two numbers"
        mock_tool_def.apply_metadata_override.return_value.to_tool.return_value = (
            mock_tool
        )
        provider.list_tools.return_value = [mock_tool]

        mock_resource = MagicMock()
        mock_resource.uri = "test://resource1"
        mock_resource_def = MagicMock()
        mock_resource_def.name = "resource1"
        mock_resource_def.uri = "test://resource1"
        mock_resource_def.apply_metadata_override.return_value.to_resource.return_value = (
            mock_resource
        )
        provider.list_resources.return_value = [mock_resource]

        mock_template = MagicMock()
        mock_template.uriTemplate = "users://{user_id}/profile"
        provider.list_resource_templates.return_value = [mock_template]

        mock_prompt_def = MagicMock()
        mock_prompt_def.name = "greeting"
        mock_prompt_def.short_description = "greeting"
        mock_prompt_def.long_description = "greeting"
        mock_prompt_def.arguments = []
        provider.list_prompts.return_value = [mock_prompt_def]

        provider.mcp = MagicMock()
        provider.mcp.tools_map = {"calculate_sum": mock_tool_def}
        provider.mcp._static_resources = {"test://resource1": mock_resource_def}
        provider.mcp._template_resources = []
        provider.mcp.prompts_map = {"greeting": mock_prompt_def}

        return provider

    async def test_mcp_service_init(self, mcp_service_instance):
        """测试 MCP 服务初始化"""
        assert mcp_service_instance is not None
        assert mcp_service_instance.sdk_server is not None
        assert len(mcp_service_instance.providers) == 0

    async def test_add_provider(self, mcp_service_instance, mock_provider):
        """测试添加 Provider"""
        mcp_service_instance.add_mcp_provider(mock_provider)
        assert len(mcp_service_instance.providers) == 1

    async def test_list_tools_with_provider(self, mcp_service_instance, mock_provider):
        """测试列出工具（带 Provider）"""
        mcp_service_instance.add_mcp_provider(mock_provider)

        tools = await mcp_service_instance.list_tools()
        assert len(tools) >= 1
        assert any(t.name == "calculate_sum" for t in tools)

    async def test_list_resources_with_provider(
        self, mcp_service_instance, mock_provider
    ):
        """测试列出资源（带 Provider）"""
        mcp_service_instance.add_mcp_provider(mock_provider)

        resources = await mcp_service_instance.list_resources()
        assert len(resources) >= 1

    async def test_list_prompts_with_provider(
        self, mcp_service_instance, mock_provider
    ):
        """测试列出提示（带 Provider）"""
        mcp_service_instance.add_mcp_provider(mock_provider)

        prompts = await mcp_service_instance.list_prompts()
        assert len(prompts) >= 1

    async def test_call_tool_not_found(self, mcp_service_instance):
        """测试调用不存在的工具"""
        result = await mcp_service_instance.call_tool("nonexistent", {})

        assert "error" in result
        assert "TOOL_NOT_FOUND" in result

    async def test_call_tool_success(self, mcp_service_instance, mock_provider):
        """测试成功调用工具"""
        mock_provider.call_tool = AsyncMock(return_value={"sum": 30})
        mcp_service_instance.add_mcp_provider(mock_provider)

        result = await mcp_service_instance.call_tool(
            "calculate_sum", {"a": 10, "b": 20}
        )

        assert "sum" in result or "success" in result

    async def test_read_resource_not_found(self, mcp_service_instance):
        """测试读取不存在的资源"""
        uri = AnyUrl("test://nonexistent")
        result = await mcp_service_instance.read_resource(uri)

        assert "error" in result
        assert "RESOURCE_NOT_FOUND" in result

    async def test_read_resource_success(self, mcp_service_instance, mock_provider):
        """测试成功读取资源"""
        mock_provider.read_resource = AsyncMock(return_value="resource content")
        mcp_service_instance.add_mcp_provider(mock_provider)

        uri = AnyUrl("test://resource1")
        result = await mcp_service_instance.read_resource(uri)

        assert result == "resource content"

    async def test_get_prompt_not_found(self, mcp_service_instance):
        """测试获取不存在的提示"""
        result = await mcp_service_instance.get_prompt("nonexistent")

        assert result is not None

    async def test_get_prompt_success(self, mcp_service_instance, mock_provider):
        """测试成功获取提示"""
        from mcp.server.stdio import types

        mock_result = types.GetPromptResult(
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text="Hello!"),
                )
            ]
        )
        mock_provider.get_prompt = AsyncMock(return_value=mock_result)
        mcp_service_instance.add_mcp_provider(mock_provider)

        result = await mcp_service_instance.get_prompt("greeting")

        assert result is not None


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPProviderRegistration:
    """MCP Provider 注册测试类"""

    async def test_multiple_providers_registration(self, mock_settings):
        """测试多个 Provider 注册"""
        from tests.integration.conftest import make_mcp_service

        service = make_mcp_service(mock_settings.server)

        # 创建多个 Provider
        provider1 = MagicMock()
        provider1.name = "provider1"
        provider1.list_tools.return_value = [MagicMock(name="tool1")]
        provider1.list_resources.return_value = []
        provider1.list_resource_templates.return_value = []
        provider1.list_prompts.return_value = []

        provider2 = MagicMock()
        provider2.name = "provider2"
        provider2.list_tools.return_value = [MagicMock(name="tool2")]
        provider2.list_resources.return_value = []
        provider2.list_resource_templates.return_value = []
        provider2.list_prompts.return_value = []

        # 批量添加
        service.add_mcp_providers([provider1, provider2])

        assert len(service.providers) == 2


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPResourceMapping:
    """MCP 资源映射测试类"""

    async def test_resource_uri_mapping(self, mock_settings):
        """测试资源 URI 映射"""
        from tests.integration.conftest import make_mcp_service

        service = make_mcp_service(mock_settings.server)

        # 创建带资源的 Provider
        provider = MagicMock()
        resource = MagicMock()
        resource.uri = "db://primary/tables"
        provider.list_resources.return_value = [resource]
        provider.list_resource_templates.return_value = []

        service.add_mcp_provider(provider)

        # 验证资源映射
        resource_map = service._providers_resource_map
        assert "db://primary/tables" in resource_map

    async def test_template_uri_mapping(self, mock_settings):
        """测试模板 URI 映射"""
        from tests.integration.conftest import make_mcp_service

        service = make_mcp_service(mock_settings.server)

        # 创建带模板的 Provider
        provider = MagicMock()
        template = MagicMock()
        template.uriTemplate = "users://{user_id}/profile"
        provider.list_resources.return_value = []
        provider.list_resource_templates.return_value = [template]

        service.add_mcp_provider(provider)

        # 验证模板映射
        resource_map = service._providers_resource_map
        assert "users://{user_id}/profile" in resource_map


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPToolMapping:
    """MCP 工具映射测试类"""

    async def test_tool_provider_mapping(self, mock_settings):
        """测试工具到 Provider 的映射"""
        from tests.integration.conftest import make_mcp_service

        service = make_mcp_service(mock_settings.server)

        # 创建带工具的 Provider
        provider = MagicMock()
        tool = MagicMock()
        tool.name = "execute_query"
        tool.description = "Execute a database query"
        provider.list_tools.return_value = [tool]
        provider.list_resources.return_value = []
        provider.list_resource_templates.return_value = []
        provider.list_prompts.return_value = []
        provider.mcp = MagicMock()
        provider.mcp.tools_map = {"execute_query": tool}

        service.add_mcp_provider(provider)

        # 验证工具映射
        tool_map = service._providers_tool_map
        assert "execute_query" in tool_map


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPErrorHandlingIntegration:
    """MCP 错误处理集成测试类"""

    async def test_tool_execution_error(self, mock_settings):
        """测试工具执行错误"""
        from tests.integration.conftest import make_mcp_service

        service = make_mcp_service(mock_settings.server)

        # 创建会抛出异常的 Provider
        provider = MagicMock()
        tool = MagicMock()
        tool.name = "error_tool"
        provider.list_tools.return_value = [tool]
        provider.call_tool = AsyncMock(side_effect=RuntimeError("Database error"))
        provider.list_resources.return_value = []
        provider.list_resource_templates.return_value = []
        provider.list_prompts.return_value = []
        provider.mcp = MagicMock()
        provider.mcp.tools_map = {"error_tool": tool}

        service.add_mcp_provider(provider)

        result = await service.call_tool("error_tool", {})

        assert "error" in result

    async def test_resource_read_error(self, mock_settings):
        """测试资源读取错误"""
        from tests.integration.conftest import make_mcp_service

        service = make_mcp_service(mock_settings.server)

        # 创建会抛出异常的 Provider
        provider = MagicMock()
        resource = MagicMock()
        resource.uri = "test://error"
        provider.list_resources.return_value = [resource]
        provider.read_resource = AsyncMock(
            side_effect=RuntimeError("Resource not found")
        )
        provider.list_resource_templates.return_value = []

        service.add_mcp_provider(provider)

        uri = AnyUrl("test://error")
        result = await service.read_resource(uri)

        assert "error" in result
