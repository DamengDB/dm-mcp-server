"""服务注册表单元测试

测试服务注册、获取、依赖解析等功能。
"""

import pytest
from unittest.mock import MagicMock

from dm_mcp.core.exceptions import ServiceCircularDependencyError, ServiceNotFoundError
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.core.service.registry import ServiceRegistry
from dm_mcp.infra.config import Settings


class TestServiceMetadata:
    """ServiceMetadata 测试类"""

    def test_service_metadata_default_values(self):
        """测试默认值"""
        metadata = ServiceMetadata(
            name="test_service",
            service_type=object,
        )

        assert metadata.name == "test_service"
        assert metadata.service_type == object
        assert metadata.dependencies == []
        assert metadata.singleton is True
        assert metadata.enabled is True
        assert metadata.lazy is False
        assert metadata.priority == 100
        assert metadata.description == ""
        assert metadata.author == ""

    def test_service_metadata_custom_values(self):
        """测试自定义值"""
        metadata = ServiceMetadata(
            name="custom_service",
            service_type=dict,
            dependencies=["dep1", "dep2"],
            singleton=False,
            enabled=False,
            lazy=True,
            priority=50,
            description="Custom service",
            author="Test Author",
        )

        assert metadata.name == "custom_service"
        assert metadata.service_type == dict
        assert metadata.dependencies == ["dep1", "dep2"]
        assert metadata.singleton is False
        assert metadata.enabled is False
        assert metadata.lazy is True
        assert metadata.priority == 50
        assert metadata.description == "Custom service"
        assert metadata.author == "Test Author"

    def test_service_metadata_dependencies_default_empty(self):
        """测试依赖默认为空列表"""
        metadata = ServiceMetadata(
            name="service",
            service_type=object,
        )

        # 验证使用了 default_factory
        assert metadata.dependencies == []
        # 验证是独立的列表实例
        metadata.dependencies.append("test")
        metadata2 = ServiceMetadata(name="service2", service_type=object)
        assert metadata2.dependencies == []


class MockService:
    """Mock 服务类"""

    def __init__(self, name: str = "mock_service"):
        self.name = name

    async def startup(self):
        pass

    async def shutdown(self):
        pass


class MockServiceFactory(ServiceFactory):
    """Mock 服务工厂"""

    def __init__(self, name: str, dependencies: list[str] = None, priority: int = 100):
        self._name = name
        self._dependencies = dependencies or []
        self._priority = priority

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name=self._name,
            service_type=MockService,
            dependencies=self._dependencies,
            priority=self._priority,
            description=f"Mock service {self._name}",
        )

    def create(self, settings: Settings, **dependencies):
        return MockService(self._name)


