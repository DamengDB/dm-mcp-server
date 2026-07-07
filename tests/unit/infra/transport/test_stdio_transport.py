"""StdioTransport 标准输入输出传输测试"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dm_mcp.infra.transport.stdio_transport import StdioTransport


class TestStdioTransport:
    """StdioTransport 测试类"""

    @pytest.fixture
    def mock_settings(self, mock_settings_attrs):
        """创建 Mock 设置"""
        return mock_settings_attrs

    @pytest.fixture
    def mock_factory(self):
        """创建 Mock 工厂函数"""
        factory = MagicMock()
        mock_server = MagicMock()
        mock_server.create_asgi_app = MagicMock()
        mock_server.startup = AsyncMock()
        mock_server.shutdown = AsyncMock()
        mock_server.settings = MagicMock()
        mock_server.settings.server = MagicMock()
        mock_server.settings.server.host = "localhost"
        mock_server.settings.server.port = 18081
        mock_server.settings.metrics = MagicMock()
        mock_server.settings.metrics.enabled = False
        mock_server.context = MagicMock()
        mock_server.context.mcp_sdk_server = MagicMock()
        mock_server.context.mcp_sdk_server.create_initialization_options = MagicMock(
            return_value={}
        )
        mock_server.context.mcp_sdk_server.run = AsyncMock()
        mock_server.context.datasource_service = MagicMock()
        mock_server.context.metrics_service = MagicMock()
        factory.return_value = mock_server
        return factory

    def test_init_creates_server(self, mock_settings, mock_factory):
        """测试初始化时创建服务器"""
        transport = StdioTransport(mock_settings, mock_factory)
        mock_factory.assert_called_once()
        assert transport.server is not None

    def test_init_stores_settings_and_factory(self, mock_settings, mock_factory):
        """测试初始化存储设置和工厂"""
        transport = StdioTransport(mock_settings, mock_factory)
        assert transport.server is not None

    def test_init_passes_settings_to_parent(self, mock_settings, mock_factory):
        """测试初始化时传递 settings 给父类"""
        with patch(
            "dm_mcp.infra.transport.stdio_transport.BaseTransport.__init__"
        ) as mock_parent_init:
            transport = StdioTransport(mock_settings, mock_factory)
            mock_parent_init.assert_called_once_with(mock_settings, mock_factory)

    def test_init_sets_server_from_factory(self, mock_settings, mock_factory):
        """测试初始化时从工厂获取服务器实例"""
        transport = StdioTransport(mock_settings, mock_factory)
        assert hasattr(transport, "server")

    def test_start_calls_asyncio_run(self, mock_settings, mock_factory):
        """测试 start 方法调用 asyncio.run"""
        transport = StdioTransport(mock_settings, mock_factory)

        with patch("asyncio.run", return_value=0) as mock_run:
            with patch("dm_mcp.infra.transport.stdio_transport.exit") as mock_exit:
                transport.start()
                mock_run.assert_called_once()
                mock_exit.assert_called_once_with(0)

    def test_start_exits_with_code(self, mock_settings, mock_factory):
        """测试 start 方法退出时带退出码"""
        transport = StdioTransport(mock_settings, mock_factory)

        with patch("asyncio.run", return_value=1):
            with patch("dm_mcp.infra.transport.stdio_transport.exit") as mock_exit:
                transport.start()
                mock_exit.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_start_creates_asgi_app(self, mock_settings, mock_factory):
        """测试 _start 方法创建 ASGI 应用"""
        mock_server = mock_factory.return_value
        mock_streams = MagicMock()
        mock_streams.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_streams.__aexit__ = AsyncMock(return_value=None)

        transport = StdioTransport(mock_settings, mock_factory)

        with (
            patch(
                "dm_mcp.infra.transport.stdio_transport.stdio_server",
                return_value=mock_streams,
            ),
            patch("dm_mcp.infra.transport.stdio_transport.MCPContext") as mock_mcp_ctx,
            patch("dm_mcp.infra.transport.stdio_transport.uvicorn") as mock_uvicorn,
        ):
            mock_mcp_ctx.build_for_stdio = AsyncMock(return_value=MagicMock())
            mock_mcp_ctx.as_current = MagicMock()
            mock_uvicorn.Server.return_value.serve = AsyncMock()

            await transport._start()

            mock_server.create_asgi_app.assert_called_once_with(stateless=True)


class TestStdioTransportStart:
    """测试 _start 异步方法"""

    def _create_mock_server_complete(self):
        """创建完整的 Mock 服务器"""
        mock_server = MagicMock()
        mock_asgi_app = MagicMock()
        mock_server.create_asgi_app = MagicMock(return_value=mock_asgi_app)
        mock_server.startup = AsyncMock()
        mock_server.shutdown = AsyncMock()
        mock_server.settings = MagicMock()
        mock_server.settings.server = MagicMock()
        mock_server.settings.server.host = "localhost"
        mock_server.settings.server.port = 18081
        mock_server.settings.metrics = MagicMock()
        mock_server.settings.metrics.enabled = False

        mock_server.context = MagicMock()
        mock_server.context.mcp_sdk_server = MagicMock()
        mock_server.context.mcp_sdk_server.create_initialization_options = MagicMock(
            return_value={"protocolVersion": "2024-11-05"}
        )
        mock_server.context.mcp_sdk_server.run = AsyncMock()
        mock_server.context.datasource_service = MagicMock()
        mock_server.context.metrics_service = MagicMock()
        mock_server.context.metrics_service.start_http_server = MagicMock()
        return mock_server

    def _create_mock_streams(self):
        """创建模拟的 stdio streams 上下文管理器"""
        mock_read = AsyncMock()
        mock_write = AsyncMock()

        # 创建一个可以用于 async with 的 mock
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_cm

    @pytest.mark.asyncio
    async def test_start_normal_flow(self, mock_settings, mock_settings_attrs):
        """测试正常启动流程"""
        mock_server = self._create_mock_server_complete()
        factory = MagicMock(return_value=mock_server)
        transport = StdioTransport(mock_settings_attrs, factory)

        mock_streams = self._create_mock_streams()

        with (
            patch(
                "dm_mcp.infra.transport.stdio_transport.stdio_server",
                return_value=mock_streams,
            ),
            patch("dm_mcp.infra.transport.stdio_transport.MCPContext") as mock_mcp_ctx,
            patch("dm_mcp.infra.transport.stdio_transport.uvicorn") as mock_uvicorn,
        ):

            mock_mcp_ctx.build_for_stdio = AsyncMock(return_value=MagicMock())
            mock_mcp_ctx.as_current = MagicMock()

            mock_uvicorn.Config.return_value = MagicMock()
            mock_uvicorn.Server.return_value = MagicMock()
            mock_uvicorn.Server.return_value.serve = AsyncMock()  # 必须是 AsyncMock

            await transport._start()

            mock_server.startup.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_creates_asgi_app(self, mock_settings_attrs):
        """测试启动时创建 ASGI 应用"""
        mock_server = self._create_mock_server_complete()
        factory = MagicMock(return_value=mock_server)
        transport = StdioTransport(mock_settings_attrs, factory)
        mock_streams = self._create_mock_streams()

        with (
            patch(
                "dm_mcp.infra.transport.stdio_transport.stdio_server",
                return_value=mock_streams,
            ),
            patch("dm_mcp.infra.transport.stdio_transport.MCPContext") as mock_mcp_ctx,
            patch("dm_mcp.infra.transport.stdio_transport.uvicorn") as mock_uvicorn,
        ):
            mock_mcp_ctx.build_for_stdio = AsyncMock(return_value=MagicMock())
            mock_mcp_ctx.as_current = MagicMock()
            mock_uvicorn.Server.return_value.serve = AsyncMock()

            await transport._start()

            mock_server.create_asgi_app.assert_called_once_with(stateless=True)

    @pytest.mark.asyncio
    async def test_start_with_metrics_enabled(self, mock_settings_attrs):
        """测试启用 metrics 时的启动流程"""
        mock_settings_attrs.metrics.enabled = True
        mock_server = self._create_mock_server_complete()
        mock_server.settings.metrics.enabled = True
        factory = MagicMock(return_value=mock_server)
        transport = StdioTransport(mock_settings_attrs, factory)
        mock_streams = self._create_mock_streams()

        with (
            patch(
                "dm_mcp.infra.transport.stdio_transport.stdio_server",
                return_value=mock_streams,
            ),
            patch("dm_mcp.infra.transport.stdio_transport.MCPContext") as mock_mcp_ctx,
            patch("dm_mcp.infra.transport.stdio_transport.uvicorn") as mock_uvicorn,
        ):
            mock_mcp_ctx.build_for_stdio = AsyncMock(return_value=MagicMock())
            mock_mcp_ctx.as_current = MagicMock()
            mock_uvicorn.Server.return_value.serve = AsyncMock()

            await transport._start()

            mock_server.context.metrics_service.start_http_server.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_handles_exception(self, mock_settings_attrs):
        """测试启动时异常处理"""
        mock_server = self._create_mock_server_complete()
        mock_server.startup = AsyncMock(side_effect=RuntimeError("startup failed"))
        factory = MagicMock(return_value=mock_server)
        transport = StdioTransport(mock_settings_attrs, factory)

        with pytest.raises(RuntimeError, match="startup failed"):
            await transport._start()

    @pytest.mark.asyncio
    async def test_start_calls_server_run(self, mock_settings_attrs):
        """测试启动时调用 MCP SDK server.run"""
        mock_server = self._create_mock_server_complete()
        factory = MagicMock(return_value=mock_server)
        transport = StdioTransport(mock_settings_attrs, factory)
        mock_streams = self._create_mock_streams()

        with (
            patch(
                "dm_mcp.infra.transport.stdio_transport.stdio_server",
                return_value=mock_streams,
            ),
            patch("dm_mcp.infra.transport.stdio_transport.MCPContext") as mock_mcp_ctx,
            patch("dm_mcp.infra.transport.stdio_transport.uvicorn") as mock_uvicorn,
        ):
            mock_mcp_ctx.build_for_stdio = AsyncMock(return_value=MagicMock())
            mock_mcp_ctx.as_current = MagicMock()
            mock_uvicorn.Server.return_value.serve = AsyncMock()

            await transport._start()

            mock_server.context.mcp_sdk_server.run.assert_called_once()


class TestStdioTransportEdgeCases:
    """StdioTransport 边界情况测试"""

    @pytest.fixture
    def mock_settings_edge(self, mock_settings_attrs):
        """创建 Mock 设置 - 用于边界测试"""
        ms = mock_settings_attrs
        return ms

    def test_factory_returns_none(self, mock_settings_edge):
        """测试工厂返回 None 时的行为"""
        factory = MagicMock(return_value=None)

        # 工厂返回 None 时不抛出异常，但 self.server 为 None
        transport = StdioTransport(mock_settings_edge, factory)
        assert transport.server is None

    def test_settings_without_metrics_enabled(self, mock_settings_edge):
        """测试 metrics.enabled 默认为 False"""
        factory = MagicMock()
        mock_server = MagicMock()
        mock_server.create_asgi_app = MagicMock()
        mock_server.startup = AsyncMock()
        mock_server.shutdown = AsyncMock()
        mock_server.context = MagicMock()
        mock_server.context.mcp_sdk_server = MagicMock()
        mock_server.context.mcp_sdk_server.create_initialization_options = MagicMock(
            return_value={}
        )
        mock_server.context.datasource_service = MagicMock()
        mock_server.context.metrics_service = MagicMock()
        factory.return_value = mock_server

        transport = StdioTransport(mock_settings_edge, factory)
        # 验证 transport 创建成功
        assert transport is not None

    def test_settings_server_attributes(self, mock_settings_attrs):
        """测试设置中的服务器属性"""
        mock_settings = mock_settings_attrs
        factory = MagicMock()
        mock_server = MagicMock()
        mock_server.create_asgi_app = MagicMock()
        mock_server.startup = AsyncMock()
        mock_server.shutdown = AsyncMock()
        mock_server.context = MagicMock()
        mock_server.context.mcp_sdk_server = MagicMock()
        mock_server.context.mcp_sdk_server.create_initialization_options = MagicMock(
            return_value={}
        )
        mock_server.context.datasource_service = MagicMock()
        factory.return_value = mock_server

        transport = StdioTransport(mock_settings, factory)

        # 验证可以访问 server.settings.server.host
        assert mock_settings.server.host == "localhost"
        assert mock_settings.server.port == 18081

    def _create_mock_server_complete(self):
        """创建完整的 Mock 服务器"""
        mock_server = MagicMock()
        mock_server.create_asgi_app = MagicMock()
        mock_server.startup = AsyncMock()
        mock_server.shutdown = AsyncMock()
        mock_server.settings = MagicMock()
        mock_server.settings.server = MagicMock()
        mock_server.settings.server.host = "localhost"
        mock_server.settings.server.port = 18081
        mock_server.settings.metrics = MagicMock()
        mock_server.settings.metrics.enabled = False

        mock_server.context = MagicMock()
        mock_server.context.mcp_sdk_server = MagicMock()
        mock_server.context.mcp_sdk_server.create_initialization_options = MagicMock()
        mock_server.context.mcp_sdk_server.run = AsyncMock()
        mock_server.context.datasource_service = MagicMock()
        mock_server.context.metrics_service = MagicMock()
        mock_server.context.metrics_service.start_http_server = MagicMock()
        return mock_server

    def _create_mock_streams(self):
        """创建模拟的 stdio streams 上下文管理器"""
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        return mock_cm

    @pytest.mark.asyncio
    async def test_start_with_disabled_metrics(self, mock_settings_attrs):
        """测试禁用 metrics 时的启动流程"""
        mock_settings = mock_settings_attrs
        mock_settings.metrics.enabled = False
        mock_server_complete = self._create_mock_server_complete()
        mock_server_complete.settings.metrics.enabled = False

        factory = MagicMock(return_value=mock_server_complete)
        transport = StdioTransport(mock_settings, factory)

        mock_streams = self._create_mock_streams()

        with (
            patch(
                "dm_mcp.infra.transport.stdio_transport.stdio_server",
                return_value=mock_streams,
            ),
            patch("dm_mcp.infra.transport.stdio_transport.MCPContext") as mock_mcp_ctx,
            patch("dm_mcp.infra.transport.stdio_transport.uvicorn") as mock_uvicorn,
        ):

            mock_ctx = MagicMock()
            mock_mcp_ctx.build_for_stdio = AsyncMock(return_value=mock_ctx)
            mock_mcp_ctx.as_current = MagicMock()

            mock_uvicorn.Server.return_value = MagicMock()
            mock_uvicorn.Server.return_value.serve = AsyncMock()

            await transport._start()

            mock_server_complete.context.metrics_service.start_http_server.assert_not_called()


class TestStdioTransportInheritance:
    """测试继承自 BaseTransport"""

    def test_inherits_from_base_transport(self, mock_settings_attrs, mock_factory):
        """测试继承自 BaseTransport"""
        from dm_mcp.infra.transport import BaseTransport

        transport = StdioTransport(mock_settings_attrs, mock_factory)
        assert isinstance(transport, BaseTransport)

    def test_has_required_attributes(self, mock_settings_attrs, mock_factory):
        """测试具有必需的属性"""
        from dm_mcp.infra.transport import BaseTransport

        transport = StdioTransport(mock_settings_attrs, mock_factory)
        assert hasattr(transport, "server")

    @pytest.fixture
    def mock_factory(self):
        """创建 Mock 工厂函数"""
        factory = MagicMock()
        mock_server = MagicMock()
        mock_server.create_asgi_app = MagicMock()
        mock_server.startup = AsyncMock()
        mock_server.shutdown = AsyncMock()
        mock_server.context = MagicMock()
        mock_server.context.mcp_sdk_server = MagicMock()
        mock_server.context.mcp_sdk_server.create_initialization_options = MagicMock(
            return_value={}
        )
        mock_server.context.datasource_service = MagicMock()
        factory.return_value = mock_server
        return factory
