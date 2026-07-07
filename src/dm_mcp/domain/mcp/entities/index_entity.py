"""Index 实体定义"""


from pydantic import BaseModel, Field


class IndexEntity(BaseModel):
    """索引元数据实体"""

    index_name: str = Field(..., description="索引名称")
    index_type: str | None = Field(None, description="索引类型")
    is_unique: bool = Field(default=False, description="是否唯一索引")
    columns: list[str] = Field(default_factory=list, description="索引列名列表")
