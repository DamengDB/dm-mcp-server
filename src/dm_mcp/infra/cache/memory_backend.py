"""内存缓存后端模块

提供基于内存的缓存实现，适用于单进程场景。
"""

from .backend import BaseCacheBackend


class MemoryBackend(BaseCacheBackend):
    """内存缓存后端

    基于字典实现的进程内缓存，支持TTL过期机制。
    适用于单进程场景，不适用于多进程或分布式环境。
    """

    def __init__(self):
        """初始化内存缓存后端"""
        import time

        self._store = {}
        self._expiry = {}
        self.time = time

    def get(self, key: str):
        """获取缓存值

        Args:
            key: 缓存键

        Returns:
            Any: 缓存值，如果不存在或已过期则返回None
        """
        if key in self._expiry and self.time.time() > self._expiry[key]:
            self.delete(key)
            return None
        return self._store.get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值（字符串）
            ttl: 过期时间（秒），如果为None则不过期
        """
        self._store[key] = value
        if ttl:
            self._expiry[key] = self.time.time() + ttl

    def delete(self, key: str) -> None:
        """删除缓存

        Args:
            key: 缓存键
        """
        self._store.pop(key, None)
        self._expiry.pop(key, None)

    def keys(self, pattern: str):
        """获取匹配模式的所有键

        Args:
            pattern: 匹配模式（支持通配符，使用fnmatch）

        Returns:
            list: 匹配的键列表
        """
        import fnmatch

        # 简单清理一下过期键
        self.get("")
        return fnmatch.filter(self._store.keys(), pattern)
