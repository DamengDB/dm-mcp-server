"""事件契约模块

提供事件总线的数据契约:事件基类 Event、订阅模型 Subscription / EventSubscription、
发布结果 PublishResult / FailedHandler 以及 handler 类型别名。

事件总线服务实现位于 dm_mcp.services.event_service,异常位于 dm_mcp.core.exceptions。
业务事件契约定义在 dm_mcp.events 顶层目录。

使用约定:
    from dm_mcp.core.events import Event, EventSubscription
    from dm_mcp.infra.messaging.event import EventService
    from dm_mcp.domain.datasource.events import DataSourceCreated
"""

from .event import Event
from .result import FailedHandler, PublishResult
from .subscription import EventHandler, EventSubscription, Subscription

__all__ = [
    "Event",
    "Subscription",
    "EventSubscription",
    "EventHandler",
    "PublishResult",
    "FailedHandler",
]
