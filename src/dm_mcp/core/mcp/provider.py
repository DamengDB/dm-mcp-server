"""MCP Provider基类模块

提供MCP Provider的抽象基类，用于将业务能力暴露为MCP工具、资源和提示词。
"""

from abc import ABC
from typing import Any, Dict, List

from mcp import Resource, Tool, types
from pydantic import AnyUrl

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.core.metrics.metrics_context import MetricsContext

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
            raise ValueError("No auth context set")
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
            raise ValueError("No metrics context set")
        return ctx.metrics

    def list_prompts(self) -> List[types.Prompt]:
        """列出所有可用的提示词

        Returns:
            List[types.Prompt]: 提示词列表
        """
        return self.mcp.list_prompts()

    async def get_prompt(
        self, name: str, arguments: Dict[str, Any] | None = None
    ) -> types.GetPromptResult:
        """获取指定的提示词

        Args:
            name: 提示词名称
            arguments: 提示词参数（可选）

        Returns:
            types.GetPromptResult: 提示词结果
        """
        return await self.mcp.get_prompt(name, arguments)

    def list_resources(self) -> List[Resource]:
        """列出所有静态资源

        Returns:
            List[Resource]: 静态资源列表
        """
        return self.mcp.list_resources()

    def list_resource_templates(self) -> List[types.ResourceTemplate]:
        """列出所有资源模板

        Returns:
            List[types.ResourceTemplate]: 资源模板列表
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

    def list_tools(self) -> List[Tool]:
        """列出所有可用的工具

        Returns:
            List[Tool]: 工具列表
        """
        return self.mcp.list_tools()

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定的工具

        Args:
            name: 工具名称
            args: 工具参数

        Returns:
            Dict[str, Any]: 工具执行结果
        """
        return await self.mcp.call_tool(name, args)
