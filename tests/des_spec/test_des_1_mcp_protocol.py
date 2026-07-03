"""DES-1 MCP 协议能力测试：以 HTTP 请求为入口，验证 MCP JSON-RPC 行为（不依赖底层 streamable-http 实现细节）。"""

import asyncio
import json
from typing import Any, Dict

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from mcp import types
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from dm_mcp.core.exceptions import DmMCPError
from dm_mcp.core.mcp import BaseMCPProvider
from dm_mcp.services.mcp_service import MCPService
from dm_mcp.settings.settings import ServerConfig


class _FakeProvider(BaseMCPProvider):
    """用于 DM_MCP-des-1 的 Provider，仅用装饰器 @self.mcp.tool / resource / prompt 注册（与真实 Provider 一致）。"""

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name
        self._tool_handlers: Dict[str, Any] = {}
        self._resource_handlers: Dict[str, Any] = {}
        self._template_handlers: Dict[str, Any] = {}
        self._prompt_handlers: Dict[str, Any] = {}
        self._register_routes()

    def _register_routes(self) -> None:
        async def _run_tool(
            name: str, a: int = 0, arg: int = 0, value: int = 0
        ) -> Dict[str, Any]:
            h = self._tool_handlers.get(name)
            if h is None:
                return {}
            if asyncio.iscoroutinefunction(h):
                return await h(a=a, arg=arg, value=value)
            return h(a=a, arg=arg, value=value)

        @self.mcp.tool(name="tool_a", description="Fake tool_a")
        async def tool_a(a: int = 0, arg: int = 0, value: int = 0) -> Dict[str, Any]:
            return await _run_tool("tool_a", a=a, arg=arg, value=value)

        @self.mcp.tool(name="tool_b", description="Fake tool_b")
        async def tool_b(a: int = 0, arg: int = 0, value: int = 0) -> Dict[str, Any]:
            return await _run_tool("tool_b", a=a, arg=arg, value=value)

        @self.mcp.tool(name="tool_c", description="Fake tool_c")
        async def tool_c(a: int = 0, arg: int = 0, value: int = 0) -> Dict[str, Any]:
            return await _run_tool("tool_c", a=a, arg=arg, value=value)

        @self.mcp.tool(name="ok_tool", description="Fake ok_tool")
        async def ok_tool(a: int = 0, arg: int = 0, value: int = 0) -> Dict[str, Any]:
            return await _run_tool("ok_tool", a=a, arg=arg, value=value)

        @self.mcp.tool(name="biz_tool", description="Fake biz_tool")
        async def biz_tool(a: int = 0, arg: int = 0, value: int = 0) -> Dict[str, Any]:
            return await _run_tool("biz_tool", a=a, arg=arg, value=value)

        @self.mcp.tool(name="sys_tool", description="Fake sys_tool")
        async def sys_tool(a: int = 0, arg: int = 0, value: int = 0) -> Dict[str, Any]:
            return await _run_tool("sys_tool", a=a, arg=arg, value=value)

        @self.mcp.resource(
            "dm://schema/TEST",
            description="Fake static resource",
            mime_type="application/json",
        )
        async def res_schema_test() -> Any:
            h = self._resource_handlers.get("dm://schema/TEST")
            if h is None:
                return {}
            if asyncio.iscoroutinefunction(h):
                return await h()
            return h()

        @self.mcp.resource(
            "dm://table/{schema}/{table}",
            description="Fake table resource",
            mime_type="application/json",
        )
        async def res_table(schema: str, table: str) -> Any:
            key = "dm://table/{schema}/{table}"
            h = self._template_handlers.get(key)
            if h is None:
                return {}
            if asyncio.iscoroutinefunction(h):
                return await h(schema=schema, table=table)
            return h(schema=schema, table=table)

        @self.mcp.prompt(name="hello", description="Fake prompt hello")
        async def prompt_hello(x: str = "") -> Any:
            h = self._prompt_handlers.get("hello")
            if h is None:
                return ""
            if asyncio.iscoroutinefunction(h):
                return await h(x=x)
            return h(x=x)


def _dump_model(obj: Any) -> Any:
    """将 pydantic/Typed 对象转换为可 JSON 序列化的 dict."""
    if hasattr(obj, "model_dump"):
        # 使用 mode="json" 确保 AnyUrl 等类型被转换为字符串
        return obj.model_dump(mode="json")  # type: ignore[call-arg]
    if hasattr(obj, "dict"):
        return obj.dict()
    return obj


