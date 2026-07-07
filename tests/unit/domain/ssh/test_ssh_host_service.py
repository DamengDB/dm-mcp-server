"""SSHHostService 单元测试

验证 SSH 主机配置管理的 CRUD、密码加解密、权限校验逻辑。
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions.auth_errors import AuthorizationError
from dm_mcp.domain.ssh.services.host import SSHHostConfig, SSHHostService, SSHHostServiceFactory
from dm_mcp.infra.persistence import SSHHostModel
from dm_mcp.infra.security.crypto import FernetCrypto
from tests.conftest import FakeEventService


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_settings():
    """创建测试用 Settings"""
    settings = MagicMock()
    settings.app_secret = MagicMock()
    settings.app_secret.get_secret_value.return_value = "test-app-secret-for-testing-only"
    return settings


@pytest.fixture
def sample_host_model():
    """创建测试用 SSHHostModel"""
    return SSHHostModel(
        id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
        name="test_host",
        host="192.168.1.100",
        port=22,
        username="root",
        key_based=False,
        password_enc="plain_password",
        description="Test SSH host",
        owner_id="user_a",
    )


@pytest.fixture
def crypto():
    """创建测试用 FernetCrypto"""
    from dm_mcp.common.utils.crypto import to_fernet_key

    return FernetCrypto(to_fernet_key("test-app-secret-for-testing-only"))


@pytest.fixture
def service(mock_settings, crypto):
    """创建测试用 SSHHostService"""
    return SSHHostService(mock_settings, FakeEventService(), crypto)


def create_mock_session_context(mock_result):
    """创建模拟的会话上下文"""
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.delete = AsyncMock()
    mock_session.add = MagicMock()

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_context.__aexit__ = AsyncMock(return_value=None)
    return mock_context


# ============================================================
# CRUD 测试
# ============================================================
class TestSSHHostServiceCRUD:
    """测试 SSHHostService CRUD 操作"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_list_hosts(self, mock_get_session, service, sample_host_model):
        """测试列出 SSH 主机"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_host_model]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            hosts = await service.list_hosts()

        assert len(hosts) == 1
        assert hosts[0].name == "test_host"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_get_host(self, mock_get_session, service, sample_host_model):
        """测试按 ID 获取 SSH 主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            host = await service.get_host(str(sample_host_model.id))

        assert host is not None
        assert host.name == "test_host"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_get_host_not_found(self, mock_get_session, service):
        """测试获取不存在的 SSH 主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        host = await service.get_host("12345678-1234-5678-1234-567812345678")
        assert host is None

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_get_host_by_name(self, mock_get_session, service, sample_host_model):
        """测试按名称获取 SSH 主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            host = await service.get_host_by_name("test_host")

        assert host is not None
        assert host.name == "test_host"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_create_host(self, mock_get_session, service):
        """测试创建 SSH 主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            config = await service.create_host(
                name="new_host",
                host="192.168.1.200",
                port=22,
                username="admin",
                key_based=False,
                password="secret123",
                description="New host",
            )

        assert config.name == "new_host"
        assert config.host == "192.168.1.200"
        assert config.owner_id == "user_a"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_create_host_duplicate_name(self, mock_get_session, service, sample_host_model):
        """测试创建同名 SSH 主机应报错"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(ValueError, match="已存在"):
            await service.create_host(
                name="test_host",
                host="192.168.1.200",
                port=22,
                username="admin",
            )

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_update_host(self, mock_get_session, service, sample_host_model):
        """测试更新 SSH 主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            config = await service.update_host(
                str(sample_host_model.id),
                host="192.168.1.300",
            )

        assert config.host == "192.168.1.300"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_delete_host(self, mock_get_session, service, sample_host_model):
        """测试删除 SSH 主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            await service.delete_host(str(sample_host_model.id))

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_delete_host_not_found(self, mock_get_session, service):
        """测试删除不存在的 SSH 主机应报错"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(ValueError, match="不存在"):
            await service.delete_host("12345678-1234-5678-1234-567812345678")


# ============================================================
# 密码加解密测试
# ============================================================
class TestSSHHostServiceCrypto:
    """测试密码加解密逻辑"""

    def test_encrypt_password(self, service):
        """测试加密密码"""
        encrypted = service._encrypt_password("plaintext")
        assert encrypted.startswith("enc$")

    def test_decrypt_password(self, service):
        """测试解密密码"""
        encrypted = service._encrypt_password("plaintext")
        decrypted = service._decrypt_password(encrypted)
        assert decrypted == "plaintext"

    def test_encrypt_empty_password(self, service):
        """测试空密码不加密"""
        assert service._encrypt_password("") == ""
        assert service._encrypt_password(None) is None

    def test_decrypt_plaintext(self, service):
        """测试非加密字符串不解密"""
        assert service._decrypt_password("plaintext") == "plaintext"

    def test_model_to_config_decrypts_password(self, service):
        """测试模型转换时自动解密密码"""
        model = SSHHostModel(
            id=uuid.uuid4(),
            name="test",
            host="127.0.0.1",
            port=22,
            username="root",
            password_enc=service._encrypt_password("secret"),
        )
        config = service._model_to_config(model)
        assert config.password == "secret"


# ============================================================
# 所有权隔离测试
# ============================================================
class TestSSHHostServiceOwnership:
    """测试 SSH 主机所有权隔离"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_owner_can_access_own_host(self, mock_get_session, service, sample_host_model):
        """所有者可以访问自己的主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            host = await service.get_host(str(sample_host_model.id))

        assert host is not None

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_non_owner_cannot_access_private_host(self, mock_get_session, service, sample_host_model):
        """非所有者不能访问他人的私有主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_b", auth_type="token")
        ), pytest.raises(AuthorizationError) as exc_info:
            await service.get_host(str(sample_host_model.id))

        assert "无权访问" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_admin_cannot_access_others_host(self, mock_get_session, service, sample_host_model):
        """admin 也不能访问他人的私有主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="admin", auth_type="basic_auth")
        ), pytest.raises(AuthorizationError):
            await service.get_host(str(sample_host_model.id))

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_public_resource_accessible_to_all(self, mock_get_session, service):
        """owner_id 为 None 的公共资源所有人可访问"""
        public_model = SSHHostModel(
            id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            name="public_host",
            host="192.168.1.1",
            port=22,
            username="root",
            owner_id=None,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = public_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_b", auth_type="token")
        ):
            host = await service.get_host("12345678-1234-5678-1234-567812345678")

        assert host is not None
        assert host.name == "public_host"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_non_owner_cannot_update_others_host(self, mock_get_session, service, sample_host_model):
        """非所有者不能更新他人的主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_b", auth_type="token")
        ), pytest.raises(AuthorizationError):
            await service.update_host(
                str(sample_host_model.id),
                host="192.168.1.300",
            )

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_non_owner_cannot_delete_others_host(self, mock_get_session, service, sample_host_model):
        """非所有者不能删除他人的主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_b", auth_type="token")
        ), pytest.raises(AuthorizationError):
            await service.delete_host(str(sample_host_model.id))

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_anonymous_cannot_access_private_host(self, mock_get_session, service, sample_host_model):
        """匿名用户不能访问私有主机"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with pytest.raises(AuthorizationError):
            await service.get_host(str(sample_host_model.id))


