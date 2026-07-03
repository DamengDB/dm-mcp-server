"""认证相关异常测试"""

import pytest
from dm_mcp.core.exceptions.base_error import DmMCPError
from dm_mcp.core.exceptions.auth_errors import (
    AuthenticationError,
    AuthorizationError,
    TokenExpiredError,
    InvalidTokenError,
    OAuthError,
    IpNotAllowedError,
    TokenDatasourceNotFoundError,
)


class TestAuthenticationError:
    """AuthenticationError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = AuthenticationError()
        assert error.message == "Authentication failed"
        assert error.error_code == "AUTH_FAILED"
        assert error.status_code == 401

    def test_custom_message(self):
        """测试自定义消息"""
        error = AuthenticationError("Custom auth failed")
        assert error.message == "Custom auth failed"

    def test_custom_error_code(self):
        """测试自定义错误码"""
        error = AuthenticationError(error_code="AUTH_CUSTOM")
        assert error.error_code == "AUTH_CUSTOM"

    def test_status_code_always_401(self):
        """测试状态码为401（不会被kwargs覆盖）"""
        error = AuthenticationError()
        assert error.status_code == 401

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(AuthenticationError, DmMCPError)


class TestAuthorizationError:
    """AuthorizationError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = AuthorizationError()
        assert error.message == "Authorization failed"
        assert error.error_code == "AUTH_FORBIDDEN"
        assert error.status_code == 403

    def test_custom_message(self):
        """测试自定义消息"""
        error = AuthorizationError("No permission")
        assert error.message == "No permission"

    def test_status_code_always_403(self):
        """测试状态码为403（不会被kwargs覆盖）"""
        error = AuthorizationError()
        assert error.status_code == 403

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(AuthorizationError, DmMCPError)


class TestTokenExpiredError:
    """TokenExpiredError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = TokenExpiredError()
        assert error.message == "Token expired"
        assert error.error_code == "AUTH_TOKEN_EXPIRED"
        assert error.status_code == 401

    def test_custom_message(self):
        """测试自定义消息"""
        error = TokenExpiredError("Session expired")
        assert error.message == "Session expired"

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(TokenExpiredError, AuthenticationError)


class TestInvalidTokenError:
    """InvalidTokenError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = InvalidTokenError()
        assert error.message == "Invalid token"
        assert error.error_code == "AUTH_INVALID_TOKEN"
        assert error.status_code == 401

    def test_custom_message(self):
        """测试自定义消息"""
        error = InvalidTokenError("Token malformed")
        assert error.message == "Token malformed"

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(InvalidTokenError, AuthenticationError)


class TestOAuthError:
    """OAuthError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = OAuthError("OAuth failed")
        assert error.message == "OAuth failed"
        assert error.error_code == "OAUTH_ERROR"
        assert error.status_code == 401

    def test_with_provider(self):
        """测试带 provider 参数"""
        error = OAuthError("OAuth failed", provider="github")
        assert error.details["provider"] == "github"

    def test_provider_in_details(self):
        """测试 provider 在 details 中"""
        error = OAuthError("test", provider="google")
        assert "provider" in error.details

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(OAuthError, AuthenticationError)


class TestIpNotAllowedError:
    """IpNotAllowedError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = IpNotAllowedError()
        assert error.message == "IP address not allowed"
        assert error.error_code == "IP_NOT_ALLOWED"
        assert error.status_code == 403

    def test_custom_message(self):
        """测试自定义消息"""
        error = IpNotAllowedError("Your IP is blocked")
        assert error.message == "Your IP is blocked"

    def test_inheritance(self):
        """测试继承关系 - 继承自 AuthorizationError"""
        assert issubclass(IpNotAllowedError, AuthorizationError)


class TestTokenDatasourceNotFoundError:
    """TokenDatasourceNotFoundError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = TokenDatasourceNotFoundError()
        assert error.message == "Token datasource not found or unavailable"
        assert error.error_code == "AUTH_TOKEN_DATASOURCE_NOT_FOUND"
        assert error.status_code == 401

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(TokenDatasourceNotFoundError, AuthenticationError)
