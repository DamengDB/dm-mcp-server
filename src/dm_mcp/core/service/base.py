"""服务基类模块

提供服务基类和生命周期协议定义，所有服务都应继承BaseService或实现ServiceProtocol。
"""

from abc import ABC
from typing import Protocol, runtime_checkable

from dm_mcp.core.auth.auth_context import AuthContext


@runtime_checkable
class ServiceProtocol(Protocol):
    """服务生命周期协议

    定义了服务的生命周期方法。任何实现了这两个方法的对象，
    都会被GlobalContext自动管理，在应用启动时调用startup，关闭时调用shutdown。
    """

    async def startup(self) -> None:
        """服务启动方法

        在应用启动时调用，用于初始化服务资源。
        """
        ...

    async def shutdown(self) -> None:
        """服务关闭方法

        在应用关闭时调用，用于清理服务资源。
        """
        ...


class BaseService(ABC):
    """服务基类

    所有业务服务的基类，提供默认的生命周期方法实现。
    子类可以重写startup和shutdown方法来定义自定义的启动和关闭逻辑。
    """

    @property
    def current_user_id(self) -> str | None:
        """获取当前认证用户 ID，无上下文时返回 None"""
        try:
            return AuthContext.get().user_id
        except ValueError:
            return None

    async def startup(self):
        """服务启动方法

        在应用启动时调用，默认实现为空。子类可以重写此方法。
        """
        pass

    async def shutdown(self):
        """服务关闭方法

        在应用关闭时调用，默认实现为空。子类可以重写此方法。
        """
        pass
