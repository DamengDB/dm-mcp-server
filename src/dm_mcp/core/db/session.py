"""数据库会话管理模块

提供异步数据库会话管理功能，支持SQLite、达梦、MySQL、PostgreSQL等多种数据库。
包括数据库初始化、表创建、会话获取等功能。
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dm_mcp.settings.database_config import (
    DamengConfig,
    DatabaseConfig,
    MySQLConfig,
    PostgreSQLConfig,
    SQLiteConfig,
)

from .models import AdminUserModel, AppSettingsModel, Base, DataSourceModel, TokenModel

logger = logging.getLogger(__name__)

# 全局引擎和会话工厂
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _ensure_dameng_schema_if_needed(cfg: DamengConfig) -> None:
    """在达梦中确保目标模式存在

    仅在配置了database时生效。
    - 如果cfg.database为空：不做任何事，使用登录用户默认模式。
    - 如果cfg.database非空：尝试执行CREATE SCHEMA，如果已存在则忽略错误。

    Args:
        cfg: 达梦数据库配置
    """
    schema = cfg.database
    if not schema:
        return

    password = cfg.password.get_secret_value()
    base_url = f"dm+dmPython://{cfg.user}:{password}" f"@{cfg.host}:{cfg.port}/"

    engine = create_engine(base_url, future=True)
    try:
        with engine.connect() as conn:
            # 使用双引号保证大小写一致
            stmt = sa_text(f'CREATE SCHEMA "{schema}" AUTHORIZATION "{cfg.user}"')
            try:
                conn.execute(stmt)
                conn.commit()
                logger.info(
                    f'已在达梦中创建模式 "{schema}" (AUTHORIZATION "{cfg.user}")'
                )
            except Exception as e:  # noqa: BLE001
                # 如果模式已存在或没有权限，记录日志后继续使用（由后续操作报错）
                logger.info(
                    f'创建达梦模式 "{schema}" 时出现异常，可能已存在或权限不足: {e}'
                )
    finally:
        engine.dispose()


def _ensure_mysql_database_if_needed(cfg: MySQLConfig) -> None:
    """在MySQL中确保目标数据库存在

    仅在配置了database时生效。
    - 如果cfg.database为空：不做任何事。
    - 如果cfg.database非空：尝试执行CREATE DATABASE IF NOT EXISTS。

    Args:
        cfg: MySQL数据库配置
    """
    db_name = cfg.database
    if not db_name:
        return

    password = cfg.password.get_secret_value()
    # 不指定数据库名，连接到服务器级别
    server_url = f"mysql+pymysql://{cfg.user}:{password}" f"@{cfg.host}:{cfg.port}/"

    engine = create_engine(server_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            stmt = sa_text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"DEFAULT CHARACTER SET {cfg.charset}"
            )
            try:
                conn.execute(stmt)
                logger.info(f"已在 MySQL 中创建数据库 `{db_name}`（如不存在）")
            except Exception as e:  # noqa: BLE001
                logger.info(
                    f"创建 MySQL 数据库 `{db_name}` 时出现异常，可能已存在或权限不足: {e}"
                )
    finally:
        engine.dispose()


def _ensure_postgres_database_if_needed(cfg: PostgreSQLConfig) -> None:
    """在PostgreSQL中确保目标数据库存在

    仅在配置了database时生效。
    - 如果cfg.database为空：不做任何事。
    - 如果cfg.database非空：连接到postgres库，尝试CREATE DATABASE。

    Args:
        cfg: PostgreSQL数据库配置
    """
    db_name = cfg.database
    if not db_name:
        return

    password = cfg.password.get_secret_value()
    server_url = (
        f"postgresql+psycopg2://{cfg.user}:{password}"
        f"@{cfg.host}:{cfg.port}/postgres"
    )

    engine = create_engine(server_url, future=True)
    try:
        with engine.connect() as conn:
            stmt = sa_text(f'CREATE DATABASE "{db_name}"')
            try:
                conn.execute(stmt)
                logger.info(f'已在 PostgreSQL 中创建数据库 "{db_name}"')
            except Exception as e:  # noqa: BLE001
                # 如果已存在或权限不足，记录日志后继续
                logger.info(
                    f'创建 PostgreSQL 数据库 "{db_name}" 时出现异常，可能已存在或权限不足: {e}'
                )
    finally:
        engine.dispose()


def build_database_url(cfg: DatabaseConfig) -> str:
    """根据配置构建数据库连接URL

    支持SQLite、达梦、MySQL、PostgreSQL等多种数据库类型。

    Args:
        cfg: 数据库配置对象

    Returns:
        str: 数据库连接URL字符串

    Raises:
        ValueError: 当数据库类型不支持时
    """
    db_type = cfg.db_type
    active_config = cfg.get_active_config()

    if db_type == "sqlite":
        assert isinstance(active_config, SQLiteConfig)
        db_path = Path(active_config.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite+aiosqlite:///{db_path.absolute()}"

    elif db_type == "dameng":
        assert isinstance(active_config, DamengConfig)
        password = active_config.password.get_secret_value()
        # 达梦数据库：使用 dmSQLAlchemy 异步方言（dm+dmAsync）
        base_url = (
            f"dm+dmAsync://{active_config.user}:{password}"
            f"@{active_config.host}:{active_config.port}"
        )
        # database 为空时使用登录用户默认模式（如 SYSDBA），不在 URL 中指定模式名，避免 Invalid schema。
        if active_config.database:
            return f"{base_url}/{active_config.database}"
        else:
            return f"{base_url}/"

    elif db_type == "mysql":
        assert isinstance(active_config, MySQLConfig)
        password = active_config.password.get_secret_value()
        return (
            f"mysql+aiomysql://{active_config.user}:{password}"
            f"@{active_config.host}:{active_config.port}/{active_config.database}"
            f"?charset={active_config.charset}"
        )

    elif db_type == "postgresql":
        assert isinstance(active_config, PostgreSQLConfig)
        password = active_config.password.get_secret_value()
        return (
            f"postgresql+asyncpg://{active_config.user}:{password}"
            f"@{active_config.host}:{active_config.port}/{active_config.database}"
        )

    else:
        raise ValueError(f"不支持的数据库类型: {db_type}")


def init_db(cfg: DatabaseConfig) -> None:
    """初始化数据库引擎和会话工厂

    根据配置创建异步数据库引擎和会话工厂，支持自动创建数据库/模式。
    如果引擎已初始化，则跳过重复初始化。

    Args:
        cfg: 数据库配置对象
    """
    global _engine, _async_session_maker

    if _engine is not None:
        logger.warning("数据库引擎已初始化，跳过重复初始化")
        return

    # 在创建异步引擎前，为不同数据库类型执行一次性初始化逻辑：
    # - 达梦：确保目标模式存在（CREATE SCHEMA）。
    # - MySQL：确保目标数据库存在（CREATE DATABASE IF NOT EXISTS）。
    # - PostgreSQL：确保目标数据库存在（CREATE DATABASE）。
    if cfg.db_type == "dameng":
        dameng_cfg = cfg.get_active_config()
        assert isinstance(dameng_cfg, DamengConfig)
        _ensure_dameng_schema_if_needed(dameng_cfg)
    elif cfg.db_type == "mysql":
        mysql_cfg = cfg.get_active_config()
        assert isinstance(mysql_cfg, MySQLConfig)
        _ensure_mysql_database_if_needed(mysql_cfg)
    elif cfg.db_type == "postgresql":
        pg_cfg = cfg.get_active_config()
        assert isinstance(pg_cfg, PostgreSQLConfig)
        _ensure_postgres_database_if_needed(pg_cfg)

    database_url = build_database_url(cfg)

    # 根据数据库类型设置不同的连接参数
    connect_args = {}
    if cfg.db_type == "sqlite":
        connect_args = {"check_same_thread": False}

    # 达梦数据库（dmAsync）不支持 pool_pre_ping，需要禁用
    # 其他数据库类型可以使用 pool_pre_ping
    pool_pre_ping = cfg.pool_pre_ping if cfg.db_type != "dameng" else False

    # 创建异步引擎
    _engine = create_async_engine(
        database_url,
        echo=cfg.echo,
        future=True,
        connect_args=connect_args,
        pool_pre_ping=pool_pre_ping,
    )

    # 创建会话工厂
    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False,
    )

    logger.info(f"数据库引擎已初始化: type={cfg.db_type}, url={database_url}")


async def create_tables() -> None:
    """创建所有数据库表

    如果表不存在则创建，如果已存在则跳过。根据要求，不创建索引。

    Raises:
        RuntimeError: 当数据库引擎未初始化时
    """
    if _engine is None:
        raise RuntimeError("数据库引擎未初始化，请先调用 init_db()")

    async with _engine.begin() as conn:
        # 创建所有表（不创建索引）
        await conn.run_sync(Base.metadata.create_all)
        logger.info("数据库表已创建或已存在")


async def close_db() -> None:
    """关闭数据库连接

    释放数据库引擎和会话工厂，清理资源。
    """
    global _engine, _async_session_maker

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None
        logger.info("数据库连接已关闭")


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """获取异步数据库会话

    异步上下文管理器，自动处理事务提交和回滚。
    使用方式：
        async with get_async_session() as session:
            # 使用 session 进行操作
            pass

    Yields:
        AsyncSession: 异步数据库会话对象

    Raises:
        RuntimeError: 当数据库会话工厂未初始化时
    """
    if _async_session_maker is None:
        raise RuntimeError("数据库会话工厂未初始化，请先调用 init_db()")

    async with _async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
