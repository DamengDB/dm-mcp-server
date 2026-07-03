"""TokenAuthConfig Token认证配置测试"""

import uuid
import pytest
from datetime import datetime, timedelta, timezone
from dm_mcp.settings.token_auth_config import TokenAuthConfig, TokenConfig


class TestTokenAuthConfig:
    """TokenAuthConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = TokenAuthConfig()
        assert config.enabled is False
        assert config.cleanup_interval == 3600
        assert config.auto_cleanup is True
        assert config.default_expires_in == 604800  # 7天

    def test_custom_values(self):
        """测试自定义值"""
        config = TokenAuthConfig(
            enabled=True,
            cleanup_interval=7200,
            auto_cleanup=False,
            default_expires_in=86400,  # 1天
        )
        assert config.enabled is True
        assert config.cleanup_interval == 7200
        assert config.auto_cleanup is False
        assert config.default_expires_in == 86400

    def test_cleanup_interval_range(self):
        """测试清理间隔范围"""
        # 最小值 60 秒
        config = TokenAuthConfig(cleanup_interval=60)
        assert config.cleanup_interval == 60

    def test_default_expires_in_range(self):
        """测试默认过期时间范围"""
        # 最小值 60 秒
        config = TokenAuthConfig(default_expires_in=60)
        assert config.default_expires_in == 60


class TestTokenConfig:
    """TokenConfig 测试类"""

    def test_required_fields(self):
        """测试必需字段"""
        ds_id = uuid.uuid4()
        token = "test-token"
        user_id = "user1"
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        config = TokenConfig(
            token=token,
            user_id=user_id,
            datasource_id=ds_id,
            expires_at=expires_at,
        )
        assert config.token == token
        assert config.user_id == user_id
        assert config.datasource_id == ds_id
        assert config.expires_at == expires_at

    def test_optional_fields(self):
        """测试可选字段"""
        ds_id = uuid.uuid4()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        config = TokenConfig(
            token="test-token",
            user_id="user1",
            datasource_id=ds_id,
            expires_at=expires_at,
            description="Test token",
            ip_whitelist=["192.168.1.1", "10.0.0.0/8"],
            ip_blacklist=["192.168.1.100"],
        )
        assert config.description == "Test token"
        assert config.ip_whitelist == ["192.168.1.1", "10.0.0.0/8"]
        assert config.ip_blacklist == ["192.168.1.100"]

    def test_default_values(self):
        """测试默认值"""
        ds_id = uuid.uuid4()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        config = TokenConfig(
            token="test-token",
            user_id="user1",
            datasource_id=ds_id,
            expires_at=expires_at,
        )
        assert config.created_at is not None
        assert config.last_used_at is None
        assert config.description is None
        assert config.metadata == {}

    def test_metadata_field(self):
        """测试元数据字段"""
        ds_id = uuid.uuid4()
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        config = TokenConfig(
            token="test-token",
            user_id="user1",
            datasource_id=ds_id,
            expires_at=expires_at,
            metadata={"role": "admin", "scope": ["read", "write"]},
        )
        assert config.metadata["role"] == "admin"
        assert config.metadata["scope"] == ["read", "write"]


class TestTokenConfigValidation:
    """TokenConfig 验证测试"""

    def test_datasource_id_required(self):
        """测试 datasource_id 必需"""
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        with pytest.raises(Exception):
            TokenConfig(
                token="test-token",
                user_id="user1",
                datasource_id=None,
                expires_at=expires_at,
            )

    def test_expires_at_required(self):
        """测试 expires_at 必需"""
        ds_id = uuid.uuid4()

        with pytest.raises(Exception):
            TokenConfig(
                token="test-token",
                user_id="user1",
                datasource_id=ds_id,
                expires_at=None,
            )
