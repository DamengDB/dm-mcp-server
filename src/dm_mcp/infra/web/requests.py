
from typing import Literal

from pydantic import BaseModel, Field


class BaseDBObjectConfigRequest(BaseModel):
    """数据库对象配置请求基类

    DataSource 级配置请求模型，用于元数据覆盖的 CRUD 操作。
    """

    object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"] = Field(...)
    schema_name: str = Field(..., max_length=128)
    table_name: str | None = Field(None, max_length=128)
    column_name: str | None = Field(None, max_length=128)
    access_policy: Literal["allow", "deny", "inherit"] | None = Field(
        None, description="allow=白名单, deny=黑名单, inherit=继承上级, None=不更新"
    )
    comment_override: str | None = Field(None, max_length=4000)


class UpsertDBObjectConfigRequest(BaseDBObjectConfigRequest):
    """创建/更新数据库对象配置请求"""
    pass


class BatchUpsertDBObjectConfigRequest(BaseModel):
    """批量创建/更新数据库对象配置请求"""

    configs: list[UpsertDBObjectConfigRequest]


class DeleteDBObjectConfigRequest(BaseDBObjectConfigRequest):
    """删除数据库对象配置请求"""

    pass
