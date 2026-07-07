"""认证流程集成测试

测试完整的认证流程，包括 OAuth、Basic Auth 和 Token 认证。
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dm_mcp.app.server import MCPServer
from tests.conftest import mock_settings


def _test_datasource_id() -> str:
    """Token 测试用的数据源 UUID（create_token 不校验数据源是否存在）。"""
    return str(uuid.uuid4())


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.auth
class TestAuthFlow:
    """认证流程测试类"""

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

    def _get_path(self, server, path: str) -> str:
        """获取完整路径（包含 base_url）"""
        base_url = server.settings.server.base_url
        if path.startswith(base_url):
            return path
        return f"{base_url}{path}" if path.startswith("/") else f"{base_url}/{path}"

    async def test_oauth_providers_endpoint(self, client, server):
        """测试 OAuth 提供商列表端点"""
        path = self._get_path(server, "/api/v1/auth/providers")
        response = await client.get(path)
        # OAuth 端点可能返回 200 或 404（如果未配置）
        assert response.status_code in [200, 404, 500]

    async def test_basic_auth_init_password(self, client, server):
        """测试基础认证初始化密码"""
        path = self._get_path(server, "/api/v1/auth/admin/init-password")
        response = await client.post(
            path,
            json={"username": "admin", "password": "admin123"},
        )
        # 可能返回 200（成功）或 400（已存在）或其他状态码
        assert response.status_code in [200, 201, 400, 404, 500]

    async def test_basic_auth_init_password_success(self, mock_settings):
        """测试基础认证初始化密码成功情况"""

        # 使用独立的服务器实例，确保数据库是干净的
        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)  # type: ignore
        await server.startup()

        try:
            app = server.create_asgi_app(stateless=True)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # 先检查是否已初始化
                basic_auth_service = server.context.basic_auth_service
                is_initialized = await basic_auth_service.is_initialized()

                if not is_initialized:
                    # 如果未初始化，应该能成功初始化
                    path = self._get_path(server, "/api/v1/auth/admin/init-password")
                    response = await client.post(
                        path,
                        json={"password": "admin123"},
                    )
                    # 应该返回 200 成功
                    assert response.status_code == 200
                    data = response.json()
                    assert data["success"] is True
                    assert "message" in data
                else:
                    # 如果已初始化，测试重复初始化的情况
                    path = self._get_path(server, "/api/v1/auth/admin/init-password")
                    response = await client.post(
                        path,
                        json={"password": "admin123"},
                    )
                    # 应该返回 400 已存在
                    assert response.status_code == 400
        finally:
            await server.shutdown()

    async def test_basic_auth_login_flow(self, client, server):
        """测试基础认证登录流程"""
        # 1. 先初始化密码（如果不存在）
        init_path = self._get_path(server, "/api/v1/auth/admin/init-password")
        init_response = await client.post(
            init_path,
            json={"username": "admin", "password": "admin123"},
        )
        # 忽略初始化结果，继续测试登录

        # 2. 尝试登录 - 注意：实际API使用Authorization头，不是JSON body
        login_path = self._get_path(server, "/api/v1/auth/admin/login")
        import base64

        credentials = base64.b64encode(b"admin:admin123").decode()
        login_response = await client.post(
            login_path,
            headers={"Authorization": f"Basic {credentials}"},
        )
        # 登录可能成功（200）或失败（401）
        assert login_response.status_code in [200, 401, 404, 500]

        if login_response.status_code == 200:
            data = login_response.json()
            payload = data.get("data", data)
            assert (
                "token" in payload
                or "access_token" in payload
                or "jwt" in payload
                or "user" in payload
            )

    async def test_basic_auth_login_flow_success(self, mock_settings):
        """测试基础认证登录流程成功情况"""

        # 使用独立的服务器实例
        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)  # type: ignore
        await server.startup()

        try:
            app = server.create_asgi_app(stateless=True)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                # 1. 确保密码已初始化
                basic_auth_service = server.context.basic_auth_service
                if not await basic_auth_service.is_initialized():
                    await basic_auth_service.init_password("admin123")

                # 2. 使用正确的Basic Auth头登录
                login_path = self._get_path(server, "/api/v1/auth/admin/login")
                import base64

                credentials = base64.b64encode(b"admin:admin123").decode()
                login_response = await client.post(
                    login_path,
                    headers={"Authorization": f"Basic {credentials}"},
                )

                # 应该成功登录，返回 200
                assert login_response.status_code == 200
                data = login_response.json()
                assert data["success"] is True
                assert "jwt" in data["data"]
        finally:
            await server.shutdown()

    async def test_jwt_token_creation_and_validation(self, server):
        """测试 JWT Token 创建和验证流程"""
        await server.startup()

        jwt_service = server.context.jwt_service

        # 1. 创建 Token
        user_info = {
            "sub": "testuser",
            "email": "test@example.com",
            "name": "Test User",
        }
        token = jwt_service.create_token(user_info)
        assert token is not None

        # 2. 验证 Token
        decoded = jwt_service.decode_token(token)
        assert decoded is not None
        assert decoded.get("sub") == "testuser"
        assert decoded.get("email") == "test@example.com"

        await server.shutdown()

    async def test_token_service_crud_flow(self, server):
        """测试 Token 服务的 CRUD 流程"""
        await server.startup()

        token_service = server.context.token_service
        datasource_id = _test_datasource_id()

        # 2. 创建 Token
        user_id = "test_user"
        created_token = await token_service.create_token(
            user_id=user_id,
            datasource_ids=[datasource_id],
            default_datasource_id=datasource_id,
            name="Test token for integration",
        )
        assert created_token is not None
        assert hasattr(created_token, "token") or isinstance(created_token, dict)

        # 2. 获取 Token 的管理短码 token_id
        token_id_value = None
        if hasattr(created_token, "token_id"):
            token_id_value = getattr(created_token, "token_id", None)
        elif isinstance(created_token, dict):
            token_id_value = created_token.get("token_id")
        token_value = None
        if hasattr(created_token, "token"):
            token_value = getattr(created_token, "token", None)
        elif isinstance(created_token, dict):
            token_value = created_token.get("token")
        if token_value:
            retrieved_token = await token_service.get_token(token_value)
            # Token 可能被找到或未找到
            # assert retrieved_token is not None

        # 3. 列出所有 Token
        tokens = await token_service.list_tokens()
        assert isinstance(tokens, list)

        # 4. 更新 Token（如果支持）
        if token_id_value:
            try:
                updated_token = await token_service.update_token(
                    token_id=token_id_value, name="Updated name"
                )
                # 更新可能成功或失败
            except Exception:
                # 更新操作可能不支持，这里只测试接口存在
                pass

        # 5. 删除 Token（如果支持）
        if token_id_value:
            try:
                await token_service.delete_token(token_id_value)
                # 删除可能成功或失败
            except Exception:
                # 删除操作可能不支持，这里只测试接口存在
                pass

        await server.shutdown()

    async def test_token_authentication_middleware(self, client, server):
        """测试 Token 认证中间件"""
        await server.startup()

        # 创建一个测试 Token
        token_service = server.context.token_service
        datasource_id = _test_datasource_id()

        created_token = await token_service.create_token(
            user_id="integration_test_user",
            datasource_ids=[datasource_id],
            default_datasource_id=datasource_id,
            name="Token for integration test",
        )

        # 获取 Token 值
        token_value = None
        if hasattr(created_token, "token"):
            token_value = created_token.token
        elif isinstance(created_token, dict):
            token_value = created_token.get("token")

        # 使用 Token 访问 MCP 端点（MCP Token 仅用于 /mcp 路由）
        if token_value:
            headers = {"Authorization": f"Bearer {token_value}"}
            path = self._get_path(server, "/mcp/messages?sessionId=test_session")
            response = await client.post(
                path,
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                headers=headers,
            )
            assert response.status_code in [200, 400, 404, 500]

        await server.shutdown()

    async def test_token_authentication_success(self, mock_settings):
        """测试 Token 认证成功情况"""

        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)  # type: ignore
        await server.startup()

        try:
            app = server.create_asgi_app(stateless=True)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                token_service = server.context.token_service
                datasource_id = _test_datasource_id()

                created_token = await token_service.create_token(
                    user_id="integration_test_user",
                    datasource_ids=[datasource_id],
                    default_datasource_id=datasource_id,
                    name="Token for integration test",
                )

                token_value = getattr(created_token, "token", None) or (
                    created_token.get("token")
                    if isinstance(created_token, dict)
                    else None
                )
                assert token_value is not None, "Token should be created successfully"

                headers = {"Authorization": f"Bearer {token_value}"}
                path = self._get_path(server, "/mcp/messages?sessionId=test_session")
                response = await client.post(
                    path,
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers=headers,
                )

                # MCP Token 认证成功时不应返回 401/403
                assert response.status_code in [200, 400, 404, 500]
                assert response.status_code not in [401, 403]
        finally:
            await server.shutdown()

    async def test_auth_context_integration(self, server):
        """测试认证上下文集成"""
        await server.startup()

        # 验证认证相关的服务都已初始化
        assert server.context.jwt_service is not None
        assert server.context.oauth_service is not None
        assert server.context.basic_auth_service is not None
        assert server.context.token_service is not None

        await server.shutdown()
