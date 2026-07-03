"""认证上下文模块

提供认证上下文的数据结构和线程安全的上下文变量管理。
"""

import contextvars
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

_auth_context_var = contextvars.ContextVar[Optional["AuthContext"]](
    "mcp_auth_context", default=None
)


class AuthContext(BaseModel):
    """认证上下文

    存储当前请求的认证信息，包括用户ID、登录时间、认证类型、Token等信息。
    使用contextvars实现线程安全的上下文传递。
    """

    user_id: str = Field(default="anonymous")
    login_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    token: Optional[str] = Field(None, description="使用的 Token")
    auth_type: Literal["oauth", "token", "basic_auth", "anonymous"] = Field(
        default="anonymous", description="认证类型"
    )

    @classmethod
    def get(cls) -> "AuthContext":
        """获取当前上下文

        Returns:
            AuthContext: 当前请求的认证上下文

        Raises:
            ValueError: 如果当前上下文中没有设置认证上下文则抛出异常
        """
        res = _auth_context_var.get()
        if res is None:
            raise ValueError("No auth context set")
        return res

    @classmethod
    @contextmanager
    def as_current(cls, auth_context: "AuthContext"):
        """设置当前上下文的上下文管理器

        在上下文管理器的范围内，可以通过get()方法获取设置的认证上下文。

        Args:
            auth_context: 要设置的认证上下文

        Yields:
            无返回值，用作上下文管理器
        """
        old_auth_context = _auth_context_var.set(auth_context)
        try:
            yield
        finally:
            _auth_context_var.reset(old_auth_context)
