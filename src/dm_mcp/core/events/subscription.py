"""订阅描述模块

提供两类订阅模型:
- Subscription: 运行期订阅记录,EventService.subscribe 返回此对象,用于精确解绑
- EventSubscription: 声明式订阅元数据,在 ServiceFactory.metadata().event_subscriptions 中使用
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar
from uuid import UUID, uuid4

from .event import Event

E = TypeVar("E", bound=Event)
EventHandler = Callable[[E], Awaitable[None]]


@dataclass(frozen=True)
class Subscription:
    """运行期订阅记录,EventService.subscribe 返回此对象,用于精确解绑。"""

    event_type: type[Event]
    handler: EventHandler[Any]
    priority: int
    owner: str | None
    sub_id: UUID = field(default_factory=uuid4)


@dataclass
class EventSubscription:
    """声明式订阅元数据

    在 ServiceFactory.metadata().event_subscriptions 中使用。
    启动时通过反射 getattr(instance, handler_method) 绑定到 EventService。

    Attributes:
        event_type: 事件类型(Event 子类)
        handler_method: service 实例上的方法名
        priority: 优先级,数字越小越先执行(默认 100)
    """

    event_type: type[Event]
    handler_method: str
    priority: int = 100
