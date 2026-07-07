"""
提供服务功能：
- 基于 Uvicorn 的 HTTP 传输实现
- 支持 MCP 2025-03-26 协议的流式 HTTP 传输
- 多进程 Worker 支持
- 工厂函数动态加载
- 配置同步到环境变量
"""

from dm_mcp.common import messages

import importlib
import logging
import multiprocessing
import os
from typing import Callable

import uvicorn

from dm_mcp.app.server import MCPServer
from dm_mcp.domain.system.services.logging import LoggingService
from dm_mcp.infra.config import Settings
from dm_mcp.infra.transport import BaseTransport, T_ServerFactory

logger = logging.getLogger(__name__)


class StreamableHttpTransport(BaseTransport):
    """流式 HTTP 传输实现

    基于 Uvicorn 实现的 HTTP 传输层，支持 MCP 2025-03-26 协议的流式传输。

    主要功能：
    - 基于 Uvicorn 的 HTTP 服务器
    - 支持多进程 Worker 模式
    - 工厂函数动态加载（支持跨进程）
    - 配置同步到环境变量（供子进程使用）
    - 生命周期管理（启动和关闭）
    """

    def __init__(self, settings: Settings, factory: T_ServerFactory):
        """初始化流式 HTTP 传输

        Args:
            settings: 服务器设置
            factory: 服务器工厂函数
        """
        super().__init__(settings, factory)
        self.factory_import_str = self._resolve_import_string(factory)
        self.settings = settings

    def start(self):
        """启动 HTTP 传输服务

        准备环境并启动 Uvicorn 服务器，阻塞直到服务停止。
        此方法会：
        1. 同步配置到环境变量（供子进程使用）
        2. 设置工厂函数路径到环境变量
        3. 计算 Worker 数量
        4. 初始化日志系统
        5. 启动 Uvicorn 服务器
        """
        # 1. 将配置同步到环境变量
        # 这是为了让子进程(Worker)启动时能读到同样的配置
        self._sync_settings_to_env()

        # 2. 将工厂函数的路径写入环境变量
        # Uvicorn 的 Worker 进程将通过这个路径找到并执行 create_server
        os.environ["DM_MCP_FACTORY_REF"] = self.factory_import_str

        # 3. 计算 Workers 数量
        workers = self.settings.server.workers
        if workers <= 0:
            workers = multiprocessing.cpu_count()

        # 记录到环境变量供 create_app 使用
        os.environ["SERVER_WORKERS"] = str(workers)

        # 4. 初始化日志 (主进程)
        logging_service = LoggingService(self.settings.logging)
        logging_service.setup_logging()
        logger.info(
            f"HTTP 传输层准备启动 - 主机: {self.settings.server.host}, 端口: {self.settings.server.port}, Workers: {workers}"
        )

        # 5. 构造 Uvicorn 入口字符串
        # 指向本类的静态方法 create_app，而不是用户的 main.py
        app_target = f"{self.__module__}:{self.__class__.__name__}.create_app"

        try:
            logger.info("正在启动 Uvicorn 服务器...")
            uvicorn.run(
                app_target,
                host=self.settings.server.host,
                port=self.settings.server.port,
                workers=workers,
                factory=True,  # 告诉 Uvicorn 这是一个工厂方法
                log_config=logging_service.get_uvicorn_config(),
                lifespan="on",  # 显式开启生命周期管理
            )
        finally:
            logger.info("正在关闭 HTTP 传输层...")
            logging_service.close_logging()

    @classmethod
    def create_app(cls):
        """Worker 进程的引导加载器（Bootstrapper）

        Uvicorn 会在每个 Worker 子进程中调用此方法来获取 ASGI App。
        此方法会：
        1. 从环境变量获取工厂函数路径
        2. 动态导入并执行工厂函数
        3. 创建 MCPServer 实例
        4. 生成并返回 ASGI App

        Returns:
            ASGI 应用实例

        Raises:
            RuntimeError: 环境变量缺失或工厂函数加载失败
            TypeError: 工厂函数返回的对象不是 MCPServer 类型
        """

        # 1. 获取用户定义的 Factory 函数路径
        factory_ref = os.environ.get("DM_MCP_FACTORY_REF")
        if not factory_ref:
            raise RuntimeError(messages.MSG_TRANSPORT_FACTORY_REF_MISSING)

        # 2. 动态导入用户的 Factory 函数
        try:
            module_name, func_name = factory_ref.split(":")
            module = importlib.import_module(module_name)
            factory_func = getattr(module, func_name)
        except (ValueError, ImportError, AttributeError) as e:
            raise RuntimeError(messages.MSG_TRANSPORT_FACTORY_LOAD_FAILED.format(factory_ref=factory_ref, error=str(e)))

        # 3. 执行用户的 Factory，创建 MCPServer Facade 实例
        # 此时内部会构建 AppContext (Service Container)
        logger.info(f"Worker 进程正在加载服务器实例，工厂函数: {factory_ref}")
        server_instance = factory_func()

        if not isinstance(server_instance, MCPServer):
            raise TypeError(messages.MSG_TRANSPORT_FACTORY_TYPE_MISMATCH.format(type=type(server_instance)))

        # 4. 调用 Facade 的方法生成 ASGI App
        # 这里的 stateless 参数决定是否开启 Session 粘滞等逻辑
        workers = int(os.environ.get("SERVER_WORKERS", 1))
        use_stateless = workers > 1

        # !调试用，生产环境请根据实际情况设置
        # use_stateless = True

        logger.info(f"Worker 进程已创建 ASGI 应用，无状态模式: {use_stateless}")
        return server_instance.create_asgi_app(stateless=use_stateless)

    def _resolve_import_string(self, factory: Callable) -> str:
        """解析可调用的工厂函数为 'module:function' 格式的字符串

        将工厂函数转换为可序列化的导入路径字符串，用于跨进程传递。

        Args:
            factory: 工厂函数（可调用对象）

        Returns:
            'module:function' 格式的字符串，例如 'main:create_server'
        """
        if factory.__module__ == "__main__":
            # 如果是在 main.py 里定义的，需要获取文件名
            import os
            import sys

            try:
                # 获取脚本的主文件名 (去掉 .py)
                main_file = os.path.basename(sys.argv[0]).rsplit(".", 1)[0]
                return f"{main_file}:{factory.__name__}"
            except Exception:
                return f"__main__:{factory.__name__}"
        else:
            return f"{factory.__module__}:{factory.__name__}"

    def _sync_settings_to_env(self):
        """将 Pydantic 配置同步到环境变量

        将 Settings 对象中的配置项同步到环境变量，供子进程使用。
        注意：logging 相关配置会被跳过，避免字符串 Path 污染环境。
        """

        for key, value in self.settings.to_env().items():
            key = key.upper()

            # 不同步 logging 配置（调试时字符串 Path 污染环境）
            if key.startswith("LOGGING__"):
                continue

            # 普通字段转字符串
            os.environ[key] = str(value)
