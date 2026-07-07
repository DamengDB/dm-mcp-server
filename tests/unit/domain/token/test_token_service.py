"""TokenService 单元测试"""

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from dm_mcp.infra.persistence import TokenModel
from dm_mcp.core.exceptions.auth_errors import InvalidTokenError, TokenExpiredError
from dm_mcp.domain.token.events import TokenRevoked
from dm_mcp.domain.token.services.token import TokenService, TokenServiceFactory
from dm_mcp.infra.config import Settings
from dm_mcp.infra.config.database_config import DatabaseConfig

from tests.conftest import FakeEventService
from dm_mcp.infra.config.logging_config import LoggingConfig
from dm_mcp.infra.config.metrics_config import MetricsConfig
from dm_mcp.infra.persistence.pool_config import DmPoolConfig
from dm_mcp.infra.config.server_config import ServerConfig
from dm_mcp.infra.config.token_auth_config import TokenConfig


# ============================================================
# Fixtures
# ============================================================
def _make_mock_auth_config_service():
    """创建测试用 AuthConfigService"""
    service = MagicMock()
    service.token_auth_enabled = True
    service.token_auth_default_expires_in = 3600
    service.token_auth_auto_cleanup = True
    service.token_auth_cleanup_interval = 3600
    return service


@pytest.fixture
def mock_settings():
    """创建测试用 Settings"""
    settings = MagicMock(spec=Settings)
    settings.database = DatabaseConfig()
    return settings


@pytest.fixture
def sample_token_config():
    """创建测试用 TokenConfig"""
    now = datetime.now(timezone.utc)
    ds_id = str(uuid.uuid4())
    return TokenConfig(
        token="test_token_12345678",
        token_id="testtokenid1",
        user_id="user123",
        datasource_ids=[ds_id],
        default_datasource_id=ds_id,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        last_used_at=now,
        name="Test token",
        metadata={},
        ip_whitelist=None,
        ip_blacklist=None,
    )


@pytest.fixture
def sample_token_model(sample_token_config):
    """创建测试用 TokenModel"""
    return TokenModel(
        token=sample_token_config.token,
        token_id=sample_token_config.token_id,
        user_id=sample_token_config.user_id,
        datasource_ids=json.dumps([str(ds_id) for ds_id in sample_token_config.datasource_ids]),
        default_datasource_id=sample_token_config.default_datasource_id,
        created_at=sample_token_config.created_at,
        expires_at=sample_token_config.expires_at,
        last_used_at=sample_token_config.last_used_at,
        name=sample_token_config.name,
        token_metadata=json.dumps(sample_token_config.metadata),
    )


