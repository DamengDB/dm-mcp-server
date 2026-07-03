"""基础服务单元测试

测试 BaseService 基类的功能。
"""

import pytest

from dm_mcp.services.base_service import BaseService, ServiceProtocol


class TestBaseService:
    """基础服务测试类"""

    def test_base_service_instantiation(self):
        """测试基础服务可以实例化"""
        service = BaseService()
        assert service is not None

    @pytest.mark.asyncio
    async def test_base_service_startup(self):
        """测试基础服务的启动方法"""
        service = BaseService()

        # 默认实现应该不抛出异常
        await service.startup()

    @pytest.mark.asyncio
    async def test_base_service_shutdown(self):
        """测试基础服务的关闭方法"""
        service = BaseService()

        # 默认实现应该不抛出异常
        await service.shutdown()

    def test_base_service_implements_protocol(self):
        """测试 BaseService 实现了 ServiceProtocol"""
        service = BaseService()

        # 使用 runtime_checkable 检查
        assert isinstance(service, ServiceProtocol)

    @pytest.mark.asyncio
    async def test_custom_service_override(self):
        """测试自定义服务可以重写生命周期方法"""

        class CustomService(BaseService):
            def __init__(self):
                super().__init__()
                self.started = False
                self.stopped = False

            async def startup(self):
                self.started = True

            async def shutdown(self):
                self.stopped = True

        service = CustomService()

        # 验证初始状态
        assert not service.started
        assert not service.stopped

        # 测试启动
        await service.startup()
        assert service.started

        # 测试关闭
        await service.shutdown()
        assert service.stopped
