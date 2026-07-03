"""TokenService 单元测试"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from dm_mcp.core.db import TokenModel
from dm_mcp.core.exceptions.auth_errors import InvalidTokenError, TokenExpiredError
from dm_mcp.services.token_service import TokenService, TokenServiceFactory
from dm_mcp.settings import Settings
from dm_mcp.settings.database_config import DatabaseConfig
from dm_mcp.settings.datasource_config import DataSourcesConfig
from dm_mcp.settings.jwt_config import JwtConfig
from dm_mcp.settings.logging_config import LoggingConfig
from dm_mcp.settings.metrics_config import MetricsConfig
from dm_mcp.settings.oauth_config import OAuthConfig
from dm_mcp.settings.pool_config import DmPoolConfig
from dm_mcp.settings.server_config import ServerConfig
from dm_mcp.settings.token_auth_config import TokenAuthConfig, TokenConfig


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_settings():
    """创建测试用 Settings"""
    settings = MagicMock(spec=Settings)
    settings.database = DatabaseConfig()
    settings.token_auth = TokenAuthConfig(
        enabled=True,
        default_expires_in=3600,
        auto_cleanup=True,
        cleanup_interval=3600,
    )
    return settings


@pytest.fixture
def sample_token_config():
    """创建测试用 TokenConfig"""
    now = datetime.now(timezone.utc)
    return TokenConfig(
        token="test_token_12345678",
        user_id="user123",
        datasource_id=uuid.uuid4(),
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_used_at=now,
        description="Test token",
        metadata={},
        ip_whitelist=None,
        ip_blacklist=None,
    )


@pytest.fixture
def sample_token_model(sample_token_config):
    """创建测试用 TokenModel"""
    return TokenModel(
        token=sample_token_config.token,
        user_id=sample_token_config.user_id,
        datasource_id=sample_token_config.datasource_id,
        created_at=sample_token_config.created_at,
        expires_at=sample_token_config.expires_at,
        last_used_at=sample_token_config.last_used_at,
        description=sample_token_config.description,
        token_metadata=json.dumps(sample_token_config.metadata),
    )


# ============================================================
# TokenService 生命周期测试
# ============================================================
class TestTokenServiceLifecycle:
    """测试服务生命周期"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.init_db")
    @patch("dm_mcp.services.token_service.create_tables", new_callable=AsyncMock)
    @patch("dm_mcp.services.token_service.close_db", new_callable=AsyncMock)
    async def test_startup(
        self, mock_close_db, mock_create_tables, mock_init_db, mock_settings
    ):
        """测试服务启动"""
        service = TokenService(mock_settings)
        await service.startup()

        # 验证数据库初始化被调用
        mock_init_db.assert_called_once()
        mock_create_tables.assert_called_once()

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.init_db")
    @patch("dm_mcp.services.token_service.create_tables", new_callable=AsyncMock)
    @patch("dm_mcp.services.token_service.close_db", new_callable=AsyncMock)
    async def test_shutdown(
        self, mock_close_db, mock_create_tables, mock_init_db, mock_settings
    ):
        """测试服务关闭"""
        service = TokenService(mock_settings)

        # 先启动服务
        await service.startup()

        # 关闭服务
        await service.shutdown()

        # 验证关闭被调用
        mock_close_db.assert_called_once()


# ============================================================
# TokenService CRUD 测试
# ============================================================
def create_mock_session_context(mock_result):
    """创建模拟的会话上下文"""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    return mock_context


class TestTokenServiceCRUD:
    """测试 Token CRUD 操作"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_create_token(self, mock_get_session, mock_settings):
        """测试创建 Token"""
        service = TokenService(mock_settings)
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        datasource_id = uuid.uuid4()
        token_config = await service.create_token(
            user_id="user123",
            datasource_id=datasource_id,
            expires_in=3600,
            description="Test token",
        )

        assert token_config.user_id == "user123"
        assert token_config.datasource_id == datasource_id
        assert token_config.description == "Test token"

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_list_tokens(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试列出所有 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_token_model]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        tokens = await service.list_tokens()

        assert len(tokens) == 1
        assert tokens[0].token == sample_token_model.token

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_list_tokens_by_user(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试按用户列出 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_token_model]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        tokens = await service.list_tokens(user_id="user123")

        assert len(tokens) == 1

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_get_token(self, mock_get_session, mock_settings, sample_token_model):
        """测试获取单个 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = await service.get_token(sample_token_model.token)

        assert token is not None
        assert token.token == sample_token_model.token

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_get_token_not_found(self, mock_get_session, mock_settings):
        """测试获取不存在的 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = await service.get_token("nonexistent_token")

        assert token is None

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_update_token(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试更新 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        new_description = "Updated description"
        token = await service.update_token(
            sample_token_model.token, description=new_description
        )

        assert token.description == new_description

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_delete_token(self, mock_get_session, mock_settings):
        """测试删除 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "deleted_token"
        mock_get_session.return_value = create_mock_session_context(mock_result)

        # 不应该抛出异常
        await service.delete_token("test_token")


