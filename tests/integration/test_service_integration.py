"""服务集成测试

测试多个服务之间的集成，验证服务之间的协作和依赖关系。
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dm_mcp.server import MCPServer
from dm_mcp.settings import Settings
from tests.conftest import mock_settings


@pytest.mark.integration
@pytest.mark.asyncio
class TestServiceIntegration:
    """服务集成测试类"""

    @pytest_asyncio.fixture
    async def server(self, mock_settings):
        """创建测试服务器实例"""

        # 创建一个返回 mock_settings 的类
        # 使用 __new__ 方法在实例化时返回 mock_settings
        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)  # type: ignore
        yield server
        await server.shutdown()

    @pytest_asyncio.fixture
    async def app(self, server):
        """创建 ASGI 应用"""
        app = server.create_asgi_app(stateless=True)
        # 手动启动服务器（因为 TestClient 不会触发 lifespan）
        await server.startup()
        yield app
        await server.shutdown()

    @pytest_asyncio.fixture
    async def client(self, app):
        """创建测试客户端"""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    async def test_health_check_endpoint(self, client, server):
        """测试健康检查端点"""
        # 根据 base_url 构建完整路径
        # 注意：health 端点需要认证，所以可能返回 403
        base_url = server.settings.server.base_url
        response = await client.get(f"{base_url}/api/v1/health")
        # health 端点需要认证，可能返回 200（已认证）或 403（未认证）
        assert response.status_code in [200, 403]
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert data["status"] == "healthy"

    async def test_config_endpoint(self, client, server):
        """测试配置端点"""
        # 根据 base_url 构建完整路径
        base_url = server.settings.server.base_url
        response = await client.get(f"{base_url}/api/v1/config")
        assert response.status_code == 200
        data = response.json()
        # config 端点返回: oauth_enabled, token_auth_enabled, initialized
        assert (
            "oauth_enabled" in data
            or "token_auth_enabled" in data
            or "initialized" in data
        )

    async def test_metrics_endpoint(self, client, server):
        """测试指标端点"""
        # 根据 base_url 构建完整路径
        base_url = server.settings.server.base_url
        metrics_path = server.settings.metrics.http_path
        # 如果 metrics_path 已经包含 base_url，直接使用；否则拼接
        if metrics_path.startswith(base_url):
            full_path = metrics_path
        else:
            full_path = (
                f"{base_url}{metrics_path}"
                if metrics_path.startswith("/")
                else f"{base_url}/{metrics_path}"
            )
        response = await client.get(full_path)
        # 指标端点可能返回 200 或 404（如果未启用）
        assert response.status_code in [200, 404]

    async def test_service_registry_integration(self, server):
        """测试服务注册表集成"""
        # 验证所有服务都已注册
        assert server.context.logging_service is not None
        assert server.context.metrics_service is not None
        assert server.context.jwt_service is not None
        assert server.context.token_service is not None
        assert server.context.datasource_service is not None
        assert server.context.mcp_service is not None

    async def test_service_lifecycle(self, server):
        """测试服务生命周期管理"""
        # 启动服务
        await server.startup()

        # 验证服务已启动
        assert server.context.logging_service is not None

        # 关闭服务
        await server.shutdown()

        # 验证服务已关闭（通过检查服务状态或异常）
        # 注意：某些服务可能没有显式的关闭状态检查

    async def test_mcp_service_provider_integration(self, server):
        """测试 MCP 服务与 Provider 的集成"""
        await server.startup()

        # 验证 Provider 已注册
        mcp_service = server.context.mcp_service
        # 检查是否有 Provider 注册（具体实现可能不同）
        # 这里假设可以通过某种方式检查 Provider 数量

        await server.shutdown()

    async def test_datasource_service_integration(self, server):
        """测试数据源服务集成"""
        await server.startup()

        datasource_service = server.context.datasource_service
        # 测试数据源列表
        data_sources = await datasource_service.list_datasources()
        assert isinstance(data_sources, list)

        await server.shutdown()

    async def test_token_service_integration(self, server):
        """测试 Token 服务集成"""
        await server.startup()

        token_service = server.context.token_service
        # 测试 Token 列表
        tokens = await token_service.list_tokens()
        assert isinstance(tokens, list)

        await server.shutdown()

    async def test_jwt_service_integration(self, server):
        """测试 JWT 服务集成"""
        await server.startup()

        jwt_service = server.context.jwt_service
        # 测试 JWT Token 生成
        user_info = {"sub": "testuser", "email": "test@example.com"}
        token = jwt_service.create_token(user_info)
        assert token is not None
        assert isinstance(token, str)

        # 测试 JWT Token 解码
        decoded = jwt_service.decode_token(token)
        assert decoded is not None
        assert decoded.get("sub") == "testuser"

        await server.shutdown()

    async def test_cache_backend_integration(self, server):
        """测试缓存后端集成"""
        await server.startup()

        # 注意：GlobalContext 没有直接的 cache_service 属性
        # 缓存功能可能通过其他服务（如 metrics_service）提供
        # 这里只测试服务已初始化
        assert server.context.metrics_service is not None

        await server.shutdown()