def _make_mcp_http_app(
    fake_provider: _FakeProvider,
    settings,
    metrics_service,
    datasource_service,
    logging_service,
):
    """构建仅含 FakeProvider 的 MCP HTTP ASGI 应用。

    这里不通过 streamable-http 的 SessionManager，而是直接把 JSON-RPC 方法
    映射到 MCPService 的 list_* / call_tool / read_resource / get_prompt 等入口，
    以 HTTP 请求作为协议层入口验证行为。
    """
    server_cfg = (
        settings.server
        if hasattr(settings, "server")
        else ServerConfig(name="test-mcp")
    )
    mcp_service = MCPService(
        server_cfg, metrics_service, datasource_service, logging_service
    )
    mcp_service.add_mcp_provider(fake_provider)

    base_url = getattr(settings.server, "base_url", "/dm-mcp") or "/dm-mcp"

    async def mcp_messages(request: Request):
        body = await request.json()
        method = body.get("method")
        rpc_id = body.get("id")
        params = body.get("params") or {}

        # 基本 JSON-RPC 包装
        def ok(result: Dict[str, Any]) -> JSONResponse:
            return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": result})

        def err(code: int, message: str) -> JSONResponse:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {"code": code, "message": message},
                },
                status_code=200,
            )

        try:
            if method == "tools/list":
                tools = await mcp_service.list_tools()
                return ok({"tools": [_dump_model(t) for t in tools]})

            if method == "tools/call":
                name = params.get("name", "")
                arguments = params.get("arguments") or {}
                text = await mcp_service.call_tool(name, arguments)
                return ok({"content": [{"type": "text", "text": text}]})

            if method == "resources/list":
                resources = await mcp_service.list_resources()
                return ok({"resources": [_dump_model(r) for r in resources]})

            if method == "resources/read":
                uri = params.get("uri", "")
                text = await mcp_service.read_resource(uri)
                # 与 tools/call 一致，封装为 content[].text
                return ok({"content": [{"type": "text", "text": text}]})

            if method == "prompts/list":
                prompts = await mcp_service.list_prompts()
                return ok({"prompts": [_dump_model(p) for p in prompts]})

            if method == "prompts/get":
                name = params.get("name", "")
                arguments = params.get("arguments")
                result = await mcp_service.get_prompt(name, arguments)
                return ok(_dump_model(result))

            return err(-32601, f"Unknown method: {method}")
        except Exception as e:  # pragma: no cover - 统一兜底
            return err(-32000, f"Internal error: {e}")

    app = Starlette(
        routes=[
            Route(f"{base_url}/mcp/messages", mcp_messages, methods=["POST"]),
        ]
    )
    return app, base_url


@pytest_asyncio.fixture
async def fake_provider():
    """每个用例共用的 FakeProvider，用例内通过 _tool_handlers 等配置行为。"""
    return _FakeProvider("p")


@pytest_asyncio.fixture
async def mcp_http_app(
    fake_provider,
    mock_settings,
    mock_metrics_service,
    mock_datasource_service,
    mock_logging_service,
):
    """MCP HTTP ASGI 应用（仅含 FakeProvider，认证已注入）。"""
    return _make_mcp_http_app(
        fake_provider,
        mock_settings,
        mock_metrics_service,
        mock_datasource_service,
        mock_logging_service,
    )


@pytest_asyncio.fixture
async def mcp_http_client(mcp_http_app):
    """HTTP 测试客户端，base_url 指向 testserver。"""
    app, base_url = mcp_http_app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        timeout=30.0,
    ) as client:
        yield client, base_url


def _messages_url(base_url: str, session_id: str = "test_session") -> str:
    return f"{base_url}/mcp/messages?sessionId={session_id}"


async def _post_mcp(
    client: AsyncClient,
    base_url: str,
    method: str,
    params: Dict[str, Any] | None = None,
    req_id: int = 1,
):
    """发送 MCP JSON-RPC 请求，可选先发 initialize。"""
    url = _messages_url(base_url)
    body = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post(url, json=body)


def _tool_result_text(data: dict) -> str:
    """从 tools/call 的 result 中取出 content[0].text。"""
    if (
        "result" in data
        and "content" in data["result"]
        and len(data["result"]["content"]) > 0
    ):
        return data["result"]["content"][0].get("text", "")
    return ""


@pytest.mark.asyncio
async def test_des_1_tc_01_tools_aggregation_and_get_definition(
    mcp_http_client, fake_provider
):
    """[DM_MCP-des-1] DES-1-TC-01 工具聚合与发现（HTTP 入口）。"""
    client, base_url = mcp_http_client
    resp = await _post_mcp(client, base_url, "tools/list")
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data and "tools" in data["result"]
    names = {t["name"] for t in data["result"]["tools"]}
    assert names == {"tool_a", "tool_b", "tool_c", "ok_tool", "biz_tool", "sys_tool"}


