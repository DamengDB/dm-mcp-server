"""MCP控制器模块

提供MCP协议请求处理，包括认证验证和会话管理。
"""

import logging
from typing import Optional

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from dm_mcp.core.exceptions import AuthorizationError
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.settings import Settings

logger = logging.getLogger(__name__)


class MCPController(object):
    """MCP控制器

    处理MCP协议的ASGI请求，包括认证验证、上下文设置和会话管理。
    注意：由于ASGI请求的特性，不能使用@requires装饰器，需要手动验证认证。
    """

    def __init__(
        self,
        session_manager: StreamableHTTPSessionManager,
        settings: Settings,
        datasource_service: Optional[DataSourceService] = None,
    ) -> None:
        """初始化MCP控制器

        Args:
            session_manager: MCP流式HTTP会话管理器
            settings: 服务器设置
            datasource_service: 数据源服务（可选，用于解析默认数据源）
        """
        self.session_manager = session_manager
        self.settings = settings
        self.datasource_service = datasource_service

    # @requires('authenticated') 不兼容 asgi 请求，只能手动包裹认证检测功能
    async def handle_request(self, scope: Scope, receive: Receive, send: Send):
        """处理MCP ASGI请求

        验证用户认证，设置认证上下文和指标上下文，然后转发给会话管理器处理。

        Args:
            scope: ASGI scope对象
            receive: ASGI receive函数
            send: ASGI send函数

        Raises:
            AuthorizationError: 当用户未认证时
        """
        path = scope.get("path", "unknown")
        try:
            auth_credentials = scope.get("auth", None)
            auth_user = scope.get("user", None)

            if (
                auth_credentials is None
                or "authenticated" not in auth_credentials.scopes
            ):
                logger.warning(f"MCP 请求认证失败: {path}")
                raise AuthorizationError("Authentication required for MCP endpoint")

            # 构建 HTTP 模式的请求上下文
            ctx = await MCPContext.build_for_http(
                auth_user, self.settings, self.datasource_service
            )

            user_id = ctx.auth.user_id if ctx.auth else "anonymous"
            logger.info(f"处理 MCP 请求: {path}, 用户: {user_id}")

            with MCPContext.as_current(ctx):
                await self.session_manager.handle_request(scope, receive, send)

            logger.debug(f"MCP 请求处理完成: {path}")

        except AuthorizationError as e:
            logger.warning(f"MCP 请求认证错误: {path}, 错误: {e.message}")
            response = JSONResponse(
                {"error": e.error_code, "message": e.message}, status_code=e.status_code
            )
            await response(scope, receive, send)
        except Exception as e:
            logger.error(f"MCP 请求处理失败: {path}, 错误: {str(e)}", exc_info=True)
            response = JSONResponse(
                {"error": "INTERNAL_ERROR", "message": "Internal server error"},
                status_code=500,
            )
            await response(scope, receive, send)
