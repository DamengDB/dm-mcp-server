"""EventService 单元测试

覆盖订阅/解订阅、顺序广播、错误隔离、严格模式、同步 handler 拒绝、
按 owner 批量解订阅、生命周期和 FakeEventService 工具类。
"""

from __future__ import annotations

import asyncio

import pytest

from dm_mcp.core.events import (
    Event,
    EventSubscription,
)
from dm_mcp.core.exceptions import (
    HandlerSyncError,
    PublishStrictError,
)
from dm_mcp.infra.messaging.event import (
    EventService,
    EventServiceFactory,
)
from tests.conftest import FakeEventService


class _SampleEvent(Event):
    """测试用事件"""

    payload: str


class _OtherEvent(Event):
    """另一个测试用事件,用于隔离断言"""

    code: int


class TestEventBaseClass:
    """Event 基类不可变 / 严格字段约束"""

    def test_event_has_id_and_timestamp(self):
        e = _SampleEvent(payload="hi")
        assert e.event_id is not None
        assert e.occurred_at is not None
        assert e.payload == "hi"

    def test_event_is_frozen(self):
        e = _SampleEvent(payload="hi")
        with pytest.raises(Exception):
            e.payload = "changed"  # type: ignore[misc]

    def test_event_forbids_extra_fields(self):
        with pytest.raises(Exception):
            _SampleEvent(payload="hi", unknown="x")  # type: ignore[call-arg]


class TestSubscribeAndPublish:
    """基础订阅 / 发布"""

    async def test_publish_no_subscribers_returns_empty_result(self):
        bus = EventService()
        result = await bus.publish(_SampleEvent(payload="x"))
        assert result.event_type == "_SampleEvent"
        assert result.succeeded == []
        assert result.failed == []
        assert not result.has_failures

    async def test_subscribe_and_publish_invokes_handler(self):
        bus = EventService()
        received: list[_SampleEvent] = []

        async def handler(event: _SampleEvent) -> None:
            received.append(event)

        bus.subscribe(_SampleEvent, handler, owner="svc")
        e = _SampleEvent(payload="hello")
        result = await bus.publish(e)

        assert received == [e]
        assert result.succeeded == ["svc"]
        assert result.failed == []

    async def test_publish_routes_only_to_matching_event_type(self):
        bus = EventService()
        sample_calls: list[_SampleEvent] = []
        other_calls: list[_OtherEvent] = []

        async def on_sample(event: _SampleEvent) -> None:
            sample_calls.append(event)

        async def on_other(event: _OtherEvent) -> None:
            other_calls.append(event)

        bus.subscribe(_SampleEvent, on_sample)
        bus.subscribe(_OtherEvent, on_other)

        await bus.publish(_SampleEvent(payload="a"))
        await bus.publish(_OtherEvent(code=1))

        assert len(sample_calls) == 1
        assert len(other_calls) == 1


class TestPriorityOrdering:
    """priority 越小越先执行,稳定排序保留同优先级注册顺序"""

    async def test_lower_priority_runs_first(self):
        bus = EventService()
        order: list[str] = []

        async def first(event: _SampleEvent) -> None:
            order.append("first")

        async def second(event: _SampleEvent) -> None:
            order.append("second")

        # 注册顺序故意倒着,验证按 priority 排序
        bus.subscribe(_SampleEvent, second, priority=20)
        bus.subscribe(_SampleEvent, first, priority=10)

        await bus.publish(_SampleEvent(payload="x"))
        assert order == ["first", "second"]

    async def test_same_priority_preserves_registration_order(self):
        bus = EventService()
        order: list[str] = []

        async def a(event: _SampleEvent) -> None:
            order.append("a")

        async def b(event: _SampleEvent) -> None:
            order.append("b")

        bus.subscribe(_SampleEvent, a, priority=10)
        bus.subscribe(_SampleEvent, b, priority=10)

        await bus.publish(_SampleEvent(payload="x"))
        assert order == ["a", "b"]