@pytest.mark.asyncio
async def test_des_1_tc_02_unknown_tool_returns_standard_error(mcp_http_client):
    """[DM_MCP-des-1] DES-1-TC-02 未知工具调用返回统一错误结构（HTTP 入口）。"""
    client, base_url = mcp_http_client
    resp = await _post_mcp(
        client,
        base_url,
        "tools/call",
        params={"name": "non_exists", "arguments": {"x": 1}},
    )
    assert resp.status_code == 200
    data = resp.json()
    text = _tool_result_text(data)
    assert text
    payload = json.loads(text)
    assert payload["error"] == "TOOL_NOT_FOUND"
    assert payload["tool_name"] == "non_exists"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_des_1_tc_03_tool_call_success_with_execution_info(
    mcp_http_client, fake_provider
):
    """[DM_MCP-des-1] DES-1-TC-03 正常工具调用附带执行信息（HTTP 入口）。"""
    from unittest.mock import AsyncMock

    client, base_url = mcp_http_client
    fake_provider._tool_handlers["ok_tool"] = AsyncMock(return_value={"value": 1})

    resp = await _post_mcp(
        client,
        base_url,
        "tools/call",
        params={"name": "ok_tool", "arguments": {"a": 1}},
    )
    assert resp.status_code == 200
    data = resp.json()
    text = _tool_result_text(data)
    assert text
    payload = json.loads(text)
    assert payload["value"] == 1
    exec_info = payload["_execution_info"]
    assert exec_info["tool_name"] == "ok_tool"
    assert isinstance(exec_info["execution_time"], float)
    assert "timestamp" in exec_info


@pytest.mark.asyncio
async def test_des_1_tc_04_business_error_wrapped_as_json(
    mcp_http_client, fake_provider
):
    """[DM_MCP-des-1] DES-1-TC-04 业务异常包装为统一 JSON（HTTP 入口）。"""
    from unittest.mock import AsyncMock

    class MyBizError(DmMCPError):
        pass

    client, base_url = mcp_http_client
    fake_provider._tool_handlers["biz_tool"] = AsyncMock(
        side_effect=MyBizError(
            message="biz failed", error_code="BIZ_ERR", details={"k": "v"}
        )
    )

    resp = await _post_mcp(
        client,
        base_url,
        "tools/call",
        params={"name": "biz_tool", "arguments": {"arg": 1}},
    )
    assert resp.status_code == 200
    text = _tool_result_text(resp.json())
    payload = json.loads(text)
    assert payload["error"] == "BIZ_ERR"
    assert payload["message"] == "biz failed"
    assert payload["details"] == {"k": "v"}
    assert payload["tool_name"] == "biz_tool"
    assert payload["arguments"] == {"arg": 1}


@pytest.mark.asyncio
async def test_des_1_tc_05_system_error_wrapped_as_json(mcp_http_client, fake_provider):
    """[DM_MCP-des-1] DES-1-TC-05 系统异常包装为统一 JSON（HTTP 入口）。"""
    from unittest.mock import AsyncMock

    client, base_url = mcp_http_client
    fake_provider._tool_handlers["sys_tool"] = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    resp = await _post_mcp(
        client,
        base_url,
        "tools/call",
        params={"name": "sys_tool", "arguments": {}},
    )
    assert resp.status_code == 200
    text = _tool_result_text(resp.json())
    payload = json.loads(text)
    assert payload["error"] == "TOOL_EXECUTION_ERROR"
    assert "Tool execution failed" in payload["message"]
    assert payload["tool_name"] == "sys_tool"


