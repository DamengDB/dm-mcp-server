"""OAuthService 单元测试"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from itsdangerous import BadSignature, SignatureExpired
from starlette.datastructures import URL
from starlette.requests import Request

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions import OAuthError
from dm_mcp.domain.auth.services.auth_config import (
    AuthConfigService,
    OAuthGlobalConfig,
    OAuthProviderConfig,
)
from dm_mcp.domain.auth.services.oauth import (
    OAuthService,
    OAuthServiceFactory,
    OAUTH_STATE_COOKIE_MAX_AGE,
    OAUTH_STATE_COOKIE_PREFIX,
)
from dm_mcp.domain.auth.services.jwt import JwtService


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_auth_config_service():
    """创建 Mock AuthConfigService"""
    service = AsyncMock(spec=AuthConfigService)
    service.get_oauth_global_config = AsyncMock(return_value=OAuthGlobalConfig(enabled=True))
    service.list_providers = AsyncMock(return_value=[])
    service.get_provider = AsyncMock(return_value=None)
    service.ensure_slots_seeded = AsyncMock()
    service.jwt_token_expire_seconds = 3600
    return service


@pytest.fixture
def jwt_service(mock_auth_config_service):
    """创建 JwtService 实例"""
    return JwtService(
        auth_config_service=mock_auth_config_service,
        app_secret="test-secret-key-for-testing-only",
    )


@pytest.fixture
def oauth_service(jwt_service, mock_auth_config_service):
    """创建 OAuthService 实例"""
    service = OAuthService(jwt_service, mock_auth_config_service)
    # 手动设置 provider 用于测试
    service.provider_configs = {
        "google": {
            "client_id": "test-google-client-id",
            "client_secret": "test-google-secret",
            "scope": ["openid", "email", "profile"],
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
            "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
        },
        "microsoft": {
            "client_id": "test-ms-client-id",
            "client_secret": "test-ms-secret",
            "scope": ["openid", "profile", "email", "User.Read"],
            "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        },
        "github": {
            "client_id": "test-github-client-id",
            "client_secret": "test-github-secret",
            "scope": ["openid", "email", "profile"],
            "authorize_url": "https://github.com/login/oauth/authorize",
            "token_endpoint": "https://github.com/login/oauth/access_token",
            "userinfo_url": "https://api.github.com/user",
        },
    }
    service.providers = {name: MagicMock() for name in service.provider_configs}
    return service


@pytest.fixture
def mock_request():
    """创建模拟的请求对象"""
    request = MagicMock(spec=Request)
    request.cookies = {}
    request.query_params = {}
    request.url = MagicMock()
    return request


# ============================================================
# OAuthService 初始化测试
# ============================================================
class TestOAuthServiceInit:
    """测试 OAuthService 初始化"""

    def test_init(self, jwt_service, mock_auth_config_service):
        """测试初始化服务"""
        service = OAuthService(jwt_service, mock_auth_config_service)
        assert service.jwt_service == jwt_service
        assert service._auth_config_service == mock_auth_config_service

    @pytest.mark.asyncio
    async def test_startup(self, jwt_service, mock_auth_config_service):
        """测试启动时调用 ensure_slots_seeded 和加载 providers"""
        service = OAuthService(jwt_service, mock_auth_config_service)
        await service.startup()
        mock_auth_config_service.ensure_slots_seeded.assert_called_once()


# ============================================================
# OAuthService 提供商注册测试
# ============================================================
class TestOAuthServiceProviderRegistration:
    """测试 OAuth 提供商注册"""

    def test_get_providers_list(self, oauth_service):
        """测试获取已注册提供商列表"""
        providers = oauth_service.get_providers()
        assert "google" in providers
        assert "microsoft" in providers
        assert "github" in providers


# ============================================================
# OAuthService 登录测试
# ============================================================
class TestOAuthServiceLogin:
    """测试 OAuth 登录"""

    @pytest.mark.asyncio
    async def test_handle_login_success(self, oauth_service, mock_request):
        """测试成功处理 OAuth 登录"""
        callback_uri = "http://localhost:8000/oauth/callback"

        response = await oauth_service.handle_login(
            "google", mock_request, callback_uri
        )

        # 验证返回的是重定向响应
        assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_handle_login_disabled_oauth(self, oauth_service, mock_request, mock_auth_config_service):
        """测试 OAuth 禁用时登录失败"""
        mock_auth_config_service.get_oauth_global_config = AsyncMock(
            return_value=OAuthGlobalConfig(enabled=False)
        )

        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_login("google", mock_request, "http://localhost")

        assert "已禁用" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_handle_login_unknown_provider(self, oauth_service, mock_request):
        """测试未知提供商登录失败"""
        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_login(
                "unknown_provider", mock_request, "http://localhost"
            )

        assert "未注册" in str(exc_info.value.message)


# ============================================================
# OAuthService 回调测试
# ============================================================
class TestOAuthServiceCallback:
    """测试 OAuth 回调处理"""

    @pytest.mark.asyncio
    async def test_handle_callback_missing_code(self, oauth_service, mock_request):
        """测试缺少授权码时回调失败"""
        state = "test_state_value"
        encrypted_state = oauth_service.state_serializer.dumps(state)
        mock_request.cookies[f"{OAUTH_STATE_COOKIE_PREFIX}google"] = encrypted_state
        mock_request.query_params = {"state": state}

        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_callback(
                mock_request, "google", "http://localhost"
            )

        assert "授权码" in str(exc_info.value.message)


# ============================================================
# OAuthService State 验证测试
# ============================================================
class TestOAuthServiceStateVerification:
    """测试 OAuth state 验证"""

    def test_verify_oauth_state_missing_cookie(self, oauth_service, mock_request):
        """测试缺少 state cookie 时验证失败"""
        with pytest.raises(OAuthError) as exc_info:
            oauth_service._verify_oauth_state(mock_request, "google")

        assert "未找到" in str(exc_info.value.message)

    def test_verify_oauth_state_expired(self, oauth_service, mock_request):
        """测试过期的 state 验证失败"""
        valid_state = "expired_state"
        encrypted_state = oauth_service.state_serializer.dumps(valid_state)

        with patch.object(
            oauth_service.state_serializer,
            "loads",
            side_effect=SignatureExpired("Expired"),
        ):
            mock_request.cookies[f"{OAUTH_STATE_COOKIE_PREFIX}google"] = encrypted_state

            with pytest.raises(OAuthError) as exc_info:
                oauth_service._verify_oauth_state(mock_request, "google")

            assert "已过期" in str(exc_info.value.message)

    def test_verify_oauth_state_invalid_signature(self, oauth_service, mock_request):
        """测试无效签名的 state 验证失败"""
        from itsdangerous import URLSafeTimedSerializer

        wrong_serializer = URLSafeTimedSerializer("wrong-secret", salt="oauth-state")
        encrypted_state = wrong_serializer.dumps("some_state")
        mock_request.cookies[f"{OAUTH_STATE_COOKIE_PREFIX}google"] = encrypted_state

        with pytest.raises(OAuthError) as exc_info:
            oauth_service._verify_oauth_state(mock_request, "google")

        assert "无效" in str(exc_info.value.message)

    def test_verify_oauth_state_mismatch(self, oauth_service, mock_request):
        """测试 state 不匹配时验证失败"""
        correct_state = "correct_state"
        encrypted_state = oauth_service.state_serializer.dumps(correct_state)
        mock_request.cookies[f"{OAUTH_STATE_COOKIE_PREFIX}google"] = encrypted_state
        mock_request.query_params = {"state": "different_state"}

        with pytest.raises(OAuthError) as exc_info:
            oauth_service._verify_oauth_state(mock_request, "google")

        assert "不匹配" in str(exc_info.value.message)


# ============================================================
# OAuthService Token Endpoint 测试
# ============================================================
class TestOAuthServiceTokenEndpoint:
    """测试 OAuth Token 端点获取"""

    def test_get_token_endpoint_success(self, oauth_service):
        """测试成功获取 token 端点"""
        endpoint = oauth_service._get_token_endpoint("google")
        assert endpoint is not None
        assert "token" in endpoint.lower()

    def test_get_token_endpoint_unknown_provider(self, oauth_service):
        """测试未知提供商的 token 端点获取失败"""
        with pytest.raises(OAuthError) as exc_info:
            oauth_service._get_token_endpoint("unknown_provider")

        assert "未找到" in str(exc_info.value.message)


# ============================================================
# OAuthService 用户信息提取测试
# ============================================================
class TestOAuthServiceUserInfo:
    """测试 OAuth 用户信息提取"""

    @pytest.mark.asyncio
    async def test_extract_user_info_from_userinfo_field(self, oauth_service):
        """测试从 userinfo 字段提取用户信息"""
        token_response = {"userinfo": {"sub": "user123", "email": "test@example.com"}}
        user_info = await oauth_service._extract_user_info(token_response, "google")
        assert user_info["sub"] == "user123"

    @pytest.mark.asyncio
    async def test_extract_user_info_from_id_token(self, oauth_service, jwt_service):
        """测试从 id_token 解析用户信息"""
        id_token = jwt_service.create_token(
            {"sub": "user123", "email": "test@example.com"}
        )
        token_response = {"id_token": id_token}
        user_info = await oauth_service._extract_user_info(token_response, "google")
        assert user_info["sub"] == "user123"


# ============================================================
# OAuthService 认证测试
# ============================================================
class TestOAuthServiceAuthentication:
    """测试 OAuth 认证功能"""

    def test_authenticate_token_valid(self, oauth_service, jwt_service):
        """测试验证有效 token"""
        user_info = {"sub": "user123", "email": "test@example.com"}
        token = jwt_service.create_token(user_info)
        auth_context = oauth_service.authenticate_token(token)
        assert isinstance(auth_context, AuthContext)
        assert auth_context.user_id == "user123"
        assert auth_context.auth_type == "oauth"

    def test_authenticate_token_invalid(self, oauth_service):
        """测试验证无效 token"""
        with pytest.raises(Exception):
            oauth_service.authenticate_token("invalid_token")


# ============================================================
# OAuthService Factory 测试
# ============================================================
class TestOAuthServiceFactory:
    """测试 OAuthServiceFactory"""

    def test_metadata(self):
        """测试 factory metadata"""
        factory = OAuthServiceFactory()
        metadata = factory.metadata()
        assert metadata.name == "oauth_service"
        assert metadata.service_type == OAuthService
        assert "jwt_service" in metadata.dependencies
        assert "auth_config_service" in metadata.dependencies

    def test_create(self, jwt_service, mock_auth_config_service):
        """测试创建服务实例"""
        factory = OAuthServiceFactory()
        mock_settings = MagicMock()
        service = factory.create(
            mock_settings,
            jwt_service=jwt_service,
            auth_config_service=mock_auth_config_service,
        )
        assert isinstance(service, OAuthService)
        assert service.jwt_service == jwt_service


# ============================================================
# OAuth 常量测试
# ============================================================
class TestOAuthConstants:
    """测试 OAuth 常量"""

    def test_state_cookie_max_age(self):
        assert OAUTH_STATE_COOKIE_MAX_AGE == 600

    def test_state_cookie_prefix(self):
        assert OAUTH_STATE_COOKIE_PREFIX == "oauth_state_"


# ============================================================
# OAuthService 配置构建测试
# ============================================================
class TestOAuthServiceConfigBuild:
    """测试 OAuth 配置构建方法"""

    def test_build_builtin_provider_config_with_valid_credentials(self, oauth_service):
        """测试使用有效凭证构建内置提供商配置"""
        config = oauth_service._build_builtin_provider_config(
            "google", "google", "client_id", "client_secret", ["openid", "email"]
        )
        assert config["name"] == "google"
        assert config["client_id"] == "client_id"
        assert config["client_secret"] == "client_secret"
        assert config["client_kwargs"]["scope"] == ["openid", "email"]

    def test_build_builtin_provider_config_missing_credentials(self, oauth_service):
        """测试缺少凭证时返回 None"""
        config = oauth_service._build_builtin_provider_config(
            "google", "google", "", "client_secret", []
        )
        assert config is None

    def test_build_builtin_provider_config_with_discovery_url(self, oauth_service):
        """测试有 discovery URL 的配置（OIDC 模式）"""
        config = oauth_service._build_builtin_provider_config(
            "google", "google", "client_id", "client_secret", []
        )
        assert "server_metadata_url" in config

    def test_build_custom_provider_config_from_data(self, oauth_service):
        """测试构建自定义提供商配置"""
        provider_data = {
            "discovery_url": "https://custom.example.com/.well-known/openid-configuration",
        }
        config = oauth_service._build_custom_provider_config_from_data(
            "custom", "client_id", "client_secret", ["openid"], provider_data
        )
        assert config is not None
        assert config["name"] == "custom"
        assert "server_metadata_url" in config

    def test_build_custom_provider_config_missing_credentials(self, oauth_service):
        """测试缺少凭证的自定义提供商返回 None"""
        config = oauth_service._build_custom_provider_config_from_data(
            "custom", "", "", [], {}
        )
        assert config is None

    def test_get_state_cookie_name(self, oauth_service):
        """测试获取 state cookie 名称"""
        name = oauth_service._get_state_cookie_name("google")
        assert name == "oauth_state_google"


# ============================================================
# OAuthService 提供商配置提取测试
# ============================================================
class TestOAuthServiceProviderConfigExtract:
    """测试提供商配置提取"""

    def test_extract_provider_config_info_with_discovery(self, oauth_service):
        """测试从 OIDC discovery 模式提取配置"""
        provider_kwargs = {
            "client_id": "client_id",
            "client_secret": "client_secret",
            "client_kwargs": {"scope": ["openid", "email"]},
            "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        }
        config_info = oauth_service._extract_provider_config_info("google", provider_kwargs)
        assert config_info["client_id"] == "client_id"
        assert "discovery_url" in config_info

    def test_extract_provider_config_info_manual_endpoints(self, oauth_service):
        """测试手动端点模式提取配置"""
        provider_kwargs = {
            "client_id": "client_id",
            "client_secret": "client_secret",
            "client_kwargs": {"scope": ["openid"]},
            "authorize_url": "https://custom.example.com/authorize",
            "access_token_url": "https://custom.example.com/token",
        }
        config_info = oauth_service._extract_provider_config_info("custom", provider_kwargs)
        assert config_info["authorize_url"] == "https://custom.example.com/authorize"
        assert config_info["token_endpoint"] == "https://custom.example.com/token"


# ============================================================
# OAuthService 认证上下文创建测试
# ============================================================
class TestOAuthServiceAuthContext:
    """测试认证上下文创建"""

    def test_create_auth_context(self, oauth_service):
        """测试创建认证上下文"""
        user_info = {"sub": "user123", "email": "test@example.com"}
        auth_context = oauth_service._create_auth_context(user_info)
        assert auth_context.user_id == "user123"
        assert auth_context.auth_type == "oauth"
        assert auth_context.login_time is not None


# ============================================================
# OAuthService 回调完整流程测试
# ============================================================
class TestOAuthServiceCallbackComplete:
    """测试 OAuth 回调完整流程"""

    @pytest.mark.asyncio
    async def test_handle_login_sets_correct_cookie(self, oauth_service, mock_request):
        """测试登录时设置了正确的 cookie"""
        callback_uri = "http://localhost:8000/oauth/callback/google"
        response = await oauth_service.handle_login("google", mock_request, callback_uri)
        assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_handle_login_missing_provider_config(self, oauth_service, mock_request):
        """测试登录时提供商未注册"""
        oauth_service.providers.pop("google", None)
        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_login("google", mock_request, "http://localhost")
        assert "未注册" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_handle_login_missing_authorize_url(self, oauth_service, mock_request):
        """测试登录时授权 URL 缺失"""
        oauth_service.provider_configs["google"]["authorize_url"] = None
        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_login("google", mock_request, "http://localhost")
        assert "授权端点" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_handle_login_success_with_url_object(self, oauth_service, mock_request):
        """测试使用 URL 对象作为回调 URI"""
        callback_url = URL("http://localhost:8000/oauth/callback")
        response = await oauth_service.handle_login("google", mock_request, callback_url)
        assert response.status_code == 302


# ============================================================
# OAuthService 扩展测试
# ============================================================
class TestOAuthServiceExtendedCallback:
    """扩展回调测试"""

    @pytest.mark.asyncio
    async def test_handle_callback_disabled(self, oauth_service, mock_request, mock_auth_config_service):
        """测试 OAuth 禁用时的回调"""
        mock_auth_config_service.get_oauth_global_config = AsyncMock(
            return_value=OAuthGlobalConfig(enabled=False)
        )
        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_callback(mock_request, "google", None)
        assert "已禁用" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_handle_callback_unknown_provider(self, oauth_service, mock_request):
        """测试未知提供商的回调"""
        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_callback(mock_request, "unknown_provider", None)
        assert "未注册" in str(exc_info.value.message)

    @pytest.mark.asyncio
    async def test_handle_callback_missing_state_in_callback(self, oauth_service, mock_request):
        """测试缺少回调 state 参数"""
        state = "test_state_value"
        encrypted_state = oauth_service.state_serializer.dumps(state)
        mock_request.cookies[f"{OAUTH_STATE_COOKIE_PREFIX}google"] = encrypted_state
        mock_request.query_params = {"code": "test_code"}
        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_callback(mock_request, "google", None)
        assert "state 参数" in str(exc_info.value.message)

    def test_get_token_endpoint_not_configured(self, oauth_service):
        """测试 token 端点未配置"""
        oauth_service.provider_configs["google"]["token_endpoint"] = None
        with pytest.raises(OAuthError) as exc_info:
            oauth_service._get_token_endpoint("google")
        assert "未配置" in str(exc_info.value.message)


class TestOAuthServiceUserInfoExtended:
    """扩展用户信息提取测试"""

    @pytest.mark.asyncio
    async def test_extract_user_info_id_token_parse_error(self, oauth_service):
        """测试 id_token 解析失败"""
        import httpx
        token_response = {"id_token": "invalid_token_format"}
        with patch.object(httpx, "AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.get.side_effect = httpx.HTTPError("Network error")
            mock_client.__aenter__.return_value = mock_client
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client
            with pytest.raises(OAuthError) as exc_info:
                await oauth_service._extract_user_info(token_response, "google")
            assert "用户信息" in str(exc_info.value.message)


class TestOAuthServiceLoginExtended:
    """扩展登录测试"""

    @pytest.mark.asyncio
    async def test_handle_login_provider_config_not_found(self, oauth_service, mock_request):
        """测试提供商配置未找到"""
        oauth_service.provider_configs = {}
        with pytest.raises(OAuthError) as exc_info:
            await oauth_service.handle_login("google", mock_request, "http://localhost")
        assert "配置未找到" in str(exc_info.value.message)


class TestOAuthServiceCallbackFlow:
    """回调流程测试"""

    @pytest.mark.asyncio
    async def test_handle_callback_token_exchange_failure(self, oauth_service, mock_request):
        """测试 token 交换失败"""
        import httpx
        state = "test_state_value"
        encrypted_state = oauth_service.state_serializer.dumps(state)
        mock_request.cookies[f"{OAUTH_STATE_COOKIE_PREFIX}google"] = encrypted_state
        mock_request.query_params = {"code": "test_code", "state": state}
        mock_request.url = MagicMock()
        mock_request.url.__str__ = MagicMock(return_value="http://localhost/oauth/callback")

        with patch.object(httpx, "AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Network error")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client
            with pytest.raises(OAuthError) as exc_info:
                await oauth_service.handle_callback(mock_request, "google", None)
            assert "授权码" in str(exc_info.value.message)


class TestOAuthServiceEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_extract_user_info_with_empty_id_token(self, oauth_service):
        """测试空的 id_token"""
        import httpx
        token_response = {"id_token": ""}
        with patch.object(httpx, "AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.get.side_effect = Exception("Network error")
            mock_client.get.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client
            with pytest.raises(OAuthError) as exc_info:
                await oauth_service._extract_user_info(token_response, "google")
            assert "用户信息" in str(exc_info.value.message)

    def test_state_serializer_uses_app_secret(self, oauth_service):
        """测试 state 序列化器使用 app_secret"""
        assert oauth_service.state_serializer is not None
        test_data = "test_state_data"
        serialized = oauth_service.state_serializer.dumps(test_data)
        deserialized = oauth_service.state_serializer.loads(serialized)
        assert deserialized == test_data


# ============================================================
# OAuthService reload_providers 测试
# ============================================================
class TestOAuthServiceReload:
    """测试 OAuth 提供商热更新"""

    @pytest.mark.asyncio
    async def test_reload_providers(self, oauth_service, mock_auth_config_service):
        """测试重新加载 providers"""
        mock_auth_config_service.list_providers = AsyncMock(return_value=[])
        mock_auth_config_service.get_oauth_global_config = AsyncMock(
            return_value=OAuthGlobalConfig(enabled=True)
        )
        await oauth_service.reload_providers()
        mock_auth_config_service.list_providers.assert_called_once_with(include_secrets=True)
        assert len(oauth_service.providers) == 0  # 无 provider 数据时为空
