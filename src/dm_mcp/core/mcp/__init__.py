"""MCP核心模块

提供MCP协议的核心组件，包括Provider基类、Router、Middleware和工具定义。
"""

from dm_mcp.domain.mcp.groups import CliGroupEntry, CliGroupRegistry
from .middleware import BaseMCPMiddleware
from .provider import BaseMCPProvider
from .router import MCPRouter, ToolDefinition

__all__ = [
    # Provider 相关
    "BaseMCPProvider",
    # 中间件
    "BaseMCPMiddleware",
    # 路由
    "MCPRouter",
    "ToolDefinition",
    # CLI 分组元数据（与 MCP 运行时解耦）
    "CliGroupRegistry",
    "CliGroupEntry",
]