class TestErrorIsolation:
    """单个 handler 失败不影响其他 handler"""

    async def test_one_failing_handler_does_not_block_others(self):
        bus = EventService()
        called: list[str] = []

        async def boom(event: _SampleEvent) -> None:
            raise RuntimeError("boom")

        async def ok(event: _SampleEvent) -> None:
            called.append("ok")

        bus.subscribe(_SampleEvent, boom, owner="svc_a", priority=10)
        bus.subscribe(_SampleEvent, ok, owner="svc_b", priority=20)

        result = await bus.publish(_SampleEvent(payload="x"))

        assert called == ["ok"]
        assert result.succeeded == ["svc_b"]
        assert len(result.failed) == 1
        failure = result.failed[0]
        assert failure.owner == "svc_a"
        assert failure.error_type == "RuntimeError"
        assert failure.error_message == "boom"
        assert result.has_failures

    async def test_publish_strict_raises_on_failure(self):
        bus = EventService()

        async def boom(event: _SampleEvent) -> None:
            raise ValueError("nope")

        bus.subscribe(_SampleEvent, boom, owner="svc")

        with pytest.raises(PublishStrictError) as exc_info:
            await bus.publish_strict(_SampleEvent(payload="x"))

        assert exc_info.value.result.has_failures
        assert exc_info.value.result.failed[0].error_type == "ValueError"

    async def test_publish_strict_succeeds_when_all_handlers_ok(self):
        bus = EventService()

        async def ok(event: _SampleEvent) -> None:
            pass

        bus.subscribe(_SampleEvent, ok, owner="svc")

        result = await bus.publish_strict(_SampleEvent(payload="x"))
        assert result.succeeded == ["svc"]
        assert not result.has_failures


class TestSyncHandlerRejected:
    """同步 handler 必须被拒绝"""

    def test_sync_function_raises_handler_sync_error(self):
        bus = EventService()

        def sync_handler(event: _SampleEvent) -> None:
            pass

        with pytest.raises(HandlerSyncError):
            bus.subscribe(_SampleEvent, sync_handler)  # type: ignore[arg-type]

    def test_lambda_raises_handler_sync_error(self):
        bus = EventService()
        with pytest.raises(HandlerSyncError):
            bus.subscribe(_SampleEvent, lambda e: None)  # type: ignore[arg-type]


class TestUnsubscribe:
    """精确解订阅 / 按 owner 批量解订阅"""

    async def test_unsubscribe_removes_subscription(self):
        bus = EventService()
        called: list[str] = []

        async def handler(event: _SampleEvent) -> None:
            called.append("hit")

        sub = bus.subscribe(_SampleEvent, handler)
        bus.unsubscribe(sub)

        await bus.publish(_SampleEvent(payload="x"))
        assert called == []

    async def test_unsubscribe_unknown_subscription_is_safe(self):
        bus = EventService()

        async def handler(event: _SampleEvent) -> None:
            pass

        sub = bus.subscribe(_SampleEvent, handler)
        bus.unsubscribe(sub)
        # 重复解订阅不应抛异常
        bus.unsubscribe(sub)

    async def test_unsubscribe_owner_removes_all_for_owner(self):
        bus = EventService()
        called: list[str] = []

        async def h_a(event: _SampleEvent) -> None:
            called.append("a")

        async def h_b(event: _SampleEvent) -> None:
            called.append("b")

        async def h_c(event: _OtherEvent) -> None:
            called.append("c")

        bus.subscribe(_SampleEvent, h_a, owner="svc_x")
        bus.subscribe(_SampleEvent, h_b, owner="svc_x")
        bus.subscribe(_OtherEvent, h_c, owner="svc_x")

        # 还有一个 owner 不同的,不应被波及
        async def h_d(event: _SampleEvent) -> None:
            called.append("d")

        bus.subscribe(_SampleEvent, h_d, owner="svc_y")

        removed = bus.unsubscribe_owner("svc_x")
        assert removed == 3

        await bus.publish(_SampleEvent(payload="x"))
        await bus.publish(_OtherEvent(code=1))
        assert called == ["d"]

    async def test_unsubscribe_owner_returns_zero_when_no_match(self):
        bus = EventService()

        async def handler(event: _SampleEvent) -> None:
            pass

        bus.subscribe(_SampleEvent, handler, owner="svc")
        assert bus.unsubscribe_owner("nobody") == 0


class TestDynamicSubscription:
    """publish 进行中动态订阅,不影响本次广播"""

    async def test_handler_subscribing_during_publish_does_not_affect_current_round(self):
        bus = EventService()
        called: list[str] = []

        async def late_handler(event: _SampleEvent) -> None:
            called.append("late")

        async def first(event: _SampleEvent) -> None:
            called.append("first")
            bus.subscribe(_SampleEvent, late_handler)

        bus.subscribe(_SampleEvent, first)
        await bus.publish(_SampleEvent(payload="x"))
        # 第一次只有 first
        assert called == ["first"]

        # 第二次 late_handler 被触发
        await bus.publish(_SampleEvent(payload="y"))
        assert called == ["first", "first", "late"]


class TestPublishNowait:
    """publish_nowait 在 running loop 内调度任务"""

    async def test_publish_nowait_returns_task_and_completes(self):
        bus = EventService()
        called: list[str] = []

        async def handler(event: _SampleEvent) -> None:
            called.append("hit")

        bus.subscribe(_SampleEvent, handler)

        task = bus.publish_nowait(_SampleEvent(payload="x"))
        assert isinstance(task, asyncio.Task)
        result = await task
        assert called == ["hit"]
        assert result.succeeded


