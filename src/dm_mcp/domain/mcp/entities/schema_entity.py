"""Schema 实体定义"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SchemaEntity(BaseModel):
    """Schema 元数据实体

    已应用元数据覆盖后的输出结构。
    """

    name: str = Field(..., description="Schema 名称")
    owner: str | None = Field(None, description="Schema 所有者")
    created_time: datetime | None = Field(None, description="创建时间")
    comment: str | None = Field(None, description="已应用覆盖后的 comment")
    access_policy: Literal["allow", "deny"] | None = Field(
        None, description="None=未设置, allow=强制可见, deny=强制不可见"
    )