# ============================================================
# TokenService 验证测试
# ============================================================
class TestTokenServiceValidation:
    """测试 Token 验证"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_validate_token_success(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试验证有效 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token_config = await service.validate_token(sample_token_model.token)

        assert token_config.token == sample_token_model.token

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_validate_token_not_found(self, mock_get_session, mock_settings):
        """测试验证不存在的 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(InvalidTokenError):
            await service.validate_token("nonexistent_token")

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_validate_token_expired(self, mock_get_session, mock_settings):
        """测试验证过期 Token"""
        service = TokenService(mock_settings)

        # 创建一个已过期的 TokenModel
        now = datetime.now(timezone.utc)
        expired_model = TokenModel(
            token="expired_token",
            user_id="user123",
            datasource_id=uuid.uuid4(),
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),  # 已过期
            last_used_at=now,
            description="Expired token",
            token_metadata="{}",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expired_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(TokenExpiredError):
            await service.validate_token("expired_token")


# ============================================================
# TokenService 清理测试
# ============================================================
class TestTokenServiceCleanup:
    """测试 Token 清理"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_cleanup_expired_tokens(self, mock_get_session, mock_settings):
        """测试清理过期 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["token1", "token2"]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        count = await service.cleanup_expired_tokens()

        assert count == 2


# ============================================================
# IP 地址验证测试
# ============================================================
class TestIPValidation:
    """测试 IP 地址验证"""

    def test_is_ip_allowed_no_list(self):
        """测试没有黑白名单时允许访问"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._is_ip_allowed("192.168.1.100", None, None)
        assert result is True

    def test_is_ip_allowed_whitelist_match(self):
        """测试白名单匹配"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._is_ip_allowed(
            "192.168.1.100", ["192.168.1.0/24", "10.0.0.1"], None
        )
        assert result is True

    def test_is_ip_allowed_whitelist_no_match(self):
        """测试白名单不匹配"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._is_ip_allowed("192.168.2.100", ["192.168.1.0/24"], None)
        assert result is False

    def test_is_ip_allowed_blacklist_match(self):
        """测试黑名单匹配"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._is_ip_allowed("192.168.1.100", None, ["192.168.1.100"])
        assert result is False

    def test_is_ip_allowed_blacklist_priority(self):
        """测试黑名单优先于白名单"""
        from dm_mcp.services.token_service import TokenService

        # 同一个 IP 同时在白名单和黑名单中，应该被拒绝
        result = TokenService._is_ip_allowed(
            "192.168.1.100", ["192.168.1.100"], ["192.168.1.100"]
        )
        assert result is False

    def test_ip_matches_exact(self):
        """测试精确 IP 匹配"""
        from dm_mcp.services.token_service import TokenService

        assert TokenService._ip_matches("192.168.1.100", "192.168.1.100") is True
        assert TokenService._ip_matches("192.168.1.100", "192.168.1.101") is False

    def test_ip_matches_cidr(self):
        """测试 CIDR 网段匹配"""
        from dm_mcp.services.token_service import TokenService

        assert TokenService._ip_matches("192.168.1.100", "192.168.1.0/24") is True
        assert TokenService._ip_matches("192.168.2.100", "192.168.1.0/24") is False


# ============================================================
# TokenServiceFactory 测试
# ============================================================
class TestTokenServiceFactory:
    """测试 TokenServiceFactory"""

    def test_metadata(self):
        """测试 factory metadata"""
        factory = TokenServiceFactory()
        metadata = factory.metadata()

        assert metadata.name == "token_service"
        assert metadata.service_type == TokenService

    def test_create(self, mock_settings):
        """测试创建服务实例"""
        factory = TokenServiceFactory()
        service = factory.create(mock_settings)

        assert isinstance(service, TokenService)
        assert service.settings == mock_settings


