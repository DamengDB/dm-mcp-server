from typing import Literal

from pydantic import BaseModel, Field, SecretStr


class SQLiteConfig(BaseModel):
    """SQLite 数据库配置"""

    db_path: str = Field(default="server.db", description="SQLite 数据库文件路径")


class DamengConfig(BaseModel):
    """达梦数据库配置（异步，dm+dmAsync）"""

    host: str = Field(default="localhost", description="主机地址")
    port: int = Field(default=5236, ge=1, le=65535, description="端口号")
    user: str = Field(default="SYSDBA", description="用户名")
    password: SecretStr = Field(default=SecretStr("SYSDBA"), description="密码")
    # 目标数据库/模式名（可选）。
    # - 留空：使用当前登录用户的默认模式（如 SYSDBA），不会自动创建新模式。
    # - 设置为 DMMCP 等：要求该模式已在达梦中手工创建，否则会报 Invalid schema name。
    database: str = Field(default="", description="数据库名/模式名（可选）")


class MySQLConfig(BaseModel):
    """MySQL 数据库配置"""

    host: str = Field(default="localhost", description="主机地址")
    port: int = Field(default=3306, ge=1, le=65535, description="端口号")
    user: str = Field(default="root", description="用户名")
    password: SecretStr = Field(default=SecretStr(""), description="密码")
    database: str = Field(default="DMMCP", description="数据库名")
    charset: str = Field(default="utf8mb4", description="字符集")


class PostgreSQLConfig(BaseModel):
    """PostgreSQL 数据库配置"""

    host: str = Field(default="localhost", description="主机地址")
    port: int = Field(default=5432, ge=1, le=65535, description="端口号")
    user: str = Field(default="postgres", description="用户名")
    password: SecretStr = Field(default=SecretStr(""), description="密码")
    database: str = Field(default="DMMCP", description="数据库名")


class DatabaseConfig(BaseModel):
    """数据库配置（支持多种数据库类型）"""

    # 数据库类型选择
    db_type: Literal["sqlite", "dameng", "mysql", "postgresql"] = Field(
        default="sqlite", description="数据库类型"
    )

    # 各数据库的配置（根据 db_type 选择使用哪个）
    sqlite: SQLiteConfig = Field(default_factory=SQLiteConfig)
    dameng: DamengConfig = Field(default_factory=DamengConfig)
    mysql: MySQLConfig = Field(default_factory=MySQLConfig)
    postgresql: PostgreSQLConfig = Field(default_factory=PostgreSQLConfig)

    # 通用连接参数
    echo: bool = Field(default=False, description="是否打印 SQL 语句（调试用）")
    pool_pre_ping: bool = Field(default=True, description="连接池预检查")
    pool_recycle: int = Field(
        default=0, ge=0, description="连接回收时间（秒），0 表示不回收"
    )

    def get_active_config(self):
        """获取当前激活的数据库配置"""
        config_map = {
            "sqlite": self.sqlite,
            "dameng": self.dameng,
            "mysql": self.mysql,
            "postgresql": self.postgresql,
        }
        return config_map[self.db_type]
