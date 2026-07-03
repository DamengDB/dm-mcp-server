import logging

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions.auth_errors import AuthorizationError
from dm_mcp.core.mcp.middleware import BaseMCPMiddleware, NextCallable
from dm_mcp.core.mcp.tool import ToolDefinition
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.mcp_service import MCPService

logger = logging.getLogger(__name__)

# 常量定义
SOURCE_AUTO = "auto"
AUTH_TYPE_TOKEN = "token"


class TokenAuthMCPMiddleware(BaseMCPMiddleware):
    """Token 认证 MCP 中间件：验证工具调用的数据源权限

    只对需要 token 认证（requires_token_auth=True）的工具进行验证。
    如果认证类型不是 token（例如 stdio 模式下的 anonymous），则跳过验证。
    """

    def __init__(
        self,
        datasource_service: DataSourceService,
        mcp_service: MCPService,
    ) -> None:
        self.datasource_service = datasource_service
        self.mcp_service = mcp_service

    async def on_call_tool(self, call_next: NextCallable, name: str, arguments: dict):
        """
        验证工具调用是否具备 Token 级权限。

        现在的职责仅包括：
        - 判断工具是否声明 requires_token_auth
        - 判断当前请求是否存在 AuthContext 且 auth_type == "token"
        满足条件后，直接将调用传递给下一个处理器，不再基于数据源做任何授权判断。

        Args:
            call_next: 下一个中间件或最终处理函数
            name: 工具名称
            arguments: 工具参数

        Returns:
            工具调用的结果

        Raises:
            AuthorizationError: 当缺少有效的 Token 认证时
        """
        # 查询工具定义，检查是否需要 Token 认证
        tool_def = self.mcp_service.get_tool_definition(name)
        if not tool_def or not tool_def.requires_token_auth:
            return await call_next(name, arguments)

        # 获取认证上下文（如果不存在则拒绝访问）
        try:
            auth_context = AuthContext.get()
        except ValueError:
            # 如果工具需要 token 认证但没有认证上下文，拒绝访问
            logger.warning(
                f"Tool '{name}' requires token auth but no auth context available"
            )
            raise AuthorizationError(
                f"Tool '{name}' requires token authentication. "
                "Please provide a valid token in the Authorization header."
            )

        # 只对 Token 认证类型进行验证
        # stdio 模式下会创建 anonymous 类型的上下文，此时跳过验证
        if auth_context.auth_type != AUTH_TYPE_TOKEN:
            logger.debug(
                f"Tool '{name}' requires token auth but current auth type is "
                f"'{auth_context.auth_type}' (e.g., stdio mode), skipping token auth check"
            )
            return await call_next(name, arguments)

        return await call_next(name, arguments)
