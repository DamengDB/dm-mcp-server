"""Redis缓存后端测试模块 - 使用 Mock 外部导入"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestRedisBackend:
    """Redis缓存后端测试类 - 模拟整个 redis 模块"""

    @pytest.fixture
    def mock_redis_module(self):
        """创建Mock的redis模块"""
        mock_module = MagicMock()
        mock_client = MagicMock()
        mock_client.get = MagicMock(return_value=None)
        mock_client.set = MagicMock(return_value=True)
        mock_client.delete = MagicMock(return_value=1)
        mock_client.keys = MagicMock(return_value=[])
        mock_client.exists = MagicMock(return_value=0)
        mock_client.flushdb = MagicMock(return_value=True)
        mock_module.from_url = MagicMock(return_value=mock_client)
        return mock_module

    def test_init_with_mock_redis(self, mock_redis_module):
        """测试使用 mock 初始化"""
        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            # 重新导入以使用 mocked 的模块
            from dm_mcp.infra.cache.redis_backend import RedisBackend

            backend = RedisBackend("redis://localhost:6379/0")
            assert backend.client is not None
            mock_redis_module.from_url.assert_called_once_with(
                "redis://localhost:6379/0", decode_responses=True
            )

    def test_set_with_ttl(self, mock_redis_module):
        """测试设置带 TTL 的值"""
        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            from dm_mcp.infra.cache.redis_backend import RedisBackend

            backend = RedisBackend("redis://localhost:6379/0")
            backend.set("key1", "value1", ttl=3600)
            backend.client.set.assert_called_once_with("key1", "value1", ex=3600)

    def test_set_without_ttl(self, mock_redis_module):
        """测试设置不带 TTL 的值"""
        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            from dm_mcp.infra.cache.redis_backend import RedisBackend

            backend = RedisBackend("redis://localhost:6379/0")
            backend.set("key1", "value1", ttl=None)
            backend.client.set.assert_called_once_with("key1", "value1", ex=None)

    def test_get_existing_key(self, mock_redis_module):
        """测试获取存在的键"""
        mock_redis_module.from_url.return_value.get.return_value = "test_value"

        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            from dm_mcp.infra.cache.redis_backend import RedisBackend

            backend = RedisBackend("redis://localhost:6379/0")
            result = backend.get("key1")
            assert result == "test_value"

    def test_get_nonexistent_key(self, mock_redis_module):
        """测试获取不存在的键"""
        mock_redis_module.from_url.return_value.get.return_value = None

        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            from dm_mcp.infra.cache.redis_backend import RedisBackend

            backend = RedisBackend("redis://localhost:6379/0")
            result = backend.get("nonexistent")
            assert result is None

    def test_delete(self, mock_redis_module):
        """测试删除键"""
        mock_redis_module.from_url.return_value.delete.return_value = 1

        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            from dm_mcp.infra.cache.redis_backend import RedisBackend

            backend = RedisBackend("redis://localhost:6379/0")
            backend.delete("key1")
            backend.client.delete.assert_called_once_with("key1")

    def test_keys(self, mock_redis_module):
        """测试获取所有键"""
        mock_redis_module.from_url.return_value.keys.return_value = ["key1", "key2"]

        with patch.dict(sys.modules, {"redis": mock_redis_module}):
            from dm_mcp.infra.cache.redis_backend import RedisBackend

            backend = RedisBackend("redis://localhost:6379/0")
            keys = backend.keys("*")
            assert len(keys) == 2
