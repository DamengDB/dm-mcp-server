"""OAuthConfig OAuth配置测试"""

import pytest
from pydantic import SecretStr
from dm_mcp.settings.oauth_config import OAuthConfig


class TestOAuthConfig:
    """OAuthConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = OAuthConfig()
        assert config.enabled is False
        assert config.google_client_id == ""
        assert config.google_client_secret.get_secret_value() == ""
        assert config.microsoft_client_id == ""
        assert config.microsoft_client_secret.get_secret_value() == ""
        assert config.github_client_id == ""
        assert config.github_client_secret.get_secret_value() == ""
        assert config.custom_provider == "custom"
        assert config.custom_client_id == ""
        assert config.custom_scopes == ["openid", "email", "profile"]
        assert config.custom_discovery_url is None

    def test_custom_values(self):
        """测试自定义值"""
        config = OAuthConfig(
            enabled=True,
            google_client_id="google-id",
            google_client_secret=SecretStr("google-secret"),
            custom_discovery_url="https://auth.example.com/.well-known/openid-configuration",
        )
        assert config.enabled is True
        assert config.google_client_id == "google-id"
        assert config.google_client_secret.get_secret_value() == "google-secret"
        assert (
            config.custom_discovery_url
            == "https://auth.example.com/.well-known/openid-configuration"
        )

    def test_empty_config_valid(self):
        """测试空配置是有效的"""
        config = OAuthConfig()
        assert config is not None

    def test_all_providers_empty_valid(self):
        """测试所有 provider 都为空时配置有效"""
        config = OAuthConfig(
            enabled=False,
            google_client_id="",
            microsoft_client_id="",
            github_client_id="",
            custom_client_id="",
        )
        assert config is not None


class TestOAuthConfigValidation:
    """OAuthConfig 验证测试"""

    def test_custom_endpoint_requires_auth_and_token(self):
        """测试手动配置端点时需要授权和 Token 端点"""
        with pytest.raises(ValueError, match="OAuth配置不完整"):
            OAuthConfig(
                custom_authorization_endpoint="https://auth.example.com/authorize",
            )

    def test_custom_endpoint_with_both_valid(self):
        """测试手动配置授权和 Token 端点时有效"""
        config = OAuthConfig(
            custom_authorization_endpoint="https://auth.example.com/authorize",
            custom_token_endpoint="https://auth.example.com/token",
        )
        assert config is not None
        assert (
            config.custom_authorization_endpoint == "https://auth.example.com/authorize"
        )
        assert config.custom_token_endpoint == "https://auth.example.com/token"

    def test_discovery_url_alone_valid(self):
        """测试只有发现 URL 时有效"""
        config = OAuthConfig(
            custom_discovery_url="https://auth.example.com/.well-known/openid-configuration",
        )
        assert config is not None

    def test_partial_manual_config_invalid(self):
        """测试部分手动配置无效"""
        # 只有 userinfo 没有 auth
        with pytest.raises(ValueError):
            OAuthConfig(custom_userinfo_endpoint="https://auth.example.com/userinfo")

    def test_jwks_alone_valid(self):
        """测试只有 JWKS URI 时是否有效"""
        # 这种情况实际上是无效的，因为设置了其他参数但没有 auth 和 token
        with pytest.raises(ValueError):
            OAuthConfig(
                custom_jwks_uri="https://auth.example.com/.well-known/jwks.json"
            )


class TestOAuthConfigScopes:
    """OAuthConfig scopes 测试"""

    def test_default_scopes(self):
        """测试默认 scopes"""
        config = OAuthConfig()
        assert config.custom_scopes == ["openid", "email", "profile"]

    def test_custom_scopes(self):
        """测试自定义 scopes"""
        config = OAuthConfig(custom_scopes=["openid", "profile"])
        assert config.custom_scopes == ["openid", "profile"]

    def test_empty_scopes(self):
        """测试空 scopes"""
        config = OAuthConfig(custom_scopes=[])
        assert config.custom_scopes == []
