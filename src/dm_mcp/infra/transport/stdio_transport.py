"""标准输入输出（STDIO）传输模块

提供服务功能：
- 基于标准输入输出的传输实现
- 用于本地进程间通信
- 符合 MCP 协议规范
- 支持指标监控 HTTP 服务器（可选）
"""

import asyncio
import logging
from typing import override

import uvicorn
from mcp.server.stdio import stdio_server

from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.infra.config.settings import Settings
from dm_mcp.infra.transport import BaseTransport, T_ServerFactory

logger = logging.getLogger(__name__)


class StdioTransport(BaseTransport):
    """标准输入输出（STDIO）传输实现

    基于标准输入输出的传输层，用于本地进程间通信，符合 MCP 协议。

    主要功能：
    - 通过标准输入输出进行进程间通信
    - 符合 MCP 协议规范
    - 支持指标监控 HTTP 服务器（可选）
    - 异步运行 MCP 服务器
    """

    def __init__(self, settings: Settings, factory: T_ServerFactory) -> None:
        """初始化 STDIO 传输

        Args:
            settings: 服务器设置
            factory: 服务器工厂函数
        """
        super().__init__(settings, factory)
        self.server = factory()

    @override
    def start(self):
        """启动 STDIO 传输服务

        启动标准输入输出传输服务，阻塞直到服务停止。
        此方法会运行异步的 _start 方法，并在完成后退出。

        Returns:
            不会返回，直接退出进程
        """
        exit_code = asyncio.run(self._start())
        exit(exit_code)

    async def _start(self):
        """启动 STDIO 传输模式（异步实现）

        创建 stdio_server 传输，运行 MCP 服务器，并可选地启动指标监控 HTTP 服务器。

        Returns:
            退出代码（0 表示成功）

        Raises:
            Exception: 服务器启动失败
        """
        logger.info("正在启动 MCP 服务器 (stdio 模式)")

        try:
            logger.info("正在创建 stdio_server 传输...")

            # 启动 web api 服务

            app = self.server.create_asgi_app(stateless=True)

            config = uvicorn.Config(
                app,
                host=self.server.settings.server.host,
                port=self.server.settings.server.port,
                log_config=None,  # 如需可复用 LoggingService 的配置
                lifespan="on",
            )
            http_server = uvicorn.Server(config)
            # 注意：Server.serve() 是协程，用一个后台 task 跑
            http_task = asyncio.create_task(http_server.serve())
            logger.info(
                "已在 stdio 模式下启动 HTTP Web API，地址: %s:%s",
                self.server.settings.server.host,
                self.server.settings.server.port,
            )

            # 初始化服务器（启动服务，初始化数据库等）
            await self.server.startup()
            logger.info("服务器初始化完成")

            async with stdio_server() as streams:
                read_stream, write_stream = streams
                logger.info("stdio_server 流已创建成功")

                skd_server = self.server.context.mcp_sdk_server

                # 创建初始化选项
                init_options = skd_server.create_initialization_options()
                logger.info("初始化选项已创建")

                # 构建 stdio 模式的请求上下文
                ctx = await MCPContext.build_for_stdio(
                    self.server.settings, self.server.context.datasource_service
                )

                # 运行服务器（在请求上下文中）
                logger.info("MCP 服务器正在运行...")
                with MCPContext.as_current(ctx):
                    await skd_server.run(read_stream, write_stream, init_options)

                if self.server.settings.metrics.enabled:
                    logger.info("正在启动指标监控 HTTP 服务器...")
                    self.server.context.metrics_service.start_http_server()
                    logger.info("指标监控 HTTP 服务器已启动")

        except Exception as e:
            logger.error(f"stdio 服务器启动失败: {e}", exc_info=True)
            raise
        finally:
            # 确保服务器正确关闭
            try:
                await self.server.shutdown()
                logger.info("服务器关闭完成")
            except Exception as shutdown_error:
                logger.error(f"服务器关闭时发生错误: {shutdown_error}", exc_info=True)
