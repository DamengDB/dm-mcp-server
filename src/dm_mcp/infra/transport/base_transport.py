"""传输层基类模块

提供服务功能：
- 传输层的抽象基类定义
- 统一的传输接口规范
- 服务器工厂函数类型定义
"""

from abc import abstractmethod
from typing import TYPE_CHECKING, Callable

from dm_mcp.infra.config.settings import Settings

if TYPE_CHECKING:
    from dm_mcp.app.server import MCPServer


T_ServerFactory = Callable[[], "MCPServer"]
"""服务器工厂函数类型

用于创建 MCPServer 实例的工厂函数。
此函数不接受参数，返回一个 MCPServer 实例。
"""


class BaseTransport(object):
    """传输层基类

    所有传输实现的抽象基类，定义统一的传输接口。

    主要职责：
    - 定义传输层的统一接口
    - 管理服务器设置和工厂函数
    - 子类需要实现 start 方法来启动传输

    子类实现：
    - StdioTransport: 标准输入输出传输
    - StreamableHttpTransport: HTTP 传输
    """

    def __init__(self, settings: Settings, factory: T_ServerFactory) -> None:
        """初始化传输层

        Args:
            settings: 服务器设置
            factory: 服务器工厂函数
        """
        pass

    @abstractmethod
    def start(self) -> None:
        """启动传输

        启动传输服务，阻塞直到服务停止。
        子类必须实现此方法。
        """
        pass
