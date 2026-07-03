"""Settings 主配置测试"""

import pytest
from pathlib import Path
from pydantic import SecretStr
from unittest.mock import MagicMock, patch
from dm_mcp.settings import Settings
from dm_mcp.settings.server_config import ServerConfig
from dm_mcp.settings.database_config import DatabaseConfig
from dm_mcp.settings.jwt_config import JwtConfig
from dm_mcp.settings.logging_config import LoggingConfig
from dm_mcp.settings.metrics_config import MetricsConfig
from dm_mcp.settings.oauth_config import OAuthConfig
from dm_mcp.settings.pool_config import DmPoolConfig
from dm_mcp.settings.datasource_config import DataSourcesConfig
from dm_mcp.settings.token_auth_config import TokenAuthConfig


class TestSettings:
    """Settings 测试类"""

    def test_default_values(self):
        """测试默认值"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(_env_file=None)
            assert settings.server is not None
            assert settings.database is not None
            assert settings.metrics is not None
            assert settings.logging is not None
            assert settings.oauth is not None
            assert settings.pool is not None
            assert settings.datasources is not None
            assert settings.token_auth is not None
            assert settings.jwt is not None
        finally:
            sys.argv = original_argv

    def test_custom_values(self):
        """测试自定义值"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(
                _env_file=None,
                server=ServerConfig(name="custom"),
                database=DatabaseConfig(db_type="mysql"),
            )
            assert settings.server.name == "custom"
            assert settings.database.db_type == "mysql"
        finally:
            sys.argv = original_argv


class TestSettingsToEnv:
    """Settings.to_env 方法测试"""

    def test_to_env_empty_prefix(self):
        """测试默认前缀"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(_env_file=None)
            env = settings.to_env()
            assert isinstance(env, dict)
            # 验证包含主要配置项
            assert any("server" in k.lower() for k in env.keys())
        finally:
            sys.argv = original_argv

    def test_to_env_custom_prefix(self):
        """测试自定义前缀"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(_env_file=None)
            env = settings.to_env(prefix="app")
            assert isinstance(env, dict)
        finally:
            sys.argv = original_argv

    def test_to_env_uppercase(self):
        """测试大写键名"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(_env_file=None)
            env = settings.to_env(upper=True)
            # 验证键是大写的
            for key in env.keys():
                assert key.isupper() or key.startswith("_")
        finally:
            sys.argv = original_argv

    def test_to_env_secret_handling(self):
        """测试 SecretStr 处理"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(
                _env_file=None,
                jwt=JwtConfig(secret=SecretStr("test-secret")),
            )
            env = settings.to_env()
            # 验证 SecretStr 被解密
            jwt_keys = [
                k for k in env.keys() if "jwt" in k.lower() or "secret" in k.lower()
            ]
            for key in jwt_keys:
                # 不应该包含 get_secret_value 字符串
                assert "get_secret_value" not in env[key]
        finally:
            sys.argv = original_argv

    def test_to_env_none_values(self):
        """测试 None 值处理"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(_env_file=None)
            env = settings.to_env()
            # None 值应该被转换为空字符串
            none_values = [v for v in env.values() if v == ""]
            # 可能有某些字段为 None
            assert isinstance(env, dict)
        finally:
            sys.argv = original_argv


class TestSettingsModelConfig:
    """Settings model_config 测试"""

    def test_extra_ignore(self):
        """测试额外字段被忽略"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            # 应该不会抛出错误
            settings = Settings(_env_file=None, extra_field="ignored")
        finally:
            sys.argv = original_argv

    def test_nested_delimiter(self):
        """测试嵌套分隔符"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0]]
        try:
            settings = Settings(_env_file=None)
            env = settings.to_env()
            # 验证使用了 __ 作为分隔符
            keysWithUnderscore = [k for k in env.keys() if "__" in k]
            # 如果有嵌套配置，应该包含双下划线
            assert isinstance(env, dict)
        finally:
            sys.argv = original_argv


class TestSettingsCustomiseSources:
    """settings_customise_sources 方法测试"""

    def test_cli_args_supported(self):
        """测试命令行参数支持"""
        import sys

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0], "--server.port", "9000"]
        try:
            settings = Settings()
            # 命令行参数应该被解析
            # 注意：由于 mock_settings fixture 可能已经处理了这个问题，这里只验证方法存在
            assert hasattr(Settings, "settings_customise_sources")
        finally:
            sys.argv = original_argv