# ============================================================
# TokenService 生命周期测试
# ============================================================
class TestTokenServiceLifecycle:
    """测试服务生命周期"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.init_db")
    @patch("dm_mcp.domain.token.services.token.bootstrap_schema", new_callable=AsyncMock)
    @patch("dm_mcp.domain.token.services.token.close_db", new_callable=AsyncMock)
    async def test_startup(
        self, mock_close_db, mock_bootstrap_schema, mock_init_db, mock_settings
    ):
        """测试服务启动"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        await service.startup()

        # 验证数据库初始化被调用
        mock_init_db.assert_called_once()
        mock_bootstrap_schema.assert_called_once()

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.init_db")
    @patch("dm_mcp.domain.token.services.token.bootstrap_schema", new_callable=AsyncMock)
    @patch("dm_mcp.domain.token.services.token.close_db", new_callable=AsyncMock)
    async def test_shutdown(
        self, mock_close_db, mock_bootstrap_schema, mock_init_db, mock_settings
    ):
        """测试服务关闭"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())

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
    mock_session.delete = AsyncMock()

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    return mock_context


class TestTokenServiceCRUD:
    """测试 Token CRUD 操作"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_create_token(self, mock_get_session, mock_settings):
        """测试创建 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        datasource_id = str(uuid.uuid4())
        token_config = await service.create_token(
            user_id="user123",
            datasource_ids=[datasource_id],
            default_datasource_id=datasource_id,
            expires_in=3600,
            name="Test token",
        )

        assert token_config.user_id == "user123"
        assert token_config.datasource_ids == [datasource_id]
        assert token_config.default_datasource_id == datasource_id
        assert token_config.name == "Test token"
        assert token_config.token.startswith("sk-dmmcp-")

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_list_tokens(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试列出所有 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_token_model]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        tokens = await service.list_tokens()

        assert len(tokens) == 1
        assert tokens[0].token == sample_token_model.token

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_list_tokens_by_user(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试按用户列出 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_token_model]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        tokens = await service.list_tokens(user_id="user123")

        assert len(tokens) == 1

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_get_token(self, mock_get_session, mock_settings, sample_token_model):
        """测试获取单个 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = await service.get_token(sample_token_model.token)

        assert token is not None
        assert token.token == sample_token_model.token

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_get_token_not_found(self, mock_get_session, mock_settings):
        """测试获取不存在的 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = await service.get_token("nonexistent_token")

        assert token is None

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_get_by_token_id(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试通过 token_id 查询 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            token = await service.get_by_token_id(sample_token_model.token_id)

        assert token is not None
        assert token.token_id == sample_token_model.token_id
        assert token.token == sample_token_model.token

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_get_by_token_id_not_found(self, mock_get_session, mock_settings):
        """测试通过不存在的 token_id 查询返回 None"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token = await service.get_by_token_id("nonexistent12")

        assert token is None

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_update_token(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试更新 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        new_name = "Updated name"
        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            token = await service.update_token(
                sample_token_model.token_id, name=new_name
            )

        assert token.name == new_name

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_delete_token(self, mock_get_session, mock_settings, sample_token_model):
        """测试删除 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            await service.delete_token("testtokenid1")


# ============================================================
# TokenService 验证测试
# ============================================================
class TestTokenServiceValidation:
    """测试 Token 验证"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_validate_token_success(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试验证有效 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        token_config = await service.validate_token(sample_token_model.token)

        assert token_config.token == sample_token_model.token

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_validate_token_not_found(self, mock_get_session, mock_settings):
        """测试验证不存在的 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(InvalidTokenError):
            await service.validate_token("nonexistent_token")

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_validate_token_expired(self, mock_get_session, mock_settings):
        """测试验证过期 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())

        # 创建一个已过期的 TokenModel
        now = datetime.now(timezone.utc)
        expired_model = TokenModel(
            token="expired_token",
            token_id="expiredtest1",
            user_id="user123",
            datasource_ids=json.dumps([str(uuid.uuid4())]),
            default_datasource_id=uuid.uuid4(),
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),  # 已过期
            last_used_at=now,
            name="Expired token",
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
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_cleanup_expired_tokens(self, mock_get_session, mock_settings):
        """测试清理过期 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.all.return_value = [("token1", "user1"), ("token2", "user2")]
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
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._is_ip_allowed("192.168.1.100", None, None)
        assert result is True

    def test_is_ip_allowed_whitelist_match(self):
        """测试白名单匹配"""
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._is_ip_allowed(
            "192.168.1.100", ["192.168.1.0/24", "10.0.0.1"], None
        )
        assert result is True

    def test_is_ip_allowed_whitelist_no_match(self):
        """测试白名单不匹配"""
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._is_ip_allowed("192.168.2.100", ["192.168.1.0/24"], None)
        assert result is False

    def test_is_ip_allowed_blacklist_match(self):
        """测试黑名单匹配"""
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._is_ip_allowed("192.168.1.100", None, ["192.168.1.100"])
        assert result is False

    def test_is_ip_allowed_blacklist_priority(self):
        """测试黑名单优先于白名单"""
        from dm_mcp.domain.token.services.token import TokenService

        # 同一个 IP 同时在白名单和黑名单中，应该被拒绝
        result = TokenService._is_ip_allowed(
            "192.168.1.100", ["192.168.1.100"], ["192.168.1.100"]
        )
        assert result is False

    def test_ip_matches_exact(self):
        """测试精确 IP 匹配"""
        from dm_mcp.domain.token.services.token import TokenService

        assert TokenService._ip_matches("192.168.1.100", "192.168.1.100") is True
        assert TokenService._ip_matches("192.168.1.100", "192.168.1.101") is False

    def test_ip_matches_cidr(self):
        """测试 CIDR 网段匹配"""
        from dm_mcp.domain.token.services.token import TokenService

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
        assert "event_service" in metadata.dependencies

    def test_create(self, mock_settings):
        """测试创建服务实例"""
        factory = TokenServiceFactory()
        service = factory.create(mock_settings, event_service=FakeEventService(), auth_config_service=_make_mock_auth_config_service())

        assert isinstance(service, TokenService)
        assert service.settings == mock_settings


# ============================================================
# 工具方法测试
# ============================================================
class TestTokenServiceHelperMethods:
    """测试辅助方法"""

    def test_ensure_aware_datetime_naive(self):
        """测试转换 naive datetime 为 aware"""
        from dm_mcp.domain.token.services.token import TokenService

        naive_dt = datetime(2020, 1, 1, 12, 0, 0)
        result = TokenService._ensure_aware_datetime(naive_dt)

        assert result.tzinfo is not None

    def test_ensure_aware_datetime_aware(self):
        """测试 aware datetime 保持不变"""
        from dm_mcp.domain.token.services.token import TokenService

        aware_dt = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = TokenService._ensure_aware_datetime(aware_dt)

        assert result == aware_dt

    def test_ensure_aware_datetime_none(self):
        """测试 None 返回 None"""
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._ensure_aware_datetime(None)

        assert result is None

    def test_ensure_aware_datetime_required_naive(self):
        """测试 _ensure_aware_datetime_required 转换 naive datetime"""
        from dm_mcp.domain.token.services.token import TokenService

        naive_dt = datetime(2020, 1, 1, 12, 0, 0)
        result = TokenService._ensure_aware_datetime_required(naive_dt)

        assert result.tzinfo is not None

    def test_ensure_aware_datetime_required_aware(self):
        """测试 _ensure_aware_datetime_required 保持 aware datetime 不变"""
        from dm_mcp.domain.token.services.token import TokenService

        aware_dt = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = TokenService._ensure_aware_datetime_required(aware_dt)

        assert result == aware_dt


# ============================================================
# TokenService 缓存测试
# ============================================================
class TestTokenServiceCache:
    """测试 Token 缓存机制"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_validate_token_cache_hit(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试缓存命中"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
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
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_validate_token_cache_expired(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试缓存过期"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())

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
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_create_token_with_ip_whitelist(
        self, mock_get_session, mock_settings
    ):
        """测试创建带 IP 白名单的 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        datasource_id = str(uuid.uuid4())
        token_config = await service.create_token(
            user_id="user123",
            datasource_ids=[datasource_id],
            default_datasource_id=datasource_id,
            expires_in=3600,
            name="Test token",
            ip_whitelist=["192.168.1.0/24", "10.0.0.1"],
        )

        assert token_config.ip_whitelist == ["192.168.1.0/24", "10.0.0.1"]

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_create_token_with_ip_blacklist(
        self, mock_get_session, mock_settings
    ):
        """测试创建带 IP 黑名单的 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        datasource_id = str(uuid.uuid4())
        token_config = await service.create_token(
            user_id="user123",
            datasource_ids=[datasource_id],
            default_datasource_id=datasource_id,
            expires_in=3600,
            name="Test token",
            ip_blacklist=["192.168.1.100"],
        )

        assert token_config.ip_blacklist == ["192.168.1.100"]

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_update_token_with_ip_whitelist(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试更新 Token 的 IP 白名单"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            token = await service.update_token(
                sample_token_model.token_id,
                ip_whitelist=["10.0.0.0/8"],
            )

        assert token.ip_whitelist == ["10.0.0.0/8"]

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_update_token_with_both_ip_lists(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试同时更新 IP 白名单和黑名单"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            token = await service.update_token(
                sample_token_model.token_id,
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
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_delete_token_not_found(self, mock_get_session, mock_settings):
        """测试删除不存在的 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ), pytest.raises(ValueError) as exc_info:
            await service.delete_token("nonexistent12")

        assert "未找到" in str(exc_info.value)


# ============================================================
# TokenService 更新错误测试
# ============================================================
class TestTokenServiceUpdateErrors:
    """测试 Token 更新错误处理"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_update_token_not_found(self, mock_get_session, mock_settings):
        """测试更新不存在的 Token"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(ValueError) as exc_info:
            await service.update_token("nonexistent12", name="test")

        assert "未找到" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_update_token_with_expires_at(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """测试更新 Token 过期时间"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        new_expires_at = datetime(2025, 12, 31, 23, 59, 59)
        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            token = await service.update_token(
                sample_token_model.token_id,
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
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._ip_matches("invalid_ip", "192.168.1.1")
        assert result is False

    def test_ip_matches_invalid_pattern(self):
        """测试无效匹配模式"""
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._ip_matches("192.168.1.1", "invalid_cidr")
        assert result is False

    def test_ip_matches_ipv6(self):
        """测试 IPv6 匹配"""
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._ip_matches("::1", "::1")
        assert result is True

    def test_ip_matches_ipv6_cidr(self):
        """测试 IPv6 CIDR 匹配"""
        from dm_mcp.domain.token.services.token import TokenService

        result = TokenService._ip_matches("2001:db8::1", "2001:db8::/32")
        assert result is True


# ============================================================
# TokenService 生命周期扩展测试
# ============================================================
class TestTokenServiceLifecycleExtended:
    """扩展生命周期测试"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.init_db")
    @patch("dm_mcp.domain.token.services.token.bootstrap_schema", new_callable=AsyncMock)
    @patch("dm_mcp.domain.token.services.token.close_db", new_callable=AsyncMock)
    async def test_startup_without_auto_cleanup(
        self, mock_close_db, mock_bootstrap_schema, mock_init_db, mock_settings
    ):
        """测试禁用自动清理时的启动"""
        mock_auth = _make_mock_auth_config_service()
        mock_auth.token_auth_auto_cleanup = False
        service = TokenService(mock_settings, FakeEventService(), mock_auth)
        await service.startup()

        assert service._cleanup_task is None

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.init_db")
    @patch("dm_mcp.domain.token.services.token.bootstrap_schema", new_callable=AsyncMock)
    async def test_shutdown_cancelled_error(
        self, mock_bootstrap_schema, mock_init_db, mock_settings
    ):
        """测试关闭时取消清理任务"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
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
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_model_to_config_with_metadata(self, mock_get_session, mock_settings):
        """测试带 metadata 的模型转换"""
        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())

        now = datetime.now(timezone.utc)
        model = TokenModel(
            token="test_token",
            token_id="convtest0001",
            user_id="user123",
            datasource_ids=json.dumps([str(uuid.uuid4())]),
            default_datasource_id=uuid.uuid4(),
            created_at=now,
            expires_at=now + timedelta(hours=1),
            last_used_at=now,
            name="Test",
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
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_create_token_default_expires_in(
        self, mock_get_session, mock_settings
    ):
        """测试使用默认过期时间创建 Token"""
        mock_auth = _make_mock_auth_config_service()
        mock_auth.token_auth_default_expires_in = 86400  # 24 小时

        service = TokenService(mock_settings, FakeEventService(), mock_auth)
        mock_session = MagicMock()
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        ds_id = str(uuid.uuid4())
        token_config = await service.create_token(
            user_id="user123",
            datasource_ids=[ds_id],
            default_datasource_id=ds_id,
            name="Default test",
            # 不指定 expires_in，使用默认值
        )

        # 验证过期时间是 24 小时
        expected_expires = token_config.created_at + timedelta(seconds=86400)
        # 允许 1 秒误差
        assert abs((token_config.expires_at - expected_expires).total_seconds()) < 1


# ============================================================
# TokenService 事件发布测试 (P3)
# ============================================================
class TestTokenServiceEvents:
    """测试 Token 删除/过期清理时通过事件总线发布 TokenRevoked"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_delete_token_publishes_token_revoked(
        self, mock_get_session, mock_settings, sample_token_model
    ):
        """删除 Token 成功后应发布 TokenRevoked(reason='deleted', user_id=...)"""
        from dm_mcp.core.auth.auth_context import AuthContext

        bus = FakeEventService()
        service = TokenService(mock_settings, bus, _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            await service.delete_token("testtokenid1")

        event = bus.assert_published(TokenRevoked)
        assert event.token == sample_token_model.token
        assert event.reason == "deleted"
        assert event.user_id == "user123"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_delete_token_not_found_does_not_publish(
        self, mock_get_session, mock_settings
    ):
        """删除不存在的 Token 抛异常,不发布事件"""
        from dm_mcp.core.auth.auth_context import AuthContext

        bus = FakeEventService()
        service = TokenService(mock_settings, bus, _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ), pytest.raises(ValueError):
            await service.delete_token("nopeid123456")

        assert bus.published == []

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_cleanup_expired_publishes_event_per_token(
        self, mock_get_session, mock_settings
    ):
        """过期清理为每个被删除的 token 发布一次 TokenRevoked(reason='expired')"""
        bus = FakeEventService()
        service = TokenService(mock_settings, bus, _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("sk-dmmcp-aa", "user-1"),
            ("sk-dmmcp-bb", "user-2"),
            ("sk-dmmcp-cc", "user-3"),
        ]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        count = await service.cleanup_expired_tokens()

        assert count == 3
        bus.assert_published_count(TokenRevoked, 3)
        events = [e for e in bus.published if isinstance(e, TokenRevoked)]
        assert {e.token for e in events} == {
            "sk-dmmcp-aa",
            "sk-dmmcp-bb",
            "sk-dmmcp-cc",
        }
        assert all(e.reason == "expired" for e in events)
        assert {e.user_id for e in events} == {"user-1", "user-2", "user-3"}

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_cleanup_no_expired_publishes_nothing(
        self, mock_get_session, mock_settings
    ):
        """没有过期 token 时不应发布事件"""
        bus = FakeEventService()
        service = TokenService(mock_settings, bus, _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_get_session.return_value = create_mock_session_context(mock_result)

        count = await service.cleanup_expired_tokens()

        assert count == 0
        assert bus.published == []


# ============================================================
# TokenService 所有权隔离测试
# ============================================================
class TestTokenServiceOwnership:
    """测试 Token 所有权隔离（用户只能访问自己的 Token）"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_get_by_token_id_owner_can_access(self, mock_get_session, mock_settings, sample_token_model):
        """所有者可以通过 token_id 获取自己的 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            token = await service.get_by_token_id(sample_token_model.token_id)

        assert token is not None
        assert token.token_id == sample_token_model.token_id

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_get_by_token_id_non_owner_denied(self, mock_get_session, mock_settings, sample_token_model):
        """非所有者不能通过 token_id 获取他人的 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_b", auth_type="token")
        ), pytest.raises(AuthorizationError) as exc_info:
            await service.get_by_token_id(sample_token_model.token_id)

        assert "无权访问" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_update_token_owner_can_update(self, mock_get_session, mock_settings, sample_token_model):
        """所有者可以更新自己的 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            token = await service.update_token(
                sample_token_model.token_id, name="new_name"
            )

        assert token.name == "new_name"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_update_token_non_owner_denied(self, mock_get_session, mock_settings, sample_token_model):
        """非所有者不能更新他人的 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_b", auth_type="token")
        ), pytest.raises(AuthorizationError) as exc_info:
            await service.update_token(
                sample_token_model.token_id, name="new_name"
            )

        assert "无权访问" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_delete_token_owner_can_delete(self, mock_get_session, mock_settings, sample_token_model):
        """所有者可以删除自己的 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            await service.delete_token(sample_token_model.token_id)

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_delete_token_non_owner_denied(self, mock_get_session, mock_settings, sample_token_model):
        """非所有者不能删除他人的 Token"""
        from dm_mcp.core.auth.auth_context import AuthContext
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_token_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_b", auth_type="token")
        ), pytest.raises(AuthorizationError) as exc_info:
            await service.delete_token(sample_token_model.token_id)

        assert "无权访问" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.token.services.token.get_async_session")
    async def test_list_tokens_defaults_to_current_user(self, mock_get_session, mock_settings, sample_token_model):
        """list_tokens 不传 user_id 时默认从 AuthContext 获取"""
        from dm_mcp.core.auth.auth_context import AuthContext

        service = TokenService(mock_settings, FakeEventService(), _make_mock_auth_config_service())
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_token_model]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user123", auth_type="token")
        ):
            tokens = await service.list_tokens()

        assert len(tokens) == 1
        # 验证 where 条件注入了 user_id
        call_args = mock_get_session.return_value.__aenter__.return_value.execute.call_args
        stmt = call_args[0][0]
        assert "user_id" in str(stmt)
