"""JwtService 单元测试"""

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr
from authlib.jose.errors import ExpiredTokenError, JoseError

from dm_mcp.core.exceptions.auth_errors import InvalidTokenError, TokenExpiredError
from dm_mcp.services.jwt_service import JwtService, JwtServiceFactory
from dm_mcp.settings.jwt_config import JwtConfig


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def jwt_config():
    """创建测试用 JwtConfig"""
    return JwtConfig(
        secret=SecretStr("test-secret-key-for-testing-only"),
        token_expire_seconds=3600,
    )


@pytest.fixture
def jwt_service(jwt_config):
    """创建 JwtService 实例"""
    return JwtService(jwt_config)


@pytest.fixture
def valid_user_info():
    """有效的用户信息"""
    return {
        "sub": "user123",
        "username": "testuser",
        "email": "test@example.com",
    }


@pytest.fixture
def expired_token(jwt_service, valid_user_info):
    """创建一个已过期的 token"""
    # 创建一个已经过期的 token
    user_info = valid_user_info.copy()
    # 设置一个很短的过期时间，让 token 立即过期
    with patch("dm_mcp.services.jwt_service.datetime") as mock_datetime:
        # 模拟 token 刚创建时的状态
        now = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mock_datetime.now.return_value = now

        # 创建 token
        token = jwt_service.create_token(user_info, expires_in=-1)
    return token


# ============================================================
# JwtService 方法测试
# ============================================================
class TestJwtServiceCreateToken:
    """测试 create_token 方法"""

    def test_create_token_with_valid_user_info(self, jwt_service, valid_user_info):
        """测试使用有效用户信息创建 token"""
        token = jwt_service.create_token(valid_user_info)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT 格式: header.payload.signature
        assert token.count(".") == 2

    def test_create_token_with_custom_expires_in(self, jwt_service, valid_user_info):
        """测试自定义过期时间"""
        expires_in = 7200  # 2 小时
        token = jwt_service.create_token(valid_user_info, expires_in=expires_in)

        # 解码验证过期时间
        decoded = jwt_service.decode_token(token)
        expected_exp = int(
            (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).timestamp()
        )
        # 允许 5 秒误差
        assert abs(decoded["exp"] - expected_exp) < 5

    def test_create_token_does_not_modify_original_dict(
        self, jwt_service, valid_user_info
    ):
        """测试创建 token 不修改原始字典"""
        original_info = valid_user_info.copy()
        jwt_service.create_token(valid_user_info)
        assert valid_user_info == original_info

    def test_create_token_adds_standard_claims(self, jwt_service, valid_user_info):
        """测试 token 包含标准 claims"""
        token = jwt_service.create_token(valid_user_info)
        decoded = jwt_service.decode_token(token)

        assert "exp" in decoded  # 过期时间
        assert "iat" in decoded  # 签发时间
        assert decoded["sub"] == valid_user_info["sub"]
        assert decoded["username"] == valid_user_info["username"]

    def test_create_token_with_empty_user_info(self, jwt_service):
        """测试使用空用户信息（只有 sub）"""
        user_info = {"sub": "user123"}
        token = jwt_service.create_token(user_info)

        assert token is not None
        decoded = jwt_service.decode_token(token)
        assert decoded["sub"] == "user123"


class TestJwtServiceDecodeToken:
    """测试 decode_token 方法"""

    def test_decode_valid_token(self, jwt_service, valid_user_info):
        """测试解码有效 token"""
        token = jwt_service.create_token(valid_user_info)
        decoded = jwt_service.decode_token(token)

        assert decoded["sub"] == valid_user_info["sub"]
        assert decoded["username"] == valid_user_info["username"]
        assert decoded["email"] == valid_user_info["email"]

    def test_decode_invalid_token(self, jwt_service):
        """测试解码无效 token"""
        invalid_token = "invalid.token.string"

        with pytest.raises(InvalidTokenError):
            jwt_service.decode_token(invalid_token)

    def test_decode_malformed_token(self, jwt_service):
        """测试解码格式错误的 token"""
        malformed_token = "not-a-valid-jwt"

        with pytest.raises(InvalidTokenError):
            jwt_service.decode_token(malformed_token)

    def test_decode_expired_token(self, jwt_service, valid_user_info):
        """测试解码过期 token"""
        # 创建一个已过期的 token
        expired_user_info = valid_user_info.copy()
        # 使用过去的过期时间
        with patch("dm_mcp.services.jwt_service.datetime") as mock_datetime:
            mock_datetime.now.return_value = datetime(2020, 1, 1, tzinfo=timezone.utc)
            token = jwt_service.create_token(expired_user_info, expires_in=-3600)

        with pytest.raises(TokenExpiredError):
            jwt_service.decode_token(token)

    def test_decode_token_with_wrong_secret(self, jwt_service, jwt_config):
        """测试使用错误密钥解码"""
        # 用一个服务创建 token
        token = jwt_service.create_token({"sub": "user123"})

        # 用另一个密钥的服务解码
        wrong_config = JwtConfig(
            secret=SecretStr("wrong-secret-key"),
            token_expire_seconds=3600,
        )
        wrong_service = JwtService(wrong_config)

        with pytest.raises(InvalidTokenError):
            wrong_service.decode_token(token)


