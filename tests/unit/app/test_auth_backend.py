"""AuthBackend 测试"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.authentication import AuthCredentials, AuthenticationError
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse
from starlette.datastructures import URL, Headers

from dm_mcp.app.auth_backend import AuthBackend
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.auth.user import MCPUser
from dm_mcp.domain.auth.services.oauth import OAuthService
from dm_mcp.domain.token.services.token import TokenService


@pytest.fixture
def mock_auth_config_service():
    """Mock 认证配置服务"""
    mock = MagicMock()
    mock.token_auth_enabled = False
    return mock


class MockTokenConfig:
    """模拟Token配置"""

    def __init__(
        self,
        user_id="test_user",
        datasource_ids=None,
        default_datasource_id="ds_123",
        ip_whitelist=None,
        ip_blacklist=None,
    ):
        self.user_id = user_id
        self.datasource_ids = datasource_ids or ["ds_123"]
        self.default_datasource_id = default_datasource_id
        self.token = "test_token"
        self.ip_whitelist = ip_whitelist or []
        self.ip_blacklist = ip_blacklist or []


class TestAuthBackendInit:
    """AuthBackend 初始化测试"""

    def test_init_basic(self):
        """测试基本初始化"""
        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        assert backend.settings is mock_settings
        assert backend.oauth_service is mock_oauth
        assert backend.token_service is None

    def test_init_with_all_services(self):
        """测试带所有服务的初始化"""
        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_datasource_service = MagicMock()

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
            datasource_service=mock_datasource_service,
        )

        assert backend.token_service is mock_token_service
        assert backend.datasource_service is mock_datasource_service


class TestAuthBackendExtractAuthInfo:
    """_extract_auth_info 方法测试"""

    @pytest.fixture
    def mock_conn(self):
        """创建模拟的HTTP连接"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers(
            {"Authorization": "Bearer test_token_123", "X-Forwarded-For": "192.168.1.1"}
        )
        url = MagicMock(spec=URL)
        url.path = "/api/test"
        conn.url = url
        conn.query_params = {}
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"
        return conn

    def test_extract_auth_info_with_bearer(self, mock_conn):
        """测试 Bearer Token 提取"""
        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        auth_info = backend._extract_auth_info(mock_conn)

        assert auth_info["authorization"] == "Bearer"
        assert auth_info["token"] == "test_token_123"
        assert auth_info["client_ip"] == "192.168.1.1"

    def test_extract_auth_info_with_token_scheme(self, mock_conn):
        """测试 Token Scheme 提取"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Token my_token"})
        url = MagicMock(spec=URL)
        url.path = "/mcp/test"
        conn.url = url
        conn.query_params = {}
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        auth_info = backend._extract_auth_info(conn)

        assert auth_info["authorization"] == "Token"
        assert auth_info["token"] == "my_token"

    def test_extract_auth_info_no_auth_header(self):
        """测试无认证头"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({})
        url = MagicMock(spec=URL)
        url.path = "/api/test"
        conn.url = url
        conn.query_params = {}
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        auth_info = backend._extract_auth_info(conn)

        assert auth_info["authorization"] == ""
        assert auth_info["token"] == ""


class TestAuthBackendGetClientIp:
    """_get_client_ip 方法测试"""

    def test_get_client_ip_from_forwarded_for(self):
        """测试从 X-Forwarded-For 获取 IP"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"X-Forwarded-For": "10.0.0.1, 192.168.1.1"})
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        ip = backend._get_client_ip(conn)

        assert ip == "10.0.0.1"

    def test_get_client_ip_from_real_ip(self):
        """测试从 X-Real-IP 获取 IP"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"X-Real-IP": "10.0.0.2"})
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        ip = backend._get_client_ip(conn)

        assert ip == "10.0.0.2"

    def test_get_client_ip_from_direct_connection(self):
        """测试直接连接获取 IP"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({})
        conn.client = MagicMock()
        conn.client.host = "192.168.1.100"

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        ip = backend._get_client_ip(conn)

        assert ip == "192.168.1.100"

    def test_get_client_ip_no_client(self):
        """测试无客户端信息"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({})
        conn.client = None

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        ip = backend._get_client_ip(conn)

        assert ip == "unknown"


