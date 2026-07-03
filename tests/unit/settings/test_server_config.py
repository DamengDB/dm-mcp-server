"""ServerConfig 服务配置测试"""

import pytest
from pydantic import SecretStr
from dm_mcp.settings.server_config import ServerConfig


class TestServerConfig:
    """ServerConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = ServerConfig()
        assert config.name == "dameng-mcp-server"
        assert config.version == "0.1.0"
        assert config.host == "localhost"
        assert config.port == 18081
        assert config.transport == "stdio"
        assert config.workers == 1
        assert config.debug is True
        assert config.audit_enabled is True
        assert isinstance(config.session_secret, SecretStr)

    def test_custom_values(self):
        """测试自定义值"""
        config = ServerConfig(
            name="test-server",
            version="1.0.0",
            host="0.0.0.0",
            port=8080,
            transport="http",
            workers=4,
            debug=False,
            audit_enabled=False,
        )
        assert config.name == "test-server"
        assert config.version == "1.0.0"
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.transport == "http"
        assert config.workers == 4
        assert config.debug is False
        assert config.audit_enabled is False

    def test_port_range_validation(self):
        """测试端口范围验证"""
        # 有效端口
        config = ServerConfig(port=1)
        assert config.port == 1

        config = ServerConfig(port=65535)
        assert config.port == 65535

        # 无效端口应该被 Pydantic 验证拒绝
        with pytest.raises(Exception):
            ServerConfig(port=0)

        with pytest.raises(Exception):
            ServerConfig(port=65536)

    def test_transport_literal_values(self):
        """测试传输类型字面值"""
        config = ServerConfig(transport="stdio")
        assert config.transport == "stdio"

        config = ServerConfig(transport="http")
        assert config.transport == "http"

        with pytest.raises(Exception):
            ServerConfig(transport="invalid")


class TestServerConfigFields:
    """ServerConfig 字段测试"""

    def test_static_path_default(self):
        """测试静态路径默认值"""
        config = ServerConfig()
        assert config.static_path is not None
        assert "resources" in config.static_path

    def test_base_url_default(self):
        """测试基础 URL 默认值"""
        config = ServerConfig()
        assert config.base_url == "/dm-mcp"

    def test_frontend_url_optional(self):
        """测试前端 URL 可选"""
        config = ServerConfig()
        assert config.frontend_url == ""

        config = ServerConfig(frontend_url="http://localhost:3000")
        assert config.frontend_url == "http://localhost:3000"
