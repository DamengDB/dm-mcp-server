"""Column 实体定义"""


from typing import Literal

from pydantic import BaseModel, Field


class ColumnEntity(BaseModel):
    """列元数据实体

    已应用元数据覆盖后的输出结构。
    """

    schema_name: str = Field(..., description="所属 Schema")
    table_name: str = Field(..., description="所属表/视图")
    column_name: str = Field(..., description="列名")
    column_id: int = Field(..., description="列顺序号")
    data_type: str = Field(..., description="数据类型")
    data_length: int | None = Field(None, description="数据长度")
    data_precision: int | None = Field(None, description="数据精度")
    data_scale: int | None = Field(None, description="数据小数位")
    nullable: bool = Field(default=True, description="是否可为空")
    default_value: str | None = Field(None, description="默认值")
    comment: str | None = Field("", description="已应用覆盖后的 comment")
    access_policy: Literal["allow", "deny"] | None = Field(
        None, description="None=未设置, allow=强制可见, deny=强制不可见"
    )