class TestAuthBackendOnError:
    """on_error 方法测试"""

    def test_on_error_invalid_token(self):
        """测试 InvalidTokenError 处理"""
        from dm_mcp.core.exceptions.auth_errors import InvalidTokenError

        mock_request = MagicMock()
        exc = InvalidTokenError("Invalid token")

        response = AuthBackend.on_error(mock_request, exc)

        assert response.status_code == 401

    def test_on_error_token_expired(self):
        """测试 TokenExpiredError 处理"""
        from dm_mcp.core.exceptions.auth_errors import TokenExpiredError

        mock_request = MagicMock()
        exc = TokenExpiredError("Token expired")

        response = AuthBackend.on_error(mock_request, exc)

        assert response.status_code == 401

    def test_on_error_ip_not_allowed(self):
        """测试 IpNotAllowedError 处理"""
        from dm_mcp.core.exceptions.auth_errors import IpNotAllowedError

        mock_request = MagicMock()
        exc = IpNotAllowedError("IP not allowed")

        response = AuthBackend.on_error(mock_request, exc)

        assert response.status_code == 403

    def test_on_error_generic_exception(self):
        """测试通用异常处理"""
        mock_request = MagicMock()
        exc = Exception("Generic error")

        response = AuthBackend.on_error(mock_request, exc)

        assert response.status_code == 401
        assert response.body is not None


class TestAuthBackendGetTokenAuthContext:
    """_get_token_auth_context 方法测试"""

    @pytest.mark.asyncio
    async def test_get_token_auth_context_success(self):
        """测试成功获取 Token 认证上下文"""
        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(user_id="testuser")
        )

        backend = AuthBackend(
            mock_settings, mock_oauth, mock_auth_config_service, token_service=mock_token_service
        )

        context = await backend._get_token_auth_context("test_token")

        assert context.user_id == "testuser"
        assert context.auth_type == "token"

    @pytest.mark.asyncio
    async def test_get_token_auth_context_no_service(self):
        """测试无 Token 服务时抛出异常"""
        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        with pytest.raises(AuthenticationError) as exc_info:
            await backend._get_token_auth_context("test_token")

        assert "Token 服务不可用" in str(exc_info.value)


