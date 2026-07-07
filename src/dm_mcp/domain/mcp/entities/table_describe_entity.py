"""TableDescribe 聚合实体定义"""


from pydantic import BaseModel, Field

from .column_entity import ColumnEntity
from .index_entity import IndexEntity
from .metadata import ConstraintEntity


class TableDescribeEntity(BaseModel):
    """表描述聚合实体

    get_table_describe 工具的完整输出结构。
    """

    schema_name: str = Field(..., description="Schema 名称")
    table_name: str = Field(..., description="表名")
    table_comment: str | None = Field(None, description="表级 comment（已覆盖）")
    columns: list[ColumnEntity] = Field(default_factory=list, description="列列表")
    constraints: list[ConstraintEntity] = Field(
        default_factory=list, description="约束列表"
    )
    indexes: list[IndexEntity] = Field(default_factory=list, description="索引列表")
