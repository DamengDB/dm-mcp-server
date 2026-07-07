"""
函数式 MCP Provider：提供类似 fastmcp 的简洁 API
支持通过装饰器注册工具、资源和提示词
"""

from dm_mcp.core.mcp import BaseMCPProvider


class FunctionMCPProvider(BaseMCPProvider):
    """
    函数式 MCP Provider

    该 Provider 使用自己的 router（继承自 BaseMCPProvider），
    server.mcp 会使用这个 router，使得用户可以通过 `@server.mcp.tool` 等
    装饰器方式注册 MCP 工具、资源和提示词。

    示例：
        server = MCPServer(...)

        @server.mcp.tool(description="示例工具")
        async def my_tool(param: str):
            return {"result": param}

    """