@pytest.mark.asyncio
async def test_des_1_tc_06_resource_list_and_read(mcp_http_client, fake_provider):
    """[DM_MCP-des-1] DES-1-TC-06 资源列表及静态 URI 读取（HTTP 入口）。"""
    from unittest.mock import AsyncMock

    client, base_url = mcp_http_client
    handler = AsyncMock(return_value={"schema": "TEST"})
    fake_provider._resource_handlers["dm://schema/TEST"] = handler

    resp = await _post_mcp(client, base_url, "resources/list")
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data and "resources" in data["result"]
    assert any(
        str(r.get("uri", "")) == "dm://schema/TEST" for r in data["result"]["resources"]
    )

    resp2 = await _post_mcp(
        client,
        base_url,
        "resources/read",
        params={"uri": "dm://schema/TEST"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    # 读资源返回 result.content 或 result.contents
    content = data2.get("result", {})
    if "content" in content and content["content"]:
        text = (
            content["content"][0].get("text", "")
            if isinstance(content["content"][0], dict)
            else str(content["content"][0])
        )
    else:
        text = json.dumps(content)
    payload = (
        json.loads(text) if isinstance(text, str) and text.startswith("{") else content
    )
    if isinstance(payload, dict):
        assert payload.get("schema") == "TEST"
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_des_1_tc_07_resource_template_matching(mcp_http_client, fake_provider):
    """[DM_MCP-des-1] DES-1-TC-07 资源 URI 模板匹配与路由（HTTP 入口）。"""
    from unittest.mock import AsyncMock

    client, base_url = mcp_http_client
    handler = AsyncMock(return_value={"schema": "TEST", "table": "EMP"})
    fake_provider._template_handlers["dm://table/{schema}/{table}"] = handler

    resp = await _post_mcp(
        client,
        base_url,
        "resources/read",
        params={"uri": "dm://table/TEST/EMP"},
    )
    assert resp.status_code == 200
    data = resp.json()
    content = data.get("result", {})
    if "content" in content and content["content"]:
        c0 = content["content"][0]
        text = c0.get("text", "") if isinstance(c0, dict) else str(c0)
    else:
        text = json.dumps(content)
    payload = (
        json.loads(text) if isinstance(text, str) and text.startswith("{") else content
    )
    if isinstance(payload, dict):
        assert payload.get("schema") == "TEST" and payload.get("table") == "EMP"
    handler.assert_awaited_once_with(schema="TEST", table="EMP")


@pytest.mark.asyncio
async def test_des_1_tc_08_resource_not_found_returns_error(mcp_http_client):
    """[DM_MCP-des-1] DES-1-TC-08 资源不存在时返回统一错误结构（HTTP 入口）。"""
    client, base_url = mcp_http_client
    resp = await _post_mcp(
        client,
        base_url,
        "resources/read",
        params={"uri": "dm://unknown/resource"},
    )
    assert resp.status_code == 200
    data = resp.json()
    content = data.get("result", {})
    if "content" in content and content["content"]:
        c0 = content["content"][0]
        text = c0.get("text", "") if isinstance(c0, dict) else str(c0)
    else:
        text = json.dumps(content)
    payload = json.loads(text)
    assert payload.get("error") == "RESOURCE_NOT_FOUND"
    assert payload.get("uri") == "dm://unknown/resource"


@pytest.mark.asyncio
async def test_des_1_tc_09_prompts_list_and_get(mcp_http_client, fake_provider):
    """[DM_MCP-des-1] DES-1-TC-09 Prompt 列表与获取（HTTP 入口）。"""
    from unittest.mock import AsyncMock

    ok_result = types.GetPromptResult(
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text="ok"),
            )
        ]
    )
    client, base_url = mcp_http_client
    hello_handler = AsyncMock(return_value=ok_result)
    fake_provider._prompt_handlers["hello"] = hello_handler

    resp = await _post_mcp(client, base_url, "prompts/list")
    assert resp.status_code == 200
    data = resp.json()
    assert "result" in data and "prompts" in data["result"]
    assert any(p.get("name") == "hello" for p in data["result"]["prompts"])

    resp2 = await _post_mcp(
        client,
        base_url,
        "prompts/get",
        params={"name": "hello", "arguments": {"x": "1"}},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    result = data2.get("result", {})
    messages = result.get("messages", [])
    assert messages
    first_content = (
        messages[0].get("content", {})
        if isinstance(messages[0], dict)
        else getattr(messages[0], "content", None)
    )
    if isinstance(first_content, dict):
        text = first_content.get("text", "")
    else:
        text = getattr(first_content, "text", None) or ""
    assert text == "ok"
    hello_handler.assert_awaited_once_with(x="1")

    # 未知 prompt
    resp3 = await _post_mcp(
        client,
        base_url,
        "prompts/get",
        params={"name": "not-exists", "arguments": None},
    )
    assert resp3.status_code == 200
    data3 = resp3.json()
    res3 = data3.get("result", {})
    msg3 = (res3.get("messages") or [None])[0]
    if msg3:
        c3 = (
            msg3.get("content", {})
            if isinstance(msg3, dict)
            else getattr(msg3, "content", None)
        )
        t3 = c3.get("text", "") if isinstance(c3, dict) else getattr(c3, "text", "")
        body = json.loads(t3) if isinstance(t3, str) and t3.startswith("{") else {}
        assert body.get("error") == "PROMPT_NOT_FOUND"
        assert body.get("prompt_name") == "not-exists"
