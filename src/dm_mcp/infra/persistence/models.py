"""数据库模型模块

提供SQLAlchemy ORM模型定义，包括Token模型、Admin用户模型和数据源模型。
"""

import json
import secrets
import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import TIMESTAMP, Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator

_SHORT_ID_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def generate_short_id(length: int = 12) -> str:
    """生成 12 字符 base62 短随机 id（约 71 bit 熵，URL/路径友好）。"""
    return "".join(secrets.choice(_SHORT_ID_ALPHABET) for _ in range(length))


class GUID(TypeDecorator):
    """跨数据库 UUID 类型

    对于 SQLite，使用 CHAR(36) 存储 UUID 字符串
    对于 PostgreSQL，使用原生 UUID 类型
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID())
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return str(value)
        else:
            if not isinstance(value, uuid.UUID):
                return str(uuid.UUID(value))
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
            return value


class Base(DeclarativeBase):
    """SQLAlchemy基类

    所有数据库模型的基类，使用SQLAlchemy 2.0的DeclarativeBase。
    """

    pass


class TokenModel(Base):
    """Token数据模型

    存储API Token信息，包括Token值、用户ID、允许访问的数据源列表、
    过期时间、最后使用时间等。
    """

    __tablename__ = "tokens"

    # 主键（明文 token，仅用于 Bearer 认证 + 内部表外键引用，不出现在管理 URL 中）
    token: Mapped[str] = mapped_column(String(512), primary_key=True)

    # 管理用短码（12 字符 base62），所有管理类 URL 通过 token_id 寻 token
    token_id: Mapped[str] = mapped_column(
        String(12),
        unique=True,
        nullable=False,
        default=generate_short_id,
    )

    # 用户信息
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # 【改】绑定的数据源 UUID 列表（JSON 数组字符串）
    datasource_ids: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )
    # 【新增】默认数据源 UUID
    default_datasource_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        nullable=True,
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Token 名称（必填）
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # 【新增】绑定的 SSH 主机 UUID 列表（JSON 数组字符串）
    ssh_host_ids: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    # 元数据（JSON 存储）- 使用 token_metadata 避免与 DeclarativeBase.metadata 冲突
    token_metadata: Mapped[str] = mapped_column(
        Text,
        name="metadata",
        nullable=False,
        default="{}",
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "token": self.token,
            "token_id": self.token_id,
            "user_id": self.user_id,
            "datasource_ids": self.datasource_ids,
            "default_datasource_id": str(self.default_datasource_id) if self.default_datasource_id else None,
            "ssh_host_ids": self.ssh_host_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "name": self.name,
            "metadata": json.loads(self.token_metadata) if self.token_metadata else {},
        }


class AdminUserModel(Base):
    """Admin用户数据模型

    存储管理员用户信息，包括用户名和密码哈希。
    目前仅支持一个固定的admin用户。
    """

    __tablename__ = "admin_users"

    # 主键（固定为 "admin"）
    username: Mapped[str] = mapped_column(String(128), primary_key=True)

    # 密码哈希（使用 PBKDF2 SHA256）
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "username": self.username,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DataSourceModel(Base):
    """数据源配置数据模型

    存储数据源连接配置信息，包括基本配置、连接参数、连接池参数和负载均衡参数。
    """

    __tablename__ = "datasources"

    # 主键：UUID（唯一标识，即使删除重建同名数据源也不会复用）
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )

    # 名称（唯一索引，用于用户友好的标识）
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    # 基本配置
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deploy_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="dmstandalone",
    )
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 连接参数
    dsn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    host: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="localhost",
    )
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=5236)
    user: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        default="SYSDBA",
    )
    password: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # DPC集群配置（JSON字符串存储）
    dpc_cluster: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 连接池参数
    minsize: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    maxsize: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    timeout: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)

    # 负载均衡参数
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # 所有者（创建该数据源的用户ID；admin 用户不受此限制）
    owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("enabled", True)
        kwargs.setdefault("deploy_type", "dmstandalone")
        kwargs.setdefault("read_only", False)
        kwargs.setdefault("dsn", "")
        kwargs.setdefault("host", "localhost")
        kwargs.setdefault("port", 5236)
        kwargs.setdefault("user", "SYSDBA")
        kwargs.setdefault("password", "")
        kwargs.setdefault("minsize", 1)
        kwargs.setdefault("maxsize", 10)
        kwargs.setdefault("timeout", 30.0)
        kwargs.setdefault("weight", 1)
        super().__init__(**kwargs)

    def to_dict(self, include_password: bool = False) -> dict[str, Any]:
        """转换为字典

        Args:
            include_password: 是否包含明文密码（默认 False，脱敏）

        Returns:
            dict[str, Any]: 包含模型所有字段的字典
        """
        result = {
            "id": str(self.id),
            "name": self.name,
            "enabled": self.enabled,
            "deploy_type": self.deploy_type,
            "read_only": self.read_only,
            "dsn": self.dsn,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "dpc_cluster": self.dpc_cluster,
            "minsize": self.minsize,
            "maxsize": self.maxsize,
            "timeout": self.timeout,
            "weight": self.weight,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_password:
            result["password"] = self.password
        return result


class CliGroupModel(Base):
    """CLI 分组元数据（邻接表）

    身份由 12 字符 base62 短 ``id`` 表征，``name`` 仅是当前层级的段名（如 "mysql"）。
    重命名 = 改 ``name``；移动 = 改 ``parent_id``。完整 path 由 id 链按需拼接。
    """

    __tablename__ = "mcp_cli_groups"

    id: Mapped[str] = mapped_column(
        String(12),
        primary_key=True,
        default=generate_short_id,
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(12),
        ForeignKey("mcp_cli_groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    short_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    long_description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint("parent_id", "name", name="uq_group_parent_name"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class EntityGroupAssignmentModel(Base):
    """MCP 实体（tool / resource / prompt）↔ CLI 分组归属

    一个实体最多一行 assignment；没有行表示"沿用 Provider 默认 group 或无分组"。
    分组删除时 CASCADE 连带删除归属行 → 实体回退到默认 group。
    """

    __tablename__ = "mcp_entity_group_assignments"

    object_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    key: Mapped[str] = mapped_column(String(512), primary_key=True)

    group_id: Mapped[str] = mapped_column(
        String(12),
        ForeignKey("mcp_cli_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "key": self.key,
            "group_id": self.group_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AppSettingsModel(Base):
    """应用设置数据模型

    存储应用级别的设置，如默认数据源名称等。
    使用 key-value 存储方式。
    """

    __tablename__ = "app_settings"

    # 主键：设置键名
    key: Mapped[str] = mapped_column(String(128), primary_key=True)

    # 设置值
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MetadataOverrideModel(Base):
    """统一元数据覆盖模型（仅描述/启用开关）

    合并 tool/resource/prompt 的元数据覆盖，用 object_type 区分类型。
    分组归属由 ``EntityGroupAssignmentModel`` 单独承担。
    name 写死不可修改（无 display_name 字段）。
    资源使用 name（而非 uri）作为 key。
    """

    __tablename__ = "mcp_metadata_overrides"

    # 对象类型：tool | resource | prompt
    object_type: Mapped[str] = mapped_column(String(20), primary_key=True)
    # 对象标识：tool_name / resource_name / prompt_name
    key: Mapped[str] = mapped_column(String(512), primary_key=True)

    # 覆盖的短描述
    short_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 覆盖的长描述
    long_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 是否禁用
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_type": self.object_type,
            "key": self.key,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "disabled": self.disabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class GenericSqlDefinitionModel(Base):
    """通用SQL定义模型

    存储通过数据库定义的MCP工具或资源的SQL模板和元数据。
    """

    __tablename__ = "generic_sql_definitions"

    # 主键：UUID
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )

    # 工具/资源名称
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # 类型："tool" 或 "resource"
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="tool")

    # SQL模板（支持 :param 占位符）
    sql_template: Mapped[str] = mapped_column(Text, nullable=False)

    # 描述信息
    short_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    long_description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 分组路径（与 CliGroupModel.path 对应）
    group: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # 输入Schema（JSON格式，用于Tool）
    input_schema: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 是否需要token认证
    requires_token_auth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 是否启用
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "id": str(self.id),
            "name": self.name,
            "type": self.type,
            "sql_template": self.sql_template,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "group": self.group,
            "input_schema": json.loads(self.input_schema) if self.input_schema else None,
            "requires_token_auth": self.requires_token_auth,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TokenDBObjectConfigModel(Base):
    """[DEPRECATED] Token 级数据库对象元数据配置模型

    已取消 Token 级覆盖，此模型不再使用。保留表结构待后续版本清理。
    """

    __tablename__ = "token_db_object_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )

    # 关联 Token
    token: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    # 对象类型：SCHEMA, TABLE, VIEW, COLUMN
    object_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # 对象标识
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 对象级访问策略：None=未设置（遵循全局模式），"allow"=强制可见，"deny"=强制不可见
    access_policy: Mapped[Literal["allow", "deny"] | None] = mapped_column(
        String(16), nullable=True, default=None
    )

    # comment 覆盖（None 表示不覆盖，使用数据库原始值）
    comment_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "token",
            "object_type",
            "schema_name",
            "table_name",
            "column_name",
            name="uq_token_db_object",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典

        Returns:
            dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "id": str(self.id),
            "token": self.token,
            "object_type": self.object_type,
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "access_policy": self.access_policy,
            "comment_override": self.comment_override,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DBObjectConfigModel(Base):
    """数据库对象元数据配置模型

    绑定到具体数据源，该数据源下所有 Token 默认继承。
    """

    __tablename__ = "datasource_db_object_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )

    # 关联数据源
    datasource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), nullable=False, index=True
    )

    # 对象类型：SCHEMA, TABLE, VIEW, COLUMN
    object_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # 对象标识
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 对象级访问策略
    access_policy: Mapped[Literal["allow", "deny"] | None] = mapped_column(
        String(16), nullable=True, default=None
    )

    # comment 覆盖
    comment_override: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "datasource_id",
            "object_type",
            "schema_name",
            "table_name",
            "column_name",
            name="uq_datasource_db_object",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "datasource_id": str(self.datasource_id),
            "object_type": self.object_type,
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "access_policy": self.access_policy,
            "comment_override": self.comment_override,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DBSystemObjectDefaultModel(Base):
    """全局系统对象默认元数据模型

    存储 DM8 系统视图的预置中文注释，所有数据源共享。
    仅包含 comment_override，不包含 access_policy（系统对象的可见性由 Token 全局模式兜底）。
    """

    __tablename__ = "db_system_object_defaults"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )

    # 对象类型：SCHEMA, TABLE, VIEW, COLUMN
    object_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # 对象标识（系统对象的 schema 通常是 SYS）
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 仅 comment 覆盖（系统对象的默认中文注释）
    comment_override: Mapped[str] = mapped_column(Text, nullable=False)

    # 可选：数据类型描述（用于文档展示）
    data_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        UniqueConstraint(
            "object_type",
            "schema_name",
            "table_name",
            "column_name",
            name="uq_system_object_default",
        ),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "object_type": self.object_type,
            "schema_name": self.schema_name,
            "table_name": self.table_name,
            "column_name": self.column_name,
            "comment_override": self.comment_override,
            "data_type": self.data_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class OAuthProviderModel(Base):
    """OAuth 提供商配置数据模型

    存储 OAuth 提供商的配置信息，支持内置（google/microsoft/github）
    和自定义（custom）provider。client_secret 以 Fernet 加密形式存储。
    """

    __tablename__ = "oauth_providers"

    # 槽位：固定 4 个值（google / microsoft / github / custom）
    slot: Mapped[str] = mapped_column(
        String(16),
        primary_key=True,
    )

    # OAuth 标识（authlib key + callback URL 路径段）
    # builtin: 锁定 = slot; custom: 可由 API 自由设定，默认 "custom"
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")

    # 前端按钮文案，如 "用 Google 登录"
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 是否为内置 provider（slot != 'custom' 时 true）
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # provider 级启用开关
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 前端登录页是否显示
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # OAuth 凭证
    client_id: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    client_secret_enc: Mapped[str] = mapped_column(
        String(2048), nullable=False, default=""
    )

    # OAuth scope 列表（JSON 格式）
    scopes: Mapped[str] = mapped_column(
        String(512), nullable=False, default='["openid", "email", "profile"]'
    )

    # 自定义端点（slot='custom' 时用，builtin 留空）
    discovery_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    authorization_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    token_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    userinfo_endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True)
    jwks_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    __table_args__ = (
        CheckConstraint(
            "slot IN ('google', 'microsoft', 'github', 'oidc')",
            name="ck_oauth_providers_slot",
        ),
        UniqueConstraint("name", name="uq_oauth_providers_name"),
    )

    def to_dict(self, include_secret: bool = False) -> dict[str, Any]:
        """转换为字典

        Args:
            include_secret: 是否包含加密后的 client_secret（默认 False）

        Returns:
            dict[str, Any]: 包含模型字段的字典
        """
        result: dict[str, Any] = {
            "slot": self.slot,
            "name": self.name,
            "display_name": self.display_name,
            "is_builtin": self.is_builtin,
            "enabled": self.enabled,
            "visible": self.visible,
            "client_id": self.client_id,
            "scopes": json.loads(self.scopes) if self.scopes else [],
            "discovery_url": self.discovery_url,
            "authorization_endpoint": self.authorization_endpoint,
            "token_endpoint": self.token_endpoint,
            "userinfo_endpoint": self.userinfo_endpoint,
            "jwks_uri": self.jwks_uri,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_secret:
            result["client_secret_enc"] = self.client_secret_enc
        return result


class SSHHostModel(Base):
    """SSH 主机配置数据模型

    存储 SSH 连接信息，密码以 Fernet 加密形式存储。
    免密模式（key_based=True）时 password_enc 为空，依赖 OS 级 ssh-agent 或密钥。
    """

    __tablename__ = "ssh_hosts"

    # 主键：UUID
    id: Mapped[uuid.UUID] = mapped_column(
        GUID(), primary_key=True, default=uuid.uuid4
    )

    # 名称（唯一索引，用户友好标识）
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    # 主机地址
    host: Mapped[str] = mapped_column(String(255), nullable=False)

    # SSH 端口
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)

    # 登录用户名
    username: Mapped[str] = mapped_column(String(128), nullable=False)

    # 认证方式
    key_based: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # 密码（Fernet 加密存储；key_based=True 时为空字符串）
    password_enc: Mapped[str] = mapped_column(
        String(2048), nullable=False, default=""
    )

    # 描述
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 创建者（用于权限过滤，类似 DataSourceModel.owner_id）
    owner_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )

    def to_dict(self, include_secret: bool = False) -> dict[str, Any]:
        result = {
            "id": str(self.id),
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "key_based": self.key_based,
            "description": self.description,
            "owner_id": self.owner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_secret:
            result["password_enc"] = self.password_enc
        return result
