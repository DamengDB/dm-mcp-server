"""服务注册表模块

提供服务注册表的实现，负责服务的注册、创建、依赖解析和生命周期管理。
"""

import logging
from typing import Any, Dict, List, Optional

from dm_mcp.core.exceptions import ServiceCircularDependencyError, ServiceNotFoundError

from .factory import ServiceFactory, ServiceMetadata

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """服务注册表

    负责服务的注册、创建、依赖解析和生命周期管理。

    Attributes:
        settings: 全局配置
        factories: 已注册的服务工厂字典，key 为服务名称
        instances: 已实例化的服务字典，key 为服务名称

    Examples:
        >>> registry = ServiceRegistry(settings)
        >>> registry.register_factory(LoggingServiceFactory())
        >>> service = registry.get_service("logging_service")
        >>> all_services = registry.get_all()
    """

    def __init__(self, settings) -> None:
        """初始化服务注册表

        Args:
            settings: 全局配置
        """
        self.settings = settings
        self.factories: Dict[str, ServiceFactory] = {}
        self.instances: Dict[str, Any] = {}
        self._building: set[str] = set()

    def register_factory(self, factory: ServiceFactory) -> None:
        """注册服务工厂

        Args:
            factory: 服务工厂实例
        """
        metadata = factory.metadata()

        if metadata.name in self.factories:
            logger.warning(f"服务工厂 '{metadata.name}' 已注册，将被替换")

        self.factories[metadata.name] = factory
        logger.debug(
            f"已注册服务工厂: {metadata.name} "
            f"(类型: {metadata.service_type.__name__}, "
            f"优先级: {metadata.priority})"
        )

    def register_factories(self, factories: List[ServiceFactory]) -> None:
        """批量注册服务工厂

        Args:
            factories: 服务工厂列表
        """
        for factory in factories:
            self.register_factory(factory)

    def has(self, name: str) -> bool:
        """检查服务是否已注册

        Args:
            name: 服务名称

        Returns:
            是否已注册
        """
        return name in self.factories

    def get_service(self, name: str) -> Any:
        """获取服务实例

        如果服务是单例且已创建，直接返回缓存的实例。
        否则创建新实例（会自动解析依赖）。

        Args:
            name: 服务名称

        Returns:
            服务实例

        Raises:
            ServiceNotFoundError: 当服务未注册时
            ServiceCircularDependencyError: 当检测到循环依赖时
        """
        # 检查服务是否存在
        if name not in self.factories:
            raise ServiceNotFoundError(name)

        factory = self.factories[name]
        metadata = factory.metadata()

        # 检查是否启用
        if not metadata.enabled:
            logger.debug(f"Service '{name}' is disabled")
            return None

        # 如果是单例且已创建，直接返回
        if metadata.singleton and name in self.instances:
            return self.instances[name]

        # 创建实例
        instance = self._create_instance(name)

        # 如果是单例，缓存实例
        if metadata.singleton:
            self.instances[name] = instance

        return instance

    def get_all(self) -> Dict[str, Any]:
        """获取所有已启用的服务实例

        按依赖顺序创建所有服务（拓扑排序）。

        Returns:
            服务名称到实例的字典
        """
        # 按依赖顺序排序
        sorted_names = self._topological_sort()

        # 创建所有服务
        services = {}
        for name in sorted_names:
            factory = self.factories[name]
            metadata = factory.metadata()

            # 跳过未启用的服务
            if not metadata.enabled:
                logger.debug(f"服务 '{name}' 未启用，跳过")
                continue

            # 跳过懒加载的服务
            if metadata.lazy:
                logger.debug(f"服务 '{name}' 为懒加载，暂跳过")
                continue

            try:
                services[name] = self.get_service(name)
            except Exception as e:
                logger.error(f"创建服务 '{name}' 失败: {e}", exc_info=True)
                raise

        return services

    def unload_service(self, name: str) -> None:
        """卸载服务

        Args:
            name: 服务名称
        """
        if name in self.instances:
            del self.instances[name]
            logger.debug(f"已卸载服务: {name}")

    def reload_service(self, name: str) -> Any:
        """重新加载服务

        Args:
            name: 服务名称

        Returns:
            重新创建的服务实例
        """
        self.unload_service(name)
        return self.get_service(name)

    def list_services(self) -> List[ServiceMetadata]:
        """列出所有已注册的服务

        Returns:
            服务元数据列表
        """
        return [factory.metadata() for factory in self.factories.values()]

    def get_service_info(self, name: str) -> Optional[ServiceMetadata]:
        """获取服务信息

        Args:
            name: 服务名称

        Returns:
            服务元数据，如果不存在返回 None
        """
        if name not in self.factories:
            return None
        return self.factories[name].metadata()

    def _create_instance(self, name: str) -> Any:
        """创建服务实例（自动解析依赖）

        Args:
            name: 服务名称

        Returns:
            服务实例

        Raises:
            ServiceCircularDependencyError: 当检测到循环依赖时
        """
        # 检测循环依赖
        if name in self._building:
            path = " -> ".join(list(self._building) + [name])
            raise ServiceCircularDependencyError(name, path)

        factory = self.factories[name]
        metadata = factory.metadata()

        # 标记正在构建
        self._building.add(name)

        try:
            # 解析依赖
            dependencies = {}
            for dep_name in metadata.dependencies:
                if dep_name not in self.factories:
                    raise ServiceNotFoundError(dep_name)
                dependencies[dep_name] = self.get_service(dep_name)

            # 调用工厂创建实例
            logger.debug(f"正在创建服务: {name} (优先级: {metadata.priority})")

            instance = factory.create(self.settings, **dependencies)

            return instance

        finally:
            # 清除构建标记
            self._building.discard(name)

    def _topological_sort(self) -> List[str]:
        """拓扑排序（解决依赖顺序）

        使用 Kahn 算法进行拓扑排序。

        Returns:
            按依赖顺序排序的服务名称列表

        Raises:
            ServiceCircularDependencyError: 当存在循环依赖时
        """
        # 计算入度
        in_degree = {}
        for name in self.factories.keys():
            in_degree[name] = 0

        # 构建邻接表和计算入度
        adj_list = {name: [] for name in self.factories.keys()}
        for name, factory in self.factories.items():
            metadata = factory.metadata()
            for dep in metadata.dependencies:
                if dep in self.factories:
                    adj_list[dep].append(name)
                    in_degree[name] += 1

        # 按优先级排序（同级别的服务按优先级排序）
        queue = []
        for name, degree in in_degree.items():
            if degree == 0:
                priority = self.factories[name].metadata().priority
                queue.append((priority, name))
        queue.sort()  # 按优先级排序

        result = []
        while queue:
            # 取出优先级最高的
            _, name = queue.pop(0)
            result.append(name)

            # 更新邻接节点的入度
            for neighbor in adj_list[name]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    priority = self.factories[neighbor].metadata().priority
                    queue.append((priority, neighbor))
                    queue.sort()  # 重新排序

        # 检查是否有循环依赖
        if len(result) != len(self.factories):
            remaining = set(self.factories.keys()) - set(result)
            path = " -> ".join(result)
            raise ServiceCircularDependencyError(name, path)

        return result
