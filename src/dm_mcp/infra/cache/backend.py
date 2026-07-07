"""缓存后端抽象接口模块

提供缓存后端的抽象基类，定义统一的缓存接口。
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseCacheBackend(ABC):
    """缓存后端抽象基类

    定义缓存后端的统一接口，所有缓存实现都应继承此类。
    """

    @abstractmethod
    def get(self, key: str) -> Any:
        """获取缓存值

        Args:
            key: 缓存键

        Returns:
            Any: 缓存值，如果不存在则返回None

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现 get 方法")

    @abstractmethod
    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        """设置缓存值

        Args:
            key: 缓存键
            value: 缓存值（字符串）
            ttl: 过期时间（秒），如果为None则不过期

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现 set 方法")

    @abstractmethod
    def delete(self, key: str) -> None:
        """删除缓存

        Args:
            key: 缓存键

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现 delete 方法")

    @abstractmethod
    def keys(self, pattern: str) -> Any:
        """获取匹配模式的所有键

        Args:
            pattern: 匹配模式（支持通配符）

        Returns:
            Any: 匹配的键列表

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现 keys 方法")
