"""MCP服务器主类模块

提供MCP服务器的主类实现，负责服务器的初始化、生命周期管理、Provider和中间件的加载。
"""

import logging
from contextlib import asynccontextmanager
from typing import Callable, Generic, Type

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.cors import CORSMiddleware

from dm_mcp.common import messages
from dm_mcp.core.mcp import BaseMCPMiddleware, BaseMCPProvider
from dm_mcp.domain.mcp.middleware import (
    AuditMCPMiddleware,
    MetricsMCPMiddleware,
    TokenAuthMCPMiddleware,
)
from dm_mcp.domain.mcp.providers.cluster import DpcClusterMCPProvider
from dm_mcp.domain.mcp.providers.function import FunctionMCPProvider
from dm_mcp.domain.mcp.providers.data import DataMCPProvider
from dm_mcp.domain.mcp.providers.generic_sql import GenericSqlMCPProvider
from dm_mcp.domain.mcp.providers.inspection import InspectionMCPProvider
from dm_mcp.domain.mcp.providers.metadata import MetadataMCPProvider
from dm_mcp.domain.mcp.providers.query_exec import QueryExecMCPProvider
from dm_mcp.domain.mcp.registry import MCPFunctionRegistry
from dm_mcp.infra.middleware import ExceptionHandlerMiddleware
from dm_mcp.infra.middleware.audit_http import AuditHTTPMiddleware
from dm_mcp.infra.middleware.auth_context_sync import AuthContextSyncMiddleware
from dm_mcp.infra.middleware.utf8 import UTF8ResponseMiddleware
from dm_mcp.infra.config.settings import Settings, T_Settings

from .auth_backend import AuthBackend
from .context import GlobalContext, T_Context

#
logger = logging.getLogger(__name__)