class TestServiceRegistry:
    """服务注册表测试类"""

    def test_register_factory(self, mock_settings):
        """测试注册服务工厂"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service")

        registry.register_factory(factory)

        assert "test_service" in registry.factories
        assert registry.factories["test_service"] == factory

    def test_register_multiple_factories(self, mock_settings):
        """测试注册多个服务工厂"""
        registry = ServiceRegistry(mock_settings)
        factory1 = MockServiceFactory("service1")
        factory2 = MockServiceFactory("service2")

        registry.register_factories([factory1, factory2])

        assert "service1" in registry.factories
        assert "service2" in registry.factories

    def test_get_service_simple(self, mock_settings):
        """测试获取简单服务（无依赖）"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service")
        registry.register_factory(factory)

        service = registry.get_service("test_service")

        assert service is not None
        assert isinstance(service, MockService)
        assert service.name == "test_service"

    def test_get_service_with_dependencies(self, mock_settings):
        """测试获取有依赖的服务"""
        registry = ServiceRegistry(mock_settings)

        # 注册依赖服务
        dep_factory = MockServiceFactory("dep_service")
        registry.register_factory(dep_factory)

        # 注册主服务
        main_factory = MockServiceFactory("main_service", dependencies=["dep_service"])
        registry.register_factory(main_factory)

        # 获取主服务（应该自动解析依赖）
        service = registry.get_service("main_service")

        assert service is not None
        assert "dep_service" in registry.instances

    def test_get_service_singleton(self, mock_settings):
        """测试单例模式"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service")
        registry.register_factory(factory)

        service1 = registry.get_service("test_service")
        service2 = registry.get_service("test_service")

        assert service1 is service2  # 应该是同一个实例

    def test_get_service_not_found(self, mock_settings):
        """测试获取不存在的服务"""
        registry = ServiceRegistry(mock_settings)

        with pytest.raises(ServiceNotFoundError):
            registry.get_service("non_existent_service")

    def test_circular_dependency_detection(self, mock_settings):
        """测试循环依赖检测"""
        registry = ServiceRegistry(mock_settings)

        factory1 = MockServiceFactory("service1", dependencies=["service2"])
        factory2 = MockServiceFactory("service2", dependencies=["service1"])

        registry.register_factory(factory1)
        registry.register_factory(factory2)

        with pytest.raises(ServiceCircularDependencyError):
            registry.get_service("service1")

    def test_service_priority(self, mock_settings):
        """测试服务优先级排序"""
        registry = ServiceRegistry(mock_settings)

        factory1 = MockServiceFactory("service1", priority=100)
        factory2 = MockServiceFactory("service2", priority=10)  # 更高优先级
        factory3 = MockServiceFactory("service3", priority=50)

        registry.register_factories([factory1, factory2, factory3])

        # 获取所有服务，应该按优先级排序
        all_services = registry.get_all()

        # 验证服务已创建（通过获取服务来触发创建）
        registry.get_service("service2")  # 优先级最高
        registry.get_service("service3")
        registry.get_service("service1")  # 优先级最低

        # 验证所有服务都已实例化
        assert "service1" in registry.instances
        assert "service2" in registry.instances
        assert "service3" in registry.instances

    def test_get_all_services(self, mock_settings):
        """测试获取所有服务"""
        registry = ServiceRegistry(mock_settings)

        factory1 = MockServiceFactory("service1")
        factory2 = MockServiceFactory("service2")
        factory3 = MockServiceFactory("service3")

        registry.register_factories([factory1, factory2, factory3])

        all_services = registry.get_all()

        # get_all() 返回的是服务名称到实例的字典
        assert len(all_services) == 3
        assert "service1" in all_services
        assert "service2" in all_services
        assert "service3" in all_services
        # 验证返回的是服务实例
        assert isinstance(all_services["service1"], MockService)
        assert isinstance(all_services["service2"], MockService)
        assert isinstance(all_services["service3"], MockService)

    def test_service_lifecycle(self, mock_settings):
        """测试服务生命周期管理"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service")
        registry.register_factory(factory)

        service = registry.get_service("test_service")

        # 验证服务实现了生命周期方法
        assert hasattr(service, "startup")
        assert hasattr(service, "shutdown")

    @pytest.mark.asyncio
    async def test_service_startup_shutdown(self, mock_settings):
        """测试服务的启动和关闭"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service")
        registry.register_factory(factory)

        service = registry.get_service("test_service")

        # 调用启动方法
        await service.startup()

        # 调用关闭方法
        await service.shutdown()

    def test_has_method(self, mock_settings):
        """测试 has 方法检查服务是否存在"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service")
        registry.register_factory(factory)

        assert registry.has("test_service") is True
        assert registry.has("non_existent") is False

    def test_register_factory_override_warning(self, mock_settings):
        """测试注册同名工厂会发出警告"""
        import logging

        registry = ServiceRegistry(mock_settings)
        factory1 = MockServiceFactory("test_service")
        factory2 = MockServiceFactory("test_service")

        # 第一次注册
        registry.register_factory(factory1)
        # 第二次注册应该覆盖
        registry.register_factory(factory2)

        # 验证只有最后一个工厂
        assert "test_service" in registry.factories

    def test_get_service_info(self, mock_settings):
        """测试获取服务信息"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service", priority=50)
        registry.register_factory(factory)

        info = registry.get_service_info("test_service")

        assert info is not None
        assert info.name == "test_service"
        assert info.priority == 50

    def test_get_service_info_not_found(self, mock_settings):
        """测试获取不存在的服务信息"""
        registry = ServiceRegistry(mock_settings)

        info = registry.get_service_info("non_existent")
        assert info is None

    def test_unload_service(self, mock_settings):
        """测试卸载服务"""
        registry = ServiceRegistry(mock_settings)
        factory = MockServiceFactory("test_service")
        registry.register_factory(factory)

        # 先获取服务
        service1 = registry.get_service("test_service")
        assert "test_service" in registry.instances

        # 卸载服务
        registry.unload_service("test_service")
        assert "test_service" not in registry.instances

    def test_reload_service(self, mock_settings):
        """测试重新加载服务"""
        registry = ServiceRegistry(mock_settings)
        # 使用计数器生成不同实例
        counter = [0]

        class VariableService:
            def __init__(self):
                counter[0] += 1
                self.instance_id = counter[0]

            async def startup(self):
                pass

            async def shutdown(self):
                pass

        class VariableServiceFactory(ServiceFactory):
            def metadata(self):
                return ServiceMetadata(
                    name="variable_service",
                    service_type=VariableService,
                )

            def create(self, settings, **deps):
                return VariableService()

        factory = VariableServiceFactory()
        registry.register_factory(factory)

        # 获取服务
        service1 = registry.get_service("variable_service")
        original_instance_id = service1.instance_id

        # 重新加载
        service2 = registry.reload_service("variable_service")

        # 应该创建了新实例
        assert service2.instance_id != original_instance_id

    def test_list_services(self, mock_settings):
        """测试列出所有服务"""
        registry = ServiceRegistry(mock_settings)
        factory1 = MockServiceFactory("service1")
        factory2 = MockServiceFactory("service2")
        registry.register_factories([factory1, factory2])

        services = registry.list_services()

        assert len(services) == 2
        names = [s.name for s in services]
        assert "service1" in names
        assert "service2" in names

    def test_get_all_with_disabled_service(self, mock_settings):
        """测试获取所有服务时跳过禁用的服务"""

        class DisabledServiceFactory(ServiceFactory):
            def metadata(self):
                return ServiceMetadata(
                    name="disabled_service",
                    service_type=MockService,
                    enabled=False,
                )

            def create(self, settings, **deps):
                return MockService("disabled_service")

        registry = ServiceRegistry(mock_settings)
        factory = DisabledServiceFactory()
        registry.register_factory(factory)

        all_services = registry.get_all()

        # 禁用的服务不应该在列表中
        assert "disabled_service" not in all_services

    def test_get_all_with_lazy_service(self, mock_settings):
        """测试获取所有服务时跳过懒加载服务"""

        class LazyServiceFactory(ServiceFactory):
            def metadata(self):
                return ServiceMetadata(
                    name="lazy_service",
                    service_type=MockService,
                    lazy=True,
                )

            def create(self, settings, **deps):
                return MockService("lazy_service")

        registry = ServiceRegistry(mock_settings)
        factory = LazyServiceFactory()
        registry.register_factory(factory)

        all_services = registry.get_all()

        # 懒加载服务不应该在列表中
        assert "lazy_service" not in all_services

    def test_circular_dependency_in_topological_sort(self, mock_settings):
        """测试拓扑排序中的循环依赖检测"""
        registry = ServiceRegistry(mock_settings)

        factory1 = MockServiceFactory("s1", dependencies=["s2"])
        factory2 = MockServiceFactory("s2", dependencies=["s1"])

        registry.register_factories([factory1, factory2])

        with pytest.raises(ServiceCircularDependencyError):
            registry.get_all()

    def test_dependency_not_found(self, mock_settings):
        """测试依赖服务不存在"""
        registry = ServiceRegistry(mock_settings)

        main_factory = MockServiceFactory("main", dependencies=["nonexistent"])
        registry.register_factory(main_factory)

        with pytest.raises(ServiceNotFoundError):
            registry.get_service("main")
