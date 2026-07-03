"""Redis缓存后端模块

提供基于Redis的缓存实现，适用于分布式环境。
"""

from .backend import BaseCacheBackend


class RedisBackend(BaseCacheBackend):
    """Redis缓存后端

    基于Redis实现的分布式缓存，支持多进程、多服务器场景。
    需要Redis服务支持。
    """

    def __init__(self, redis_url: str):
        """初始化Redis缓存后端

        Args:
            redis_url: Redis连接URL（如"redis://localhost:6379/0"）
        """
        import redis

        # decode_responses=True 确保拿到的是 str 而不是 bytes
        self.client = redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str):
        """获取缓存值

        Args:
            key: 缓存键

        Returns:
            str | None: 缓存值，如果不存在则返回None
        """
        return self.client.get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值（字符串）
            ttl: 过期时间（秒），如果为None则不过期
        """
        self.client.set(key, value, ex=ttl)

    def delete(self, key: str) -> None:
        """删除缓存

        Args:
            key: 缓存键
        """
        self.client.delete(key)

    def keys(self, pattern: str):
        """获取匹配模式的所有键

        Args:
            pattern: 匹配模式（支持Redis通配符，如"*"、"?"等）

        Returns:
            list: 匹配的键列表
        """
        return self.client.keys(pattern)
