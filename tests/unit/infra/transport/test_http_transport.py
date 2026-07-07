"""StreamableHttpTransport 流式 HTTP 传输测试"""

import os
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from dm_mcp.app.server import MCPServer
from dm_mcp.infra.transport.http_transport import StreamableHttpTransport
from dm_mcp.infra.config.server_config import ServerConfig
from dm_mcp.infra.config.logging_config import LoggingConfig


class TestStreamableHttpTransport:
    """StreamableHttpTransport 测试类"""

    @pytest.fixture
    def mock_settings(self, mock_settings_attrs):
        """创建 Mock 设置"""
        ms = mock_settings_attrs
        ms.server = ServerConfig(host="0.0.0.0", port=18081, workers=1)
        ms.logging = LoggingConfig()
        return ms

    @pytest.fixture
    def mock_factory(self):
        """创建 Mock 工厂函数"""
        factory = MagicMock()
        factory.__module__ = "test_module"
        factory.__name__ = "create_server"
        return factory

    def test_init_stores_factory_import_string(self, mock_settings, mock_factory):
        """测试初始化存储工厂导入字符串"""
        transport = StreamableHttpTransport(mock_settings, mock_factory)
        assert transport.factory_import_str is not None

    def test_init_stores_settings(self, mock_settings, mock_factory):
        """测试初始化存储设置"""
        transport = StreamableHttpTransport(mock_settings, mock_factory)
        assert transport.settings == mock_settings

    def test_resolve_import_string_from_module(self, mock_settings):
        """测试解析模块中的工厂函数"""

        def test_factory():
            pass

        test_factory.__module__ = "myapp.main"
        test_factory.__name__ = "create_server"

        transport = StreamableHttpTransport(mock_settings, test_factory)
        assert transport.factory_import_str == "myapp.main:create_server"

    def test_resolve_import_string_from_main(self, mock_settings):
        """测试解析 __main__ 中的工厂函数"""

        def test_factory():
            pass

        test_factory.__module__ = "__main__"
        test_factory.__name__ = "create_server"

        with patch("sys.argv", ["script.py"]):
            transport = StreamableHttpTransport(mock_settings, test_factory)
            assert "script" in transport.factory_import_str
            assert "create_server" in transport.factory_import_str


class TestStreamableHttpTransportStart:
    """StreamableHttpTransport start 方法测试"""

    @pytest.fixture
    def mock_settings_with_workers(self, mock_settings_attrs):
        """创建带 workers 配置的 Mock 设置"""
        ms = mock_settings_attrs
        ms.server = ServerConfig(host="0.0.0.0", port=18081, workers=2)
        ms.logging = LoggingConfig()
        ms.to_env = MagicMock(return_value={"test_key": "test_value"})
        return ms

    @pytest.fixture
    def mock_factory(self):
        """创建 Mock 工厂函数"""
        factory = MagicMock()
        factory.__module__ = "test_module"
        factory.__name__ = "create_server"
        return factory

    @patch("dm_mcp.infra.transport.http_transport.uvicorn")
    @patch("dm_mcp.infra.transport.http_transport.LoggingService")
    def test_start_syncs_settings_to_env(
        self,
        mock_logging_service,
        mock_uvicorn,
        mock_settings_with_workers,
        mock_factory,
    ):
        """测试 start 方法同步设置到环境变量"""
        mock_logging_service_instance = MagicMock()
        mock_logging_service_instance.setup_logging = MagicMock()
        mock_logging_service_instance.get_uvicorn_config = MagicMock(return_value={})
        mock_logging_service.return_value = mock_logging_service_instance

        with patch.dict("os.environ", {}, clear=False):
            transport = StreamableHttpTransport(
                mock_settings_with_workers, mock_factory
            )
            transport.start()

            mock_settings_with_workers.to_env.assert_called()

    @patch("dm_mcp.infra.transport.http_transport.uvicorn")
    @patch("dm_mcp.infra.transport.http_transport.LoggingService")
    def test_start_sets_factory_env_var(
        self,
        mock_logging_service,
        mock_uvicorn,
        mock_settings_with_workers,
        mock_factory,
    ):
        """测试 start 方法设置工厂函数环境变量"""
        mock_logging_service_instance = MagicMock()
        mock_logging_service_instance.setup_logging = MagicMock()
        mock_logging_service_instance.get_uvicorn_config = MagicMock(return_value={})
        mock_logging_service.return_value = mock_logging_service_instance

        with patch.dict("os.environ", {}, clear=False):
            transport = StreamableHttpTransport(
                mock_settings_with_workers, mock_factory
            )
            transport.start()

            assert "DM_MCP_FACTORY_REF" in os.environ

    @patch("dm_mcp.infra.transport.http_transport.uvicorn")
    @patch("dm_mcp.infra.transport.http_transport.LoggingService")
    def test_start_calculates_workers_from_cpu_count(
        self,
        mock_logging_service,
        mock_uvicorn,
        mock_settings_with_workers,
        mock_factory,
    ):
        """测试 workers 为 0 时使用 CPU 核心数"""
        mock_settings_with_workers.server = ServerConfig(
            host="0.0.0.0", port=18081, workers=0
        )
        mock_settings_with_workers.to_env = MagicMock(return_value={})

        mock_logging_service_instance = MagicMock()
        mock_logging_service_instance.setup_logging = MagicMock()
        mock_logging_service_instance.get_uvicorn_config = MagicMock(return_value={})
        mock_logging_service.return_value = mock_logging_service_instance

        with patch("multiprocessing.cpu_count", return_value=4):
            with patch.dict("os.environ", {}, clear=False):
                transport = StreamableHttpTransport(
                    mock_settings_with_workers, mock_factory
                )
                transport.start()

                mock_uvicorn.run.assert_called()


