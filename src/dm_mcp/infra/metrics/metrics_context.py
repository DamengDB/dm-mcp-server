"""指标上下文模块

提供指标上下文的数据结构和线程安全的上下文变量管理。
"""

import contextvars
from contextlib import contextmanager
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

_metrics_context_var = contextvars.ContextVar[Optional["MetricsContext"]](
    "mcp_metrics_context", default=None
)


class MetricsContext(BaseModel):
    """指标上下文

    存储当前请求的指标信息，包括元数据和指标快照列表。
    使用contextvars实现线程安全的上下文传递。
    """

    # 允许存储任意类型的 Dataclass 对象
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # 1. 扩展数据 (用于 Labels，如 user_id)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # 2. 【核心修改】指标快照列表 (用于 Metrics Dataclass)
    # 我们不预定义具体的 Class，而是用 list[Any] 存储用户传进来的任何指标对象
    _snapshots: list[Any] = PrivateAttr(default_factory=list)

    # --- API ---

    def record(self, metric_instance: Any):
        """记录指标实例

        用户调用此方法将自定义的指标dataclass放入上下文。

        Args:
            metric_instance: 指标数据类实例
        """
        self._snapshots.append(metric_instance)

    def collect(self) -> list[Any]:
        """收集所有暂存的指标

        供Service层提取所有暂存的指标快照。

        Returns:
            list[Any]: 指标实例列表
        """
        return self._snapshots

    # ... (原有的 set_meta, get_meta, get, as_current 保持不变) ...

    @classmethod
    def get(cls) -> "MetricsContext":
        """获取当前指标上下文

        Returns:
            MetricsContext: 当前请求的指标上下文，如果不存在则返回新实例
        """
        res = _metrics_context_var.get()
        return res or cls()

    @classmethod
    @contextmanager
    def as_current(cls, metrics_context: "MetricsContext"):
        """设置当前指标上下文的上下文管理器

        Args:
            metrics_context: 要设置的指标上下文

        Yields:
            无返回值，用作上下文管理器
        """
        token = _metrics_context_var.set(metrics_context)
        try:
            yield
        finally:
            _metrics_context_var.reset(token)
