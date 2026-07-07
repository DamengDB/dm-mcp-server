"""DatabaseConfig 数据库配置测试"""

import pytest
from pydantic import SecretStr
from dm_mcp.infra.config.database_config import (
    DatabaseConfig,
    SQLiteConfig,
    DamengConfig,
    MySQLConfig,
    PostgreSQLConfig,
)


class TestSQLiteConfig:
    """SQLiteConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = SQLiteConfig()
        assert config.db_path == "server.db"

    def test_custom_values(self):
        """测试自定义值"""
        config = SQLiteConfig(db_path="custom.db")
        assert config.db_path == "custom.db"


class TestDamengConfig:
    """DamengConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = DamengConfig()
        assert config.host == "localhost"
        assert config.port == 5236
        assert config.user == "SYSDBA"
        assert isinstance(config.password, SecretStr)
        assert config.password.get_secret_value() == "SYSDBA"
        assert config.database == ""

    def test_custom_values(self):
        """测试自定义值"""
        config = DamengConfig(
            host="192.168.1.100",
            port=5237,
            user="TESTUSER",
            password=SecretStr("testpass"),
            database="TESTDB",
        )
        assert config.host == "192.168.1.100"
        assert config.port == 5237
        assert config.user == "TESTUSER"
        assert config.password.get_secret_value() == "testpass"
        assert config.database == "TESTDB"

    def test_port_range(self):
        """测试端口范围"""
        config = DamengConfig(port=1)
        assert config.port == 1

        config = DamengConfig(port=65535)
        assert config.port == 65535

        with pytest.raises(Exception):
            DamengConfig(port=0)


class TestMySQLConfig:
    """MySQLConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = MySQLConfig()
        assert config.host == "localhost"
        assert config.port == 3306
        assert config.user == "root"
        assert config.password.get_secret_value() == ""
        assert config.database == "DMMCP"
        assert config.charset == "utf8mb4"

    def test_custom_values(self):
        """测试自定义值"""
        config = MySQLConfig(
            host="mysql.example.com",
            port=3307,
            user="admin",
            password=SecretStr("secret"),
            database="mydb",
            charset="utf8",
        )
        assert config.host == "mysql.example.com"
        assert config.port == 3307
        assert config.user == "admin"
        assert config.password.get_secret_value() == "secret"
        assert config.database == "mydb"
        assert config.charset == "utf8"


class TestPostgreSQLConfig:
    """PostgreSQLConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = PostgreSQLConfig()
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.user == "postgres"
        assert config.password.get_secret_value() == ""
        assert config.database == "DMMCP"

    def test_custom_values(self):
        """测试自定义值"""
        config = PostgreSQLConfig(
            host="pg.example.com",
            port=5433,
            user="admin",
            password=SecretStr("pgpass"),
            database="pgdb",
        )
        assert config.host == "pg.example.com"
        assert config.port == 5433
        assert config.user == "admin"
        assert config.password.get_secret_value() == "pgpass"
        assert config.database == "pgdb"


class TestDatabaseConfig:
    """DatabaseConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = DatabaseConfig()
        assert config.db_type == "sqlite"
        assert config.echo is False
        assert config.pool_pre_ping is True
        assert config.sqlite is not None
        assert config.dameng is not None
        assert config.mysql is not None
        assert config.postgresql is not None

    def test_get_active_config_sqlite(self):
        """测试获取 SQLite 配置"""
        config = DatabaseConfig(db_type="sqlite")
        active = config.get_active_config()
        assert isinstance(active, SQLiteConfig)

    def test_get_active_config_dameng(self):
        """测试获取达梦数据库配置"""
        config = DatabaseConfig(db_type="dameng")
        active = config.get_active_config()
        assert isinstance(active, DamengConfig)

    def test_get_active_config_mysql(self):
        """测试获取 MySQL 配置"""
        config = DatabaseConfig(db_type="mysql")
        active = config.get_active_config()
        assert isinstance(active, MySQLConfig)

    def test_get_active_config_postgresql(self):
        """测试获取 PostgreSQL 配置"""
        config = DatabaseConfig(db_type="postgresql")
        active = config.get_active_config()
        assert isinstance(active, PostgreSQLConfig)

    def test_db_type_validation(self):
        """测试数据库类型验证"""
        config = DatabaseConfig(db_type="sqlite")
        assert config.db_type == "sqlite"

        with pytest.raises(Exception):
            DatabaseConfig(db_type="invalid")

    def test_all_db_types_have_factories(self):
        """测试所有数据库类型都有默认值工厂"""
        config = DatabaseConfig()
        # 检查各配置被正确初始化
        assert isinstance(config.sqlite, SQLiteConfig)
        assert isinstance(config.dameng, DamengConfig)
        assert isinstance(config.mysql, MySQLConfig)
        assert isinstance(config.postgresql, PostgreSQLConfig)
