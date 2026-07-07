"""Web API 数据模型 (DTO / Schema)

用于 Controller 层与 Service 层之间的数据转换，以及 HTTP 响应序列化。
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class DataSourceCreateDTO(BaseModel):
    """创建数据源的请求 DTO"""

    name: str = Field(pattern=r"^[\w-]+$", description="数据源名称")
    enabled: bool = True
    deploy_type: Literal["dmstandalone", "dmwatcher", "dmdsc", "dmdpc"] = "dmstandalone"
    read_only: bool = False
    dsn: str = ""
    host: str = "localhost"
    port: int = 5236
    user: str = "SYSDBA"
    password: SecretStr = Field(default=SecretStr("SYSDBA"))
    minsize: int = 1
    maxsize: int = 10
    timeout: float = 30.0
    weight: int = 1


class DataSourceUpdateDTO(BaseModel):
    """更新数据源的请求 DTO

    与 CreateDTO 的区别：password 允许传入明文字符串（用于保持旧密码的场景）。
    """

    name: str = Field(pattern=r"^[\w-]+$", description="数据源名称")
    enabled: bool = True
    deploy_type: Literal["dmstandalone", "dmwatcher", "dmdsc", "dmdpc"] = "dmstandalone"
    read_only: bool = False
    dsn: str = ""
    host: str = "localhost"
    port: int = 5236
    user: str = "SYSDBA"
    password: SecretStr | str = Field(default=SecretStr("SYSDBA"))
    minsize: int = 1
    maxsize: int = 10
    timeout: float = 30.0
    weight: int = 1


class DBObjectConfigItem(BaseModel):
    """数据库对象配置响应项

    适用于 DataSource 级配置和全局系统对象默认配置。
    """

    id: str
    object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"]
    schema_name: str
    table_name: str | None = None
    column_name: str | None = None
    access_policy: Literal["allow", "deny", "inherit"] = "inherit"
    comment_override: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    datasource_id: str | None = None

    @classmethod
    def from_model(cls, model, *, include_datasource_id: bool = False) -> "DBObjectConfigItem":
        """从 SQLAlchemy 模型创建响应项。

        Args:
            model: DBObjectConfigModel 或 DBSystemObjectDefaultModel
            include_datasource_id: 是否包含 datasource_id（DataSource 级配置需要）
        """
        data = {
            "id": str(model.id),
            "object_type": model.object_type,
            "schema_name": model.schema_name,
            "table_name": model.table_name,
            "column_name": model.column_name,
            # None → "inherit" 语义化转换
            "access_policy": model.access_policy if model.access_policy is not None else "inherit",
            "comment_override": model.comment_override,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "updated_at": model.updated_at.isoformat() if model.updated_at else None,
        }
        if include_datasource_id:
            data["datasource_id"] = str(model.datasource_id)
        return cls(**data)
