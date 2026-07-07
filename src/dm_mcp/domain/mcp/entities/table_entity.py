"""Table / View 实体定义"""


from typing import Literal

from pydantic import BaseModel, Field


class TableEntity(BaseModel):
    """表或视图元数据实体

    已应用元数据覆盖后的输出结构。
    """

    schema_name: str = Field(..., description="所属 Schema")
    table_name: str = Field(..., description="表/视图名称")
    table_type: str = Field(default="TABLE", description="TABLE 或 VIEW")
    comment: str | None = Field(None, description="已应用覆盖后的 comment")
    access_policy: Literal["allow", "deny"] | None = Field(
        None, description="None=未设置, allow=强制可见, deny=强制不可见"
    )
