"""服务工厂模块

提供服务工厂协议和元数据定义，用于服务的注册和创建。
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, Type

if TYPE_CHECKING:
    from dm_mcp.settings.settings import Settings


@dataclass
class ServiceMetadata:
    """服务元数据

    Attributes:
        name: 服务名称，必须唯一
        service_type: 服务类型
        dependencies: 依赖的服务名称列表
        singleton: 是否为单例（默认 True）
        enabled: 是否启用该服务（默认 True）
        lazy: 是否懒加载（默认 False，立即创建）
        priority: 初始化优先级（数字越小越早初始化，默认 100）
        description: 服务描述
        author: 服务作者

    Examples:
        >>> metadata = ServiceMetadata(
        ...     name="logging_service",
        ...     service_type=LoggingService,
        ...     description="日志服务",
        ...     author="DM MCP Team",
        ...     dependencies=[],
        ...     priority=10,
        ... )
    """

    name: str
    service_type: Type
    dependencies: list[str] = field(default_factory=list)
    singleton: bool = True
    enabled: bool = True
    lazy: bool = False
    priority: int = 100
    description: str = ""
    author: str = ""


class ServiceFactory(Protocol):
    """服务工厂协议

    所有服务工厂必须实现此协议，提供元数据和创建方法。

    Examples:
        >>> class LoggingServiceFactory:
        ...     def metadata(self) -> ServiceMetadata:
        ...         return ServiceMetadata(
        ...             name="logging_service",
        ...             service_type=LoggingService,
        ...             description="日志服务",
        ...             author="Your Name",
        ...         )
        ...
        ...     def create(self, settings: Settings, **deps) -> LoggingService:
        ...         return LoggingService(settings.logging)
    """

    def metadata(self) -> ServiceMetadata:
        """返回服务元数据

        Returns:
            服务的元数据信息
        """
        ...

    def create(self, settings: "Settings", **dependencies: Any) -> Any:
        """创建服务实例

        Args:
            settings: 全局配置
            **dependencies: 依赖的服务实例（key 为服务名称）

        Returns:
            创建的服务实例

        Raises:
            Exception: 当服务创建失败时
        """
        ...
