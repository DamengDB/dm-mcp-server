"""服务容器模块包

提供服务工厂和注册表实现，用于服务的注册、创建和依赖管理。
"""

from .factory import ServiceFactory, ServiceMetadata
from .registry import ServiceRegistry

__all__ = [
    "ServiceFactory",
    "ServiceMetadata",
    "ServiceRegistry",
]