class TestStreamableHttpTransportCreateApp:
    """StreamableHttpTransport.create_app 方法测试"""

    def test_create_app_missing_env_var(self):
        """测试缺失环境变量时创建应用"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError):
                StreamableHttpTransport.create_app()

    def test_create_app_invalid_factory_ref(self):
        """测试无效的工厂引用时创建应用"""
        env = {"DM_MCP_FACTORY_REF": "not-a-valid-ref"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(RuntimeError):
                StreamableHttpTransport.create_app()

    @patch("dm_mcp.infra.transport.http_transport.importlib")
    def test_create_app_wrong_return_type(self, mock_importlib):
        """测试工厂返回错误类型时创建应用"""
        mock_module = MagicMock()
        mock_module.create_server = MagicMock(return_value=object())
        mock_importlib.import_module.return_value = mock_module

        env = {"DM_MCP_FACTORY_REF": "fake_module:create_server", "SERVER_WORKERS": "1"}
        with patch.dict("os.environ", env, clear=True):
            with pytest.raises(TypeError):
                StreamableHttpTransport.create_app()

    @patch("dm_mcp.infra.transport.http_transport.importlib")
    def test_create_app_success(self, mock_importlib):
        """测试成功创建应用"""
        mock_server = MagicMock(spec=MCPServer)
        mock_server.create_asgi_app = MagicMock(return_value=MagicMock())

        mock_module = MagicMock()
        mock_module.create_server = MagicMock(return_value=mock_server)
        mock_importlib.import_module.return_value = mock_module

        env = {"DM_MCP_FACTORY_REF": "fake_module:create_server", "SERVER_WORKERS": "2"}
        with patch.dict("os.environ", env, clear=True):
            app = StreamableHttpTransport.create_app()

        assert app is not None
        mock_server.create_asgi_app.assert_called_once_with(stateless=True)


class TestStreamableHttpTransportSyncSettings:
    """_sync_settings_to_env 方法测试"""

    @pytest.fixture
    def mock_settings(self, mock_settings_attrs):
        """创建 Mock 设置"""
        ms = mock_settings_attrs
        ms.server = ServerConfig(host="0.0.0.0", port=18081, workers=1)
        ms.logging = LoggingConfig()
        ms.to_env = MagicMock(
            return_value={
                "SERVER__HOST": "0.0.0.0",
                "SERVER__PORT": "18081",
                "LOGGING__LEVEL": "INFO",
                "LOGGING__LOG_DIR": "/tmp/logs",
            }
        )
        return ms

    @pytest.fixture
    def mock_factory(self):
        factory = MagicMock()
        factory.__module__ = "test_module"
        factory.__name__ = "create_server"
        return factory

    def test_sync_settings_excludes_logging(self, mock_settings, mock_factory):
        """测试同步设置时排除 logging 前缀"""
        with patch.dict("os.environ", {}, clear=True):
            transport = StreamableHttpTransport(mock_settings, mock_factory)
            transport._sync_settings_to_env()

            assert os.environ.get("SERVER__HOST") == "0.0.0.0"
            assert "LOGGING__LEVEL" not in os.environ
            assert "LOGGING__LOG_DIR" not in os.environ

    def test_sync_settings_converts_values_to_string(self, mock_settings, mock_factory):
        """测试同步设置时转换值为字符串"""
        mock_settings.to_env = MagicMock(
            return_value={"SERVER__PORT": 18081, "SERVER__DEBUG": False}
        )

        with patch.dict("os.environ", {}, clear=True):
            transport = StreamableHttpTransport(mock_settings, mock_factory)
            transport._sync_settings_to_env()

            assert os.environ["SERVER__PORT"] == "18081"
            assert os.environ["SERVER__DEBUG"] == "False"
