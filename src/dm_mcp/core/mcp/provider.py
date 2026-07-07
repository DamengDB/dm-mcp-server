"""MCP Provider基类模块

提供MCP Provider的抽象基类，用于将业务能力暴露为MCP工具、资源和提示词。
"""

from abc import ABC
from typing import Any

from mcp import Resource, Tool, types
from pydantic import AnyUrl

from dm_mcp.common import messages
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext

from .router import MCPRouter


class BaseMCPProvider(ABC):
    """MCP Provider基类

    所有MCP Provider的抽象基类，提供统一的接口来访问统一的 MCPContext，
    以及注册和管理MCP工具、资源和提示词。

    子类应继承此类并实现具体的业务逻辑，通过MCPRouter来注册工具、资源和提示词。
    """

    def __init__(self) -> None:
        self.mcp = MCPRouter()

    @property
    def context(self) -> MCPContext:
        """获取当前 MCP 统一上下文

        Returns:
            MCPContext: 当前请求的 MCP 上下文（包含 auth、metrics 及扩展上下文）
        """
        return MCPContext.current()

    # 兼容旧用法：保留 auth / metrics 属性，但实现基于 MCPContext
    @property
    def auth(self) -> AuthContext:
        """获取当前认证上下文（向后兼容）

        Returns:
            AuthContext: 当前请求的认证上下文

        Raises:
            ValueError: 如果当前请求没有设置认证上下文
        """
        ctx = MCPContext.current()
        if ctx.auth is None:
            raise ValueError(messages.MSG_AUTH_NO_AUTH_CONTEXT)
        return ctx.auth

    @property
    def metrics(self) -> MetricsContext:
        """获取当前指标上下文（向后兼容）

        Returns:
            MetricsContext: 当前请求的指标上下文

        Raises:
            ValueError: 如果当前请求没有设置指标上下文
        """
        ctx = MCPContext.current()
        if ctx.metrics is None:
            raise ValueError(messages.MSG_AUTH_NO_METRICS_CONTEXT)
        return ctx.metrics

    def list_prompts(self) -> list[types.Prompt]:
        """列出所有可用的提示词

        Returns:
            list[types.Prompt]: 提示词列表
        """
        return self.mcp.list_prompts()

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> types.GetPromptResult:
        """获取指定的提示词

        Args:
            name: 提示词名称
            arguments: 提示词参数（可选）

        Returns:
            types.GetPromptResult: 提示词结果
        """
        return await self.mcp.get_prompt(name, arguments)

    def list_resources(self) -> list[Resource]:
        """列出所有静态资源

        Returns:
            list[Resource]: 静态资源列表
        """
        return self.mcp.list_resources()

    def list_resource_templates(self) -> list[types.ResourceTemplate]:
        """列出所有资源模板

        Returns:
            list[types.ResourceTemplate]: 资源模板列表
        """
        return self.mcp.list_resource_templates()

    async def read_resource(self, uri: AnyUrl | str) -> str:
        """读取指定URI的资源

        Args:
            uri: 资源URI

        Returns:
            str: 资源内容
        """
        return await self.mcp.read_resource(uri)

    def list_tools(self) -> list[Tool]:
        """列出所有可用的工具

        Returns:
            list[Tool]: 工具列表
        """
        return self.mcp.list_tools()

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """调用指定的工具

        Args:
            name: 工具名称
            args: 工具参数

        Returns:
            dict[str, Any]: 工具执行结果
        """
        return await self.mcp.call_tool(name, args)

    async def startup(self) -> None:
        """Provider启动钩子

        子类可以覆盖此方法，在Provider启动时执行初始化操作，
        例如从数据库加载配置、注册动态工具等。

        此方法会在 MCPService.startup() 阶段被调用。
        """
        pass

    async def shutdown(self) -> None:
        """Provider关闭钩子

        子类可以覆盖此方法，在Provider关闭时执行清理操作。

        此方法会在 MCPService 关闭时被调用。
        """
        pass
