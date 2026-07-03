"""DataSourceConfig 数据源配置测试"""

import uuid
import pytest
from pydantic import SecretStr
from dm_mcp.settings.datasource_config import (
    DataSourceConfig,
    DataSourcesConfig,
)


class TestDataSourceConfig:
    """DataSourceConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = DataSourceConfig()
        assert config.name == "primary"
        assert config.enabled is True
        assert config.deploy_type == "dmstandonle"
        assert config.read_only is False
        assert config.host == "localhost"
        assert config.port == 5236
        assert config.user == "SYSDBA"

    def test_custom_values(self):
        """测试自定义值"""
        config = DataSourceConfig(
            name="test_ds",
            enabled=False,
            deploy_type="dmdsc",
            host="192.168.1.100",
            port=5237,
            user="testuser",
            password=SecretStr("password"),
            minsize=2,
            maxsize=20,
            read_only=True,
        )
        assert config.name == "test_ds"
        assert config.enabled is False
        assert config.deploy_type == "dmdsc"
        assert config.host == "192.168.1.100"
        assert config.port == 5237
        assert config.user == "testuser"
        assert config.password.get_secret_value() == "password"
        assert config.minsize == 2
        assert config.maxsize == 20
        assert config.read_only is True

    def test_uuid_generation(self):
        """测试 UUID 自动生成"""
        config = DataSourceConfig()
        assert isinstance(config.id, uuid.UUID)

    def test_deploy_type_options(self):
        """测试部署类型选项"""
        for deploy_type in ["dmstandonle", "dmwatcher", "dmdsc", "dmdpc"]:
            config = DataSourceConfig(deploy_type=deploy_type)
            assert config.deploy_type == deploy_type


class TestDataSourcesConfig:
    """DataSourcesConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = DataSourcesConfig()
        assert isinstance(config.data_sources, list)
        assert len(config.data_sources) == 0

    def test_with_sources(self):
        """测试添加数据源"""
        config = DataSourcesConfig(
            data_sources=[
                DataSourceConfig(name="primary"),
                DataSourceConfig(name="secondary"),
            ]
        )
        assert len(config.data_sources) == 2

    def test_get_source_by_name(self):
        """测试按名称获取数据源"""
        config = DataSourcesConfig(
            data_sources=[
                DataSourceConfig(name="primary"),
                DataSourceConfig(name="secondary"),
            ]
        )
        primary = next((s for s in config.data_sources if s.name == "primary"), None)
        assert primary is not None
        assert primary.name == "primary"

    def test_empty_config_valid(self):
        """测试空配置有效"""
        config = DataSourcesConfig()
        assert config is not None
