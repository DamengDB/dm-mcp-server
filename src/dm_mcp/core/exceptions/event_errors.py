"""事件相关异常模块

提供事件总线相关的异常类定义,包括基类异常、同步 handler 拒绝、
publish_strict 失败聚合等异常。
"""

from typing import TYPE_CHECKING

from .base_error import DmMCPError

if TYPE_CHECKING:
    from dm_mcp.core.events import PublishResult


class EventServiceError(DmMCPError):
    """事件服务基础异常

    所有事件总线相关异常的基类,HTTP状态码为500。
    """

    def __init__(
        self,
        message: str,
        error_code: str = "EVENT_ERROR",
        status_code: int = 500,
        **kwargs,
    ):
        """初始化事件服务异常

        Args:
            message: 错误消息
            error_code: 错误码(默认"EVENT_ERROR")
            status_code: HTTP状态码(默认500)
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )


class HandlerSyncError(EventServiceError):
    """同步 handler 异常

    订阅时传入的 handler 不是 async 函数时抛出,HTTP状态码为500。
    """

    def __init__(self, handler_repr: str, **kwargs):
        """初始化同步 handler 异常

        Args:
            handler_repr: handler 的 repr 信息,便于定位问题
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=f"EventService 只接受 async handler,收到同步函数: {handler_repr}",
            error_code="EVENT_HANDLER_SYNC",
            status_code=500,
            **kwargs,
        )


class PublishStrictError(EventServiceError):
    """严格发布失败异常

    publish_strict 模式下至少一个 handler 失败时抛出。
    其他 handler 仍会执行(错误隔离),只是最终聚合失败抛错。

    Attributes:
        result: PublishResult,包含成功和失败的 handler 列表
    """

    def __init__(self, result: "PublishResult", **kwargs):
        """初始化严格发布失败异常

        Args:
            result: 发布结果聚合对象
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=(
                f"publish_strict 失败: 事件 {result.event_type} 有 "
                f"{len(result.failed)} 个 handler 失败"
            ),
            error_code="EVENT_PUBLISH_STRICT_FAILED",
            status_code=500,
            **kwargs,
        )
        self.result = result
        self.details["event_type"] = result.event_type
        self.details["failed_count"] = len(result.failed)
