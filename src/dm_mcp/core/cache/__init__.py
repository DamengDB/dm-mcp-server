"""缓存模块包

提供缓存后端的抽象接口和实现，包括内存缓存和Redis缓存。
"""

from .backend import BaseCacheBackend
from .memory_backend import MemoryBackend
from .redis_backend import RedisBackend

__all__ = [
    "BaseCacheBackend",
    "MemoryBackend",
    "RedisBackend",
]
