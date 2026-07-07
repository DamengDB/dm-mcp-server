"""数据库会话管理模块

提供异步数据库会话管理功能，支持SQLite、达梦、MySQL、PostgreSQL等多种数据库。
包括数据库初始化、表创建、会话获取等功能。
"""

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy import text as sa_text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from dm_mcp.common import messages
from dm_mcp.infra.config.database_config import (
    DamengConfig,
    DatabaseConfig,
    MySQLConfig,
    PostgreSQLConfig,
    SQLiteConfig,
)

from .models import Base
from .schema_check import verify_schema_compatible_sync

logger = logging.getLogger(__name__)

# 全局引擎和会话工厂
_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None

# 防止同一事件循环内并发 create_all（与多进程竞态下的重试逻辑配合）
_create_tables_lock = asyncio.Lock()


def _sync_create_all_tables(sync_conn) -> None:
    """在 run_sync 中执行的同步建表（显式 checkfirst）。"""
    Base.metadata.create_all(sync_conn, checkfirst=True)

# 安全的 SQL 标识符正则：字母、数字、下划线，且不以数字开头
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_sql_identifier(name: str, context: str = "identifier") -> None:
    """验证 SQL 标识符不包含危险字符，防止标识符注入

    仅允许字母、数字和下划线，且不以数字开头。
    这是保守策略，覆盖达梦/MySQL/PostgreSQL 的通用安全子集。

    Args:
        name: 要验证的标识符名称
        context: 上下文描述（用于错误消息）

    Raises:
        ValueError: 当标识符包含非法字符时
    """
    if not _SAFE_IDENTIFIER_RE.match(name):
        raise ValueError(
            messages.MSG_DB_UNSAFE_SQL_IDENTIFIER.format(context=context, name=name)
        )


def _ensure_database_if_needed(
    server_url: str,
    create_stmt: str,
    db_name: str,
    *,
    connect_args: dict | None = None,
    isolation_level: str | None = None,
    commit: bool = False,
) -> None:
    """确保目标数据库/模式存在

    通用辅助函数，用于不同数据库类型的数据库/模式初始化。
    执行 CREATE 语句，忽略已存在的错误。

    Args:
        server_url: 服务器级连接 URL（不指定数据库/模式）
        create_stmt: CREATE DATABASE/SCHEMA 语句
        db_name: 数据库/模式名称（用于日志）
        connect_args: 额外的连接参数
        isolation_level: 事务隔离级别（如 AUTOCOMMIT）
        commit: 是否在执行后显式 commit
    """
    engine_kwargs: dict = {"future": True}
    if connect_args:
        engine_kwargs["connect_args"] = connect_args
    if isolation_level:
        engine_kwargs["isolation_level"] = isolation_level

    engine = create_engine(server_url, **engine_kwargs)
    try:
        with engine.connect() as conn:
            try:
                conn.execute(sa_text(create_stmt))
                if commit:
                    conn.commit()
                logger.info(f'已创建数据库/模式 "{db_name}"（如不存在）')
            except Exception as e:  # noqa: BLE001
                logger.info(
                    f'创建数据库/模式 "{db_name}" 时出现异常，可能已存在或权限不足: {e}'
                )
    finally:
        engine.dispose()


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

    _validate_sql_identifier(schema, context="schema 名称")
    _validate_sql_identifier(cfg.user, context="用户名称")

    password = cfg.password.get_secret_value()
    base_url = f"dm+dmPython://{cfg.user}:{password}" f"@{cfg.host}:{cfg.port}/"

    _ensure_database_if_needed(
        server_url=base_url,
        create_stmt=f'CREATE SCHEMA "{schema}" AUTHORIZATION "{cfg.user}"',
        db_name=schema,
        connect_args={"local_code": 1},
        commit=True,
    )


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

    _validate_sql_identifier(db_name, context="database 名称")

    password = cfg.password.get_secret_value()
    server_url = f"mysql+pymysql://{cfg.user}:{password}" f"@{cfg.host}:{cfg.port}/"

    _ensure_database_if_needed(
        server_url=server_url,
        create_stmt=f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
        f"DEFAULT CHARACTER SET {cfg.charset}",
        db_name=db_name,
        isolation_level="AUTOCOMMIT",
    )


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

    _validate_sql_identifier(db_name, context="database 名称")

    password = cfg.password.get_secret_value()
    server_url = (
        f"postgresql+psycopg2://{cfg.user}:{password}"
        f"@{cfg.host}:{cfg.port}/postgres"
    )

    _ensure_database_if_needed(
        server_url=server_url,
        create_stmt=f'CREATE DATABASE "{db_name}"',
        db_name=db_name,
    )


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
        raise ValueError(messages.MSG_DB_UNSUPPORTED_TYPE.format(db_type=db_type))


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
    connect_args: dict = {}
    if cfg.db_type == "sqlite":
        connect_args = {"check_same_thread": False}
    elif cfg.db_type == "dameng":
        connect_args = {"local_code": 1}

    # 达梦数据库（dmAsync）不支持 pool_pre_ping，需要禁用
    # 其他数据库类型可以使用 pool_pre_ping
    pool_pre_ping = cfg.pool_pre_ping if cfg.db_type != "dameng" else False

    # 达梦数据库不支持 pool_pre_ping，需用 pool_recycle 兜底防止拿到死连接
    # 用户未配置时，默认 300 秒（小于达梦默认 IDLE_TIME 10 分钟）
    pool_recycle = cfg.pool_recycle
    if cfg.db_type == "dameng" and pool_recycle == 0:
        pool_recycle = 300

    # 创建异步引擎
    engine_kwargs: dict = dict(
        echo=cfg.echo,
        future=True,
        connect_args=connect_args,
        pool_pre_ping=pool_pre_ping,
    )
    if pool_recycle > 0:
        engine_kwargs["pool_recycle"] = pool_recycle

    _engine = create_async_engine(database_url, **engine_kwargs)

    # 创建会话工厂
    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False,
    )

    recycle_info = f", pool_recycle={pool_recycle}s" if pool_recycle > 0 else ""
    logger.info(
        f"数据库引擎已初始化: type={cfg.db_type}, url={database_url}{recycle_info}"
    )


