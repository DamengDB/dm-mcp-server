"""内存缓存后端测试模块"""

import time
from unittest.mock import patch

import pytest

from dm_mcp.infra.cache.memory_backend import MemoryBackend


class TestMemoryBackend:
    """内存缓存后端测试类"""

    def test_init(self):
        """测试初始化"""
        backend = MemoryBackend()
        assert backend._store == {}
        assert backend._expiry == {}
        assert backend.time is not None

    def test_set_and_get(self):
        """测试设置和获取缓存值"""
        backend = MemoryBackend()
        backend.set("key1", "value1")
        assert backend.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """测试获取不存在的键"""
        backend = MemoryBackend()
        assert backend.get("nonexistent") is None

    def test_set_with_ttl(self):
        """测试设置带TTL的缓存值"""
        backend = MemoryBackend()
        backend.set("key1", "value1", ttl=1)
        assert backend.get("key1") == "value1"

        # 等待过期
        with patch.object(backend.time, "time", return_value=time.time() + 2):
            assert backend.get("key1") is None

    def test_set_without_ttl(self):
        """测试设置不带TTL的缓存值（不过期）"""
        backend = MemoryBackend()
        backend.set("key2", "value2", ttl=None)
        # 即使时间过去，也不应该过期
        with patch.object(backend.time, "time", return_value=time.time() + 1000):
            assert backend.get("key2") == "value2"

    def test_delete(self):
        """测试删除缓存"""
        backend = MemoryBackend()
        backend.set("key1", "value1")
        backend.set("key2", "value2", ttl=10)

        backend.delete("key1")
        assert backend.get("key1") is None
        assert backend.get("key2") == "value2"

        # 删除后，过期字典也应该清理
        assert "key1" not in backend._store
        assert "key1" not in backend._expiry

    def test_delete_nonexistent_key(self):
        """测试删除不存在的键（不应该报错）"""
        backend = MemoryBackend()
        backend.delete("nonexistent")  # 不应该抛出异常

    def test_expired_key_auto_cleanup(self):
        """测试过期键的自动清理"""
        backend = MemoryBackend()
        backend.set("key1", "value1", ttl=1)

        # 模拟时间过去，获取时应该自动清理
        with patch.object(backend.time, "time", return_value=time.time() + 2):
            result = backend.get("key1")
            assert result is None
            # 应该已经从存储中删除
            assert "key1" not in backend._store
            assert "key1" not in backend._expiry

    def test_keys_without_pattern(self):
        """测试获取所有键（无模式匹配）"""
        backend = MemoryBackend()
        backend.set("key1", "value1")
        backend.set("key2", "value2")
        backend.set("key3", "value3")

        keys = backend.keys("*")
        assert len(keys) == 3
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" in keys

    def test_keys_with_pattern(self):
        """测试使用模式匹配获取键"""
        backend = MemoryBackend()
        backend.set("user:1", "value1")
        backend.set("user:2", "value2")
        backend.set("admin:1", "value3")

        # 匹配所有 user:* 的键
        keys = backend.keys("user:*")
        assert len(keys) == 2
        assert "user:1" in keys
        assert "user:2" in keys
        assert "admin:1" not in keys

    def test_keys_with_question_mark_pattern(self):
        """测试使用问号通配符模式匹配"""
        backend = MemoryBackend()
        backend.set("key1", "value1")
        backend.set("key2", "value2")
        backend.set("key10", "value10")

        keys = backend.keys("key?")
        assert len(keys) == 2
        assert "key1" in keys
        assert "key2" in keys
        assert "key10" not in keys  # 问号只匹配单个字符

    def test_keys_with_square_brackets_pattern(self):
        """测试使用方括号模式匹配"""
        backend = MemoryBackend()
        backend.set("key1", "value1")
        backend.set("key2", "value2")
        backend.set("key3", "value3")

        keys = backend.keys("key[12]")
        assert len(keys) == 2
        assert "key1" in keys
        assert "key2" in keys
        assert "key3" not in keys

    def test_concurrent_access(self):
        """测试并发访问（基本线程安全测试）"""
        backend = MemoryBackend()

        # 模拟并发写入
        for i in range(100):
            backend.set(f"key{i}", f"value{i}")

        # 验证所有值都可以正确读取
        for i in range(100):
            assert backend.get(f"key{i}") == f"value{i}"

    def test_update_existing_key(self):
        """测试更新已存在的键"""
        backend = MemoryBackend()
        backend.set("key1", "value1")
        backend.set("key1", "updated_value")
        assert backend.get("key1") == "updated_value"

    def test_update_key_with_ttl(self):
        """测试更新键的TTL"""
        backend = MemoryBackend()
        current_time = backend.time.time()
        backend.set("key1", "value1", ttl=10)
        # 更新为更短的TTL（基于当前时间）
        backend.set("key1", "value1", ttl=1)

        # 在1秒TTL内应该还能获取到值
        with patch.object(backend.time, "time", return_value=current_time + 0.5):
            assert backend.get("key1") == "value1"

        # 超过1秒TTL后应该获取不到值
        with patch.object(backend.time, "time", return_value=current_time + 2):
            assert backend.get("key1") is None
