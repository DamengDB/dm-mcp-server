"""缓存系统集成测试

测试缓存后端的集成，包括 Memory 和 Redis 后端的协作。
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from dm_mcp.infra.cache.backend import BaseCacheBackend
from dm_mcp.infra.cache.memory_backend import MemoryBackend


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheIntegration:
    """缓存系统集成测试类"""

    @pytest_asyncio.fixture
    async def memory_backend(self):
        """创建内存缓存后端"""
        backend = MemoryBackend()
        yield backend
        # 清理
        backend._store.clear()
        backend._expiry.clear()

    @pytest_asyncio.fixture
    async def cache_backend_with_data(self, memory_backend):
        """创建带有数据的缓存后端"""
        memory_backend.set("user:1", "admin")
        memory_backend.set("user:2", "user")
        memory_backend.set("session:abc", '{"user_id": 1}')
        yield memory_backend

    async def test_cache_set_and_get(self, memory_backend):
        """测试缓存设置和获取"""
        memory_backend.set("key1", "value1")
        result = memory_backend.get("key1")
        assert result == "value1"

    async def test_cache_get_nonexistent(self, memory_backend):
        """测试获取不存在的键"""
        result = memory_backend.get("nonexistent")
        assert result is None

    async def test_cache_delete(self, memory_backend):
        """测试缓存删除"""
        memory_backend.set("key1", "value1")
        memory_backend.delete("key1")
        result = memory_backend.get("key1")
        assert result is None

    async def test_cache_update(self, memory_backend):
        """测试缓存更新"""
        memory_backend.set("key1", "value1")
        memory_backend.set("key1", "value2")
        result = memory_backend.get("key1")
        assert result == "value2"

    async def test_cache_keys_wildcard(self, cache_backend_with_data):
        """测试通配符匹配键"""
        keys = cache_backend_with_data.keys("*")
        assert len(keys) >= 3

    async def test_cache_keys_pattern(self, cache_backend_with_data):
        """测试模式匹配键"""
        keys = cache_backend_with_data.keys("user:*")
        assert "user:1" in keys
        assert "user:2" in keys

    async def test_cache_ttl_expiry(self, memory_backend):
        """测试 TTL 过期"""
        import time
        from unittest.mock import patch as mock_patch

        memory_backend.set("temp_key", "temp_value", ttl=1)

        # 立即获取应该返回值
        result = memory_backend.get("temp_key")
        assert result == "temp_value"

        # 模拟时间流逝（超过 TTL）
        with mock_patch.object(
            memory_backend.time, "time", return_value=time.time() + 2
        ):
            result = memory_backend.get("temp_key")
            assert result is None

    async def test_cache_ttl_none(self, memory_backend):
        """测试不过期的缓存"""
        import time
        from unittest.mock import patch as mock_patch

        memory_backend.set("permanent_key", "permanent_value", ttl=None)

        # 模拟时间流逝
        with mock_patch.object(
            memory_backend.time, "time", return_value=time.time() + 1000
        ):
            result = memory_backend.get("permanent_key")
            assert result == "permanent_value"

    async def test_cache_concurrent_operations(self, memory_backend):
        """测试并发操作"""
        import asyncio

        async def write_task(start: int, count: int):
            for i in range(start, start + count):
                memory_backend.set(f"key{i}", f"value{i}")

        # 并发写入
        await asyncio.gather(
            write_task(0, 50),
            write_task(50, 50),
            write_task(100, 50),
        )

        # 验证所有数据都写入
        for i in range(150):
            assert memory_backend.get(f"key{i}") == f"value{i}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheBackendInterface:
    """缓存后端接口测试类"""

    async def test_backend_is_abstract(self):
        """测试 BaseCacheBackend 是抽象类"""
        from abc import ABC

        assert issubclass(BaseCacheBackend, ABC)

    async def test_backend_cannot_instantiate(self):
        """测试不能直接实例化抽象类"""
        with pytest.raises(TypeError):
            BaseCacheBackend()

    async def test_memory_backend_implements_interface(self):
        """测试 MemoryBackend 实现了接口"""
        backend = MemoryBackend()

        # 验证所有接口方法存在且可调用
        assert callable(backend.get)
        assert callable(backend.set)
        assert callable(backend.delete)
        assert callable(backend.keys)


@pytest.mark.integration
@pytest.mark.asyncio
class TestCacheWithService:
    """缓存服务集成测试"""

    @pytest_asyncio.fixture
    async def cache_service_with_backend(self):
        """创建带有缓存后端的服务模拟"""
        backend = MemoryBackend()

        # 模拟缓存服务
        class MockCacheService:
            def __init__(self, backend):
                self.backend = backend
                self._cache = {}

            async def get(self, key: str):
                value = self.backend.get(key)
                return value

            async def set(self, key: str, value: str, ttl: int = None):
                self.backend.set(key, value, ttl)

            async def delete(self, key: str):
                self.backend.delete(key)

        service = MockCacheService(backend)
        yield service

    async def test_cache_service_get_set(self, cache_service_with_backend):
        """测试缓存服务的 get 和 set"""
        service = cache_service_with_backend

        await service.set("test_key", "test_value")
        result = await service.get("test_key")

        assert result == "test_value"

    async def test_cache_service_delete(self, cache_service_with_backend):
        """测试缓存服务的删除"""
        service = cache_service_with_backend

        await service.set("test_key", "test_value")
        await service.delete("test_key")
        result = await service.get("test_key")

        assert result is None

    async def test_cache_service_ttl(self, cache_service_with_backend):
        """测试缓存服务的 TTL"""
        service = cache_service_with_backend
        import time
        from unittest.mock import patch as mock_patch

        await service.set("temp_key", "temp_value", ttl=1)

        # 立即获取应该返回值
        result = await service.get("temp_key")
        assert result == "temp_value"


@pytest.mark.integration
@pytest.mark.asyncio
class TestCachePerformance:
    """缓存性能测试类"""

    @pytest_asyncio.fixture
    async def large_cache_backend(self):
        """创建大量数据的缓存后端"""
        backend = MemoryBackend()

        # 添加大量数据
        for i in range(1000):
            backend.set(f"user:{i}", f"user_data_{i}")

        yield backend

        # 清理
        backend._store.clear()
        backend._expiry.clear()

    async def test_bulk_keys_retrieval(self, large_cache_backend):
        """测试批量键检索"""
        keys = large_cache_backend.keys("user:*")
        assert len(keys) == 1000

    async def test_cache_clear(self, large_cache_backend):
        """测试缓存清空"""
        large_cache_backend._store.clear()
        assert len(large_cache_backend.keys("*")) == 0
