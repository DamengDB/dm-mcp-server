"""函数式MCP注册器模块

提供类似fastmcp的简洁API，用于函数式注册MCP工具、资源和提示词。
支持认证上下文、指标上下文和服务依赖注入。
"""

from typing import Any

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.core.mcp.router import MCPRouter
from dm_mcp.core.metrics.metrics_context import MetricsContext
from dm_mcp.core.service import ServiceRegistry


class MCPFunctionRegistry:
    """
    函数式 MCP 注册器 - 统一 API

    核心设计：
    - ✅ 直接注册：装饰器执行时立即注册到 router（无需延迟注册）
    - ✅ 多 workers 安全：每个 Worker 进程独立注册
    - ✅ 直接复用 MCPRouter 的装饰器（不重写）

    所有功能都集中在 mcp 对象中：
    - mcp.tool() / mcp.resource() / mcp.prompt() - 注册工具
    - mcp.auth - 认证上下文（与 BaseMCPProvider.auth 一致）
    - mcp.metrics - 指标上下文（与 BaseMCPProvider.metrics 一致）
    - mcp.get_service() - 获取服务依赖

    使用示例：
        server = MCPServer(...)

        @server.mcp.tool(requires_token_auth=True)
        async def db_query(sql: str, source: str = "auto"):
            registry = server.mcp.get_service('registry')
            user_id = server.mcp.auth.user_id
            metrics = QueryMetrics()
            server.mcp.metrics.record(metrics)
            ...
    """

    def __init__(self, router: MCPRouter, registry: ServiceRegistry):
        """
        初始化函数式 MCP 注册器

        Args:
            router: MCPRouter 实例，用于注册工具、资源和提示词
            registry: ServiceRegistry 实例，用于获取服务依赖
        """
        self._router = router
        self._registry = registry

    @property
    def router(self) -> MCPRouter:
        """访问内部的 MCPRouter 实例"""
        return self._router

    # ==========================
    # 装饰器 - 直接注册
    # ==========================

    def tool(self, *args, **kwargs):
        """工具装饰器

        所有参数和功能都与MCPRouter.tool完全一致：
        - name: 工具名称
        - description: 工具描述
        - exclude_args: 排除的参数
        - requires_token_auth: 是否需要Token认证

        Returns:
            Callable: 装饰器函数
        """
        return self._router.tool(*args, **kwargs)

    def resource(self, *args, **kwargs):
        """资源装饰器

        所有参数和功能都与MCPRouter.resource完全一致。

        Returns:
            Callable: 装饰器函数
        """
        return self._router.resource(*args, **kwargs)

    def prompt(self, *args, **kwargs):
        """Prompt装饰器

        所有参数和功能都与MCPRouter.prompt完全一致。

        Returns:
            Callable: 装饰器函数
        """
        return self._router.prompt(*args, **kwargs)

    # ==========================
    # 便捷方法 - 认证、指标、依赖注入
    # ==========================

    @property
    def context(self) -> MCPContext:
        """获取通用上下文对象

        与BaseMCPProvider.context一致，用于在工具函数中访问统一的上下文。

        Returns:
            MCPContext: 当前请求的 MCP 上下文（包含 auth、metrics、datasource 等）

        Examples:
            ctx = mcp.context
            if ctx.auth:
                user_id = ctx.auth.user_id
            if ctx.metrics:
                ctx.metrics.record(metrics)
        """
        return MCPContext.current()

    def get_service(self, name: str) -> Any:
        """
        获取服务依赖（在工具函数中使用）

        直接通过 ServiceRegistry 获取服务，利用依赖解析、缓存等特性。

        Args:
            name: 服务名称，如 'registry', 'metrics_service' 等

        Returns:
            服务实例

        Raises:
            ServiceNotFoundError: 当服务不存在时（由 ServiceRegistry 抛出）
        """
        return self._registry.get_service(name)

    @property
    def auth(self) -> AuthContext:
        """获取认证上下文

        与BaseMCPProvider.auth一致，用于在工具函数中访问认证信息。

        Returns:
            AuthContext: 当前请求的认证上下文

        Examples:
            user_id = mcp.auth.user_id
            allowed_datasources = mcp.auth.allowed_datasources
        """
        return AuthContext.get()

    @property
    def metrics(self) -> MetricsContext:
        """获取指标上下文

        与BaseMCPProvider.metrics一致，用于在工具函数中记录指标。

        Returns:
            MetricsContext: 当前请求的指标上下文

        Examples:
            metrics = QueryMetrics()
            metrics.query_count = 1
            mcp.metrics.record(metrics)
        """
        return MetricsContext.get()
