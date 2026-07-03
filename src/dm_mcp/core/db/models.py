"""数据库模型模块

提供SQLAlchemy ORM模型定义，包括Token模型、Admin用户模型和数据源模型。
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import TIMESTAMP, Boolean, Float, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import CHAR, TypeDecorator


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

    # 主键
    token: Mapped[str] = mapped_column(String(512), primary_key=True)

    # 用户信息
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)

    # 绑定的数据源 ID（UUID，强制一 Token 一数据源）
    datasource_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        nullable=False,
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
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # 描述信息
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 元数据（JSON 存储）- 使用 token_metadata 避免与 DeclarativeBase.metadata 冲突
    token_metadata: Mapped[str] = mapped_column(
        Text,
        name="metadata",
        nullable=False,
        default="{}",
    )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            Dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "token": self.token,
            "user_id": self.user_id,
            "datasource_id": str(self.datasource_id),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "last_used_at": self.last_used_at,
            "description": self.description,
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            Dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "username": self.username,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
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
        default="dmstandonle",
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
    dpc_cluster: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 连接池参数
    minsize: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    maxsize: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    timeout: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)

    # 负载均衡参数
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            Dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "enabled": self.enabled,
            "deploy_type": self.deploy_type,
            "read_only": self.read_only,
            "dsn": self.dsn,
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "dpc_cluster": self.dpc_cluster,
            "minsize": self.minsize,
            "maxsize": self.maxsize,
            "timeout": self.timeout,
            "weight": self.weight,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
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

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典

        Returns:
            Dict[str, Any]: 包含模型所有字段的字典
        """
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