# ============================================================
# 工具方法测试
# ============================================================
class TestTokenServiceHelperMethods:
    """测试辅助方法"""

    def test_ensure_aware_datetime_naive(self):
        """测试转换 naive datetime 为 aware"""
        from dm_mcp.services.token_service import TokenService

        naive_dt = datetime(2020, 1, 1, 12, 0, 0)
        result = TokenService._ensure_aware_datetime(naive_dt)

        assert result.tzinfo is not None

    def test_ensure_aware_datetime_aware(self):
        """测试 aware datetime 保持不变"""
        from dm_mcp.services.token_service import TokenService

        aware_dt = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = TokenService._ensure_aware_datetime(aware_dt)

        assert result == aware_dt

    def test_ensure_aware_datetime_none(self):
        """测试 None 返回 None"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._ensure_aware_datetime(None)

        assert result is None

    def test_ensure_aware_datetime_required_naive(self):
        """测试 _ensure_aware_datetime_required 转换 naive datetime"""
        from dm_mcp.services.token_service import TokenService

        naive_dt = datetime(2020, 1, 1, 12, 0, 0)
        result = TokenService._ensure_aware_datetime_required(naive_dt)

        assert result.tzinfo is not None

    def test_ensure_aware_datetime_required_aware(self):
        """测试 _ensure_aware_datetime_required 保持 aware datetime 不变"""
        from dm_mcp.services.token_service import TokenService

        aware_dt = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = TokenService._ensure_aware_datetime_required(aware_dt)

        assert result == aware_dt


# ============================================================
# TokenService 缓存测试
# ============================================================
class TestTokenServiceCache:
    """测试 Token 缓存机制"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_validate_token_cache_hit(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试缓存命中"""
        service = TokenService(mock_settings)
        # 先从数据库获取，建立缓存
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = sample_token_model.token
        # 第一次调用，缓存未命中
        await service.validate_token(token)

        # 第二次调用，缓存应该命中
        now = datetime.now(timezone.utc)
        # 设置缓存时间在 TTL 内
        service._token_cache[token] = (
            service._model_to_config(sample_token_model),
            now - timedelta(seconds=60),  # 60秒前，TTL 300秒内
        )

        # 由于缓存存在，不会调用数据库
        mock_get_session.reset_mock()
        result = await service.validate_token(token)
        assert result is not None

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_validate_token_cache_expired(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试缓存过期"""
        service = TokenService(mock_settings)

        token = sample_token_model.token
        # 设置过期的缓存
        now = datetime.now(timezone.utc)
        service._token_cache[token] = (
            service._model_to_config(sample_token_model),
            now - timedelta(seconds=400),  # 超过 300 秒 TTL
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        result = await service.validate_token(token)
        assert result is not None


# ============================================================
# TokenService IP 白名单/黑名单测试
# ============================================================
class TestTokenServiceIPWhitelist:
    """测试 Token IP 白名单/黑名单"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_create_token_with_ip_whitelist(
        self, mock_get_session, mock_settings
    ):
        """测试创建带 IP 白名单的 Token"""
        service = TokenService(mock_settings)
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        datasource_id = uuid.uuid4()
        token_config = await service.create_token(
            user_id="user123",
            datasource_id=datasource_id,
            expires_in=3600,
            description="Test token",
            ip_whitelist=["192.168.1.0/24", "10.0.0.1"],
        )

        assert token_config.ip_whitelist == ["192.168.1.0/24", "10.0.0.1"]

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_create_token_with_ip_blacklist(
        self, mock_get_session, mock_settings
    ):
        """测试创建带 IP 黑名单的 Token"""
        service = TokenService(mock_settings)
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        datasource_id = uuid.uuid4()
        token_config = await service.create_token(
            user_id="user123",
            datasource_id=datasource_id,
            expires_in=3600,
            ip_blacklist=["192.168.1.100"],
        )

        assert token_config.ip_blacklist == ["192.168.1.100"]

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_update_token_with_ip_whitelist(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试更新 Token 的 IP 白名单"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = await service.update_token(
            sample_token_model.token,
            ip_whitelist=["10.0.0.0/8"],
        )

        assert token.ip_whitelist == ["10.0.0.0/8"]

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_update_token_with_both_ip_lists(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试同时更新 IP 白名单和黑名单"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = await service.update_token(
            sample_token_model.token,
            ip_whitelist=["192.168.1.0/24"],
            ip_blacklist=["10.0.0.1"],
        )

        assert token.ip_whitelist == ["192.168.1.0/24"]
        assert token.ip_blacklist == ["10.0.0.1"]


# ============================================================
# TokenService 删除错误测试
# ============================================================
class TestTokenServiceDeleteErrors:
    """测试 Token 删除错误处理"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_delete_token_not_found(self, mock_get_session, mock_settings):
        """测试删除不存在的 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(ValueError) as exc_info:
            await service.delete_token("nonexistent_token")

        assert "not found" in str(exc_info.value).lower()


