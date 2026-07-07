"""HTTP 认证上下文桥接中间件

拦截 Starlette AuthenticationMiddleware 解析出的 request.user，
将其内部的 auth_context 提取并写入 contextvars。
从而打通 HTTP 链路与底层 Service 隐式获取上下文的通道。
"""

from datetime import datetime, timezone

from starlette.types import ASGIApp, Receive, Scope, Send

from dm_mcp.core.auth.auth_context import AuthContext


class AuthContextSyncMiddleware:
    """HTTP 认证上下文桥接中间件

    放在 AuthenticationMiddleware 之后、AuditHTTPMiddleware 之前。
    将 ASGI scope 中的 user.auth_context 同步到 AuthContext contextvar，
    使下游的 Controller 和 Service 都能通过 AuthContext.get() 获取当前用户。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        user = scope.get("user")
        auth_context = getattr(user, "auth_context", None)

        if not auth_context:
            auth_context = AuthContext(
                user_id="anonymous",
                login_time=datetime.now(timezone.utc),
                last_activity=datetime.now(timezone.utc),
                token=None,
                auth_type="anonymous",
            )

        with AuthContext.as_current(auth_context):
            await self.app(scope, receive, send)