# ============================================================
# 工具方法测试
# ============================================================
class TestSSHHostServiceHelpers:
    """测试 SSHHostService 辅助方法"""

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_get_host_config(self, mock_get_session, service, sample_host_model):
        """测试获取解密的主机配置（skip_authz=True）"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        config = await service.get_host_config(str(sample_host_model.id))

        assert config is not None
        assert config.name == "test_host"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_resolve_host_ids_by_names(self, mock_get_session, service, sample_host_model):
        """测试将主机名列表解析为 ID 列表"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_host_model
        mock_get_session.return_value = create_mock_session_context(mock_result)

        ids = await service.resolve_host_ids_by_names(["test_host"])

        assert len(ids) == 1
        assert ids[0] == str(sample_host_model.id)

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_list_hosts_by_ids(self, mock_get_session, service, sample_host_model):
        """测试按 ID 列表批量查询主机"""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_host_model]
        mock_get_session.return_value = create_mock_session_context(mock_result)

        with AuthContext.as_current(
            AuthContext(user_id="user_a", auth_type="token")
        ):
            hosts = await service.list_hosts_by_ids([str(sample_host_model.id)])

        assert len(hosts) == 1
        assert hosts[0].name == "test_host"

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.ssh.services.host.get_async_session")
    async def test_list_hosts_by_ids_empty(self, mock_get_session, service):
        """测试空 ID 列表返回空结果"""
        hosts = await service.list_hosts_by_ids([])
        assert hosts == []


# ============================================================
# Factory 测试
# ============================================================
class TestSSHHostServiceFactory:
    """测试 SSHHostServiceFactory"""

    def test_metadata(self):
        """测试 factory metadata"""
        factory = SSHHostServiceFactory()
        metadata = factory.metadata()

        assert metadata.name == "ssh_host_service"
        assert metadata.service_type.__name__ == "SSHHostService"

    def test_create(self, mock_settings):
        """测试创建服务实例"""
        factory = SSHHostServiceFactory()
        service = factory.create(mock_settings, event_service=FakeEventService())

        assert isinstance(service, SSHHostService)
        assert service.settings == mock_settings
