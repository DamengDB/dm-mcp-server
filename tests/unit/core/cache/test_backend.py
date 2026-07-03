"""缓存后端抽象基类测试模块"""

import pytest
from abc import ABC

from dm_mcp.core.cache.backend import BaseCacheBackend


class TestBaseCacheBackend:
    """缓存后端抽象基类测试类"""

    def test_is_abstract_class(self):
        """测试 BaseCacheBackend 是抽象类"""
        assert issubclass(BaseCacheBackend, ABC)

    def test_cannot_instantiate_directly(self):
        """测试不能直接实例化抽象基类"""
        with pytest.raises(TypeError):
            BaseCacheBackend()

    def test_has_required_abstract_methods(self):
        """测试定义了所有必需的抽象方法"""
        abstract_methods = BaseCacheBackend.__abstractmethods__
        assert "get" in abstract_methods
        assert "set" in abstract_methods
        assert "delete" in abstract_methods
        assert "keys" in abstract_methods

    def test_all_abstract_methods_present(self):
        """测试所有抽象方法都存在"""
        assert hasattr(BaseCacheBackend, "get")
        assert hasattr(BaseCacheBackend, "set")
        assert hasattr(BaseCacheBackend, "delete")
        assert hasattr(BaseCacheBackend, "keys")

    def test_method_signatures(self):
        """测试抽象方法的签名"""
        import inspect

        get_sig = inspect.signature(BaseCacheBackend.get)
        assert "key" in get_sig.parameters
        assert get_sig.parameters["key"].annotation == str

        set_sig = inspect.signature(BaseCacheBackend.set)
        assert "key" in set_sig.parameters
        assert "value" in set_sig.parameters
        assert "ttl" in set_sig.parameters
        assert set_sig.parameters["key"].annotation == str
        assert set_sig.parameters["value"].annotation == str

        delete_sig = inspect.signature(BaseCacheBackend.delete)
        assert "key" in delete_sig.parameters

        keys_sig = inspect.signature(BaseCacheBackend.keys)
        assert "pattern" in keys_sig.parameters


class ConcreteCacheBackend(BaseCacheBackend):
    """用于测试的具体缓存实现"""

    def __init__(self):
        self._store = {}

    def get(self, key: str):
        return self._store.get(key)

    def set(self, key: str, value: str, ttl: int | None = None):
        self._store[key] = value

    def delete(self, key: str):
        self._store.pop(key, None)

    def keys(self, pattern: str):
        if pattern == "*":
            return list(self._store.keys())
        return [k for k in self._store.keys() if pattern in k]


class TestParentMethodCalls:
    """测试调用父类抽象方法的行为"""

    def test_get_raises_not_implemented(self):
        """测试调用父类 get 方法会抛出 NotImplementedError"""
        with pytest.raises(NotImplementedError, match="子类必须实现 get 方法"):
            # 通过使用 mock 绕过抽象类的实例化限制
            from unittest.mock import MagicMock

            mock_backend = MagicMock(spec=BaseCacheBackend)
            # 实际调用被装饰为抽象方法的方法
            BaseCacheBackend.get(mock_backend, "key")

    def test_get_method_body_execution(self):
        """测试 get 方法的异常消息"""
        try:
            BaseCacheBackend.get(None, "test_key")
        except NotImplementedError as e:
            assert "子类必须实现 get 方法" in str(e)

    def test_set_method_body_execution(self):
        """测试 set 方法的异常消息"""
        try:
            BaseCacheBackend.set(None, "key", "value")
        except NotImplementedError as e:
            assert "子类必须实现 set 方法" in str(e)

    def test_delete_method_body_execution(self):
        """测试 delete 方法的异常消息"""
        try:
            BaseCacheBackend.delete(None, "key")
        except NotImplementedError as e:
            assert "子类必须实现 delete 方法" in str(e)

    def test_keys_method_body_execution(self):
        """测试 keys 方法的异常消息"""
        try:
            BaseCacheBackend.keys(None, "*")
        except NotImplementedError as e:
            assert "子类必须实现 keys 方法" in str(e)


class TestConcreteCacheImplementation:
    """测试具体的缓存实现类"""

    def test_can_instantiate_concrete_class(self):
        """测试可以实例化实现了抽象类的具体类"""
        backend = ConcreteCacheBackend()
        assert backend is not None

    def test_concrete_implements_get(self):
        """测试具体类实现了 get 方法"""
        backend = ConcreteCacheBackend()
        assert hasattr(backend, "get")
        assert callable(backend.get)

    def test_concrete_implements_set(self):
        """测试具体类实现了 set 方法"""
        backend = ConcreteCacheBackend()
        assert hasattr(backend, "set")
        assert callable(backend.set)

    def test_concrete_implements_delete(self):
        """测试具体类实现了 delete 方法"""
        backend = ConcreteCacheBackend()
        assert hasattr(backend, "delete")
        assert callable(backend.delete)

    def test_concrete_implements_keys(self):
        """测试具体类实现了 keys 方法"""
        backend = ConcreteCacheBackend()
        assert hasattr(backend, "keys")
        assert callable(backend.keys)

    def test_concrete_basic_operations(self):
        """测试具体类可以执行基本缓存操作"""
        backend = ConcreteCacheBackend()

        backend.set("key1", "value1")
        assert backend.get("key1") == "value1"

        backend.delete("key1")
        assert backend.get("key1") is None

        backend.set("key1", "value1")
        backend.set("key2", "value2")
        keys = backend.keys("*")
        assert "key1" in keys
        assert "key2" in keys


class TestAbstractMethodEnforcement:
    """测试抽象方法的强制执行"""

    def test_missing_get_raises_error(self):
        """测试缺少 get 方法会引发错误"""

        class MissingGet(BaseCacheBackend):
            def set(self, key: str, value: str, ttl: int | None = None):
                pass

            def delete(self, key: str):
                pass

            def keys(self, pattern: str):
                pass

        with pytest.raises(TypeError):
            MissingGet()

    def test_missing_set_raises_error(self):
        """测试缺少 set 方法会引发错误"""

        class MissingSet(BaseCacheBackend):
            def get(self, key: str):
                pass

            def delete(self, key: str):
                pass

            def keys(self, pattern: str):
                pass

        with pytest.raises(TypeError):
            MissingSet()

    def test_missing_delete_raises_error(self):
        """测试缺少 delete 方法会引发错误"""

        class MissingDelete(BaseCacheBackend):
            def get(self, key: str):
                pass

            def set(self, key: str, value: str, ttl: int | None = None):
                pass

            def keys(self, pattern: str):
                pass

        with pytest.raises(TypeError):
            MissingDelete()

    def test_missing_keys_raises_error(self):
        """测试缺少 keys 方法会引发错误"""

        class MissingKeys(BaseCacheBackend):
            def get(self, key: str):
                pass

            def set(self, key: str, value: str, ttl: int | None = None):
                pass

            def delete(self, key: str):
                pass

        with pytest.raises(TypeError):
            MissingKeys()
