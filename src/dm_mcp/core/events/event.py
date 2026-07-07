"""事件基类模块

定义所有领域事件的统一基类 Event。
通过 frozen 保证不可变,通过 extra="forbid" 防止字段拼写错误。
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    """事件基类

    所有业务事件继承此类,自带 event_id 用于日志关联,
    occurred_at 记录事件产生时刻。
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
