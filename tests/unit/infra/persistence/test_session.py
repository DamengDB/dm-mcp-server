"""数据库会话管理测试模块"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import SecretStr

from dm_mcp.infra.persistence import session
from dm_mcp.infra.config.database_config import (
    DamengConfig,
    DatabaseConfig,
    MySQLConfig,
    PostgreSQLConfig,
    SQLiteConfig,
)


class TestBuildDatabaseUrl:
    """测试构建数据库URL"""

    def test_build_sqlite_url(self, tmp_path):
        """测试构建SQLite数据库URL"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path))
        )

        url = session.build_database_url(config)
        assert url.startswith("sqlite+aiosqlite:///")
        assert str(db_path.absolute()) in url

    def test_build_sqlite_url_creates_directory(self, tmp_path):
        """测试构建SQLite URL时创建目录"""
        db_dir = tmp_path / "subdir" / "nested"
        db_path = db_dir / "test.db"
        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path))
        )

        url = session.build_database_url(config)
        assert db_dir.exists()
        assert url.startswith("sqlite+aiosqlite:///")

    def test_build_database_url_invalid_type(self, tmp_path):
        """测试不支持的数据库类型"""
        # 由于DatabaseConfig使用了Pydantic的Literal类型，无法创建无效的配置对象
        # 我们需要mock整个config对象来测试else分支
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path))
        )

        # Mock config对象，使其db_type返回无效值，get_active_config返回一个有效的配置对象
        # 这样会跳过前面的if/elif分支，直接到达else分支
        mock_config = MagicMock()
        mock_config.db_type = "invalid_type"
        # get_active_config返回一个对象，这样不会因为KeyError而提前失败
        mock_config.get_active_config.return_value = SQLiteConfig(db_path=str(db_path))

        with pytest.raises(ValueError) as exc_info:
            session.build_database_url(mock_config)
        assert "不支持的数据库类型" in str(exc_info.value)
        assert "invalid_type" in str(exc_info.value)


class TestInitDb:
    """测试数据库初始化"""

    @pytest.fixture
    def reset_db_session(self):
        """重置数据库会话模块的全局变量"""
        # 保存原始值
        original_engine = session._engine
        original_session_maker = session._async_session_maker

        # 重置为None
        session._engine = None
        session._async_session_maker = None

        yield

        # 恢复原始值
        session._engine = original_engine
        session._async_session_maker = original_session_maker

    @pytest.mark.asyncio
    async def test_init_db_sqlite(self, tmp_path, reset_db_session):
        """测试初始化SQLite数据库"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path))
        )

        with (
            patch("dm_mcp.infra.persistence.session.create_async_engine") as mock_engine,
            patch("dm_mcp.infra.persistence.session.async_sessionmaker") as mock_session_maker,
        ):
            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            mock_session_factory = MagicMock()
            mock_session_maker.return_value = mock_session_factory

            session.init_db(config)

            # 验证引擎被创建
            mock_engine.assert_called_once()
            # 验证会话工厂被创建
            mock_session_maker.assert_called_once()
            # 验证全局变量被设置
            assert session._engine == mock_engine_instance
            assert session._async_session_maker == mock_session_factory

    def test_init_db_skip_if_already_initialized(self, tmp_path, reset_db_session):
        """测试重复初始化时跳过"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path))
        )

        # 设置一个已有的引擎
        mock_existing_engine = MagicMock()
        session._engine = mock_existing_engine

        with patch("dm_mcp.infra.persistence.session.create_async_engine") as mock_engine:
            session.init_db(config)

            # 不应该创建新引擎
            mock_engine.assert_not_called()
            # 引擎应该保持原样
            assert session._engine == mock_existing_engine


class TestCreateTables:
    """测试创建表"""

    @pytest.mark.asyncio
    async def test_create_tables_success(self):
        """测试成功创建表"""
        mock_engine = MagicMock()
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_conn.run_sync = AsyncMock()

        session._engine = mock_engine

        await session.create_tables()

        mock_conn.run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tables_engine_not_initialized(self):
        """测试引擎未初始化时创建表"""
        session._engine = None

        with pytest.raises(RuntimeError) as exc_info:
            await session.create_tables()

        assert "数据库引擎未初始化" in str(exc_info.value)


class TestCloseDb:
    """测试关闭数据库"""

    @pytest.mark.asyncio
    async def test_close_db_success(self):
        """测试成功关闭数据库"""
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        session._engine = mock_engine
        session._async_session_maker = MagicMock()

        await session.close_db()

        mock_engine.dispose.assert_called_once()
        assert session._engine is None
        assert session._async_session_maker is None

    @pytest.mark.asyncio
    async def test_close_db_when_already_closed(self):
        """测试关闭已关闭的数据库（不应该报错）"""
        session._engine = None
        session._async_session_maker = None

        # 不应该抛出异常
        await session.close_db()


