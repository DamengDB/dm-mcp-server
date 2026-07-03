"""全局上下文模块

提供全局上下文管理，统一管理所有服务的生命周期和依赖关系。
"""

import logging
from typing import Generic, TypeVar

from mcp.server import Server

from dm_mcp.core.service import ServiceRegistry
from dm_mcp.services import (
    AsyncPoolService,
    AsyncPoolServiceFactory,
    BasicAuthService,
    BasicAuthServiceFactory,
    DataSourceService,
    DataSourceServiceFactory,
    JwtService,
    JwtServiceFactory,
    LoggingService,
    LoggingServiceFactory,
    MCPService,
    MCPServiceFactory,
    MetricsService,
    MetricsServiceFactory,
    OAuthService,
    OAuthServiceFactory,
    TokenService,
    TokenServiceFactory,
)
from dm_mcp.services.base_service import ServiceProtocol
from dm_mcp.settings.settings import T_Settings

logger = logging.getLogger(__name__)


class GlobalContext(Generic[T_Settings]):
    """全局上下文

    使用服务注册表管理所有服务的生命周期和依赖关系。

    Attributes:
        settings: 全局配置
        registry: 服务注册表
    """

    def __init__(self, settings: T_Settings):
        """初始化全局上下文

        Args:
            settings: 全局配置
        """
        self.settings = settings
        self.registry = ServiceRegistry(settings)
        self._register_builtin_services()

    def _register_builtin_services(self) -> None:
        """注册所有内置服务

        注册日志、指标、JWT、OAuth、BasicAuth、Token、数据源、连接池、MCP等服务工厂。
        服务按依赖关系和优先级顺序注册。
        """
        builtin_factories = [
            LoggingServiceFactory(),
            MetricsServiceFactory(),
            JwtServiceFactory(),  # JWT 服务，优先级高，早于 OAuth 和 BasicAuth
            OAuthServiceFactory(),  # 依赖 JwtService
            BasicAuthServiceFactory(),  # 依赖 JwtService
            TokenServiceFactory(),  # 优先级高，早于其他需要认证的服务启动
            DataSourceServiceFactory(),  # 优先级高，早于连接池服务启动
            AsyncPoolServiceFactory(),
            MCPServiceFactory(),
        ]

        self.registry.register_factories(builtin_factories)

    # ============================================================
    # 属性访问
    # ============================================================

    @property
    def logging_service(self) -> LoggingService:
        """获取日志服务

        Returns:
            LoggingService: 日志服务实例
        """
        return self.registry.get_service("logging_service")

    @property
    def metrics_service(self) -> MetricsService:
        """获取指标服务

        Returns:
            MetricsService: 指标服务实例
        """
        return self.registry.get_service("metrics_service")

    @property
    def jwt_service(self) -> JwtService:
        """获取JWT服务

        Returns:
            JwtService: JWT服务实例
        """
        return self.registry.get_service("jwt_service")

    @property
    def oauth_service(self) -> OAuthService:
        """获取OAuth服务

        Returns:
            OAuthService: OAuth服务实例
        """
        return self.registry.get_service("oauth_service")

    @property
    def basic_auth_service(self) -> BasicAuthService:
        """获取BasicAuth服务

        Returns:
            BasicAuthService: BasicAuth服务实例
        """
        return self.registry.get_service("basic_auth_service")

    @property
    def token_service(self) -> TokenService:
        """获取Token服务

        Returns:
            TokenService: Token服务实例
        """
        return self.registry.get_service("token_service")

    @property
    def datasource_service(self) -> DataSourceService:
        """获取数据源管理服务

        Returns:
            DataSourceService: 数据源服务实例
        """
        return self.registry.get_service("datasource_service")

    @property
    def pool_service(self) -> AsyncPoolService:
        """获取连接池服务

        Returns:
            AsyncPoolService: 连接池服务实例
        """
        return self.registry.get_service("async_pool_service")

    @property
    def mcp_service(self) -> MCPService:
        """获取MCP服务

        Returns:
            MCPService: MCP服务实例
        """
        return self.registry.get_service("mcp_service")

    @property
    def mcp_sdk_server(self) -> Server:
        """获取MCP SDK Server

        Returns:
            Server: MCP SDK服务器实例
        """
        return self.mcp_service.sdk_server

    # ============================================================
    # 生命周期管理
    # ============================================================

    async def initialize_services(self) -> None:
        """初始化所有服务

        按依赖顺序获取所有服务，并依次调用它们的startup方法。
        如果某个服务初始化失败，会记录错误并抛出异常。

        Raises:
            Exception: 当服务初始化失败时
        """
        # 获取所有服务（按依赖顺序）
        services = self.registry.get_all()

        # 按顺序初始化
        for name, service in services.items():
            if isinstance(service, ServiceProtocol):
                logger.info(f"正在初始化服务: {name} ({type(service).__name__})")
                try:
                    await service.startup()
                    logger.info(f"服务 {name} 初始化完成")
                except Exception as e:
                    logger.critical(f"服务 {name} 初始化失败: {e}", exc_info=True)
                    raise e

    async def shutdown_services(self) -> None:
        """关闭所有服务

        按倒序获取所有已创建的服务，并依次调用它们的shutdown方法。
        如果某个服务关闭失败，会记录错误但不会中断关闭流程。
        """
        # 获取所有已创建的服务
        services = []
        for name in self.registry.factories.keys():
            try:
                service = self.registry.get_service(name)
                if service and isinstance(service, ServiceProtocol):
                    services.append((name, service))
            except:
                continue

        # 倒序关闭
        for name, service in reversed(services):
            logger.info(f"正在关闭服务: {name}")
            try:
                await service.shutdown()
                logger.info(f"服务 {name} 已关闭")
            except Exception as e:
                logger.error(f"关闭服务 {name} 时出错: {e}", exc_info=True)


T_Context = TypeVar("T_Context", bound=GlobalContext)