class TestAuthBackendAuthenticateMCPRoute:
    """MCP 路由认证测试"""

    @pytest.mark.asyncio
    @patch.object(AuthBackend, "_get_client_ip")
    async def test_authenticate_mcp_token_success(self, mock_get_ip):
        """测试 MCP Token 认证成功"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(user_id="testuser", datasource_ids=["ds_123"], default_datasource_id="ds_123")
        )

        mock_datasource_service = MagicMock()
        mock_ds = MagicMock()
        mock_ds.enabled = True
        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=mock_ds)

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
            datasource_service=mock_datasource_service,
        )

        mock_get_ip.return_value = "192.168.1.1"

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.query_params = {}

        credentials, user = await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")

        assert isinstance(credentials, AuthCredentials)
        assert isinstance(user, MCPUser)

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_deprecated_scheme(self):
        """测试 MCP Token 认证旧格式 Token scheme（Deprecated，过渡期兼容）"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(user_id="testuser", datasource_ids=["ds_123"], default_datasource_id="ds_123")
        )

        mock_datasource_service = MagicMock()
        mock_ds = MagicMock()
        mock_ds.enabled = True
        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=mock_ds)

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
            datasource_service=mock_datasource_service,
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Token test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.query_params = {}
        conn.client = MagicMock()
        conn.client.host = "192.168.1.1"

        # 通过 authenticate 入口测试，验证旧格式仍被接受但会记录 warning
        credentials, user = await backend.authenticate(conn)

        assert isinstance(credentials, AuthCredentials)
        assert isinstance(user, MCPUser)

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_wrong_scheme(self):
        """测试 MCP Token 认证错误方案（Bearer 但无前缀）"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.query_params = {}
        conn.client = MagicMock()
        conn.client.host = "192.168.1.1"

        # 通过 authenticate 入口测试：Bearer 无前缀在 MCP 路由上应被拒绝
        result = await backend.authenticate(conn)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_datasource_not_found(self):
        """测试 MCP Token 认证数据源不存在"""
        from dm_mcp.core.exceptions.auth_errors import TokenDatasourceNotFoundError

        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(user_id="testuser", datasource_ids=["ds_123"], default_datasource_id="ds_123")
        )

        mock_datasource_service = MagicMock()
        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=None)

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
            datasource_service=mock_datasource_service,
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Token test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.client = MagicMock()
        conn.client.host = "192.168.1.1"

        with pytest.raises(AuthenticationError):
            await backend._authenticate_mcp_token(conn, True)


class TestAuthBackendAuthenticate:
    """authenticate 方法测试"""

    @pytest.mark.asyncio
    async def test_authenticate_non_mcp_route_no_auth(self):
        """测试非 MCP 路由无认证头"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({})
        url = MagicMock(spec=URL)
        url.path = "/api/health"
        conn.url = url

        result = await backend.authenticate(conn)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_bearer_success(self):
        """测试 Bearer 认证成功"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = False

        mock_oauth = MagicMock(spec=OAuthService)
        mock_auth_context = MagicMock(spec=AuthContext)
        mock_auth_context.user_id = "testuser"
        mock_oauth.authenticate_token = MagicMock(return_value=mock_auth_context)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer jwt_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/test"
        conn.url = url
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        credentials, user = await backend.authenticate(conn)

        assert isinstance(credentials, AuthCredentials)
        assert isinstance(user, MCPUser)

    @pytest.mark.asyncio
    async def test_authenticate_bearer_failure(self):
        """测试 Bearer 认证失败"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = False

        mock_oauth = MagicMock(spec=OAuthService)
        mock_oauth.authenticate_token = MagicMock(
            side_effect=Exception("Invalid token")
        )

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer invalid_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/test"
        conn.url = url
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        with pytest.raises(AuthenticationError):
            await backend.authenticate(conn)

    @pytest.mark.asyncio
    async def test_authenticate_no_bearer_scheme(self):
        """测试非 Bearer 认证方案"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = False

        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Basic dXNlcjpwYXNz"})
        url = MagicMock(spec=URL)
        url.path = "/api/test"
        conn.url = url
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        result = await backend.authenticate(conn)

        assert result is None


class TestAuthBackendMCPTokenIPValidation:
    """MCP Token IP 验证测试"""

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_ip_not_allowed(self):
        """测试 MCP Token IP 不在白名单"""
        from dm_mcp.core.exceptions.auth_errors import IpNotAllowedError

        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(
                user_id="testuser",
                datasource_ids=["ds_123"],
                default_datasource_id="ds_123",
                ip_whitelist=["10.0.0.0/24"],
            )
        )

        mock_datasource_service = MagicMock()
        mock_ds = MagicMock()
        mock_ds.enabled = True
        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=mock_ds)

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
            datasource_service=mock_datasource_service,
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.client = MagicMock()
        conn.client.host = "192.168.1.1"

        # IpNotAllowedError 会直接抛出，不会被包装成 AuthenticationError
        with pytest.raises(IpNotAllowedError) as exc_info:
            await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")

        assert "IP 地址" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_ip_blacklisted(self):
        """测试 MCP Token IP 在黑名单中"""
        from dm_mcp.core.exceptions.auth_errors import IpNotAllowedError

        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(
                user_id="testuser",
                datasource_ids=["ds_123"],
                default_datasource_id="ds_123",
                ip_whitelist=["*"],
                ip_blacklist=["192.168.1.0/24"],
            )
        )

        mock_datasource_service = MagicMock()
        mock_ds = MagicMock()
        mock_ds.enabled = True
        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=mock_ds)

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
            datasource_service=mock_datasource_service,
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.client = MagicMock()
        conn.client.host = "192.168.1.100"

        # IpNotAllowedError 会直接抛出，不会被包装成 AuthenticationError
        with pytest.raises(IpNotAllowedError) as exc_info:
            await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")

        assert "IP 地址" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_invalid_error(self):
        """测试 MCP Token 无效错误"""
        from dm_mcp.core.exceptions.auth_errors import InvalidTokenError

        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            side_effect=InvalidTokenError("Invalid token")
        )

        backend = AuthBackend(
            mock_settings, mock_oauth, mock_auth_config_service, token_service=mock_token_service
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url

        with pytest.raises(AuthenticationError) as exc_info:
            await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")

        assert "Invalid token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_expired_error(self):
        """测试 MCP Token 过期错误"""
        from dm_mcp.core.exceptions.auth_errors import TokenExpiredError

        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            side_effect=TokenExpiredError("Token expired")
        )

        backend = AuthBackend(
            mock_settings, mock_oauth, mock_auth_config_service, token_service=mock_token_service
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url

        with pytest.raises(AuthenticationError) as exc_info:
            await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")

        assert "Token expired" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_generic_error(self):
        """测试 MCP Token 通用错误"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            side_effect=RuntimeError("Unexpected error")
        )

        backend = AuthBackend(
            mock_settings, mock_oauth, mock_auth_config_service, token_service=mock_token_service
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url

        with pytest.raises(AuthenticationError) as exc_info:
            await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")

        assert "Token 认证失败" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_datasource_disabled(self):
        """测试 MCP Token 绑定数据源已禁用——认证层不再校验数据源状态"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(user_id="testuser", datasource_ids=["ds_123"], default_datasource_id="ds_123")
        )

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url

        # 认证成功，不再在认证层校验数据源状态
        credentials, user = await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")
        assert "authenticated" in credentials.scopes
        assert isinstance(user, MCPUser)


class TestOnErrorDmMCPError:
    """on_error 方法 DmMCPError 测试"""

    def test_on_error_dm_mcp_error(self):
        """测试 DmMCPError 处理"""
        from dm_mcp.core.exceptions import DmMCPError

        mock_request = MagicMock()
        exc = DmMCPError(
            message="Custom error", error_code="CUSTOM_ERROR", status_code=400
        )

        response = AuthBackend.on_error(mock_request, exc)

        assert response.status_code == 400


class TestExtractAuthInfoQueryString:
    """_extract_auth_info query_string 测试"""

    def test_extract_auth_info_with_query_string(self):
        """测试从 query_string 提取 token"""
        import urllib.parse

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({})
        url = MagicMock(spec=URL)
        url.path = "/api/test"
        conn.url = url
        conn.query_params = {"token": "query_token_123"}
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        auth_info = backend._extract_auth_info(conn)

        assert auth_info["token"] == "query_token_123"

    def test_extract_auth_info_invalid_auth_header_format(self):
        """测试 Authorization 头格式无效（只有 scheme 没有 token）"""
        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer"})  # 只有 scheme，没有 token
        url = MagicMock(spec=URL)
        url.path = "/api/test"
        conn.url = url
        conn.query_params = {}
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        mock_settings = MagicMock()
        mock_oauth = MagicMock(spec=OAuthService)

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)
        auth_info = backend._extract_auth_info(conn)

        assert auth_info["authorization"] == ""
        assert auth_info["token"] == ""


class TestAuthenticateMCPRouteNoTokenService:
    """MCP 路由无 Token 服务的测试"""

    @pytest.mark.asyncio
    async def test_authenticate_mcp_token_no_service(self):
        """测试 MCP Token 认证 - 无 Token 服务"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        # 不提供 token_service

        backend = AuthBackend(mock_settings, mock_oauth, mock_auth_config_service)

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        with pytest.raises(AuthenticationError) as exc_info:
            await backend._authenticate_mcp_token(conn, "sk-dmmcp-test_token")

        assert "Token 服务不可用" in str(exc_info.value)


class TestAuthenticateMCPRouteViaMain:
    """通过 authenticate 方法测试 MCP 路由分支"""

    @pytest.mark.asyncio
    async def test_authenticate_mcp_route_bearer_prefix(self):
        """测试 MCP 路由 + Bearer sk-dmmcp- 新格式认证"""
        mock_settings = MagicMock()
        mock_settings.server.base_url = "/api"
        mock_auth_config_service.token_auth_enabled = True

        mock_oauth = MagicMock(spec=OAuthService)
        mock_token_service = MagicMock(spec=TokenService)
        mock_token_service.validate_token = AsyncMock(
            return_value=MockTokenConfig(user_id="testuser", datasource_ids=["ds_123"], default_datasource_id="ds_123")
        )

        mock_datasource_service = MagicMock()
        mock_ds = MagicMock()
        mock_ds.enabled = True
        mock_datasource_service.get_datasource_by_id = AsyncMock(return_value=mock_ds)

        backend = AuthBackend(
            mock_settings,
            mock_oauth,
            mock_auth_config_service,
            token_service=mock_token_service,
            datasource_service=mock_datasource_service,
        )

        conn = MagicMock(spec=HTTPConnection)
        conn.headers = Headers({"Authorization": "Bearer sk-dmmcp-test_token"})
        url = MagicMock(spec=URL)
        url.path = "/api/mcp/test"
        conn.url = url
        conn.query_params = {}
        conn.client = MagicMock()
        conn.client.host = "127.0.0.1"

        # 通过 authenticate 方法调用，会触发第88行的分支
        credentials, user = await backend.authenticate(conn)

        assert isinstance(credentials, AuthCredentials)
        assert isinstance(user, MCPUser)
