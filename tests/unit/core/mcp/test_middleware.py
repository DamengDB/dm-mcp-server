"""MCP Middleware 单元测试

测试 BaseMCPMiddleware 和 MCPMiddlewareStack 的功能。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp import Resource, Tool
from mcp.types import GetPromptResult, Prompt, ResourceTemplate
from pydantic.networks import AnyUrl

from dm_mcp.core.mcp.middleware import BaseMCPMiddleware, MCPMiddlewareStack


class MockMiddleware(BaseMCPMiddleware):
    """Mock 测试中间件"""

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.called_methods = []

    async def on_call_tool(self, call_next, name: str, arguments: dict):
        self.called_methods.append(("on_call_tool", name))
        result = await call_next(name, arguments)
        return result

    async def on_list_tools(self, call_next):
        self.called_methods.append(("on_list_tools",))
        return await call_next()


class TestBaseMCPMiddleware:
    """BaseMCPMiddleware 测试类"""

    def test_middleware_initialization(self):
        """测试中间件初始化"""
        middleware = MockMiddleware("test")

        assert middleware.name == "test"
        assert middleware.called_methods == []

    @pytest.mark.asyncio
    async def test_middleware_on_message(self):
        """测试消息处理中间件"""
        middleware = BaseMCPMiddleware()

        async def handler(message):
            assert message == "test_message"

        await middleware.on_message(handler, "test_message")

    @pytest.mark.asyncio
    async def test_middleware_on_list_tools(self):
        """测试列出工具中间件"""
        middleware = BaseMCPMiddleware()

        async def handler():
            return [Tool(name="test", description="Test tool", inputSchema={})]

        result = await middleware.on_list_tools(handler)

        assert len(result) == 1
        assert result[0].name == "test"

    @pytest.mark.asyncio
    async def test_middleware_on_call_tool(self):
        """测试调用工具中间件"""
        middleware = BaseMCPMiddleware()

        async def handler(name: str, arguments: dict):
            return {"result": f"{name}:{arguments}"}

        result = await middleware.on_call_tool(handler, "test_tool", {"x": 1})

        assert result == {"result": "test_tool:{'x': 1}"}

    @pytest.mark.asyncio
    async def test_middleware_on_list_prompts(self):
        """测试列出提示词中间件"""
        middleware = BaseMCPMiddleware()

        async def handler():
            return [Prompt(name="test", description="Test prompt")]

        result = await middleware.on_list_prompts(handler)

        assert len(result) == 1
        assert result[0].name == "test"

    @pytest.mark.asyncio
    async def test_middleware_on_get_prompt(self):
        """测试获取提示词中间件"""
        middleware = BaseMCPMiddleware()

        async def handler(name: str, arguments: dict | None = None):
            return GetPromptResult(description=None, messages=[])

        result = await middleware.on_get_prompt(
            handler, "test_prompt", {"arg": "value"}
        )

        assert isinstance(result, GetPromptResult)

    @pytest.mark.asyncio
    async def test_middleware_on_list_resources(self):
        """测试列出资源中间件"""
        middleware = BaseMCPMiddleware()

        async def handler():
            return [
                Resource(uri=AnyUrl("resource://test"), name="test", description="Test")
            ]

        result = await middleware.on_list_resources(handler)

        assert len(result) == 1
        assert str(result[0].uri) == "resource://test"

    @pytest.mark.asyncio
    async def test_middleware_on_list_resource_templates(self):
        """测试列出资源模板中间件"""
        middleware = BaseMCPMiddleware()

        async def handler():
            return [
                ResourceTemplate(
                    uriTemplate="resource://{id}", name="test", description="Test"
                )
            ]

        result = await middleware.on_list_resource_templates(handler)

        assert len(result) == 1
        assert result[0].uriTemplate == "resource://{id}"

    @pytest.mark.asyncio
    async def test_middleware_on_read_resource(self):
        """测试读取资源中间件"""
        middleware = BaseMCPMiddleware()

        async def handler(uri: AnyUrl):
            return "resource content"

        result = await middleware.on_read_resource(handler, AnyUrl("resource://test"))

        assert result == "resource content"


class TestMCPMiddlewareStack:
    """MCPMiddlewareStack 测试类"""

    def test_stack_initialization_empty(self):
        """测试空栈初始化"""
        stack = MCPMiddlewareStack()

        assert stack.is_empty()
        assert len(stack) == 0

    def test_stack_initialization_with_middlewares(self):
        """测试带中间件的栈初始化"""
        mw1 = MockMiddleware("mw1")
        mw2 = MockMiddleware("mw2")

        stack = MCPMiddlewareStack([mw1, mw2])

        assert not stack.is_empty()
        assert len(stack) == 2

    def test_add_middleware(self):
        """测试添加单个中间件"""
        stack = MCPMiddlewareStack()
        mw = MockMiddleware("mw1")

        stack.add_middleware(mw)

        assert len(stack) == 1
        assert not stack.is_empty()

    def test_add_middlewares(self):
        """测试批量添加中间件"""
        stack = MCPMiddlewareStack()
        mw1 = MockMiddleware("mw1")
        mw2 = MockMiddleware("mw2")

        stack.add_middlewares([mw1, mw2])

        assert len(stack) == 2

    @pytest.mark.asyncio
    async def test_stack_execution_order(self):
        """测试中间件执行顺序"""
        call_order = []

        class OrderMiddleware(BaseMCPMiddleware):
            def __init__(self, name: str):
                super().__init__()
                self.name = name

            async def on_call_tool(self, call_next, name: str, arguments: dict):
                call_order.append(f"before_{self.name}")
                result = await call_next(name, arguments)
                call_order.append(f"after_{self.name}")
                return result

        mw1 = OrderMiddleware("mw1")
        mw2 = OrderMiddleware("mw2")
        stack = MCPMiddlewareStack([mw1, mw2])

        async def handler(name: str, arguments: dict):
            call_order.append("handler")
            return {"result": "ok"}

        result = await stack.on_call_tool(handler, "test", {})

        # 执行顺序：before_mw1 -> before_mw2 -> handler -> after_mw2 -> after_mw1
        assert call_order == [
            "before_mw1",
            "before_mw2",
            "handler",
            "after_mw2",
            "after_mw1",
        ]
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_stack_on_list_tools(self):
        """测试栈执行列出工具"""
        mw = MockMiddleware("mw1")
        stack = MCPMiddlewareStack([mw])

        async def handler():
            return [Tool(name="test", description="Test", inputSchema={})]

        result = await stack.on_list_tools(handler)

        assert len(result) == 1
        assert ("on_list_tools",) in mw.called_methods

    @pytest.mark.asyncio
    async def test_stack_on_call_tool(self):
        """测试栈执行调用工具"""
        mw = MockMiddleware("mw1")
        stack = MCPMiddlewareStack([mw])

        async def handler(name: str, arguments: dict):
            return {"result": "ok"}

        result = await stack.on_call_tool(handler, "test_tool", {"x": 1})

        assert result == {"result": "ok"}
        assert ("on_call_tool", "test_tool") in mw.called_methods

    @pytest.mark.asyncio
    async def test_stack_on_get_prompt(self):
        """测试栈执行获取提示词"""
        mw = MockMiddleware("mw1")
        stack = MCPMiddlewareStack([mw])

        async def handler(name: str, arguments: dict | None = None):
            return GetPromptResult(description=None, messages=[])

        result = await stack.on_get_prompt(handler, "test_prompt", {"arg": "value"})

        assert isinstance(result, GetPromptResult)

    @pytest.mark.asyncio
    async def test_stack_on_read_resource(self):
        """测试栈执行读取资源"""
        mw = MockMiddleware("mw1")
        stack = MCPMiddlewareStack([mw])

        async def handler(uri: AnyUrl):
            return "resource content"

        result = await stack.on_read_resource(handler, AnyUrl("resource://test"))

        assert result == "resource content"

    @pytest.mark.asyncio
    async def test_stack_empty_executes_handler_directly(self):
        """测试空栈直接执行处理器"""
        stack = MCPMiddlewareStack()

        async def handler(name: str, arguments: dict):
            return {"result": "ok"}

        result = await stack.on_call_tool(handler, "test", {})

        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_stack_middleware_can_modify_result(self):
        """测试中间件可以修改结果"""

        class ModifyMiddleware(BaseMCPMiddleware):
            async def on_call_tool(
                self, call_next, name: str, arguments: dict | None = None
            ):
                result = await call_next(name, arguments)
                return {"modified": True, **result}

        mw = ModifyMiddleware()
        stack = MCPMiddlewareStack([mw])

        async def handler(name: str, arguments: dict | None = None):
            return {"original": True}

        result = await stack.on_call_tool(handler, "test", {})

        assert result["modified"] is True
        assert result["original"] is True

    @pytest.mark.asyncio
    async def test_stack_middleware_can_raise_exception(self):
        """测试中间件可以抛出异常"""

        class ErrorMiddleware(BaseMCPMiddleware):
            async def on_call_tool(
                self, call_next, name: str, arguments: dict | None = None
            ):
                raise ValueError("Middleware error")

        mw = ErrorMiddleware()
        stack = MCPMiddlewareStack([mw])

        async def handler(name: str, arguments: dict | None = None):
            return {"result": "ok"}

        with pytest.raises(ValueError, match="Middleware error"):
            await stack.on_call_tool(handler, "test", {})
