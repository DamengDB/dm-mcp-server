"""MCP Router 单元测试

测试 MCPRouter 的功能，包括工具、资源、提示词的注册和调用。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic.networks import AnyUrl

from dm_mcp.core.mcp.router import MCPRouter


class TestMCPRouter:
    """MCPRouter 测试类"""

    def test_router_initialization(self):
        """测试路由器初始化"""
        router = MCPRouter()

        assert router.tools == []
        assert router.tools_map == {}
        assert router._static_resources == {}
        assert router._template_resources == []
        assert router.prompts == []
        assert router.prompts_map == {}

    # ==================== Tool 测试 ====================

    @pytest.mark.asyncio
    async def test_register_tool_with_decorator(self):
        """测试使用装饰器注册工具"""
        router = MCPRouter()

        @router.tool()
        async def test_tool(x: int, y: str = "default") -> dict:
            """Test tool"""
            return {"result": f"{x}:{y}"}

        assert len(router.tools) == 1
        assert "test_tool" in router.tools_map
        assert router.tools[0].name == "test_tool"

    @pytest.mark.asyncio
    async def test_register_tool_with_custom_name(self):
        """测试使用自定义名称注册工具"""
        router = MCPRouter()

        @router.tool(name="custom_tool_name")
        async def test_tool(x: int) -> dict:
            """Test tool"""
            return {"result": x}

        assert router.tools[0].name == "custom_tool_name"
        assert "custom_tool_name" in router.tools_map

    @pytest.mark.asyncio
    async def test_register_tool_with_requires_token_auth(self):
        """测试注册需要 Token 认证的工具"""
        router = MCPRouter()

        @router.tool(requires_token_auth=True)
        async def protected_tool(x: int) -> dict:
            """Protected tool"""
            return {"result": x}

        tool_def = router.tools_map["protected_tool"]
        assert tool_def.requires_token_auth is True

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """测试列出工具"""
        router = MCPRouter()

        @router.tool()
        async def tool1(x: int) -> dict:
            """Tool 1"""
            return {"result": x}

        @router.tool()
        async def tool2(y: str) -> dict:
            """Tool 2"""
            return {"result": y}

        tools = router.list_tools()

        assert len(tools) == 2
        tool_names = [t.name for t in tools]
        assert "tool1" in tool_names
        assert "tool2" in tool_names

    @pytest.mark.asyncio
    async def test_call_tool(self):
        """测试调用工具"""
        router = MCPRouter()

        @router.tool()
        async def test_tool(x: int, y: str = "default") -> dict:
            """Test tool"""
            return {"result": f"{x}:{y}"}

        result = await router.call_tool("test_tool", {"x": 123, "y": "test"})

        assert result == {"result": "123:test"}

    @pytest.mark.asyncio
    async def test_call_tool_not_found(self):
        """测试调用不存在的工具"""
        router = MCPRouter()

        with pytest.raises(ValueError, match="Unknown tool"):
            await router.call_tool("nonexistent_tool", {})

    # ==================== Resource 测试 ====================

    @pytest.mark.asyncio
    async def test_register_static_resource(self):
        """测试注册静态资源"""
        router = MCPRouter()

        @router.resource("resource://static")
        async def get_static_resource() -> str:
            """Static resource"""
            return "static content"

        assert "resource://static" in router._static_resources
        assert len(router._template_resources) == 0

    @pytest.mark.asyncio
    async def test_register_template_resource(self):
        """测试注册模板资源"""
        router = MCPRouter()

        @router.resource("users://{user_id}/profile")
        async def get_user_profile(user_id: str) -> str:
            """User profile"""
            return f"Profile for {user_id}"

        assert len(router._template_resources) == 1
        assert router._template_resources[0].uri == "users://{user_id}/profile"

    @pytest.mark.asyncio
    async def test_list_resources(self):
        """测试列出静态资源"""
        router = MCPRouter()

        @router.resource("resource://static1")
        async def get_resource1() -> str:
            return "content1"

        @router.resource("resource://static2")
        async def get_resource2() -> str:
            return "content2"

        resources = router.list_resources()

        assert len(resources) == 2
        uris = [r.uri for r in resources]
        assert AnyUrl("resource://static1") in uris
        assert AnyUrl("resource://static2") in uris

    @pytest.mark.asyncio
    async def test_list_resource_templates(self):
        """测试列出资源模板"""
        router = MCPRouter()

        @router.resource("users://{user_id}/profile")
        async def get_user_profile(user_id: str) -> str:
            return f"Profile for {user_id}"

        templates = router.list_resource_templates()

        assert len(templates) == 1
        assert templates[0].uriTemplate == "users://{user_id}/profile"

    @pytest.mark.asyncio
    async def test_read_static_resource(self):
        """测试读取静态资源"""
        router = MCPRouter()

        @router.resource("resource://static")
        async def get_static_resource() -> str:
            """Static resource"""
            return "static content"

        content = await router.read_resource("resource://static")

        assert content == "static content"

    @pytest.mark.asyncio
    async def test_read_template_resource(self):
        """测试读取模板资源"""
        router = MCPRouter()

        @router.resource("users://{user_id}/profile")
        async def get_user_profile(user_id: str) -> str:
            """User profile"""
            return f"Profile for {user_id}"

        content = await router.read_resource("users://123/profile")

        assert content == "Profile for 123"

    @pytest.mark.asyncio
    async def test_read_resource_not_found(self):
        """测试读取不存在的资源"""
        router = MCPRouter()

        with pytest.raises(ValueError, match="Resource not found"):
            await router.read_resource("resource://nonexistent")

    @pytest.mark.asyncio
    async def test_read_resource_with_dict_result(self):
        """测试读取返回字典的资源"""
        router = MCPRouter()

        @router.resource("resource://json")
        async def get_json_resource() -> dict:
            return {"key": "value"}

        content = await router.read_resource("resource://json")

        assert "key" in content
        assert "value" in content

    @pytest.mark.asyncio
    async def test_template_resource_priority(self):
        """测试模板资源优先级（更长的 URI 优先）"""
        router = MCPRouter()

        @router.resource("users://{user_id}")
        async def get_user(user_id: str) -> str:
            return f"User {user_id}"

        @router.resource("users://{user_id}/profile")
        async def get_user_profile(user_id: str) -> str:
            return f"Profile for {user_id}"

        # 更具体的路径应该优先匹配
        content = await router.read_resource("users://123/profile")

        assert content == "Profile for 123"

    # ==================== Prompt 测试 ====================

    @pytest.mark.asyncio
    async def test_register_prompt(self):
        """测试注册提示词"""
        router = MCPRouter()

        @router.prompt()
        async def greeting_prompt(user_name: str) -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        assert len(router.prompts) == 1
        assert "greeting_prompt" in router.prompts_map
        assert router.prompts[0].name == "greeting_prompt"

    @pytest.mark.asyncio
    async def test_register_prompt_with_custom_name(self):
        """测试使用自定义名称注册提示词"""
        router = MCPRouter()

        @router.prompt(name="custom_greeting")
        async def greeting_prompt(user_name: str) -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        assert router.prompts[0].name == "custom_greeting"
        assert "custom_greeting" in router.prompts_map

    @pytest.mark.asyncio
    async def test_list_prompts(self):
        """测试列出提示词"""
        router = MCPRouter()

        @router.prompt()
        async def prompt1(user_name: str) -> str:
            """Prompt 1"""
            return f"Hello, {user_name}!"

        @router.prompt()
        async def prompt2(message: str) -> str:
            """Prompt 2"""
            return message

        prompts = router.list_prompts()

        assert len(prompts) == 2
        prompt_names = [p.name for p in prompts]
        assert "prompt1" in prompt_names
        assert "prompt2" in prompt_names

    @pytest.mark.asyncio
    async def test_get_prompt_with_string_result(self):
        """测试获取提示词（返回字符串）"""
        router = MCPRouter()

        @router.prompt()
        async def greeting_prompt(user_name: str) -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        result = await router.get_prompt("greeting_prompt", {"user_name": "Alice"})

        assert result is not None
        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        assert "Hello, Alice!" in result.messages[0].content.text

    @pytest.mark.asyncio
    async def test_get_prompt_with_dict_result(self):
        """测试获取提示词（返回字典，会被 JSON 序列化）"""
        router = MCPRouter()

        @router.prompt()
        async def data_prompt(key: str) -> dict:
            """Return data"""
            return {"key": key, "value": "test"}

        result = await router.get_prompt("data_prompt", {"key": "test_key"})

        assert result is not None
        assert len(result.messages) == 1
        assert "test_key" in result.messages[0].content.text

    @pytest.mark.asyncio
    async def test_get_prompt_not_found(self):
        """测试获取不存在的提示词"""
        router = MCPRouter()

        with pytest.raises(ValueError, match="Unknown prompt"):
            await router.get_prompt("nonexistent_prompt", {})

    @pytest.mark.asyncio
    async def test_get_prompt_without_arguments(self):
        """测试获取提示词（无参数）"""
        router = MCPRouter()

        @router.prompt()
        async def simple_prompt() -> str:
            """Simple prompt"""
            return "Hello!"

        result = await router.get_prompt("simple_prompt")

        assert result is not None
        assert "Hello!" in result.messages[0].content.text