class TestGetAsyncSession:
    """测试获取异步会话"""

    @pytest.mark.asyncio
    async def test_get_async_session_success(self):
        """测试成功获取异步会话"""
        mock_session_maker = MagicMock()
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        # 模拟async_sessionmaker的上下文管理器
        async def session_context():
            yield mock_session

        mock_session_maker.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        session._async_session_maker = mock_session_maker

        async with session.get_async_session() as sess:
            assert sess == mock_session

        # 验证提交被调用
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_async_session_rollback_on_exception(self):
        """测试异常时回滚"""
        mock_session_maker = MagicMock()
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()

        async def session_context():
            yield mock_session

        mock_session_maker.return_value.__aenter__ = AsyncMock(
            return_value=mock_session
        )
        mock_session_maker.return_value.__aexit__ = AsyncMock(return_value=None)

        session._async_session_maker = mock_session_maker

        with pytest.raises(ValueError):
            async with session.get_async_session() as sess:
                raise ValueError("Test error")

        # 验证回滚被调用，提交不被调用
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_async_session_not_initialized(self):
        """测试会话工厂未初始化时获取会话"""
        session._async_session_maker = None

        with pytest.raises(RuntimeError) as exc_info:
            async with session.get_async_session():
                pass

        assert "数据库会话工厂未初始化" in str(exc_info.value)


