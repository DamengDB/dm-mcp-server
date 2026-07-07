"""元数据库结构兼容性校验测试"""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, text

from dm_mcp.infra.config.database_config import DatabaseConfig, SQLiteConfig
from dm_mcp.infra.config.server_config import ServerConfig
from dm_mcp.infra.persistence.models import Base
from dm_mcp.infra.persistence import session
from dm_mcp.infra.persistence.schema_check import (
    SchemaIncompatibleError,
    collect_schema_issues,
    verify_schema_compatible_sync,
)


class TestCollectSchemaIssues:
    """collect_schema_issues 单元测试"""

    def test_detects_missing_table(self):
        inspector = MagicMock()
        inspector.has_table.return_value = False

        issues = collect_schema_issues(inspector)

        assert any("缺少表" in issue for issue in issues)
        assert inspector.has_table.called

    def test_detects_missing_column(self):
        inspector = MagicMock()

        def has_table(name: str) -> bool:
            return name == "datasources"

        inspector.has_table.side_effect = has_table
        inspector.get_columns.return_value = [
            {"name": "id"},
            {"name": "name"},
        ]

        issues = collect_schema_issues(inspector)

        assert any(
            "datasources" in issue and "owner_id" in issue for issue in issues
        )

    def test_passes_when_all_model_columns_present(self):
        inspector = MagicMock()
        table = Base.metadata.tables["datasources"]

        def has_table(name: str) -> bool:
            return name == "datasources"

        inspector.has_table.side_effect = has_table
        inspector.get_columns.return_value = [{"name": col.name} for col in table.columns]

        issues = collect_schema_issues(inspector)

        assert not any("datasources" in issue for issue in issues)


class TestSchemaIncompatibleError:
    """SchemaIncompatibleError 消息格式"""

    def test_message_contains_version_and_schema(self):
        err = SchemaIncompatibleError(
            ["表 datasources 缺少列: owner_id"],
            schema_hint="/tmp/meta.db",
            version="0.2.0",
        )
        text = str(err)
        assert "v0.2.0" in text
        assert "owner_id" in text
        assert "/tmp/meta.db" in text
        assert "不会自动升级" in text
        assert err.code == "SCHEMA_INCOMPATIBLE"

    def test_default_version_from_server_config(self):
        err = SchemaIncompatibleError(
            ["缺少表: datasources"],
            schema_hint="DM_MCP_META",
        )
        assert f"v{ServerConfig.version}" in str(err)


class TestVerifySchemaCompatibleSync:
    """同步校验入口"""

    def test_raises_on_incompatible_schema(self, tmp_path):
        db_path = tmp_path / "old_meta.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE datasources (
                        id CHAR(36) PRIMARY KEY NOT NULL,
                        name VARCHAR(128) NOT NULL UNIQUE,
                        enabled BOOLEAN NOT NULL DEFAULT 1,
                        deploy_type VARCHAR(16) NOT NULL DEFAULT 'dmstandalone',
                        read_only BOOLEAN NOT NULL DEFAULT 0,
                        dsn TEXT NOT NULL DEFAULT '',
                        host VARCHAR(255) NOT NULL DEFAULT 'localhost',
                        port INTEGER NOT NULL DEFAULT 5236,
                        user VARCHAR(128) NOT NULL DEFAULT 'SYSDBA',
                        password TEXT NOT NULL DEFAULT '',
                        dpc_cluster TEXT,
                        minsize INTEGER NOT NULL DEFAULT 1,
                        maxsize INTEGER NOT NULL DEFAULT 10,
                        timeout REAL NOT NULL DEFAULT 30.0,
                        weight INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )

        with engine.connect() as conn:
            with pytest.raises(SchemaIncompatibleError) as exc_info:
                verify_schema_compatible_sync(conn, schema_hint=str(db_path))

        assert "owner_id" in str(exc_info.value)
        engine.dispose()


class TestBootstrapSchemaIntegration:
    """bootstrap_schema 集成测试（SQLite）"""

    @pytest.fixture
    def reset_db_session(self):
        original_engine = session._engine
        original_session_maker = session._async_session_maker
        session._engine = None
        session._async_session_maker = None
        yield
        session._engine = original_engine
        session._async_session_maker = original_session_maker

    @pytest.mark.asyncio
    async def test_fresh_schema_passes(self, tmp_path, reset_db_session):
        db_path = tmp_path / "fresh.db"
        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path))
        )

        session.init_db(config)
        await session.bootstrap_schema(config)

    @pytest.mark.asyncio
    async def test_v0_1_0_datasources_rejected(self, tmp_path, reset_db_session):
        """v0.1.0 元库（无 owner_id）在 v0.2.0 启动时应失败"""
        db_path = tmp_path / "legacy.db"
        engine = create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE datasources (
                        id CHAR(36) PRIMARY KEY NOT NULL,
                        name VARCHAR(128) NOT NULL UNIQUE,
                        enabled BOOLEAN NOT NULL DEFAULT 1,
                        deploy_type VARCHAR(16) NOT NULL DEFAULT 'dmstandalone',
                        read_only BOOLEAN NOT NULL DEFAULT 0,
                        dsn TEXT NOT NULL DEFAULT '',
                        host VARCHAR(255) NOT NULL DEFAULT 'localhost',
                        port INTEGER NOT NULL DEFAULT 5236,
                        user VARCHAR(128) NOT NULL DEFAULT 'SYSDBA',
                        password TEXT NOT NULL DEFAULT '',
                        dpc_cluster TEXT,
                        minsize INTEGER NOT NULL DEFAULT 1,
                        maxsize INTEGER NOT NULL DEFAULT 10,
                        timeout REAL NOT NULL DEFAULT 30.0,
                        weight INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
            )
        engine.dispose()

        config = DatabaseConfig(
            db_type="sqlite", sqlite=SQLiteConfig(db_path=str(db_path))
        )
        session.init_db(config)

        with pytest.raises(SchemaIncompatibleError) as exc_info:
            await session.bootstrap_schema(config)

        err_text = str(exc_info.value)
        assert "owner_id" in err_text
        assert "datasources" in err_text
        assert "不会自动升级" in err_text

    @pytest.mark.asyncio
    async def test_ensure_schema_compatible_engine_not_initialized(self):
        session._engine = None
        with pytest.raises(RuntimeError, match="数据库引擎未初始化"):
            await session.ensure_schema_compatible(schema_hint="test")
