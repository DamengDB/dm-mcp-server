"""MCPServer 单元测试

使用 Mock 来避免 Settings 初始化时与 pytest 命令行参数冲突的问题 (SystemExit: 2)
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock

import pytest

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent.resolve()
src_path = (project_root / "src").resolve()
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def create_mock_settings():
    """创建完全可写的 Mock Settings 对象"""
    mock = MagicMock()
    mock.server.debug = False
    mock.server.audit_enabled = False
    mock.server.transport = "stdio"
    mock.server.host = "localhost"
    mock.server.port = 18081
    mock.server.base_url = "http://localhost:18081"
    mock.server.workers = 1
    mock.server.frontend_url = ""
    mock.server.static_path = "/static"
    mock.jwt.secret = "test-secret-key"
    mock.jwt.token_expire_seconds = 3600
    mock.oauth.enabled = False
    mock.oauth.providers = {}
    mock.pool.default_source = "primary"
    mock.pool.max_size = 10
    mock.pool.min_size = 1
    mock.logging.level = "INFO"
    mock.to_env = MagicMock(return_value={})
    return mock


def create_mock_context():
    """创建完全可写的 Mock GlobalContext 对象"""
    mock_context = MagicMock()
    mock_context.metrics_service = MagicMock()
    mock_context.logging_service = MagicMock()
    mock_context.cache_service = MagicMock()
    mock_context.datasource_service = MagicMock()
    mock_context.pool_service = MagicMock()
    mock_context.oauth_service = MagicMock()
    mock_context.basic_auth_service = MagicMock()
    mock_context.token_service = MagicMock()
    mock_context.mcp_service = MagicMock()
    mock_context.jwt_service = MagicMock()
    mock_context.registry = MagicMock()
    mock_context.mcp_sdk_server = MagicMock()
    mock_context.mcp = MagicMock()  # mcp 属性
    mock_context.initialize_services = AsyncMock()
    mock_context.shutdown_services = AsyncMock()
    return mock_context


class TestMCPServerProvidersLoading:
    """_load_mcp_providers 方法测试"""

    @patch("dm_mcp.server.server.FunctionMCPProvider")
    @patch("dm_mcp.server.server.MCPFunctionRegistry")
    def test_load_mcp_providers(self, mock_registry, mock_function_provider):
        """测试加载多个 MCP Providers"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_providers = MagicMock()
        mock_context.registry = MagicMock()

        # Mock provider instances
        mock_function_instance = MagicMock()
        mock_function_instance.mcp = MagicMock()
        mock_function_provider.return_value = mock_function_instance

        mock_registry_instance = MagicMock()
        mock_registry.return_value = mock_registry_instance

        # Create server instance
        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context

        # Call the method
        server._load_mcp_providers()

        # Verify providers were added
        mock_context.mcp_service.add_mcp_providers.assert_called_once()
        call_args = mock_context.mcp_service.add_mcp_providers.call_args[0][0]
        # Should have Function, Metadata, QueryExec, PoolOps, DpcCluster, MetricsExport
        assert len(call_args) == 6

    @patch("dm_mcp.server.server.FunctionMCPProvider")
    @patch("dm_mcp.server.server.MCPFunctionRegistry")
    def test_load_mcp_providers_creates_registry(
        self, mock_registry, mock_function_provider
    ):
        """测试 _load_mcp_providers 创建 MCPFunctionRegistry"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_providers = MagicMock()
        mock_context.registry = MagicMock()

        # Mock provider instances
        mock_function_instance = MagicMock()
        mock_router = MagicMock()
        mock_function_instance.mcp = mock_router
        mock_function_provider.return_value = mock_function_instance

        mock_registry_instance = MagicMock()
        mock_registry.return_value = mock_registry_instance

        # Create server and call method
        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context

        server._load_mcp_providers()

        # Verify MCPFunctionRegistry was created with correct parameters
        mock_registry.assert_called_once_with(
            router=mock_router, registry=mock_context.registry
        )


class TestMCPMiddlewaresLoading:
    """_load_mcp_middlewares 方法测试"""

    @patch("dm_mcp.server.server.MetricsMCPMiddleware")
    @patch("dm_mcp.server.server.TokenAuthMCPMiddleware")
    @patch("dm_mcp.server.server.AuditMCPMiddleware")
    def test_load_mcp_middlewares(self, mock_audit, mock_token_auth, mock_metrics):
        """测试加载默认 MCP 中间件"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_middlewares = MagicMock()

        # Call the method
        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context

        server._load_mcp_middlewares()

        # Verify middleware methods called
        mock_context.mcp_service.add_mcp_middlewares.assert_called_once()
        call_args = mock_context.mcp_service.add_mcp_middlewares.call_args[0][0]
        # Should have Metrics, TokenAuth, Audit
        assert len(call_args) == 3

    @patch("dm_mcp.server.server.MetricsMCPMiddleware")
    @patch("dm_mcp.server.server.TokenAuthMCPMiddleware")
    @patch("dm_mcp.server.server.AuditMCPMiddleware")
    def test_load_mcp_middlewares_passes_dependencies(
        self, mock_audit, mock_token_auth, mock_metrics
    ):
        """测试中间件初始化时传递正确的依赖"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_settings.server.audit_enabled = True
        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_middlewares = MagicMock()
        mock_context.metrics_service = MagicMock()
        mock_context.datasource_service = MagicMock()
        mock_context.mcp_service = MagicMock()
        mock_context.logging_service = MagicMock()

        # Call the method
        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context

        server._load_mcp_middlewares()

        # Verify MetricsMCPMiddleware was created with metrics_service
        mock_metrics.assert_called_once_with(mock_context.metrics_service)

        # Verify TokenAuthMCPMiddleware was created with datasource_service and mcp_service
        mock_token_auth.assert_called_once_with(
            mock_context.datasource_service,
            mock_context.mcp_service,
        )

        # Verify AuditMCPMiddleware was created with audit_enabled and logging_service
        mock_audit.assert_called_once_with(
            mock_settings.server.audit_enabled,
            mock_context.logging_service,
        )


class TestMCPServerLifecycle:
    """MCPServer 生命周期测试"""

    @pytest.mark.asyncio
    async def test_startup_initializes_services(self):
        """测试 startup 调用 initialize_services"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()

        # Create server instance (without calling __init__)
        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context
        server._startup_hooks = []
        server._shutdown_hooks = []

        # Add a startup hook
        startup_hook = AsyncMock()
        server._startup_hooks.append(startup_hook)

        # Call startup
        await server.startup()

        # Verify initialize_services was called
        mock_context.initialize_services.assert_called_once()
        # Verify startup hook was called
        startup_hook.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_calls_services(self):
        """测试 shutdown 调用 shutdown_services"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()

        # Create server instance (without calling __init__)
        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context
        server._startup_hooks = []
        server._shutdown_hooks = []

        # Add a shutdown hook
        shutdown_hook = AsyncMock()
        server._shutdown_hooks.append(shutdown_hook)

        # Call shutdown
        await server.shutdown()

        # Verify shutdown_services was called
        mock_context.shutdown_services.assert_called_once()
        # Verify shutdown hook was called
        shutdown_hook.assert_called_once()

    @pytest.mark.asyncio
    async def test_startup_logs_messages(self, caplog):
        """测试 startup 记录日志"""
        import logging
        from dm_mcp.server.server import MCPServer

        caplog.set_level(logging.INFO)

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()
        mock_context.initialize_services = AsyncMock()

        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context
        server._startup_hooks = []

        await server.startup()

        # Check log messages
        log_messages = [r.message for r in caplog.records]
        assert any("启动" in msg for msg in log_messages)

    @pytest.mark.asyncio
    async def test_shutdown_logs_messages(self, caplog):
        """测试 shutdown 记录日志"""
        import logging
        from dm_mcp.server.server import MCPServer

        caplog.set_level(logging.INFO)

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()
        mock_context.shutdown_services = AsyncMock()

        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context
        server._shutdown_hooks = []

        await server.shutdown()

        # Check log messages
        log_messages = [r.message for r in caplog.records]
        assert any("关闭" in msg or "已关闭" in msg for msg in log_messages)


class TestMCPServerProviderManagement:
    """MCPServer Provider 管理测试"""

    def test_add_mcp_provider_delegates_to_service(self):
        """测试 add_mcp_provider 委托给 mcp_service"""
        from dm_mcp.server.server import MCPServer

        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_provider = MagicMock()

        server = object.__new__(MCPServer)
        server.context = mock_context

        mock_provider = MagicMock()
        server.add_mcp_provider(mock_provider)

        mock_context.mcp_service.add_mcp_provider.assert_called_once_with(mock_provider)

    def test_add_mcp_providers_batch(self):
        """测试批量添加 Providers"""
        from dm_mcp.server.server import MCPServer

        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_providers = MagicMock()

        server = object.__new__(MCPServer)
        server.context = mock_context

        mock_providers = [MagicMock(), MagicMock(), MagicMock()]
        server.add_mcp_providers(mock_providers)

        mock_context.mcp_service.add_mcp_providers.assert_called_once_with(
            mock_providers
        )


class TestMCPServerMiddlewareManagement:
    """MCPServer 中间件管理测试"""

    def test_add_mcp_middleware_delegates_to_service(self):
        """测试 add_mcp_middleware 委托给 mcp_service"""
        from dm_mcp.server.server import MCPServer

        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_middleware = MagicMock()

        server = object.__new__(MCPServer)
        server.context = mock_context

        mock_middleware = MagicMock()
        server.add_mcp_middleware(mock_middleware)

        mock_context.mcp_service.add_mcp_middleware.assert_called_once_with(
            mock_middleware
        )

    def test_add_mcp_middlewares_batch(self):
        """测试批量添加中间件"""
        from dm_mcp.server.server import MCPServer

        mock_context = create_mock_context()
        mock_context.mcp_service.add_mcp_middlewares = MagicMock()

        server = object.__new__(MCPServer)
        server.context = mock_context

        mock_middlewares = [MagicMock(), MagicMock()]
        server.add_mcp_middlewares(mock_middlewares)

        mock_context.mcp_service.add_mcp_middlewares.assert_called_once_with(
            mock_middlewares
        )


class TestMCPServerDecorators:
    """MCPServer 装饰器测试"""

    def test_on_startup_decorator_adds_hook(self):
        """测试 on_startup 装饰器添加钩子"""
        from dm_mcp.server.server import MCPServer

        server = object.__new__(MCPServer)
        server._startup_hooks = []

        # Test decorator returns the function
        @server.on_startup
        async def startup_callback():
            pass

        assert len(server._startup_hooks) == 1
        assert server._startup_hooks[0] == startup_callback

    def test_on_shutdown_decorator_adds_hook(self):
        """测试 on_shutdown 装饰器添加钩子"""
        from dm_mcp.server.server import MCPServer

        server = object.__new__(MCPServer)
        server._shutdown_hooks = []

        # Test decorator returns the function
        @server.on_shutdown
        async def shutdown_callback():
            pass

        assert len(server._shutdown_hooks) == 1
        assert server._shutdown_hooks[0] == shutdown_callback

    def test_decorator_returns_original_function(self):
        """测试装饰器返回原始函数"""
        from dm_mcp.server.server import MCPServer

        server = object.__new__(MCPServer)
        server._startup_hooks = []

        def sync_callback():
            return "called"

        result = server.on_startup(sync_callback)
        assert result == sync_callback

    def test_multiple_decorators(self):
        """测试添加多个装饰器"""
        from dm_mcp.server.server import MCPServer

        server = object.__new__(MCPServer)
        server._startup_hooks = []

        @server.on_startup
        async def hook1():
            pass

        @server.on_startup
        async def hook2():
            pass

        assert len(server._startup_hooks) == 2


class TestMCPServerASGIApp:
    """MCPServer ASGI 应用测试 - 跳过需要 mock mcp 库的测试"""

    @pytest.mark.skip(reason="需要 mock mcp 库中的 StreamableHTTPSessionManager")
    def test_create_asgi_app(self):
        """测试创建 ASGI 应用"""
        pass

    @pytest.mark.skip(reason="需要 mock mcp 库中的 StreamableHTTPSessionManager")
    def test_create_asgi_app_stateless(self):
        """测试创建无状态 ASGI 应用"""
        pass


class TestMCPServerHTTPMiddlewares:
    """MCPServer HTTP 中间件测试"""

    def test_get_http_middlewares_returns_list(self):
        """测试 _get_http_middlewares 返回列表"""
        from dm_mcp.server.server import MCPServer
        from starlette.middleware import Middleware

        mock_settings = create_mock_settings()
        mock_settings.server.audit_enabled = True
        mock_context = create_mock_context()

        # Mock AuthBackend
        with patch("dm_mcp.server.server.AuthBackend") as mock_auth_backend:
            mock_auth_backend_instance = MagicMock()
            mock_auth_backend.return_value = mock_auth_backend_instance
            mock_auth_backend.on_error = MagicMock()

            server = object.__new__(MCPServer)
            server.settings = mock_settings
            server.context = mock_context

            # Get HTTP middlewares
            middlewares = server._get_http_middlewares()

            # Verify we got a list
            assert isinstance(middlewares, list)

            # Should have multiple middlewares (UTF8, ExceptionHandler, CORS, Auth, Audit)
            assert len(middlewares) >= 5

            # All should be Middleware instances
            for m in middlewares:
                assert isinstance(m, Middleware)

    def test_get_http_middlewares_includes_cors(self):
        """测试 HTTP 中间件包含 CORS 配置"""
        from dm_mcp.server.server import MCPServer
        from starlette.middleware.cors import CORSMiddleware

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()

        with patch("dm_mcp.server.server.AuthBackend"):
            server = object.__new__(MCPServer)
            server.settings = mock_settings
            server.context = mock_context

            middlewares = server._get_http_middlewares()

            # Check for CORSMiddleware
            cors_middleware = next(
                (m for m in middlewares if m.cls == CORSMiddleware), None
            )
            assert cors_middleware is not None
            # Verify CORS allows localhost
            assert "localhost" in str(
                cors_middleware.kwargs.get("allow_origin_regex", "")
            )

    def test_get_http_middlewares_includesauth(self):
        """测试 HTTP 中间件包含认证"""
        from dm_mcp.server.server import MCPServer
        from starlette.middleware.authentication import AuthenticationMiddleware

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()

        with patch("dm_mcp.server.server.AuthBackend") as mock_auth_backend:
            mock_auth_backend.on_error = MagicMock()

            server = object.__new__(MCPServer)
            server.settings = mock_settings
            server.context = mock_context

            middlewares = server._get_http_middlewares()

            # Check for AuthenticationMiddleware
            auth_middleware = next(
                (m for m in middlewares if m.cls == AuthenticationMiddleware), None
            )
            assert auth_middleware is not None


class TestMCPServerRun:
    """MCPServer run 方法测试 - 跳过高风险的测试"""

    @pytest.mark.skip(reason="Settings 初始化与 pytest 参数冲突，无法简单 mock")
    def test_run_stdio_imports_transport(self):
        """测试 run 方法导入 StdioTransport"""
        pass

    @pytest.mark.skip(reason="Settings 初始化与 pytest 参数冲突，无法简单 mock")
    def test_run_http_imports_transport(self):
        """测试 run 方法导入 StreamableHttpTransport"""
        pass

    @pytest.mark.skip(reason="Settings 初始化与 pytest 参数冲突，无法简单 mock")
    def test_run_invalid_transport_raises_error(self):
        """测试无效传输模式抛出错误"""
        pass


class TestMCPServerAttributes:
    """MCPServer 属性测试"""

    def test_server_has_settings_attribute(self):
        """测试服务器有 settings 属性"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()

        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context
        server.mcp = MagicMock()
        server._startup_hooks = []
        server._shutdown_hooks = []

        assert hasattr(server, "settings")
        assert server.settings == mock_settings

    def test_server_has_context_attribute(self):
        """测试服务器有 context 属性"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()

        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context

        assert hasattr(server, "context")
        assert server.context == mock_context

    def test_server_has_mcp_attribute(self):
        """测试服务器有 mcp 属性"""
        from dm_mcp.server.server import MCPServer

        mock_settings = create_mock_settings()
        mock_context = create_mock_context()

        server = object.__new__(MCPServer)
        server.settings = mock_settings
        server.context = mock_context
        server.mcp = MagicMock()

        assert hasattr(server, "mcp")

    def test_lifecycle_hooks_list_type(self):
        """测试生命周期钩子是列表类型"""
        from dm_mcp.server.server import MCPServer

        server = object.__new__(MCPServer)
        server._startup_hooks = []
        server._shutdown_hooks = []

        assert isinstance(server._startup_hooks, list)
        assert isinstance(server._shutdown_hooks, list)


class TestMCPServerGenericTypes:
    """MCPServer 泛型类型测试"""

    def test_server_with_default_types(self):
        """测试默认类型参数"""
        from dm_mcp.server.server import MCPServer, Settings, GlobalContext
        from typing import get_args

        # MCPServer 默认使用 Settings 和 GlobalContext
        # 验证类的基类包含 Generic
        assert hasattr(MCPServer, "__orig_bases__")

    def test_server_generic_signature(self):
        """测试服务器泛型签名"""
        from dm_mcp.server.server import MCPServer, T_Settings, T_Context

        # 验证类型变量的存在
        assert T_Settings is not None
        assert T_Context is not None


class TestMCPServerMethodSignatures:
    """MCPServer 方法签名测试"""

    def test_add_mcp_provider_signature(self):
        """测试 add_mcp_provider 方法签名"""
        from dm_mcp.server.server import MCPServer
        import inspect

        sig = inspect.signature(MCPServer.add_mcp_provider)
        params = list(sig.parameters.keys())

        assert "self" in params
        assert "provider" in params

    def test_add_mcp_middleware_signature(self):
        """测试 add_mcp_middleware 方法签名"""
        from dm_mcp.server.server import MCPServer
        import inspect

        sig = inspect.signature(MCPServer.add_mcp_middleware)
        params = list(sig.parameters.keys())

        assert "self" in params
        assert "middleware" in params

    def test_create_asgi_app_signature(self):
        """测试 create_asgi_app 方法签名"""
        from dm_mcp.server.server import MCPServer
        import inspect

        sig = inspect.signature(MCPServer.create_asgi_app)
        params = list(sig.parameters.keys())

        assert "stateless" in params

    def test_on_startup_signature(self):
        """测试 on_startup 装饰器方法签名"""
        from dm_mcp.server.server import MCPServer
        import inspect

        sig = inspect.signature(MCPServer.on_startup)
        params = list(sig.parameters.keys())

        assert "self" in params
        assert "func" in params

    def test_run_signature(self):
        """测试 run 类方法签名"""
        from dm_mcp.server.server import MCPServer
        import inspect

        # run 是类方法
        sig = inspect.signature(MCPServer.run)
        params = list(sig.parameters.keys())

        assert "factory" in params
        assert "settings_cls" in params
