"""DataSourceService 单元测试"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_mcp.infra.persistence import AppSettingsModel, DataSourceModel
from dm_mcp.domain.datasource.events import (
    DataSourceCreated,
    DataSourceDeleted,
    DataSourceUpdated,
)
from dm_mcp.domain.datasource.services.datasource import (
    DataSourceService,
    DataSourceServiceFactory,
)
from dm_mcp.infra.config import Settings
from dm_mcp.infra.config.database_config import DatabaseConfig
from dm_mcp.infra.persistence.pool_config import DmPoolConfig


class FakeEventService:
    """用于测试的事件服务 stub"""

    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)

    async def publish_strict(self, event):
        self.events.append(event)

    def get_events(self):
        return self.events

    def clear(self):
        self.events = []


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.database = DatabaseConfig()
    settings.app_secret = MagicMock()
    settings.app_secret.get_secret_value.return_value = "test-app-secret"
    return settings


@pytest.fixture
def pool_config():
    return DmPoolConfig(enabled=False, default_source="primary")


@pytest.fixture
def service_settings():
    settings = MagicMock(spec=Settings)
    settings.database = DatabaseConfig()
    settings.app_secret = MagicMock()
    settings.app_secret.get_secret_value.return_value = "test-app-secret"
    return settings


@pytest.fixture
def sample_datasource():
    return DataSourceModel(
        id=uuid.uuid4(),
        name="test_datasource",
        enabled=True,
        deploy_type="dmstandalone",
        read_only=False,
        dsn="",
        host="localhost",
        port=5236,
        user="SYSDBA",
        password="SYSDBA",
        minsize=1,
        maxsize=10,
        timeout=30.0,
        weight=1,
    )


# ============================================================
# 生命周期测试
# ============================================================
class TestDataSourceServiceLifecycle:
    @pytest.mark.asyncio
    @patch("dm_mcp.domain.datasource.services.datasource.init_db")
    @patch("dm_mcp.domain.datasource.services.datasource.bootstrap_schema", new_callable=AsyncMock)
    @patch("dm_mcp.domain.datasource.services.datasource.get_async_session")
    async def test_startup(self, mock_get_session, mock_bootstrap_schema, mock_init_db, mock_settings, pool_config):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_get_session.return_value = mock_context

        service = DataSourceService(mock_settings, FakeEventService(), MagicMock())
        await service.startup()
        mock_init_db.assert_called_once()
        mock_bootstrap_schema.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_settings, pool_config):
        service = DataSourceService(mock_settings, FakeEventService(), MagicMock())
        await service.shutdown()


# ============================================================
# CRUD 测试
# ============================================================
class TestDataSourceServiceCRUD:
    @pytest.mark.asyncio
    @patch("dm_mcp.domain.datasource.services.datasource.get_async_session")
    async def test_list_datasources(self, mock_get_session, mock_settings, pool_config, sample_datasource):
        service = DataSourceService(mock_settings, FakeEventService(), MagicMock())

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_datasource]
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        datasources = await service.list_datasources()
        assert len(datasources) == 1
        assert datasources[0].name == sample_datasource.name

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.datasource.services.datasource.get_async_session")
    async def test_get_datasource_by_name(self, mock_get_session, mock_settings, pool_config, sample_datasource):
        service = DataSourceService(mock_settings, FakeEventService(), MagicMock())

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_datasource
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        datasource = await service.get_datasource(sample_datasource.name)
        assert datasource is not None
        assert datasource.name == sample_datasource.name

    @pytest.mark.asyncio
    @patch("dm_mcp.domain.datasource.services.datasource.get_async_session")
    async def test_get_datasource_not_found(self, mock_get_session, mock_settings, pool_config):
        service = DataSourceService(mock_settings, FakeEventService(), MagicMock())

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        datasource = await service.get_datasource("nonexistent")
        assert datasource is None


# ============================================================
# 添加操作测试
# ============================================================
class TestDataSourceServiceAdd:
    @pytest.mark.asyncio
    async def test_add_datasource_success(self, service_settings, pool_config):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            new_ds = DataSourceModel(name="new_ds", enabled=True, deploy_type="dmstandalone",
                                     host="localhost", port=5237, user="SYSDBA", password="SYSDBA")
            await service.add_datasource(new_ds)

    @pytest.mark.asyncio
    async def test_add_datasource_duplicate_name(self, service_settings, pool_config):
        mock_session = MagicMock()
        mock_result = MagicMock()
        existing_ds = MagicMock()
        existing_ds.name = "test_ds"
        mock_result.scalar_one_or_none.return_value = existing_ds
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            new_ds = DataSourceModel(name="test_ds", enabled=True, deploy_type="dmstandalone",
                                     host="localhost", port=5237, user="SYSDBA", password="SYSDBA")
            with pytest.raises(ValueError) as exc_info:
                await service.add_datasource(new_ds)
            assert "已存在" in str(exc_info.value)


# ============================================================
# 更新操作测试
# ============================================================
class TestDataSourceServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_datasource_not_found(self, service_settings, pool_config):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            config = DataSourceModel(name="nonexistent", enabled=True, deploy_type="dmstandalone",
                                     host="localhost", port=5236, user="SYSDBA", password="SYSDBA")
            with pytest.raises(ValueError) as exc_info:
                await service.update_datasource("nonexistent", config)
            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_datasource_name_conflict(self, service_settings, pool_config):
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                target_ds = MagicMock()
                target_ds.owner_id = None
                target_ds.name = "target_ds"
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                existing_ds = MagicMock()
                existing_ds.name = "existing_ds"
                mock_result.scalar_one_or_none.return_value = existing_ds
            else:
                mock_result.scalars.return_value.all.return_value = []
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            config = DataSourceModel(name="existing_ds", enabled=True, deploy_type="dmstandalone",
                                     host="localhost", port=5237, user="SYSDBA", password="SYSDBA")
            with pytest.raises(ValueError) as exc_info:
                await service.update_datasource("target_ds", config)
            assert "已存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_datasource_inplace_success(self, service_settings, pool_config):
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "target_ds"
        target_ds.id = uuid.uuid4()

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] in (1, 2):
                mock_result.scalar_one_or_none.return_value = target_ds
            else:
                mock_result.scalars.return_value.all.return_value = [target_ds]
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            config = DataSourceModel(name="target_ds", enabled=False, deploy_type="dmstandalone",
                                     host="newhost", port=5237, user="SYSDBA", password="SYSDBA")
            await service.update_datasource("target_ds", config)

    @pytest.mark.asyncio
    async def test_update_datasource_rename_success(self, service_settings, pool_config):
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "old_name"
        target_ds.id = uuid.uuid4()

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                mock_result.scalar_one_or_none.return_value = None
            else:
                mock_result.scalars.return_value.all.return_value = []
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            config = DataSourceModel(name="new_name", enabled=True, deploy_type="dmstandalone",
                                     host="localhost", port=5236, user="SYSDBA", password="SYSDBA")
            await service.update_datasource("old_name", config)


# ============================================================
# 删除操作测试
# ============================================================
class TestDataSourceServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_datasource_not_found(self, service_settings, pool_config):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with pytest.raises(ValueError) as exc_info:
                await service.delete_datasource("nonexistent")
            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_normal_datasource(self, service_settings, pool_config):
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.id = uuid.uuid4()
        target_ds.name = "to_delete"

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                mock_result.scalar_one_or_none.return_value = None
            else:
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.delete = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            await service.delete_datasource("to_delete")

    @pytest.mark.asyncio
    async def test_delete_default_datasource(self, service_settings, pool_config):
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.id = uuid.uuid4()
        target_ds.name = "default_ds"

        default_setting = MagicMock()
        default_setting.key = "default_datasource"
        default_setting.value = "default_ds"

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                mock_result.scalar_one_or_none.return_value = default_setting
            else:
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.delete = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            await service.delete_datasource("default_ds")


# ============================================================
# 启用/禁用操作测试
# ============================================================
class TestDataSourceServiceEnableDisable:
    @pytest.mark.asyncio
    async def test_enable_datasource_not_found(self, service_settings, pool_config):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with pytest.raises(ValueError) as exc_info:
                await service.enable_datasource("nonexistent")
            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_enable_datasource_already_enabled(self, service_settings, pool_config):
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "enabled_ds"
        target_ds.enabled = True

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            await service.enable_datasource("enabled_ds")
            # 不应发布事件
            assert len(service._event_service.get_events()) == 0

    @pytest.mark.asyncio
    async def test_disable_datasource_already_disabled(self, service_settings, pool_config):
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "disabled_ds"
        target_ds.enabled = False

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            await service.disable_datasource("disabled_ds")
            assert len(service._event_service.get_events()) == 0


# ============================================================
# 默认数据源测试
# ============================================================
class TestDataSourceServiceDefaultSource:
    @pytest.mark.asyncio
    async def test_get_default_datasource_from_db(self, service_settings, pool_config):
        mock_setting = MagicMock()
        mock_setting.value = "db_default_ds"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting

        mock_ds = MagicMock()
        mock_ds.owner_id = None  # 公共数据源

        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_ds

        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_result
            return mock_result2

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            result = await service.get_default_datasource()
            assert result == "db_default_ds"

    @pytest.mark.asyncio
    async def test_get_default_datasource_owned_by_other_user(self, service_settings, pool_config):
        """当默认数据源属于其他用户时，应回退到全局默认值"""
        mock_setting = MagicMock()
        mock_setting.value = "other_user_ds"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting

        mock_ds = MagicMock()
        mock_ds.owner_id = "user_a"  # 属于其他用户

        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = mock_ds

        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_result
            return mock_result2

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            result = await service.get_default_datasource()
            assert result == "primary"

    @pytest.mark.asyncio
    async def test_get_default_datasource_not_exists(self, service_settings, pool_config):
        mock_setting = MagicMock()
        mock_setting.value = "deleted_ds"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting

        mock_result_empty = MagicMock()
        mock_result_empty.scalar_one_or_none.return_value = None

        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_result
            return mock_result_empty

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=execute_side_effect)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            result = await service.get_default_datasource()
            assert result == "primary"

    @pytest.mark.asyncio
    async def test_set_default_datasource_not_found(self, service_settings, pool_config):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            with patch.object(DataSourceService, "get_datasource", new_callable=AsyncMock, return_value=None):
                service = DataSourceService(service_settings, FakeEventService(), MagicMock())
                with pytest.raises(ValueError) as exc_info:
                    await service.set_default_datasource("nonexistent")
                assert "不存在" in str(exc_info.value)


# ============================================================
# Factory 测试
# ============================================================
class TestDataSourceServiceFactory:
    def test_metadata(self):
        factory = DataSourceServiceFactory()
        metadata = factory.metadata()
        assert metadata.name == "datasource_service"
        assert metadata.service_type == DataSourceService

    def test_create(self, mock_settings, pool_config):
        factory = DataSourceServiceFactory()
        mock_settings.pool = pool_config
        fake_svc = FakeEventService()
        service = factory.create(mock_settings, event_service=fake_svc, async_pool_service=MagicMock())
        assert isinstance(service, DataSourceService)
        assert service.settings == mock_settings
        assert service._event_service is fake_svc


# ============================================================
# 事件发布测试
# ============================================================
class TestDataSourceServiceEvents:
    @pytest.mark.asyncio
    async def test_add_datasource_publishes_created(self, service_settings, pool_config):
        fake_svc = FakeEventService()
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, fake_svc, MagicMock())
            new_ds = DataSourceModel(name="event_ds", enabled=True, deploy_type="dmstandalone",
                                     host="localhost", port=5237, user="SYSDBA", password="SYSDBA")
            await service.add_datasource(new_ds)

        events = fake_svc.get_events()
        assert len(events) == 1
        assert isinstance(events[0], DataSourceCreated)
        assert events[0].name == "event_ds"

    @pytest.mark.asyncio
    async def test_update_datasource_publishes_updated(self, service_settings, pool_config):
        fake_svc = FakeEventService()
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "old_name"
        target_ds.id = uuid.uuid4()

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = target_ds
            else:
                mock_result.scalar_one_or_none.return_value = None
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, fake_svc, MagicMock())
            new_config = DataSourceModel(name="new_name", enabled=True, deploy_type="dmstandalone",
                                         host="localhost", port=5236, user="SYSDBA", password="SYSDBA")
            await service.update_datasource("old_name", new_config, skip_authz=True)

        events = fake_svc.get_events()
        assert len(events) == 1
        assert isinstance(events[0], DataSourceUpdated)
        assert events[0].old_name == "old_name"
        assert events[0].name == "new_name"

    @pytest.mark.asyncio
    async def test_delete_datasource_publishes_deleted(self, service_settings, pool_config):
        fake_svc = FakeEventService()
        ds_id = uuid.uuid4()
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "to_delete"
        target_ds.id = ds_id

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()
            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                mock_result.scalar_one_or_none.return_value = None
            else:
                mock_result.scalars.return_value.all.return_value = []
            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.delete = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, fake_svc, MagicMock())
            await service.delete_datasource("to_delete", skip_authz=True)

        events = fake_svc.get_events()
        assert len(events) == 1
        assert isinstance(events[0], DataSourceDeleted)
        assert events[0].name == "to_delete"
        assert events[0].datasource_id == ds_id

    @pytest.mark.asyncio
    async def test_enable_datasource_publishes_updated(self, service_settings, pool_config):
        """enable_datasource 发布 DataSourceUpdated"""
        fake_svc = FakeEventService()
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "enable_me"
        target_ds.enabled = False
        target_ds.host = "localhost"
        target_ds.user = "SYSDBA"
        target_ds.password = "SYSDBA"
        target_ds.deploy_type = "dmstandalone"
        target_ds.dsn = ""

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        from dm_mcp.core.auth.auth_context import AuthContext

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, fake_svc, MagicMock())
            with AuthContext.as_current(AuthContext(user_id="admin", auth_type="basic_auth")):
                await service.enable_datasource("enable_me")

        events = fake_svc.get_events()
        assert len(events) == 1
        assert isinstance(events[0], DataSourceUpdated)
        assert events[0].old_name == "enable_me"

    @pytest.mark.asyncio
    async def test_disable_datasource_publishes_updated(self, service_settings, pool_config):
        """disable_datasource 发布 DataSourceUpdated"""
        fake_svc = FakeEventService()
        target_ds = MagicMock()
        target_ds.owner_id = None
        target_ds.name = "disable_me"
        target_ds.enabled = True
        target_ds.host = "localhost"
        target_ds.user = "SYSDBA"
        target_ds.password = "SYSDBA"
        target_ds.deploy_type = "dmstandalone"
        target_ds.dsn = ""

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        from dm_mcp.core.auth.auth_context import AuthContext

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, fake_svc, MagicMock())
            with AuthContext.as_current(AuthContext(user_id="admin", auth_type="basic_auth")):
                await service.disable_datasource("disable_me")

        events = fake_svc.get_events()
        assert len(events) == 1
        assert isinstance(events[0], DataSourceUpdated)
        assert events[0].old_name == "disable_me"


# ============================================================
# 密码加密测试
# ============================================================
class TestDataSourcePasswordEncryption:
    def test_encrypt_decrypt_roundtrip(self, service_settings, pool_config):
        """密码加解密往返一致性"""
        from dm_mcp.infra.security.crypto import FernetCrypto

        crypto = FernetCrypto("o5YctWbIRHyxGBvok6I_Xo3FERe73RMAXaXCkvaFm2g=")
        service = DataSourceService(service_settings, FakeEventService(), MagicMock(), crypto)

        original = "my_secret_password"
        encrypted = service._encrypt_password(original)
        assert encrypted.startswith("enc$")
        decrypted = service._decrypt_password(encrypted)
        assert decrypted == original

    def test_empty_password_no_encrypt(self, service_settings, pool_config):
        """空密码不加密"""
        from dm_mcp.infra.security.crypto import FernetCrypto

        crypto = FernetCrypto("o5YctWbIRHyxGBvok6I_Xo3FERe73RMAXaXCkvaFm2g=")
        service = DataSourceService(service_settings, FakeEventService(), MagicMock(), crypto)

        assert service._encrypt_password("") == ""
        assert service._decrypt_password("") == ""

    def test_crypto_none_passthrough(self, service_settings, pool_config):
        """crypto=None 时密码原样透传"""
        service = DataSourceService(service_settings, FakeEventService(), MagicMock(), None)

        assert service._encrypt_password("any_password") == "any_password"
        assert service._decrypt_password("any_password") == "any_password"

    @pytest.mark.asyncio
    async def test_add_datasource_encrypts_password(self, service_settings, pool_config):
        """add_datasource 写入加密密码，事件发布明文密码"""
        from dm_mcp.infra.security.crypto import FernetCrypto

        crypto = FernetCrypto("o5YctWbIRHyxGBvok6I_Xo3FERe73RMAXaXCkvaFm2g=")
        fake_svc = FakeEventService()
        service = DataSourceService(service_settings, fake_svc, MagicMock(), crypto)

        captured_passwords = []

        def capture_add(model):
            captured_passwords.append(model.password)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock(side_effect=capture_add)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            new_ds = DataSourceModel(
                name="encrypted_ds",
                enabled=True,
                deploy_type="dmstandalone",
                host="localhost",
                port=5237,
                user="SYSDBA",
                password="secret123",
            )
            await service.add_datasource(new_ds)

        # 事件中的密码应该是明文
        events = fake_svc.get_events()
        assert len(events) == 1
        assert events[0].password == "secret123"

        # 写入 session 时的 model 密码应该是加密的（通过 side_effect 捕获）
        assert len(captured_passwords) == 1
        assert captured_passwords[0].startswith("enc$")


# ============================================================
# DataSourceService 所有权隔离测试
# ============================================================
class TestDataSourceServiceOwnership:
    """测试数据源所有权隔离（用户只能访问自己的数据源）"""

    @pytest.mark.asyncio
    async def test_owner_can_access_own_datasource(self, service_settings, pool_config):
        """所有者可以访问自己的数据源"""
        from dm_mcp.core.auth.auth_context import AuthContext

        target_ds = DataSourceModel(
            id=uuid.uuid4(),
            name="owner_ds",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="SYSDBA",
            owner_id="user_a",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with AuthContext.as_current(AuthContext(user_id="user_a", auth_type="token")):
                ds = await service.get_datasource("owner_ds")

        assert ds is not None
        assert ds.name == "owner_ds"

    @pytest.mark.asyncio
    async def test_non_owner_cannot_access_private_datasource(self, service_settings, pool_config):
        """非所有者不能访问他人的私有数据源"""
        from dm_mcp.core.auth.auth_context import AuthContext
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        target_ds = DataSourceModel(
            id=uuid.uuid4(),
            name="private_ds",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="SYSDBA",
            owner_id="user_a",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with AuthContext.as_current(AuthContext(user_id="user_b", auth_type="token")), pytest.raises(AuthorizationError) as exc_info:
                await service.get_datasource("private_ds")

        assert "无权访问" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_admin_cannot_access_others_datasource(self, service_settings, pool_config):
        """admin 也不能访问他人的私有数据源"""
        from dm_mcp.core.auth.auth_context import AuthContext
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        target_ds = DataSourceModel(
            id=uuid.uuid4(),
            name="admin_blocked",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="SYSDBA",
            owner_id="user_a",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with AuthContext.as_current(AuthContext(user_id="admin", auth_type="basic_auth")), pytest.raises(AuthorizationError):
                await service.get_datasource("admin_blocked")

    @pytest.mark.asyncio
    async def test_public_datasource_accessible_to_all(self, service_settings, pool_config):
        """owner_id 为 None 的公共数据源所有人可访问"""
        from dm_mcp.core.auth.auth_context import AuthContext

        target_ds = DataSourceModel(
            id=uuid.uuid4(),
            name="public_ds",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="SYSDBA",
            owner_id=None,
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with AuthContext.as_current(AuthContext(user_id="user_b", auth_type="token")):
                ds = await service.get_datasource("public_ds")

        assert ds is not None
        assert ds.name == "public_ds"

    @pytest.mark.asyncio
    async def test_non_owner_cannot_update_others_datasource(self, service_settings, pool_config):
        """非所有者不能更新他人的数据源"""
        from dm_mcp.core.auth.auth_context import AuthContext
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        target_ds = DataSourceModel(
            id=uuid.uuid4(),
            name="private_ds",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="SYSDBA",
            owner_id="user_a",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        new_config = DataSourceModel(
            name="private_ds",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5237,
            user="SYSDBA",
            password="SYSDBA",
        )

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with AuthContext.as_current(AuthContext(user_id="user_b", auth_type="token")), pytest.raises(AuthorizationError):
                await service.update_datasource("private_ds", new_config)

    @pytest.mark.asyncio
    async def test_non_owner_cannot_delete_others_datasource(self, service_settings, pool_config):
        """非所有者不能删除他人的数据源"""
        from dm_mcp.core.auth.auth_context import AuthContext
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        target_ds = DataSourceModel(
            id=uuid.uuid4(),
            name="private_ds",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="SYSDBA",
            owner_id="user_a",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with AuthContext.as_current(AuthContext(user_id="user_b", auth_type="token")), pytest.raises(AuthorizationError):
                await service.delete_datasource("private_ds")

    @pytest.mark.asyncio
    async def test_anonymous_cannot_access_private_datasource(self, service_settings, pool_config):
        """匿名用户不能访问私有数据源"""
        from dm_mcp.core.exceptions.auth_errors import AuthorizationError

        target_ds = DataSourceModel(
            id=uuid.uuid4(),
            name="private_ds",
            enabled=True,
            deploy_type="dmstandalone",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password="SYSDBA",
            owner_id="user_a",
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = target_ds

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch("dm_mcp.domain.datasource.services.datasource.get_async_session", return_value=mock_context):
            service = DataSourceService(service_settings, FakeEventService(), MagicMock())
            with pytest.raises(AuthorizationError):
                await service.get_datasource("private_ds")
