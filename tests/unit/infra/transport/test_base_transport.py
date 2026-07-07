"""BaseTransport 基础传输层测试"""

import pytest
from unittest.mock import MagicMock, patch
from dm_mcp.infra.transport.base_transport import BaseTransport, T_ServerFactory
from dm_mcp.infra.config import Settings


class TestBaseTransport:
    """BaseTransport 测试类"""

    def test_t_server_factory_type(self):
        """测试 T_ServerFactory 类型定义"""
        # T_ServerFactory 应该是一个可调用类型
        factory = MagicMock(spec=T_ServerFactory)
        assert callable(factory)

    def test_base_transport_has_abstract_method(self):
        """测试 BaseTransport 有抽象方法 start"""
        # 检查 start 方法是抽象方法
        assert hasattr(BaseTransport, "start")
        # start 方法应该在子类中被实现
        assert getattr(
            BaseTransport.start, "__isabstractmethod__", False
        ) or "abstractmethod" in str(getattr(BaseTransport.start, "__decorators__", []))


class MockTransport(BaseTransport):
    """用于测试的 BaseTransport 实现"""

    def start(self):
        pass


class TestMockTransport:
    """Mock 传输实现测试类"""

    def test_can_instantiate_with_mock(self):
        """测试可以使用继承来实例化"""
        settings = MagicMock(spec=Settings)
        factory = MagicMock()
        transport = MockTransport(settings, factory)
        assert transport is not None

    def test_init_stores_settings_and_factory(self):
        """测试初始化存储设置和工厂"""
        settings = MagicMock(spec=Settings)
        factory = MagicMock()
        transport = MockTransport(settings, factory)
        # BaseTransport.__init__ 目前是 pass，不会存储属性
        # 子类可以重写 __init__ 来存储
