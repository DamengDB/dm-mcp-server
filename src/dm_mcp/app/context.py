"""全局上下文模块

提供全局上下文管理，统一管理所有服务的生命周期和依赖关系。
"""

import logging
from typing import Any, Generic, TypeVar

from mcp.server import Server

from dm_mcp.core.service import ServiceRegistry
from dm_mcp.domain.auth.services.auth_config import AuthConfigService, AuthConfigServiceFactory
from dm_mcp.domain.auth.services.basic_auth import BasicAuthService, BasicAuthServiceFactory
from dm_mcp.domain.auth.services.jwt import JwtService, JwtServiceFactory
from dm_mcp.domain.auth.services.oauth import OAuthService, OAuthServiceFactory
from dm_mcp.domain.datasource.services.datasource import DataSourceService, DataSourceServiceFactory
from dm_mcp.domain.datasource.services.pool import AsyncPoolService, AsyncPoolServiceFactory
from dm_mcp.domain.mcp.services.mcp import MCPService, MCPServiceFactory
from dm_mcp.domain.mcp.services.group import MCPGroupService, MCPGroupServiceFactory
from dm_mcp.domain.db_metadata.services.db_config import DbConfigService, DbConfigServiceFactory
from dm_mcp.domain.db_metadata.services.db_metadata import DbMetadataService, DbMetadataServiceFactory
from dm_mcp.domain.ssh.services.execution import SSHExecutionService, SSHExecutionServiceFactory
from dm_mcp.domain.ssh.services.host import SSHHostService, SSHHostServiceFactory
from dm_mcp.domain.system.services.logging import LoggingService, LoggingServiceFactory
from dm_mcp.domain.system.services.metrics import MetricsService, MetricsServiceFactory
from dm_mcp.domain.token.services.token import TokenService, TokenServiceFactory
from dm_mcp.infra.messaging.event import EventService, EventServiceFactory
from dm_mcp.core.service import ServiceProtocol
from dm_mcp.infra.config.settings import T_Settings

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

        EventService 优先级 0 最先注册;其他服务按依赖关系和优先级顺序注册。
        """
        builtin_factories = [
            EventServiceFactory(),  # 基础设施,priority=0,最先创建
            LoggingServiceFactory(),
            MetricsServiceFactory(),
            JwtServiceFactory(),  # JWT 服务，优先级高，早于 OAuth 和 BasicAuth
            AuthConfigServiceFactory(),  # 依赖 DataSourceService（priority=70），晚于 DataSourceService
            OAuthServiceFactory(),  # 依赖 JwtService + AuthConfigService
            BasicAuthServiceFactory(),  # 依赖 JwtService
            TokenServiceFactory(),  # 优先级高，早于其他需要认证的服务启动
            DbConfigServiceFactory(),  # 依赖 TokenService
            DataSourceServiceFactory(),  # priority=30，尽早初始化数据库
            AsyncPoolServiceFactory(),
            MCPGroupServiceFactory(),
            SSHHostServiceFactory(),  # 依赖 event_service
            SSHExecutionServiceFactory(),  # 依赖 ssh_host_service
            MCPServiceFactory(),
            DbMetadataServiceFactory(),  # 依赖 async_pool、datasource、db_config
        ]

        self.registry.register_factories(builtin_factories)

    # ============================================================
    # 属性访问
    # ============================================================

    @property
    def event_service(self) -> EventService:
        """获取事件总线

        Returns:
            EventService: 事件总线实例
        """
        return self.registry.get_service("event_service")

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
    def auth_config_service(self) -> AuthConfigService:
        """获取认证配置服务

        Returns:
            AuthConfigService: 认证配置服务实例
        """
        return self.registry.get_service("auth_config_service")

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
    def db_config_service(self) -> DbConfigService:
        """获取数据库对象配置服务

        Returns:
            DbConfigService: 配置服务实例
        """
        return self.registry.get_service("db_config_service")

    @property
    def db_metadata_service(self) -> DbMetadataService:
        """获取数据库元数据服务

        Returns:
            DbMetadataService: 元数据服务实例
        """
        return self.registry.get_service("db_metadata_service")

    @property
    def pool_service(self) -> AsyncPoolService:
        """获取连接池服务

        Returns:
            AsyncPoolService: 连接池服务实例
        """
        return self.registry.get_service("async_pool_service")

    @property
    def mcp_group_service(self) -> MCPGroupService:
        """获取MCP分组服务

        Returns:
            MCPGroupService: MCP分组服务实例
        """
        return self.registry.get_service("mcp_group_service")

    @property
    def ssh_host_service(self) -> SSHHostService:
        """获取SSH主机管理服务

        Returns:
            SSHHostService: SSH主机服务实例
        """
        return self.registry.get_service("ssh_host_service")

    @property
    def ssh_execution_service(self) -> SSHExecutionService:
        """获取SSH命令执行服务

        Returns:
            SSHExecutionService: SSH执行服务实例
        """
        return self.registry.get_service("ssh_execution_service")

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

    def _wire_event_subscriptions(self, services: dict[str, Any]) -> None:
        """根据服务元数据声明，将事件订阅装配到 EventService

        遍历所有已注册工厂，读取 ServiceMetadata.event_subscriptions，
        通过反射 getattr(instance, handler_method) 拿到 bound method，
        以服务名作为 owner 注册到 EventService，便于关停时按 owner 批量解订阅。

        Args:
            services: 已创建的服务实例字典(name -> instance)
        """
        event_service = self.event_service
        for name, factory in self.registry.factories.items():
            metadata = factory.metadata()
            if not metadata.event_subscriptions:
                continue
            instance = services.get(name)
            if instance is None:
                continue
            for sub in metadata.event_subscriptions:
                handler = getattr(instance, sub.handler_method, None)
                if handler is None:
                    logger.warning(
                        f"服务 {name} 声明订阅 {sub.event_type.__name__} 的 handler "
                        f"{sub.handler_method} 不存在，已跳过"
                    )
                    continue
                event_service.subscribe(
                    sub.event_type,
                    handler,
                    priority=sub.priority,
                    owner=name,
                )
                logger.debug(
                    f"已装配订阅: {name}.{sub.handler_method} <- "
                    f"{sub.event_type.__name__} (priority={sub.priority})"
                )

    async def initialize_services(self) -> None:
        """初始化所有服务

        按依赖顺序获取所有服务，先装配事件订阅，再依次调用它们的startup方法。
        如果某个服务初始化失败，会记录错误并抛出异常。

        Raises:
            Exception: 当服务初始化失败时
        """
        # 获取所有服务（按依赖顺序）
        services = self.registry.get_all()

        # 在 startup 之前装配事件订阅，确保启动期间发布的事件能被订阅者收到
        self._wire_event_subscriptions(services)

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

        按倒序获取所有已创建的服务，关停每个服务前先批量解订阅其事件，
        再依次调用它们的shutdown方法。如果某个服务关闭失败，会记录错误
        但不会中断关闭流程。
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

        # 倒序关闭：先解订阅，再 shutdown，event_service 自身留到最后由其 shutdown 清理
        try:
            event_service = self.event_service
        except Exception:
            event_service = None

        for name, service in reversed(services):
            if event_service is not None and name != "event_service":
                try:
                    event_service.unsubscribe_owner(name)
                except Exception as e:
                    logger.warning(f"解订阅服务 {name} 的事件时出错: {e}")
            logger.info(f"正在关闭服务: {name}")
            try:
                await service.shutdown()
                logger.info(f"服务 {name} 已关闭")
            except Exception as e:
                logger.error(f"关闭服务 {name} 时出错: {e}", exc_info=True)


T_Context = TypeVar("T_Context", bound=GlobalContext)