class TestEnsureDamengSchemaIfNeeded:
    """测试达梦模式创建函数"""

    def test_empty_database_skips(self):
        """测试空 database 时跳过"""
        cfg = DamengConfig(
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            database="",
        )

        with patch("dm_mcp.infra.persistence.session.create_engine") as mock_engine:
            session._ensure_dameng_schema_if_needed(cfg)
            mock_engine.assert_not_called()

    def test_creates_schema_success(self):
        """测试成功创建模式"""
        cfg = DamengConfig(
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            database="NEW_SCHEMA",
        )

        with patch("dm_mcp.infra.persistence.session.create_engine") as mock_create_engine:
            mock_conn = MagicMock()
            mock_engine = MagicMock()
            mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.connect.return_value.__exit__ = MagicMock(return_value=None)
            mock_engine.dispose = MagicMock()
            mock_create_engine.return_value = mock_engine

            session._ensure_dameng_schema_if_needed(cfg)

            mock_create_engine.assert_called_once()
            mock_conn.execute.assert_called()

    def test_schema_already_exists_ignores_error(self):
        """测试模式已存在时忽略错误"""
        cfg = DamengConfig(
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            database="TEST_SCHEMA",
        )

        with patch("dm_mcp.infra.persistence.session.create_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.return_value.__exit__ = MagicMock(return_value=None)
            mock_conn.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.connect.return_value.__exit__ = MagicMock(return_value=None)
            # 模拟模式已存在
            mock_conn.execute.side_effect = Exception("schema already exists")

            # 不应该抛出异常
            session._ensure_dameng_schema_if_needed(cfg)


class TestEnsureMysqlDatabaseIfNeeded:
    """测试 MySQL 数据库创建函数"""

    def test_empty_database_skips(self):
        """测试空 database 时跳过"""
        cfg = MySQLConfig(
            host="localhost",
            port=3306,
            user="root",
            password=SecretStr("password"),
            database="",
            charset="utf8mb4",
        )

        with patch("dm_mcp.infra.persistence.session.create_engine") as mock_engine:
            session._ensure_mysql_database_if_needed(cfg)
            mock_engine.assert_not_called()

    def test_creates_database_success(self):
        """测试成功创建数据库"""
        cfg = MySQLConfig(
            host="localhost",
            port=3306,
            user="root",
            password=SecretStr("password"),
            database="TEST_DB",
            charset="utf8mb4",
        )

        with (
            patch("dm_mcp.infra.persistence.session.create_engine") as mock_engine,
            patch("dm_mcp.infra.persistence.session.sa_text") as mock_text,
        ):
            mock_conn = MagicMock()
            mock_engine.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.return_value.__exit__ = MagicMock(return_value=None)
            mock_conn.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.connect.return_value.__exit__ = MagicMock(return_value=None)

            session._ensure_mysql_database_if_needed(cfg)

            mock_engine.assert_called_once()


class TestEnsurePostgresDatabaseIfNeeded:
    """测试 PostgreSQL 数据库创建函数"""

    def test_empty_database_skips(self):
        """测试空 database 时跳过"""
        cfg = PostgreSQLConfig(
            host="localhost",
            port=5432,
            user="postgres",
            password=SecretStr("password"),
            database="",
        )

        with patch("dm_mcp.infra.persistence.session.create_engine") as mock_engine:
            session._ensure_postgres_database_if_needed(cfg)
            mock_engine.assert_not_called()

    def test_creates_database_success(self):
        """测试成功创建数据库"""
        cfg = PostgreSQLConfig(
            host="localhost",
            port=5432,
            user="postgres",
            password=SecretStr("password"),
            database="TEST_DB",
        )

        with patch("dm_mcp.infra.persistence.session.create_engine") as mock_engine:
            mock_conn = MagicMock()
            mock_engine.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_engine.return_value.__exit__ = MagicMock(return_value=None)
            mock_conn.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.connect.return_value.__exit__ = MagicMock(return_value=None)

            session._ensure_postgres_database_if_needed(cfg)

            mock_engine.assert_called_once()


class TestBuildDatabaseUrlFull:
    """测试构建数据库 URL 的完整路径"""

    def test_build_dameng_url_without_database(self):
        """测试达梦 URL 不带 database"""
        config = DatabaseConfig(
            db_type="dameng",
            dameng=DamengConfig(
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("password"),
                database="",
            ),
        )
        url = session.build_database_url(config)
        assert "dm+dmAsync://" in url
        assert "localhost:5236" in url

    def test_build_dameng_url_with_database(self):
        """测试达梦 URL 带 database"""
        config = DatabaseConfig(
            db_type="dameng",
            dameng=DamengConfig(
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("password"),
                database="TESTDB",
            ),
        )
        url = session.build_database_url(config)
        assert "dm+dmAsync://" in url
        assert "TESTDB" in url

    def test_build_mysql_url(self):
        """测试 MySQL URL"""
        config = DatabaseConfig(
            db_type="mysql",
            mysql=MySQLConfig(
                host="localhost",
                port=3306,
                user="root",
                password=SecretStr("password"),
                database="testdb",
                charset="utf8mb4",
            ),
        )
        url = session.build_database_url(config)
        assert "mysql+aiomysql://" in url
        assert "testdb" in url
        assert "utf8mb4" in url

    def test_build_postgresql_url(self):
        """测试 PostgreSQL URL"""
        config = DatabaseConfig(
            db_type="postgresql",
            postgresql=PostgreSQLConfig(
                host="localhost",
                port=5432,
                user="postgres",
                password=SecretStr("password"),
                database="testdb",
            ),
        )
        url = session.build_database_url(config)
        assert "postgresql+asyncpg://" in url
        assert "testdb" in url


class TestInitDbFull:
    """测试数据库初始化的完整路径"""

    @pytest.fixture
    def reset_db_session(self):
        """重置数据库会话模块的全局变量"""
        original_engine = session._engine
        original_session_maker = session._async_session_maker
        session._engine = None
        session._async_session_maker = None
        yield
        session._engine = original_engine
        session._async_session_maker = original_session_maker

    @pytest.mark.asyncio
    async def test_init_db_dameng(self, reset_db_session):
        """测试初始化达梦数据库"""
        config = DatabaseConfig(
            db_type="dameng",
            dameng=DamengConfig(
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("password"),
                database="TESTDB",
            ),
            pool_pre_ping=False,
            echo=False,
        )

        with (
            patch(
                "dm_mcp.infra.persistence.session._ensure_dameng_schema_if_needed"
            ) as mock_ensure,
            patch("dm_mcp.infra.persistence.session.create_async_engine") as mock_engine,
            patch("dm_mcp.infra.persistence.session.async_sessionmaker") as mock_session_maker,
        ):
            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            mock_session_maker.return_value = MagicMock()

            session.init_db(config)

            mock_ensure.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_db_mysql(self, reset_db_session):
        """测试初始化 MySQL 数据库"""
        config = DatabaseConfig(
            db_type="mysql",
            mysql=MySQLConfig(
                host="localhost",
                port=3306,
                user="root",
                password=SecretStr("password"),
                database="testdb",
                charset="utf8mb4",
            ),
            pool_pre_ping=True,
            echo=False,
        )

        with (
            patch(
                "dm_mcp.infra.persistence.session._ensure_mysql_database_if_needed"
            ) as mock_ensure,
            patch("dm_mcp.infra.persistence.session.create_async_engine") as mock_engine,
            patch("dm_mcp.infra.persistence.session.async_sessionmaker") as mock_session_maker,
        ):
            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            mock_session_maker.return_value = MagicMock()

            session.init_db(config)

            mock_ensure.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_db_postgresql(self, reset_db_session):
        """测试初始化 PostgreSQL 数据库"""
        config = DatabaseConfig(
            db_type="postgresql",
            postgresql=PostgreSQLConfig(
                host="localhost",
                port=5432,
                user="postgres",
                password=SecretStr("password"),
                database="testdb",
            ),
            pool_pre_ping=True,
            echo=False,
        )

        with (
            patch(
                "dm_mcp.infra.persistence.session._ensure_postgres_database_if_needed"
            ) as mock_ensure,
            patch("dm_mcp.infra.persistence.session.create_async_engine") as mock_engine,
            patch("dm_mcp.infra.persistence.session.async_sessionmaker") as mock_session_maker,
        ):
            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            mock_session_maker.return_value = MagicMock()

            session.init_db(config)

            mock_ensure.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_db_dameng_disables_pool_pre_ping(self, reset_db_session):
        """测试达梦数据库禁用 pool_pre_ping"""
        config = DatabaseConfig(
            db_type="dameng",
            dameng=DamengConfig(
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("password"),
                database="",
            ),
            pool_pre_ping=True,
            echo=False,
        )

        with (
            patch("dm_mcp.infra.persistence.session._ensure_dameng_schema_if_needed"),
            patch("dm_mcp.infra.persistence.session.create_async_engine") as mock_engine,
            patch("dm_mcp.infra.persistence.session.async_sessionmaker") as mock_session_maker,
        ):
            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            mock_session_maker.return_value = MagicMock()

            session.init_db(config)

            # 验证 pool_pre_ping 被设置为 False
            call_kwargs = mock_engine.call_args[1]
            assert call_kwargs.get("pool_pre_ping") is False

    @pytest.mark.asyncio
    async def test_init_db_sqlite_sets_check_same_thread(
        self, reset_db_session, tmp_path
    ):
        """测试 SQLite 配置 check_same_thread"""
        db_path = tmp_path / "test.db"
        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path)), echo=False
        )

        with (
            patch("dm_mcp.infra.persistence.session.create_async_engine") as mock_engine,
            patch("dm_mcp.infra.persistence.session.async_sessionmaker") as mock_session_maker,
        ):
            mock_engine_instance = MagicMock()
            mock_engine.return_value = mock_engine_instance
            mock_session_maker.return_value = MagicMock()

            session.init_db(config)

            # 验证 connect_args 设置
            call_kwargs = mock_engine.call_args[1]
            assert call_kwargs.get("connect_args", {}).get("check_same_thread") is False


