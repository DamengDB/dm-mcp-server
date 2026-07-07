"""应用程序入口模块

提供应用程序的启动入口，初始化MCP服务器并运行。
"""

from dm_mcp.app.server import MCPServer


def create_server() -> MCPServer:
    """创建MCP服务器实例

    Returns:
        MCPServer: MCP服务器实例
    """
    server = MCPServer()
    return server


def main():
    """主函数

    启动MCP服务器，使用create_server工厂函数创建服务器实例。
    """
    MCPServer.run(create_server)


if __name__ == "__main__":
    main()
