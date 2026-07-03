"""缓存服务单元测试

测试缓存操作、序列化等功能。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import BaseModel

from dm_mcp.services.cache_service import CacheService
from dm_mcp.core.cache import BaseCacheBackend


class MockCacheBackend(BaseCacheBackend):
    """Mock 缓存后端（同步实现）"""

    def __init__(self):
        self._storage = {}

    def get(self, key: str):
        """同步获取缓存值"""
        return self._storage.get(key)

    def set(self, key: str, value: str, ttl: int = 3600):
        """同步设置缓存值"""
        self._storage[key] = value

    def delete(self, key: str):
        """同步删除缓存"""
        if key in self._storage:
            del self._storage[key]

    def exists(self, key: str):
        """检查键是否存在"""
        return key in self._storage

    def clear(self):
        """清空缓存"""
        self._storage.clear()

    def keys(self, pattern: str = "*"):
        """获取匹配模式的键"""
        if pattern == "*":
            return list(self._storage.keys())
        # 简单的通配符匹配
        import fnmatch

        return [k for k in self._storage.keys() if fnmatch.fnmatch(k, pattern)]


class TestCacheService:
    """缓存服务测试类"""

    @pytest.fixture
    def mock_backend(self):
        """Mock 后端 fixture"""
        return MockCacheBackend()

    @pytest.fixture
    def cache_service(self, mock_backend):
        """缓存服务 fixture"""
        return CacheService(mock_backend, prefix="test:")

    def test_make_key_adds_prefix(self, cache_service):
        """测试 Key 前缀添加"""
        key = cache_service._make_key("mykey")
        assert key == "test:mykey"

    def test_make_key_preserves_existing_prefix(self, cache_service):
        """测试已有前缀的 Key 不重复添加"""
        key = cache_service._make_key("test:mykey")
        assert key == "test:mykey"

    def test_set_string(self, cache_service):
        """测试存储字符串"""
        result = cache_service.set("key1", "value1", ttl=60)
        assert result is True

        value = cache_service.backend.get("test:key1")
        assert value == "value1"

    def test_set_dict(self, cache_service):
        """测试存储字典"""
        data = {"name": "test", "value": 123}
        result = cache_service.set("key2", data, ttl=60)
        assert result is True

        value = cache_service.backend.get("test:key2")
        assert value is not None
        import json

        assert json.loads(value) == data

    def test_set_list(self, cache_service):
        """测试存储列表"""
        data = [1, 2, 3, "test"]
        result = cache_service.set("key3", data, ttl=60)
        assert result is True

        value = cache_service.backend.get("test:key3")
        assert value is not None
        import json

        assert json.loads(value) == data

    def test_set_pydantic_model(self, cache_service):
        """测试存储 Pydantic 模型"""

        class TestModel(BaseModel):
            name: str
            value: int

        model = TestModel(name="test", value=42)
        result = cache_service.set("key4", model, ttl=60)
        assert result is True

        value = cache_service.backend.get("test:key4")
        assert value is not None
        # 验证是 JSON 格式
        import json

        parsed = json.loads(value)
        assert parsed["name"] == "test"
        assert parsed["value"] == 42

    def test_get_string(self, cache_service):
        """测试获取字符串"""
        cache_service.backend.set("test:key5", "simple_value")

        value = cache_service.get("key5")
        assert value == "simple_value"

    def test_get_dict(self, cache_service):
        """测试获取字典"""
        import json

        data = {"name": "test", "value": 123}
        cache_service.backend.set("test:key6", json.dumps(data))

        value = cache_service.get("key6")
        assert value == data

    def test_get_nonexistent(self, cache_service):
        """测试获取不存在的键"""
        value = cache_service.get("nonexistent")
        assert value is None

    def test_get_model(self, cache_service):
        """测试获取并转换为 Pydantic 模型"""

        class TestModel(BaseModel):
            name: str
            value: int

        model = TestModel(name="test", value=42)
        cache_service.set("key7", model, ttl=60)

        retrieved = cache_service.get_model("key7", TestModel)
        assert retrieved is not None
        assert retrieved.name == "test"
        assert retrieved.value == 42

    def test_get_model_nonexistent(self, cache_service):
        """测试获取不存在的模型"""

        class TestModel(BaseModel):
            name: str
            value: int

        retrieved = cache_service.get_model("nonexistent", TestModel)
        assert retrieved is None

    def test_delete(self, cache_service):
        """测试删除键"""
        cache_service.backend.set("test:key8", "value")
        cache_service.delete("key8")

        exists = cache_service.backend.exists("test:key8")
        assert exists is False

    def test_scan_keys(self, cache_service):
        """测试扫描键"""
        cache_service.backend.set("test:key9", "value1")
        cache_service.backend.set("test:key10", "value2")
        cache_service.backend.set("other:key11", "value3")  # 不同前缀

        keys = cache_service.scan_keys("*")
        assert "key9" in keys
        assert "key10" in keys
        assert "key11" not in keys  # 不同前缀不应出现

    def test_scan_keys_pattern(self, cache_service):
        """测试使用模式扫描键"""
        cache_service.backend.set("test:key12", "value1")
        cache_service.backend.set("test:key13", "value2")
        cache_service.backend.set("test:other14", "value3")

        keys = cache_service.scan_keys("key*")
        assert "key12" in keys
        assert "key13" in keys
        assert "other14" not in keys