async def create_tables() -> None:
    """创建所有数据库表

    如果表不存在则创建，如果已存在则跳过。根据要求，不创建索引。

    说明：SQLite 上多进程或热重载可能让两个 ``create_all`` 几乎同时通过
    ``checkfirst`` 后都去执行 ``CREATE TABLE``，从而出现
    ``table ... already exists``。本函数在同进程内串行化建表，并对该类
    ``OperationalError`` 做有限次重试（新事务下再次 ``create_all``）。

    Raises:
        RuntimeError: 当数据库引擎未初始化时
    """
    if _engine is None:
        raise RuntimeError(messages.MSG_DB_ENGINE_NOT_INIT)

    max_attempts = 5
    async with _create_tables_lock:
        last_err: OperationalError | None = None
        for attempt in range(max_attempts):
            try:
                async with _engine.begin() as conn:
                    await conn.run_sync(_sync_create_all_tables)
                logger.info("数据库表已创建或已存在")
                return
            except OperationalError as e:
                last_err = e
                orig = getattr(e, "orig", None)
                combined = f"{e} {orig or ''}".lower()
                if "already exists" not in combined:
                    raise
                logger.warning(
                    "建表遇到「已存在」类冲突（常见于多进程/热重载），"
                    "将重试 create_all: attempt=%s/%s, err=%s",
                    attempt + 1,
                    max_attempts,
                    e,
                )
        if last_err is not None:
            raise last_err


def get_schema_location_hint(cfg: DatabaseConfig) -> str:
    """返回用于错误提示的数据库/schema 位置描述。"""
    active_config = cfg.get_active_config()
    if cfg.db_type == "sqlite":
        assert isinstance(active_config, SQLiteConfig)
        return str(Path(active_config.db_path).absolute())
    if cfg.db_type == "dameng":
        assert isinstance(active_config, DamengConfig)
        return active_config.database or active_config.user
    if cfg.db_type == "mysql":
        assert isinstance(active_config, MySQLConfig)
        return active_config.database
    if cfg.db_type == "postgresql":
        assert isinstance(active_config, PostgreSQLConfig)
        return active_config.database
    return cfg.db_type


async def ensure_schema_compatible(*, schema_hint: str) -> None:
    """校验元数据库结构与当前模型一致，不兼容则阻止启动。"""
    if _engine is None:
        raise RuntimeError(messages.MSG_DB_ENGINE_NOT_INIT)

    async with _engine.connect() as conn:
        await conn.run_sync(
            verify_schema_compatible_sync,
            schema_hint=schema_hint,
        )
    logger.info("元数据库结构校验通过")


async def bootstrap_schema(cfg: DatabaseConfig) -> None:
    """建表并校验结构（启动时调用）。"""
    await create_tables()
    await ensure_schema_compatible(schema_hint=get_schema_location_hint(cfg))


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
        raise RuntimeError(messages.MSG_DB_SESSION_FACTORY_NOT_INIT)

    async with _async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