class TestValidateSqlIdentifier:
    """测试 SQL 标识符安全校验"""

    @pytest.mark.parametrize(
        "name",
        ["SYSDBA", "test_schema", "TEST_DB", "_private", "db123"],
    )
    def test_valid_identifiers(self, name):
        """合法的标识符不应抛异常"""
        session._validate_sql_identifier(name)

    @pytest.mark.parametrize(
        "name",
        [
            "test; DROP TABLE users",
            'test"',
            "test'",
            "test--",
            "test/*",
            "123start",
            "test space",
            "",
        ],
    )
    def test_invalid_identifiers_raise(self, name):
        """包含危险字符的标识符应抛出 ValueError"""
        with pytest.raises(ValueError, match="不安全的 SQL"):
            session._validate_sql_identifier(name)

    def test_dameng_schema_rejects_dangerous_name(self):
        """达梦模式名称包含危险字符时应被拒绝"""
        cfg = DamengConfig(
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            database='"; DROP TABLE users; --',
        )

        with pytest.raises(ValueError, match="不安全的 SQL"):
            session._ensure_dameng_schema_if_needed(cfg)

    def test_mysql_database_rejects_dangerous_name(self):
        """MySQL 数据库名称包含危险字符时应被拒绝"""
        cfg = MySQLConfig(
            host="localhost",
            port=3306,
            user="root",
            password=SecretStr("password"),
            database="db; DROP",
            charset="utf8mb4",
        )

        with pytest.raises(ValueError, match="不安全的 SQL"):
            session._ensure_mysql_database_if_needed(cfg)

    def test_postgres_database_rejects_dangerous_name(self):
        """PostgreSQL 数据库名称包含危险字符时应被拒绝"""
        cfg = PostgreSQLConfig(
            host="localhost",
            port=5432,
            user="postgres",
            password=SecretStr("password"),
            database='db"; DROP',
        )

        with pytest.raises(ValueError, match="不安全的 SQL"):
            session._ensure_postgres_database_if_needed(cfg)
