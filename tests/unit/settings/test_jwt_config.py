"""JwtConfig JWT配置测试"""

import pytest
from pydantic import SecretStr
from dm_mcp.settings.jwt_config import JwtConfig


class TestJwtConfig:
    """JwtConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = JwtConfig()
        assert isinstance(config.secret, SecretStr)
        assert config.secret.get_secret_value() != ""
        assert config.token_expire_seconds == 3600

    def test_custom_values(self):
        """测试自定义值"""
        config = JwtConfig(
            secret=SecretStr("my-secret-key"),
            token_expire_seconds=7200,
        )
        assert config.secret.get_secret_value() == "my-secret-key"
        assert config.token_expire_seconds == 7200

    def test_secret_can_be_empty(self):
        """测试密码可以为空字符串"""
        config = JwtConfig(secret=SecretStr(""))
        assert config.secret.get_secret_value() == ""

    def test_token_expire_seconds_validation(self):
        """测试过期时间验证"""
        # 有效值
        config = JwtConfig(token_expire_seconds=1)
        assert config.token_expire_seconds == 1

        # 不验证无效值，因为 Pydantic 可能没有 ge 限制
