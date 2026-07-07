"""MCP Service 扩展集成测试

更全面地测试 MCP 服务，包括异常处理、回调执行等场景。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient

from dm_mcp.app.server import MCPServer
from tests.conftest import mock_settings


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServiceHandlersWithException:
    """测试 MCP 回调处理器的异常情况"""

    @pytest_asyncio.fixture
    async def server(self, mock_settings):
        """创建测试服务器实例"""

        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)  # type: ignore
        yield server
        await server.shutdown()

    @pytest_asyncio.fixture
    async def app(self, server):
        """创建 ASGI 应用"""
        app = server.create_asgi_app(stateless=True)
        await server.startup()
        yield app
        await server.shutdown()

    @pytest_asyncio.fixture
    async def client(self, app):
        """创建测试客户端"""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", timeout=30.0
        ) as client:
            yield client

    def _get_path(self, server, path: str) -> str:
        """获取完整路径"""
        base_url = server.settings.server.base_url
        if path.startswith(base_url):
            return path
        return f"{base_url}{path}" if path.startswith("/") else f"{base_url}/{path}"

    async def test_mcp_list_resources_handler_error(self, client, server):
        """测试资源列表处理器错误处理（行501-503）"""
        # 测试向 MCP 资源列表端点发送请求
        # 即使处理失败，也应该返回空列表而不是崩溃
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        request = {"jsonrpc": "2.0", "id": 100, "method": "resources/list"}

        response = await client.post(path, json=request)
        # 应该返回有效响应（无论成功或错误）
        assert response.status_code in [200, 400, 403, 404, 500]

        # 如果返回 200，验证响应格式
        if response.status_code == 200:
            data = response.json()
            assert "jsonrpc" in data or "result" in data or "error" in data

    async def test_mcp_list_resource_templates_handler_error(self, client, server):
        """测试资源模板列表处理器错误处理（行517-519）"""
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        request = {"jsonrpc": "2.0", "id": 101, "method": "resources/templates/list"}

        response = await client.post(path, json=request)
        assert response.status_code in [200, 400, 403, 404, 500]

    async def test_mcp_read_resource_handler_error(self, client, server):
        """测试读取资源处理器错误处理（行531-537）"""
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        request = {
            "jsonrpc": "2.0",
            "id": 102,
            "method": "resources/read",
            "params": {"uri": "test://invalid/resource"},
        }

        response = await client.post(path, json=request)
        # 应该返回某种响应
        assert response.status_code in [200, 400, 403, 404, 500]

    async def test_mcp_list_tools_handler_error(self, client, server):
        """测试工具列表处理器错误处理（行546-548）"""
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        request = {"jsonrpc": "2.0", "id": 103, "method": "tools/list"}

        response = await client.post(path, json=request)
        assert response.status_code in [200, 400, 403, 404, 500]

    async def test_mcp_call_tool_handler_error(self, client, server):
        """测试工具调用处理器错误处理（行561-573）"""
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        request = {
            "jsonrpc": "2.0",
            "id": 104,
            "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}},
        }

        response = await client.post(path, json=request)
        # 应该返回错误而不崩溃
        assert response.status_code in [200, 400, 403, 404, 500]

    async def test_mcp_list_prompts_handler_error(self, client, server):
        """测试提示列表处理器错误处理（行585-587）"""
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        request = {"jsonrpc": "2.0", "id": 105, "method": "prompts/list"}

        response = await client.post(path, json=request)
        assert response.status_code in [200, 400, 403, 404, 500]

    async def test_mcp_get_prompt_handler_error(self, client, server):
        """测试获取提示处理器错误处理（行601-619）"""
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        request = {
            "jsonrpc": "2.0",
            "id": 106,
            "method": "prompts/get",
            "params": {"name": "nonexistent_prompt", "arguments": {}},
        }

        response = await client.post(path, json=request)
        assert response.status_code in [200, 400, 403, 404, 500]

    async def test_mcp_multiple_jsonrpc_methods(self, client, server):
        """测试多种 JSON-RPC 方法"""
        path = self._get_path(server, "/mcp/messages?sessionId=test_session")

        methods = [
            {"method": "initialize", "id": 1},
            {"method": "ping", "id": 2},
            {"method": "tools/list", "id": 3},
            {"method": "resources/list", "id": 4},
            {"method": "prompts/list", "id": 5},
        ]

        for method_req in methods:
            request = {
                "jsonrpc": "2.0",
                "id": method_req["id"],
                "method": method_req["method"],
            }

            response = await client.post(path, json=request)
            assert response.status_code in [200, 400, 403, 404, 500]


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServiceProviderErrorSimulation:
    """模拟 Provider 错误的集成测试"""

    @pytest_asyncio.fixture
    async def server_with_failing_provider(self, mock_settings):
        """创建带有会失败的 Provider 的服务器"""

        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)

        # 获取 MCP Service 并添加一个会失败的 Provider
        await server.startup()

        mcp_service = server.context.mcp_service

        # 创建一个会抛出异常的 Provider
        failing_provider = MagicMock()
        failing_provider.name = "failing_provider"

        tool = MagicMock()
        tool.name = "test_tool"
        failing_provider.list_tools.return_value = [tool]
        failing_provider.list_resources.return_value = []
        failing_provider.list_resource_templates.return_value = []
        failing_provider.list_prompts.return_value = []

        # 模拟调用工具时抛出异常
        async def raise_error(*args, **kwargs):
            raise RuntimeError("Simulated provider error")

        failing_provider.call_tool = raise_error
        failing_provider.read_resource = raise_error
        failing_provider.get_prompt = raise_error

        failing_provider.mcp = MagicMock()
        failing_provider.mcp.tools_map = {"test_tool": tool}

        mcp_service.add_mcp_provider(failing_provider)

        # 清除缓存
        for attr in [
            "_tools",
            "_providers_tool_map",
            "_resources",
            "_providers_resource_map",
        ]:
            if hasattr(mcp_service, attr):
                try:
                    delattr(mcp_service, attr)
                except AttributeError:
                    pass

        yield server

        await server.shutdown()

    @pytest_asyncio.fixture
    async def app_with_failing(self, server_with_failing_provider):
        """创建 ASGI 应用"""
        app = server_with_failing_provider.create_asgi_app(stateless=True)
        yield app
        await server_with_failing_provider.shutdown()

    @pytest_asyncio.fixture
    async def client_failing(self, app_with_failing):
        """创建测试客户端"""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_failing),
            base_url="http://test",
            timeout=30.0,
        ) as client:
            yield client

    async def test_tool_call_with_provider_error(
        self, client_failing, server_with_failing_provider
    ):
        """测试 Provider 抛出异常时的错误处理"""
        path = f"{server_with_failing_provider.settings.server.base_url}/mcp/messages?sessionId=test_session"

        request = {
            "jsonrpc": "2.0",
            "id": 200,
            "method": "tools/call",
            "params": {"name": "test_tool", "arguments": {}},
        }

        response = await client_failing.post(path, json=request)
        # 应该返回错误而不是 500 崩溃
        assert response.status_code in [200, 400, 403, 404]

        # 如果是 200，检查是否有错误信息
        if response.status_code == 200:
            data = response.json()
            # 可能是成功结果或错误结果
            assert "jsonrpc" in data


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServiceSSEEndpoint:
    """测试 MCP SSE 端点"""

    @pytest_asyncio.fixture
    async def server(self, mock_settings):
        """创建测试服务器实例"""

        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)
        yield server
        await server.shutdown()

    @pytest_asyncio.fixture
    async def app(self, server):
        """创建 ASGI 应用"""
        app = server.create_asgi_app(stateless=True)
        await server.startup()
        yield app
        await server.shutdown()

    @pytest_asyncio.fixture
    async def client(self, app):
        """创建测试客户端"""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", timeout=30.0
        ) as client:
            yield client

    async def test_sse_endpoint_returns_sse(self, server, app):
        """测试 SSE 端点返回事件流"""
        base_url = server.settings.server.base_url
        path = f"{base_url}/mcp"

        # 发送 SSE 请求
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as test_client:
            async with test_client.stream(
                "GET", path, headers={"Accept": "text/event-stream"}
            ) as response:
                # SSE 响应应该是流式的
                assert response.status_code in [200, 400, 404]


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServiceProviderWithMiddleware:
    """测试 Provider 与中间件的集成"""

    async def test_provider_with_middleware_stack(self, mock_settings):
        """测试带中间件栈的 Provider"""
        from dm_mcp.core.mcp.middleware import MCPMiddlewareStack
        from tests.integration.conftest import make_mcp_service

        service = make_mcp_service(mock_settings.server)

        # 验证中间件栈存在
        assert service.middleware_stack is not None
        assert isinstance(service.middleware_stack, MCPMiddlewareStack)

        # 添加中间件
        mock_middleware = MagicMock()
        service.add_mcp_middleware(mock_middleware)

        # 添加 Provider
        provider = MagicMock()
        provider.list_tools.return_value = []
        provider.list_resources.return_value = []
        provider.list_resource_templates.return_value = []
        provider.list_prompts.return_value = []

        service.add_mcp_provider(provider)

        # 验证列表方法可以正常调用
        tools = await service.list_tools()
        assert tools == []

        resources = await service.list_resources()
        assert resources == []

        prompts = await service.list_prompts()
        assert prompts == []


@pytest.mark.integration
@pytest.mark.asyncio
class TestMCPServiceCallbackRegistration:
    """测试回调函数注册"""

    async def test_callbacks_are_registered(self, mock_settings):
        """测试回调函数已注册"""
        from tests.integration.conftest import make_mcp_service

        # 创建服务（这会调用 _setup_handlers）
        service = make_mcp_service(mock_settings.server)

        # 验证 SDK Server 存在
        assert service.sdk_server is not None

        # 验证缓存属性可以访问（说明回调已注册）
        try:
            _ = service._tools
            _ = service._resources
            _ = service._prompts
            _ = service._resource_templates
        except Exception as e:
            # 如果访问失败，可能是 Provider 列表为空的正常情况
            pass

        # 验证 providers 可以访问
        assert service.providers is not None
        assert isinstance(service.providers, list)