# ============================================================
# TokenService 更新错误测试
# ============================================================
class TestTokenServiceUpdateErrors:
    """测试 Token 更新错误处理"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_update_token_not_found(self, mock_get_session, mock_settings):
        """测试更新不存在的 Token"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(ValueError) as exc_info:
            await service.update_token("nonexistent_token", description="test")

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_update_token_with_expires_at(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试更新 Token 过期时间"""
        service = TokenService(mock_settings)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        new_expires_at = datetime(2025, 12, 31, 23, 59, 59)
        token = await service.update_token(
            sample_token_model.token,
            expires_at=new_expires_at,
        )

        assert token.expires_at is not None


# ============================================================
# IP 匹配错误处理测试
# ============================================================
class TestIPMatchesErrors:
    """测试 IP 匹配错误处理"""

    def test_ip_matches_invalid_ip(self):
        """测试无效 IP 格式"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._ip_matches("invalid_ip", "192.168.1.1")
        assert result is False

    def test_ip_matches_invalid_pattern(self):
        """测试无效匹配模式"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._ip_matches("192.168.1.1", "invalid_cidr")
        assert result is False

    def test_ip_matches_ipv6(self):
        """测试 IPv6 匹配"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._ip_matches("::1", "::1")
        assert result is True

    def test_ip_matches_ipv6_cidr(self):
        """测试 IPv6 CIDR 匹配"""
        from dm_mcp.services.token_service import TokenService

        result = TokenService._ip_matches("2001:db8::1", "2001:db8::/32")
        assert result is True


# ============================================================
# TokenService 生命周期扩展测试
# ============================================================
class TestTokenServiceLifecycleExtended:
    """扩展生命周期测试"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.init_db")
    @patch("dm_mcp.services.token_service.create_tables", new_callable=AsyncMock)
    @patch("dm_mcp.services.token_service.close_db", new_callable=AsyncMock)
    async def test_startup_without_auto_cleanup(
        self, mock_close_db, mock_create_tables, mock_init_db, mock_settings
    ):
        """测试禁用自动清理时的启动"""
        mock_settings.token_auth.auto_cleanup = False
        service = TokenService(mock_settings)
        await service.startup()

        assert service._cleanup_task is None

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.init_db")
    @patch("dm_mcp.services.token_service.create_tables", new_callable=AsyncMock)
    async def test_shutdown_cancelled_error(
        self, mock_create_tables, mock_init_db, mock_settings
    ):
        """测试关闭时取消清理任务"""
        service = TokenService(mock_settings)
        await service.startup()

        # 模拟清理任务已经取消的情况
        if service._cleanup_task:
            service._cleanup_task.cancel()
            try:
                await service._cleanup_task
            except asyncio.CancelledError:
                pass

        await service.shutdown()


# ============================================================
# TokenService 模型转换测试
# ============================================================
class TestTokenServiceModelConversion:
    """测试模型转换"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_model_to_config_with_metadata(self, mock_get_session, mock_settings):
        """测试带 metadata 的模型转换"""
        service = TokenService(mock_settings)

        now = datetime.now(timezone.utc)
        model = TokenModel(
            token="test_token",
            user_id="user123",
            datasource_id=uuid.uuid4(),
            created_at=now,
            expires_at=now + timedelta(hours=1),
            last_used_at=now,
            description="Test",
            token_metadata=json.dumps(
                {
                    "ip_whitelist": ["192.168.1.0/24"],
                    "ip_blacklist": ["10.0.0.1"],
                    "custom_field": "value",
                }
            ),
        )

        config = service._model_to_config(model)

        assert config.ip_whitelist == ["192.168.1.0/24"]
        assert config.ip_blacklist == ["10.0.0.1"]
        assert config.metadata["custom_field"] == "value"


# ============================================================
# TokenService 默认值测试
# ============================================================
class TestTokenServiceDefaults:
    """测试默认值"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.token_service.get_async_session")
    async def test_create_token_default_expires_in(
        self, mock_get_session, mock_settings
    ):
        """测试使用默认过期时间创建 Token"""
        mock_settings.token_auth.default_expires_in = 86400  # 24 小时

        service = TokenService(mock_settings)
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        token_config = await service.create_token(
            user_id="user123",
            datasource_id=uuid.uuid4(),
            # 不指定 expires_in，使用默认值
        )

        # 验证过期时间是 24 小时
        expected_expires = token_config.created_at + timedelta(seconds=86400)
        # 允许 1 秒误差
        assert abs((token_config.expires_at - expected_expires).total_seconds()) < 1
