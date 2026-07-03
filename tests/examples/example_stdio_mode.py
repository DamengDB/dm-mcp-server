import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# 配置服务器启动参数
server_params = StdioServerParameters(
    command="python",  # 执行的命令
    args=["src/main.py", "--server.transport", "stdio"],
    env=None,  # 如果需要环境变量可以在这里传
)


async def run_test():
    # 建立 stdio 连接
    async with stdio_client(server_params) as (read, write):
        # 创建会话 (自动处理握手)
        async with ClientSession(read, write) as session:

            # 1. 初始化 (Initialize)
            await session.startup()
            print("\n--- 连接成功 ---")

            # 2. 列出可用工具 (List Tools)
            tools = await session.list_tools()
            print(
                f"\n发现工具: {[f"{t.name}: {t.description}" for t in tools.tools] if hasattr(tools, 'tools') else str(tools)}"
            )

            # 3. 调用工具 (Call Tool)
            # 假设你的 server 有一个叫 "calculate_sum" 的工具
            tool_name = "calculate_sum"
            tool_args = {"a": 10, "b": 20}

            print(f"\n正在调用工具 {tool_name} 参数: {tool_args}...")

            try:
                result = await session.call_tool(tool_name, tool_args)

                # 打印结果文本
                if hasattr(result, "content"):
                    for content in result.content:
                        if content.type == "text":
                            print(f"工具返回: {content.text}")
                else:
                    print(f"原始返回: {result}")

            except Exception as e:
                print(f"调用失败: {e}")


if __name__ == "__main__":
    # 确保 server.py 在同一目录下
    asyncio.run(run_test())