class TestLifecycle:
    """startup/shutdown 行为"""

    async def test_startup_is_noop_safe(self):
        bus = EventService()
        await bus.startup()  # 不应抛

    async def test_shutdown_clears_all_subscriptions(self):
        bus = EventService()

        async def handler(event: _SampleEvent) -> None:
            pass

        bus.subscribe(_SampleEvent, handler, owner="svc")
        assert bus.list_subscriptions()

        await bus.shutdown()
        assert bus.list_subscriptions() == []


class TestListSubscriptions:
    """list_subscriptions 用于诊断"""

    async def test_list_all_subscriptions(self):
        bus = EventService()

        async def h1(event: _SampleEvent) -> None:
            pass

        async def h2(event: _OtherEvent) -> None:
            pass

        bus.subscribe(_SampleEvent, h1, owner="a")
        bus.subscribe(_OtherEvent, h2, owner="b")

        all_subs = bus.list_subscriptions()
        assert len(all_subs) == 2

    async def test_list_filtered_by_event_type(self):
        bus = EventService()

        async def h1(event: _SampleEvent) -> None:
            pass

        async def h2(event: _OtherEvent) -> None:
            pass

        bus.subscribe(_SampleEvent, h1)
        bus.subscribe(_OtherEvent, h2)

        sample_subs = bus.list_subscriptions(_SampleEvent)
        assert len(sample_subs) == 1
        assert sample_subs[0].event_type is _SampleEvent


class TestEventServiceFactory:
    """工厂在 ServiceRegistry 中的元数据契约"""

    def test_metadata_uses_priority_zero(self):
        factory = EventServiceFactory()
        meta = factory.metadata()
        assert meta.name == "event_service"
        assert meta.priority == 0
        assert meta.dependencies == []

    def test_create_returns_event_service_instance(self):
        factory = EventServiceFactory()
        bus = factory.create(settings=None)  # type: ignore[arg-type]
        assert isinstance(bus, EventService)


class TestEventSubscriptionDataclass:
    """EventSubscription 声明式元数据"""

    def test_default_priority_is_100(self):
        sub = EventSubscription(event_type=_SampleEvent, handler_method="on_sample")
        assert sub.priority == 100

    def test_custom_priority(self):
        sub = EventSubscription(
            event_type=_SampleEvent,
            handler_method="on_sample",
            priority=10,
        )
        assert sub.priority == 10


class TestFakeEventService:
    """FakeEventService 测试工具的核心断言"""

    async def test_records_published_events(self):
        bus = FakeEventService()
        e1 = _SampleEvent(payload="a")
        e2 = _OtherEvent(code=1)

        await bus.publish(e1)
        await bus.publish(e2)

        assert bus.published == [e1, e2]

    async def test_assert_published_returns_last_instance(self):
        bus = FakeEventService()
        e1 = _SampleEvent(payload="first")
        e2 = _SampleEvent(payload="second")

        await bus.publish(e1)
        await bus.publish(e2)

        latest = bus.assert_published(_SampleEvent)
        assert latest is e2

    async def test_assert_published_raises_when_missing(self):
        bus = FakeEventService()
        with pytest.raises(AssertionError):
            bus.assert_published(_SampleEvent)

    async def test_assert_published_count(self):
        bus = FakeEventService()
        await bus.publish(_SampleEvent(payload="a"))
        await bus.publish(_SampleEvent(payload="b"))
        await bus.publish(_OtherEvent(code=1))

        bus.assert_published_count(_SampleEvent, 2)
        bus.assert_published_count(_OtherEvent, 1)

        with pytest.raises(AssertionError):
            bus.assert_published_count(_SampleEvent, 5)

    async def test_reset_clears_history(self):
        bus = FakeEventService()
        await bus.publish(_SampleEvent(payload="a"))
        bus.reset()
        assert bus.published == []

    async def test_publish_still_dispatches_to_subscribers(self):
        bus = FakeEventService()
        called: list[str] = []

        async def handler(event: _SampleEvent) -> None:
            called.append("hit")

        bus.subscribe(_SampleEvent, handler)
        await bus.publish(_SampleEvent(payload="x"))
        assert called == ["hit"]

    async def test_publish_strict_records_event_and_raises_on_failure(self):
        bus = FakeEventService()

        async def boom(event: _SampleEvent) -> None:
            raise RuntimeError("x")

        bus.subscribe(_SampleEvent, boom)

        with pytest.raises(PublishStrictError):
            await bus.publish_strict(_SampleEvent(payload="x"))

        # 即便失败,事件也已被记录
        bus.assert_published(_SampleEvent)
