from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from dm_mcp.core.exceptions import AuthorizationError
from dm_mcp.middlewares.audit_middleware import AuditMCPMiddleware
from dm_mcp.server.controllers.mcp_controller import MCPController
from dm_mcp.server.middlewares.audit_http_middleware import AuditHTTPMiddleware
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.logging_service import LoggingService
from dm_mcp.settings import Settings


@pytest.mark.asyncio
async def test_des_5_tc_01_mcp_http_unauthenticated_returns_403(mock_settings):
    """[DM_MCP-des-5][DM_MCP-des-sec-1] DES-5-TC-01 未认证 MCP 请求返回 403。"""
    session_manager = MagicMock()
    session_manager.handle_request = AsyncMock()
    controller = MCPController(
        session_manager, mock_settings, MagicMock(spec=DataSourceService)
    )

    scope: Dict[str, Any] = {
        "type": "http",
        "path": "/dm-mcp/mcp/messages",
        "auth": None,
        "user": None,
    }

    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        return {"type": "http.request"}

    await controller.handle_request(scope, receive, send)

    http_response = next(m for m in messages if m["type"] == "http.response.start")
    assert http_response["status"] == AuthorizationError().status_code


@pytest.mark.asyncio
async def test_des_5_tc_02_mcp_http_authenticated_delegates_to_session_manager(
    mock_settings,
):
    """[DM_MCP-des-5][DM_MCP-des-sec-1] DES-5-TC-02 认证通过时转发给 SessionManager。"""
    session_manager = MagicMock()
    session_manager.handle_request = AsyncMock()
    controller = MCPController(
        session_manager, mock_settings, MagicMock(spec=DataSourceService)
    )

    auth = MagicMock()
    auth.scopes = ["authenticated"]
    user = MagicMock()

    scope: Dict[str, Any] = {
        "type": "http",
        "path": "/dm-mcp/mcp/messages",
        "auth": auth,
        "user": user,
    }

    async def send(_):
        return None

    async def receive():
        return {"type": "http.request"}

    # Patch MCPContext.build_for_http 以避免真实依赖
    from dm_mcp.core.mcp.context import MCPContext

    ctx = MagicMock()
    ctx.auth = MagicMock()
    ctx.auth.user_id = "u1"
    MCPContext.build_for_http = AsyncMock(return_value=ctx)  # type: ignore[assignment]

    await controller.handle_request(scope, receive, send)
    session_manager.handle_request.assert_awaited_once()


@pytest.mark.asyncio
async def test_des_5_tc_03_audit_mcp_middleware_logs_tool_calls(monkeypatch):
    """[DM_MCP-des-sec-3] DES-5-TC-03 AuditMCPMiddleware 记录工具调用审计日志。"""
    logging_service = MagicMock(spec=LoggingService)
    audit_logger = MagicMock()
    logging_service.get_audit_logger.return_value = audit_logger

    mw = AuditMCPMiddleware(audit_enabled=True, logging_service=logging_service)

    async def fake_next(name, arguments):
        return "ok"

    result = await mw.on_call_tool(fake_next, "test_tool", {"a": 1})
    assert result == "ok"
    audit_logger.info.assert_called()
    msg = audit_logger.info.call_args[0][0]
    assert "test_tool" in msg
    # 未显式设置认证上下文时，会回落到 anonymous 用户
    assert "用户: anonymous" in msg


@pytest.mark.asyncio
async def test_des_5_tc_04_audit_http_middleware_masks_sensitive_fields(monkeypatch):
    """[DM_MCP-des-sec-3] DES-5-TC-04 AuditHTTPMiddleware 对敏感字段脱敏。"""
    app = MagicMock()
    logging_service = MagicMock(spec=LoggingService)
    audit_logger = MagicMock()
    logging_service.get_audit_logger.return_value = audit_logger

    middleware = AuditHTTPMiddleware(
        app=app,
        audit_enabled=True,
        logging_service=logging_service,
        base_url="/dm-mcp",
    )

    async def app_call(scope, receive, send):
        response = Response(content=b"OK", status_code=200)
        await response(scope, receive, send)

    app.__call__ = app_call  # type: ignore[assignment]

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/dm-mcp/api/v1/tokens",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
    }

    async def receive():
        import json

        body = json.dumps(
            {
                "name": "test",
                "password": "secret-password",
                "token": "abcdef1234567890",
            }
        ).encode("utf-8")
        return {"type": "http.request", "body": body, "more_body": False}

    # 避免在未安装 AuthenticationMiddleware 时访问 request.user 触发断言，
    # 通过模拟认证上下文让中间件不再访问 request.user。
    from dm_mcp.server.middlewares import audit_http_middleware as audit_mod

    class _AuthCtx:
        user_id = "u1"
        auth_type = "token"

    monkeypatch.setattr(audit_mod.AuthContext, "get", lambda: _AuthCtx())

    request = Request(scope, receive)

    async def call_next(req: Request):
        return Response("OK", status_code=200)

    await middleware.dispatch(request, call_next)

    audit_logger.info.assert_called()
    logged = audit_logger.info.call_args[0][0]
    # 敏感字段被脱敏，不应包含完整密码或 token
    assert "secret-password" not in logged
    assert "abcdef1234567890" not in logged


@pytest.mark.asyncio
async def test_des_5_tc_05_audit_http_middleware_skips_health_and_static(monkeypatch):
    """[DM_MCP-des-sec-3] DES-5-TC-05 AuditHTTPMiddleware 对静态资源和健康检查不记审计。"""
    app = MagicMock()
    logging_service = MagicMock(spec=LoggingService)
    audit_logger = MagicMock()
    logging_service.get_audit_logger.return_value = audit_logger

    middleware = AuditHTTPMiddleware(
        app=app,
        audit_enabled=True,
        logging_service=logging_service,
        base_url="/dm-mcp",
    )

    async def call_next(req: Request):
        return Response("OK", status_code=200)

    # /static
    for path in ["/dm-mcp/static/app.js", "/dm-mcp/health"]:
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(scope, receive)
        audit_logger.info.reset_mock()

        await middleware.dispatch(request, call_next)
        audit_logger.info.assert_not_called()