class MCPServer(Generic[T_Settings, T_Context]):
    """MCP服务器主类

    负责MCP服务器的初始化和生命周期管理，包括加载Provider、中间件、
    创建ASGI应用等功能。支持通过传输层（stdio或HTTP）启动服务器。

    Type Parameters:
        T_Settings: 设置类类型
        T_Context: 上下文类类型
    """

    def __init__(
        self,
        settings_cls: Type[T_Settings] = Settings,
        context_cls: Type[T_Context] = GlobalContext,
    ) -> None:
        """初始化MCP服务器

        Args:
            settings_cls: 设置类（默认Settings）
            context_cls: 上下文类（默认GlobalContext）
        """
        self.settings: T_Settings = settings_cls()
        self.context: T_Context = context_cls(self.settings)

        self._startup_hooks: list[Callable] = []
        self._shutdown_hooks: list[Callable] = []

        self._load_mcp_providers()
        self._load_mcp_middlewares()

    def _load_mcp_middlewares(self) -> None:
        """加载默认的MCP中间件

        加载指标、Token认证、审计等中间件。
        """
        middlewares = [
            MetricsMCPMiddleware(self.context.metrics_service),
            TokenAuthMCPMiddleware(
                self.context.datasource_service,
                self.context.mcp_service,
            ),
            AuditMCPMiddleware(
                self.settings.server.audit_enabled, self.context.logging_service
            ),
        ]
        self.add_mcp_middlewares(middlewares)
        logger.info(f"已加载 {len(middlewares)} 个 MCP 中间件")

    def _load_mcp_providers(self) -> None:
        """加载MCP提供者

        加载函数式Provider和连接池Provider。
        """
        # 创建函数式 MCP Provider（它会有自己的 router）
        function_provider = FunctionMCPProvider()

        # 使用 FunctionMCPProvider 的 router 创建函数式注册器
        self.mcp = MCPFunctionRegistry(
            router=function_provider.mcp, registry=self.context.registry
        )

        # 创建 GenericSqlProvider 并设置回调
        generic_sql_provider = GenericSqlMCPProvider(
            self.context.datasource_service,
        )

        providers = [
            function_provider,
            MetadataMCPProvider(
                self.context.datasource_service,
                self.context.db_config_service,
                self.context.db_metadata_service,
            ),
            QueryExecMCPProvider(
                self.context.datasource_service,
            ),
            DpcClusterMCPProvider(
                self.context.datasource_service,
            ),
            InspectionMCPProvider(
                self.context.datasource_service,
            ),
            DataMCPProvider(
                self.context.datasource_service,
            ),
            generic_sql_provider,
        ]
        self.add_mcp_providers(providers)

        # 设置刷新回调，避免循环依赖
        generic_sql_provider.set_refresh_callback(
            lambda: self.context.mcp_service.clear_caches()
        )

        logger.info(f"已加载 {len(providers)} 个 MCP Provider")

    # =================================================
    # 生命周期管理
    # =================================================
    async def startup(self) -> None:
        """服务器启动方法

        初始化所有服务并执行启动钩子函数。
        """
        logger.info("正在启动 MCP 服务器...")
        await self.context.initialize_services()
        logger.info(f"正在执行 {len(self._startup_hooks)} 个启动钩子函数")
        for hook in self._startup_hooks:
            await hook()
        logger.info("MCP 服务器启动完成")

    async def shutdown(self) -> None:
        """服务器关闭方法

        关闭所有服务并执行关闭钩子函数。
        """
        logger.info("正在关闭 MCP 服务器...")
        await self.context.shutdown_services()
        logger.info(f"正在执行 {len(self._shutdown_hooks)} 个关闭钩子函数")
        for hook in self._shutdown_hooks:
            await hook()
        logger.info("MCP 服务器已关闭")

    # =================================================
    # 属性管理
    # =================================================
    def add_mcp_provider(self, provider: BaseMCPProvider) -> None:
        """注册MCP提供者

        Args:
            provider: MCP提供者实例
        """
        self.context.mcp_service.add_mcp_provider(provider)

    def add_mcp_providers(self, providers: list[BaseMCPProvider]) -> None:
        """批量注册MCP提供者

        Args:
            providers: MCP提供者列表
        """
        self.context.mcp_service.add_mcp_providers(providers)

    def add_mcp_middleware(self, middleware: BaseMCPMiddleware) -> None:
        """注册MCP中间件

        Args:
            middleware: MCP中间件实例
        """
        self.context.mcp_service.add_mcp_middleware(middleware)

    def add_mcp_middlewares(self, middlewares: list[BaseMCPMiddleware]) -> None:
        """批量注册MCP中间件

        Args:
            middlewares: MCP中间件列表
        """
        self.context.mcp_service.add_mcp_middlewares(middlewares)

    # =================================================
    # worker 入口
    # =================================================
    def create_asgi_app(self, stateless: bool = False):
        """将MCPServer实例包裹成ASGI应用

        创建Starlette应用，配置路由、中间件和生命周期管理。

        Args:
            stateless: 是否使用无状态模式（默认False）

        Returns:
            Starlette: ASGI应用实例
        """
        # 创建 MCP Session Manager
        session_manager = StreamableHTTPSessionManager(
            app=self.context.mcp_sdk_server,
            json_response=True,
            stateless=stateless,
        )

        # 定义生命周期 (Lifespan)
        @asynccontextmanager
        async def lifespan(app):
            await self.startup()
            async with session_manager.run():
                yield
            await self.shutdown()

        # 创建 Starlette 应用
        from .routes import get_routes

        starlette_app = Starlette(
            debug=self.settings.server.debug,
            routes=get_routes(self.context, session_manager),
            middleware=self._get_http_middlewares(),
            lifespan=lifespan,
        )

        return starlette_app

    def _get_http_middlewares(self):
        """获取HTTP中间件列表

        返回无状态架构的中间件列表。
        注意：已移除 SessionMiddleware，OAuth state 现在通过加密 Cookie 存储（无状态模式）。

        Returns:
            list[Middleware]: HTTP中间件列表，包括UTF-8、异常处理、CORS、认证等
        """
        return [
            # UTF-8 响应头中间件（最先执行，确保所有响应都包含 UTF-8 字符集）
            Middleware(UTF8ResponseMiddleware),
            Middleware(
                ExceptionHandlerMiddleware,
            ),
            Middleware(
                CORSMiddleware,
                allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",  # 允许的源
                allow_methods=["*"],  # 允许所有 HTTP 方法（包含 OPTIONS preflight）
                allow_headers=["*"],  # 允许所有 HTTP 头
                allow_credentials=True,  # 是否允许携带 Cookie/凭证
            ),
            # 注意：已移除 SessionMiddleware，实现真正的无状态架构
            # OAuth state 现在通过加密的 Cookie 存储（在 OAuthService 中处理）
            Middleware(
                AuthenticationMiddleware,
                backend=AuthBackend(
                    self.settings,
                    self.context.oauth_service,
                    self.context.auth_config_service,
                    self.context.token_service,
                    self.context.datasource_service,
                ),
                on_error=AuthBackend.on_error,
            ),
            # 将 Starlette 认证结果同步到 AuthContext contextvar，
            # 使下游 Controller 和 Service 都能通过 AuthContext.get() 获取当前用户
            Middleware(AuthContextSyncMiddleware),
            # HTTP 审计中间件（在认证之后，记录所有已认证和未认证的关键操作）
            Middleware(
                AuditHTTPMiddleware,
                audit_enabled=self.settings.server.audit_enabled,
                logging_service=self.context.logging_service,
                base_url=self.settings.server.base_url,
            ),
        ]

    @classmethod
    def run(
        cls,
        factory: Callable[[], "MCPServer"],
        settings_cls: Type[T_Settings] = Settings,
    ):
        """运行MCP服务器

        根据配置选择传输方式（stdio或HTTP），创建传输实例并启动服务器。

        Args:
            factory: 服务器工厂函数，用于创建MCPServer实例
            settings_cls: 设置类（默认Settings）

        Raises:
            ValueError: 当传输方式不支持时
        """
        settings = settings_cls()
        logger.info(f"使用传输方式: {settings.server.transport}")

        if settings.server.transport == "stdio":
            from dm_mcp.infra.transport.stdio_transport import StdioTransport

            transport = StdioTransport(settings, factory)
        elif settings.server.transport == "http":
            from dm_mcp.infra.transport.http_transport import StreamableHttpTransport

            transport = StreamableHttpTransport(settings, factory)
        else:
            raise ValueError(messages.MSG_UNKNOWN_TRANSPORT.format(transport=settings.server.transport))

        # 启动
        logger.info("正在启动传输层...")
        transport.start()

    # =================================================
    # 装饰器
    # =================================================
    def on_startup(self, func: Callable) -> Callable:
        """装饰器：注册服务器启动时的回调函数

        回调函数将在context.startup_services()之后执行。

        Args:
            func: 回调函数

        Returns:
            Callable: 原函数，支持装饰器链式调用
        """
        self._startup_hooks.append(func)
        return func

    def on_shutdown(self, func: Callable) -> Callable:
        """装饰器：注册服务器关闭时的回调函数

        回调函数将在context.shutdown_services()之前执行。

        Args:
            func: 回调函数

        Returns:
            Callable: 原函数，支持装饰器链式调用
        """
        self._shutdown_hooks.append(func)
        return func