class TestJwtServiceParseJwtPayload:
    """测试 parse_jwt_payload 方法"""

    def test_parse_payload_without_verification(self, jwt_service, valid_user_info):
        """测试不验证签名解析 payload"""
        token = jwt_service.create_token(valid_user_info)
        payload = jwt_service.parse_jwt_payload(token, verify_signature=False)

        assert payload["sub"] == valid_user_info["sub"]
        assert payload["username"] == valid_user_info["username"]

    def test_parse_payload_with_verification(self, jwt_service, valid_user_info):
        """测试验证签名解析 payload"""
        token = jwt_service.create_token(valid_user_info)
        payload = jwt_service.parse_jwt_payload(token, verify_signature=True)

        assert payload["sub"] == valid_user_info["sub"]

    def test_parse_payload_invalid_format(self, jwt_service):
        """测试解析格式错误的 JWT"""
        invalid_token = "invalid.format"

        with pytest.raises(InvalidTokenError):
            jwt_service.parse_jwt_payload(invalid_token, verify_signature=False)

    def test_parse_payload_with_wrong_secret_and_verification(
        self, jwt_service, jwt_config
    ):
        """测试验证签名时使用错误密钥"""
        token = jwt_service.create_token({"sub": "user123"})

        wrong_config = JwtConfig(
            secret=SecretStr("wrong-secret-key"),
            token_expire_seconds=3600,
        )
        wrong_service = JwtService(wrong_config)

        with pytest.raises(InvalidTokenError):
            wrong_service.parse_jwt_payload(token, verify_signature=True)


class TestJwtServiceEdgeCases:
    """边界情况测试"""

    def test_create_token_with_unicode_characters(self, jwt_service):
        """测试包含 Unicode 字符的用户信息"""
        user_info = {
            "sub": "用户123",
            "username": "测试用户",
            "email": "test@example.com",
        }
        token = jwt_service.create_token(user_info)
        decoded = jwt_service.decode_token(token)

        assert decoded["sub"] == "用户123"
        assert decoded["username"] == "测试用户"

    def test_create_token_with_special_characters(self, jwt_service):
        """测试包含特殊字符的用户信息"""
        user_info = {
            "sub": "user@example.com",
            "username": "user:name|test",
            "email": "test@example.com",
        }
        token = jwt_service.create_token(user_info)
        decoded = jwt_service.decode_token(token)

        assert decoded["sub"] == "user@example.com"
        assert decoded["username"] == "user:name|test"

    def test_decode_token_with_additional_claims(self, jwt_service):
        """测试解码包含额外 claims 的 token"""
        user_info = {
            "sub": "user123",
            "roles": ["admin", "user"],
            "permissions": ["read", "write"],
        }
        token = jwt_service.create_token(user_info)
        decoded = jwt_service.decode_token(token)

        assert decoded["roles"] == ["admin", "user"]
        assert decoded["permissions"] == ["read", "write"]

    def test_create_token_with_default_expiration(self, jwt_service, valid_user_info):
        """测试使用默认过期时间创建 token"""
        token = jwt_service.create_token(valid_user_info)

        assert token is not None
        decoded = jwt_service.decode_token(token)
        # 验证默认过期时间（约1小时，从 jwt_config 来）
        expected_exp = int(
            (datetime.now(timezone.utc) + timedelta(seconds=3600)).timestamp()
        )
        # 允许 5 秒误差
        assert abs(decoded["exp"] - expected_exp) < 5


# ============================================================
# JwtServiceFactory 测试
# ============================================================
class TestJwtServiceFactory:
    """测试 JwtServiceFactory"""

    def test_metadata(self):
        """测试 factory metadata"""
        factory = JwtServiceFactory()
        metadata = factory.metadata()

        assert metadata.name == "jwt_service"
        assert metadata.service_type == JwtService
        assert "JWT" in metadata.description

    def test_create(self, jwt_config):
        """测试创建服务实例"""
        factory = JwtServiceFactory()
        # Mock settings 对象
        mock_settings = MagicMock()
        mock_settings.jwt = jwt_config

        service = factory.create(mock_settings)

        assert isinstance(service, JwtService)
        assert service.jwt_config == jwt_config


# ============================================================
# 测试辅助函数
# ============================================================
class TestJwtServiceHelperFunctions:
    """测试辅助功能"""

    def test_token_format(self, jwt_service, valid_user_info):
        """测试 token 格式"""
        token = jwt_service.create_token(valid_user_info)

        # JWT 应该有三部分，用 . 分隔
        parts = token.split(".")
        assert len(parts) == 3
        # 每部分应该是 base64 编码
        for part in parts:
            assert part  # 不为空
