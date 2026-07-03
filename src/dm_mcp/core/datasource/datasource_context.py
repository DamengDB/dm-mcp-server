"""数据源上下文模块

提供 DatasourceContext，用于在一次请求/会话范围内保存“当前使用的数据源”信息。

设计目标：
- 与 AuthContext / MetricsContext 一致，基于 contextvars 提供线程安全的上下文传递
- 由认证层、MCP 中间件或传输层在合适的位置设置当前数据源
"""

import contextvars
import uuid
from contextlib import contextmanager
from typing import Optional

from pydantic import BaseModel, Field

_datasource_context_var = contextvars.ContextVar[Optional["DatasourceContext"]](
    "mcp_datasource_context", default=None
)


class DatasourceContext(BaseModel):
    """数据源上下文

    表示当前请求实际使用的数据源（按 UUID 标识）。
    """

    datasource_id: uuid.UUID = Field(..., description="当前选中的数据源 UUID")

    @classmethod
    def get(cls) -> "DatasourceContext":
        """获取当前数据源上下文

        Raises:
            ValueError: 如果当前未设置数据源上下文
        """
        ctx = _datasource_context_var.get()
        if ctx is None:
            raise ValueError("No datasource context set")
        return ctx

    @classmethod
    @contextmanager
    def as_current(cls, ctx: "DatasourceContext"):
        """设置当前数据源上下文的上下文管理器"""
        token = _datasource_context_var.set(ctx)
        try:
            yield
        finally:
            _datasource_context_var.reset(token)
