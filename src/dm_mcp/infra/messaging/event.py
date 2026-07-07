"""事件服务模块

提供异步事件总线服务,顺序广播,错误隔离,声明式订阅。

关键约束:
- handler 必须是 async 函数(同步函数会被拒绝并抛 HandlerSyncError)
- 同事件多个 handler 顺序 await(保证因果)
- 单个 handler 失败不影响其他 handler(只记日志和返回失败信息)
- 提供 publish 和 publish_strict 两种语义
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import TypeVar

from dm_mcp.core.events import (
    Event,
    EventHandler,
    FailedHandler,
    PublishResult,
    Subscription,
)
from dm_mcp.core.exceptions import HandlerSyncError, PublishStrictError
from dm_mcp.core.service import ServiceFactory, ServiceMetadata

from dm_mcp.core.service import BaseService

logger = logging.getLogger(__name__)

E = TypeVar("E", bound=Event)


class EventService(BaseService):
    """异步事件总线服务

    实现 ServiceProtocol 的 startup/shutdown,可被 ServiceRegistry 管理。

    使用要点:
    - subscribe() 返回 Subscription,通过它精确解绑
    - 同步业务请用 publish() 或 publish_strict()
    - 非 async 上下文请用 publish_nowait()(fire-and-forget)
    """

    def __init__(self) -> None:
        self._subs: dict[type[Event], list[Subscription]] = {}

    # ---------------------------
    # 生命周期
    # ---------------------------
    async def startup(self) -> None:
        logger.debug("EventService 已启动")

    async def shutdown(self) -> None:
        total = sum(len(subs) for subs in self._subs.values())
        if total:
            logger.info("关闭 EventService,清空 %d 个订阅", total)
        self._subs.clear()

    # ---------------------------
    # 订阅
    # ---------------------------
    def subscribe(
        self,
        event_type: type[E],
        handler: EventHandler[E],
        *,
        priority: int = 100,
        owner: str | None = None,
    ) -> Subscription:
        """订阅事件

        Args:
            event_type: 事件类型(Event 子类)
            handler: 异步 handler(必须是 async def 或返回 Awaitable 的可调用对象)
            priority: 优先级,数字越小越先执行(默认 100)
            owner: 订阅者标识,用于日志/批量解绑(通常是 service name)

        Returns:
            Subscription 对象,通过它精确解绑

        Raises:
            HandlerSyncError: handler 不是 async 函数时
        """
        if not inspect.iscoroutinefunction(handler):
            raise HandlerSyncError(repr(handler))

        sub = Subscription(
            event_type=event_type,
            handler=handler,
            priority=priority,
            owner=owner,
        )
        subs = self._subs.setdefault(event_type, [])
        subs.append(sub)
        # 稳定排序保证同优先级时注册顺序保留
        subs.sort(key=lambda s: s.priority)

        logger.debug(
            "已订阅事件: type=%s owner=%s priority=%d",
            event_type.__name__, owner, priority,
        )
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        """精确解绑某个订阅"""
        subs = self._subs.get(sub.event_type)
        if not subs:
            return
        try:
            subs.remove(sub)
            logger.debug(
                "已解绑事件订阅: type=%s owner=%s",
                sub.event_type.__name__, sub.owner,
            )
        except ValueError:
            pass

    def unsubscribe_owner(self, owner: str) -> int:
        """按 owner 批量解绑,返回解绑数量。shutdown 时使用。"""
        count = 0
        for subs in self._subs.values():
            removed = [s for s in subs if s.owner == owner]
            for s in removed:
                subs.remove(s)
                count += 1
        if count:
            logger.debug("已批量解绑 owner=%s: %d 个订阅", owner, count)
        return count

    # ---------------------------
    # 发布
    # ---------------------------
    async def publish(self, event: Event) -> PublishResult:
        """发布事件,顺序 await 所有 handler,错误隔离

        Returns:
            PublishResult,包含成功和失败的 handler 列表
        """
        return await self._publish(event)

    async def publish_strict(self, event: Event) -> PublishResult:
        """严格发布:任一 handler 失败时抛 PublishStrictError

        其他 handler 仍会执行(错误隔离),只是最终聚合失败抛错。

        Raises:
            PublishStrictError: 至少一个 handler 失败时
        """
        result = await self._publish(event)
        if result.has_failures:
            raise PublishStrictError(result)
        return result

    def publish_nowait(self, event: Event) -> asyncio.Task[PublishResult]:
        """同步入口:在非 async 上下文调用,通过 create_task 调度

        失败时会被 task 吞掉,适合 fire-and-forget。需要严格性请用 publish。
        必须在 running event loop 内调用,否则抛 RuntimeError。
        """
        return asyncio.get_running_loop().create_task(self.publish(event))

    async def _publish(self, event: Event) -> PublishResult:
        """内部发布实现

        拷贝当前订阅列表后再 await,允许 handler 期间动态订阅而不影响本次发布。
        """
        event_type = type(event)
        subs = list(self._subs.get(event_type, []))

        result = PublishResult(event_type=event_type.__name__)
        if not subs:
            logger.debug(
                "事件无订阅者: type=%s id=%s",
                event_type.__name__, event.event_id,
            )
            return result

        logger.info(
            "发布事件: type=%s id=%s subs=%d",
            event_type.__name__, event.event_id, len(subs),
        )

        for sub in subs:
            handler_name = self._handler_name(sub.handler)
            try:
                await sub.handler(event)
                result.succeeded.append(sub.owner or handler_name)
            except Exception as e:
                logger.error(
                    "事件 handler 执行失败: type=%s id=%s owner=%s handler=%s err=%s",
                    event_type.__name__, event.event_id,
                    sub.owner, handler_name, e,
                    exc_info=True,
                )
                result.failed.append(FailedHandler(
                    owner=sub.owner,
                    handler_name=handler_name,
                    error_type=type(e).__name__,
                    error_message=str(e),
                ))

        return result

    @staticmethod
    def _handler_name(handler: EventHandler) -> str:
        """提取 handler 的可读名称(优先 __qualname__)"""
        return getattr(handler, "__qualname__", repr(handler))

    # ---------------------------
    # 内省 / 调试
    # ---------------------------
    def list_subscriptions(self, event_type: type[Event] | None = None) -> list[Subscription]:
        """列出当前订阅(用于诊断)"""
        if event_type is not None:
            return list(self._subs.get(event_type, []))
        return [s for subs in self._subs.values() for s in subs]


# =========================================================
# Factory
# =========================================================
class EventServiceFactory(ServiceFactory):
    """事件服务工厂

    EventService 是基础设施级 service,priority=0 最先初始化,
    供其他 service 在 startup 时使用。
    """

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="event_service",
            service_type=EventService,
            description="异步事件总线服务(声明式订阅 + 顺序广播 + 错误隔离)",
            author="DM MCP Team",
            dependencies=[],
            priority=0,
        )

    def create(self, settings, **deps) -> EventService:
        return EventService()
