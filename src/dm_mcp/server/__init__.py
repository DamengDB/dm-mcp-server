"""服务器模块包

提供MCP服务器主类和相关功能，包括HTTP控制器、路由配置、全局上下文管理等。
"""

from .server import MCPServer

__all__ = [
    "MCPServer",
]
