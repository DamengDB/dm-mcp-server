"""DataSourceService 单元测试"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from pydantic import SecretStr

from dm_mcp.core.db import AppSettingsModel, DataSourceModel
from dm_mcp.services.datasource_service import (
    DataSourceService,
    DataSourceServiceFactory,
)
from dm_mcp.settings import Settings
from dm_mcp.settings.database_config import DatabaseConfig
from dm_mcp.settings.datasource_config import DataSourceConfig, DataSourcesConfig
from dm_mcp.settings.pool_config import DmPoolConfig


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_settings():
    """创建测试用 Settings"""
    settings = MagicMock(spec=Settings)
    settings.database = DatabaseConfig()
    return settings


@pytest.fixture
def pool_config():
    """创建测试用 DmPoolConfig"""
    return DmPoolConfig(
        enabled=False,
        default_source="primary",
    )


@pytest.fixture
def sample_datasource_config():
    """创建测试用 DataSourceConfig"""
    return DataSourceConfig(
        id=uuid.uuid4(),
        name="test_datasource",
        enabled=True,
        deploy_type="dmstandonle",
        read_only=False,
        dsn="",
        host="localhost",
        port=5236,
        user="SYSDBA",
        password=SecretStr("password123"),
        minsize=1,
        maxsize=10,
        timeout=30.0,
        weight=1,
    )


@pytest.fixture
def sample_datasource_model(sample_datasource_config):
    """创建测试用 DataSourceModel"""
    return DataSourceModel(
        id=sample_datasource_config.id,
        name=sample_datasource_config.name,
        enabled=sample_datasource_config.enabled,
        deploy_type=sample_datasource_config.deploy_type,
        read_only=sample_datasource_config.read_only,
        dsn=sample_datasource_config.dsn,
        host=sample_datasource_config.host,
        port=sample_datasource_config.port,
        user=sample_datasource_config.user,
        password=sample_datasource_config.password.get_secret_value(),
        minsize=sample_datasource_config.minsize,
        maxsize=sample_datasource_config.maxsize,
        timeout=sample_datasource_config.timeout,
        weight=sample_datasource_config.weight,
    )


# ============================================================
# DataSourceService 生命周期测试
# ============================================================
class TestDataSourceServiceLifecycle:
    """测试服务生命周期"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="startup 依赖数据库连接，需要更复杂的 mock 设置")
    @patch("dm_mcp.services.datasource_service.init_db")
    @patch("dm_mcp.services.datasource_service.create_tables", new_callable=AsyncMock)
    @patch(
        "dm_mcp.services.datasource_service.get_async_session", new_callable=AsyncMock
    )
    async def test_startup(
        self,
        mock_get_session,
        mock_create_tables,
        mock_init_db,
        mock_settings,
        pool_config,
    ):
        """测试服务启动"""
        # Mock get_async_session
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        service = DataSourceService(mock_settings, pool_config)
        await service.startup()

        mock_init_db.assert_called_once()
        mock_create_tables.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown(self, mock_settings, pool_config):
        """测试服务关闭"""
        service = DataSourceService(mock_settings, pool_config)
        await service.shutdown()  # 不应该抛出异常


# ============================================================
# DataSourceService CRUD 测试（使用 patch）
# ============================================================
class TestDataSourceServiceCRUD:
    """测试 DataSource CRUD 操作"""

    @pytest.mark.asyncio
    @patch("dm_mcp.services.datasource_service.get_async_session")
    async def test_list_datasources(
        self, mock_get_session, mock_settings, pool_config, sample_datasource_model
    ):
        """测试列出所有数据源"""
        service = DataSourceService(mock_settings, pool_config)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [sample_datasource_model]
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        datasources = await service.list_datasources()

        assert len(datasources) == 1
        assert datasources[0].name == sample_datasource_model.name

    @pytest.mark.asyncio
    @patch("dm_mcp.services.datasource_service.get_async_session")
    async def test_get_datasource_by_name(
        self, mock_get_session, mock_settings, pool_config, sample_datasource_model
    ):
        """测试通过名称获取数据源"""
        service = DataSourceService(mock_settings, pool_config)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_datasource_model
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        datasource = await service.get_datasource(sample_datasource_model.name)

        assert datasource is not None
        assert datasource.name == sample_datasource_model.name

    @pytest.mark.asyncio
    @patch("dm_mcp.services.datasource_service.get_async_session")
    async def test_get_datasource_by_id(
        self, mock_get_session, mock_settings, pool_config, sample_datasource_model
    ):
        """测试通过 ID 获取数据源"""
        service = DataSourceService(mock_settings, pool_config)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_datasource_model
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        datasource = await service.get_datasource_by_id(sample_datasource_model.id)

        assert datasource is not None
        assert datasource.id == sample_datasource_model.id

    @pytest.mark.asyncio
    @patch("dm_mcp.services.datasource_service.get_async_session")
    async def test_get_datasource_not_found(
        self, mock_get_session, mock_settings, pool_config
    ):
        """测试获取不存在的数据源"""
        service = DataSourceService(mock_settings, pool_config)

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        datasource = await service.get_datasource("nonexistent")

        assert datasource is None


# ============================================================
# DataSourceService 验证测试
# ============================================================
class TestDataSourceServiceValidation:
    """测试数据源验证"""

    def test_validate_datasources_empty(self, mock_settings, pool_config):
        """测试空数据源列表验证通过"""
        service = DataSourceService(mock_settings, pool_config)
        # 空列表不应该抛出异常
        service._validate_datasources([])

    def test_validate_datasources_unique_names(self, mock_settings, pool_config):
        """测试唯一名称验证"""
        service = DataSourceService(mock_settings, pool_config)

        configs = [
            DataSourceConfig(
                id=uuid.uuid4(),
                name="ds1",
                enabled=True,
                deploy_type="dmstandonle",
                read_only=False,
                dsn="",
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("pass"),
                minsize=1,
                maxsize=10,
                timeout=30.0,
                weight=1,
            ),
            DataSourceConfig(
                id=uuid.uuid4(),
                name="ds2",
                enabled=True,
                deploy_type="dmstandonle",
                read_only=False,
                dsn="",
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("pass"),
                minsize=1,
                maxsize=10,
                timeout=30.0,
                weight=1,
            ),
        ]

        service._validate_datasources(configs)  # 不应该抛出异常

    def test_validate_datasources_duplicate_names(self, mock_settings, pool_config):
        """测试重复名称验证失败"""
        service = DataSourceService(mock_settings, pool_config)

        configs = [
            DataSourceConfig(
                id=uuid.uuid4(),
                name="ds1",
                enabled=True,
                deploy_type="dmstandonle",
                read_only=False,
                dsn="",
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("pass"),
                minsize=1,
                maxsize=10,
                timeout=30.0,
                weight=1,
            ),
            DataSourceConfig(
                id=uuid.uuid4(),
                name="ds1",  # 重复名称
                enabled=True,
                deploy_type="dmstandonle",
                read_only=False,
                dsn="",
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("pass"),
                minsize=1,
                maxsize=10,
                timeout=30.0,
                weight=1,
            ),
        ]

        with pytest.raises(ValueError) as exc_info:
            service._validate_datasources(configs)

        assert "唯一" in str(exc_info.value)


# ============================================================
# DataSourceService 数据转换测试
# ============================================================
class TestDataSourceServiceConversion:
    """测试数据转换方法"""

    def test_config_to_model(
        self, mock_settings, pool_config, sample_datasource_config
    ):
        """测试 Config 到 Model 转换"""
        service = DataSourceService(mock_settings, pool_config)

        model = service._config_to_model(sample_datasource_config)

        assert model.id == sample_datasource_config.id
        assert model.name == sample_datasource_config.name
        assert model.host == sample_datasource_config.host

    def test_model_to_config(self, mock_settings, pool_config, sample_datasource_model):
        """测试 Model 到 Config 转换"""
        service = DataSourceService(mock_settings, pool_config)

        config = service._model_to_config(sample_datasource_model)

        assert config.id == sample_datasource_model.id
        assert config.name == sample_datasource_model.name
        assert config.host == sample_datasource_model.host

    def test_model_to_config_invalid_deploy_type(
        self, mock_settings, pool_config, sample_datasource_model
    ):
        """测试无效 deploy_type 转换失败"""
        service = DataSourceService(mock_settings, pool_config)
        sample_datasource_model.deploy_type = "invalid_type"

        with pytest.raises(ValueError) as exc_info:
            service._model_to_config(sample_datasource_model)

        assert "无效" in str(exc_info.value)


# ============================================================
# DataSourceServiceFactory 测试
# ============================================================
class TestDataSourceServiceFactory:
    """测试 DataSourceServiceFactory"""

    def test_metadata(self):
        """测试 factory metadata"""
        factory = DataSourceServiceFactory()
        metadata = factory.metadata()

        assert metadata.name == "datasource_service"
        assert metadata.service_type == DataSourceService

    def test_create(self, mock_settings, pool_config):
        """测试创建服务实例"""
        factory = DataSourceServiceFactory()
        mock_settings.pool = pool_config

        service = factory.create(mock_settings)

        assert isinstance(service, DataSourceService)
        assert service.settings == mock_settings


# ============================================================
# DataSourceService 添加操作测试
# ============================================================
class TestDataSourceServiceAdd:
    """测试 add_datasource 方法"""

    @pytest.mark.asyncio
    async def test_add_datasource_success(self, service_settings, pool_config):
        """测试添加数据源成功"""
        from unittest.mock import AsyncMock, MagicMock, patch

        # 创建 mock session
        mock_session = MagicMock()
        mock_result = MagicMock()

        # 第一次查询：检查名称是否重复 → 返回空
        # 第二次查询：获取所有数据源 → 返回空列表
        # 后续：session.add
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            new_config = DataSourceConfig(
                name="new_ds",
                enabled=True,
                deploy_type="dmstandonle",
                read_only=False,
                dsn="",
                host="localhost",
                port=5237,
                user="SYSDBA",
                password=SecretStr("password"),
                minsize=1,
                maxsize=10,
                timeout=30.0,
                weight=1,
            )

            await service.add_datasource(new_config)

    @pytest.mark.asyncio
    async def test_add_datasource_duplicate_name(self, service_settings, pool_config):
        """测试添加数据源 - 名称重复"""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = MagicMock()
        mock_result = MagicMock()

        # 名称检查查询 → 返回已存在
        existing_ds = MagicMock()
        existing_ds.name = "test_ds"
        mock_result.scalar_one_or_none.return_value = existing_ds

        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            new_config = DataSourceConfig(
                name="test_ds",
                enabled=True,
                deploy_type="dmstandonle",
                host="localhost",
                port=5237,
                user="SYSDBA",
                password=SecretStr("password"),
            )

            with pytest.raises(ValueError) as exc_info:
                await service.add_datasource(new_config)

            assert "已存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_add_datasource_validation_error(self, service_settings, pool_config):
        """测试添加数据源 - 验证失败（重复名称在所有数据源中）"""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = MagicMock()
        mock_result = MagicMock()

        # 名称检查 → 无重复（让验证失败）
        mock_result.scalar_one_or_none.return_value = None

        # 获取所有数据源 → 有重复名称
        existing_ds = MagicMock()
        existing_ds.name = "ds1"
        existing_ds.id = uuid.uuid4()
        existing_ds.enabled = True
        existing_ds.deploy_type = "dmstandonle"
        existing_ds.read_only = False
        existing_ds.dsn = ""
        existing_ds.host = "localhost"
        existing_ds.port = 5236
        existing_ds.user = "SYSDBA"
        existing_ds.password = "pass"
        existing_ds.minsize = 1
        existing_ds.maxsize = 10
        existing_ds.timeout = 30.0
        existing_ds.weight = 1
        mock_result.scalars.return_value.all.return_value = [existing_ds]

        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            new_config = DataSourceConfig(
                name="ds1",  # 重复名称
                enabled=True,
                deploy_type="dmstandonle",
                host="localhost",
                port=5238,
                user="SYSDBA",
                password=SecretStr("password"),
            )

            with pytest.raises(ValueError) as exc_info:
                await service.add_datasource(new_config)

            assert "唯一" in str(exc_info.value)


# ============================================================
# DataSourceService 更新操作测试
# ============================================================
class TestDataSourceServiceUpdate:
    """测试 update_datasource 方法"""

    @pytest.mark.asyncio
    async def test_update_datasource_not_found(self, service_settings, pool_config):
        """测试更新数据源 - 数据源不存在"""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            config = DataSourceConfig(
                name="nonexistent",
                enabled=True,
                deploy_type="dmstandonle",
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("password"),
            )

            with pytest.raises(ValueError) as exc_info:
                await service.update_datasource("nonexistent", config)

            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_datasource_name_conflict(self, service_settings, pool_config):
        """测试更新数据源 - 新名称与已存在的数据源冲突"""
        from unittest.mock import AsyncMock, MagicMock, patch

        # 创建不同阶段的 mock 结果
        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:
                # 第一次：查询目标数据源
                target_ds = MagicMock()
                target_ds.name = "target_ds"
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                # 第二次：检查新名称是否已存在
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

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            config = DataSourceConfig(
                name="existing_ds",  # 冲突的名称
                enabled=True,
                deploy_type="dmstandonle",
                host="localhost",
                port=5237,
                user="SYSDBA",
                password=SecretStr("password"),
            )

            with pytest.raises(ValueError) as exc_info:
                await service.update_datasource("target_ds", config)

            assert "已存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_datasource_inplace_success(
        self, service_settings, pool_config
    ):
        """测试更新数据源 - 原地更新成功"""
        from unittest.mock import AsyncMock, MagicMock, patch

        target_ds = MagicMock()
        target_ds.name = "target_ds"
        target_ds.id = uuid.uuid4()

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] in (1, 2):
                # 第一次：查询目标数据源
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

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            config = DataSourceConfig(
                name="target_ds",
                enabled=False,
                deploy_type="dmstandonle",
                host="newhost",
                port=5237,
                user="SYSDBA",
                password=SecretStr("newpassword"),
            )

            await service.update_datasource("target_ds", config)

    @pytest.mark.asyncio
    async def test_update_datasource_rename_success(
        self, service_settings, pool_config
    ):
        """测试更新数据源 - 修改名称成功（删除+新建）"""
        from unittest.mock import AsyncMock, MagicMock, patch

        target_ds = MagicMock()
        target_ds.name = "old_name"
        target_ds.id = uuid.uuid4()

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:
                # 第一次：查询目标数据源
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                # 第二次：检查新名称是否已存在 → 不存在
                mock_result.scalar_one_or_none.return_value = None
            else:
                # 后续：获取所有数据源验证
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

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            config = DataSourceConfig(
                name="new_name",
                enabled=True,
                deploy_type="dmstandonle",
                host="localhost",
                port=5236,
                user="SYSDBA",
                password=SecretStr("password"),
            )

            await service.update_datasource("old_name", config)


# ============================================================
# DataSourceService 删除操作测试
# ============================================================
class TestDataSourceServiceDelete:
    """测试 delete_datasource 方法"""

    @pytest.mark.asyncio
    async def test_delete_datasource_not_found(self, service_settings, pool_config):
        """测试删除数据源 - 数据源不存在"""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            with pytest.raises(ValueError) as exc_info:
                await service.delete_datasource("nonexistent")

            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_normal_datasource(self, service_settings, pool_config):
        """测试删除普通数据源"""
        from unittest.mock import AsyncMock, MagicMock, patch

        target_ds = MagicMock()
        target_ds.name = "to_delete"

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            mock_result = MagicMock()

            if call_count[0] == 1:
                mock_result.scalar_one_or_none.return_value = target_ds
            elif call_count[0] == 2:
                # 查询默认设置 - 返回 None
                mock_result.scalar_one_or_none.return_value = None
            else:
                mock_result.scalars.return_value.all.return_value = []
                mock_result.scalar_one_or_none.return_value = None

            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.delete = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            await service.delete_datasource("to_delete")

    @pytest.mark.asyncio
    async def test_delete_default_datasource(self, service_settings, pool_config):
        """测试删除默认数据源 - 同时清理默认设置"""
        from unittest.mock import AsyncMock, MagicMock, patch

        target_ds = MagicMock()
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
                # 查询默认设置 - 返回设置
                mock_result.scalar_one_or_none.return_value = default_setting
            else:
                mock_result.scalars.return_value.all.return_value = []
                mock_result.scalar_one_or_none.return_value = None

            return mock_result

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_session.delete = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            await service.delete_datasource("default_ds")


# ============================================================
# DataSourceService 启用/禁用操作测试
# ============================================================
class TestDataSourceServiceEnableDisable:
    """测试 enable_datasource 和 disable_datasource 方法"""

    @pytest.mark.asyncio
    async def test_enable_datasource_not_found(self, service_settings, pool_config):
        """测试启用数据源 - 数据源不存在"""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)

            with pytest.raises(ValueError) as exc_info:
                await service.enable_datasource("nonexistent")

            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_enable_datasource_already_enabled(
        self, service_settings, pool_config, mock_db
    ):
        """测试启用数据源 - 已经启用"""
        from unittest.mock import patch

        target_ds = mock_db.add_datasource(
            name="enabled_ds",
            enabled=True,
            host="localhost",
            port=5236,
        )

        mock_db.setup_query_results()

        # 返回已启用的数据源
        converted_config = DataSourceConfig(
            id=target_ds.id,
            name=target_ds.name,
            enabled=True,
            deploy_type=target_ds.deploy_type,
            read_only=target_ds.read_only,
            dsn=target_ds.dsn,
            host=target_ds.host,
            port=target_ds.port,
            user=target_ds.user,
            password=SecretStr(target_ds.password),
            minsize=target_ds.minsize,
            maxsize=target_ds.maxsize,
            timeout=target_ds.timeout,
            weight=target_ds.weight,
        )

        # 模拟 get_datasource 返回
        async def mock_get_datasource(name):
            return converted_config

        service = DataSourceService(service_settings, pool_config)
        service.get_datasource = mock_get_datasource

        # 不应该抛出异常，只是记录日志
        await service.enable_datasource("enabled_ds")

    @pytest.mark.asyncio
    async def test_disable_datasource_already_disabled(
        self, service_settings, pool_config, mock_db
    ):
        """测试禁用数据源 - 已经禁用"""
        from unittest.mock import patch

        target_ds = mock_db.add_datasource(
            name="disabled_ds",
            enabled=False,
            host="localhost",
            port=5236,
        )

        converted_config = DataSourceConfig(
            id=target_ds.id,
            name=target_ds.name,
            enabled=False,
            deploy_type=target_ds.deploy_type,
            read_only=target_ds.read_only,
            dsn=target_ds.dsn,
            host=target_ds.host,
            port=target_ds.port,
            user=target_ds.user,
            password=SecretStr(target_ds.password),
            minsize=target_ds.minsize,
            maxsize=target_ds.maxsize,
            timeout=target_ds.timeout,
            weight=target_ds.weight,
        )

        async def mock_get_datasource(name):
            return converted_config

        service = DataSourceService(service_settings, pool_config)
        service.get_datasource = mock_get_datasource

        await service.disable_datasource("disabled_ds")


# ============================================================
# DataSourceService 默认数据源测试
# ============================================================
class TestDataSourceServiceDefaultSource:
    """测试 get_default_datasource 和 set_default_datasource 方法"""

    @pytest.mark.asyncio
    async def test_get_default_datasource_from_db(self, service_settings, pool_config):
        """测试从数据库获取默认数据源"""
        from unittest.mock import patch, MagicMock, AsyncMock

        mock_setting = MagicMock()
        mock_setting.value = "db_default_ds"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        # 模拟两次查询：第一次查设置返回设置，第二次查数据源存在
        mock_result2 = MagicMock()
        mock_result2.scalar_one_or_none.return_value = MagicMock()  # 数据源存在

        call_count = [0]

        async def execute_side_effect(query):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_result
            return mock_result2

        mock_session.execute = AsyncMock(side_effect=execute_side_effect)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)
            result = await service.get_default_datasource()
            assert result == "db_default_ds"

    @pytest.mark.asyncio
    async def test_get_default_datasource_not_exists(
        self, service_settings, pool_config
    ):
        """测试默认数据源不存在时清理并回退"""
        from unittest.mock import patch, MagicMock, AsyncMock

        mock_setting = MagicMock()
        mock_setting.value = "deleted_ds"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting

        # 设置第二次查询（检查数据源是否存在）返回 None
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
        mock_session.delete = AsyncMock()  # 需要添加 delete 的 mock
        mock_session.commit = AsyncMock()

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)
            # 回退到配置中的默认值
            result = await service.get_default_datasource()
            assert result == "primary"

    @pytest.mark.asyncio
    async def test_get_default_datasource_fallback(self, service_settings, pool_config):
        """测试无数据库配置时回退到默认值"""
        from unittest.mock import patch, MagicMock, AsyncMock

        # 模拟查询返回 None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            service = DataSourceService(service_settings, pool_config)
            result = await service.get_default_datasource()
            # 回退到 pool_config 的 default_source
            assert result == "primary"

    @pytest.mark.asyncio
    async def test_set_default_datasource_not_found(
        self, service_settings, pool_config
    ):
        """测试设置默认数据源 - 数据源不存在"""
        from unittest.mock import patch, MagicMock, AsyncMock

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            # 同时需要 patch get_datasource
            with patch.object(
                DataSourceService,
                "get_datasource",
                new_callable=AsyncMock,
                return_value=None,
            ):
                service = DataSourceService(service_settings, pool_config)

                with pytest.raises(ValueError) as exc_info:
                    await service.set_default_datasource("nonexistent")

                assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_set_default_datasource_success(self, service_settings, pool_config):
        """测试设置默认数据源成功"""
        from unittest.mock import patch, MagicMock, AsyncMock

        # Mock get_datasource 返回存在的数据源
        existing_ds = DataSourceConfig(
            name="existing_ds",
            enabled=True,
            deploy_type="dmstandonle",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # 没有现有设置

        mock_session = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_context = MagicMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "dm_mcp.services.datasource_service.get_async_session",
            return_value=mock_context,
        ):
            with patch.object(
                DataSourceService,
                "get_datasource",
                new_callable=AsyncMock,
                return_value=existing_ds,
            ):
                service = DataSourceService(service_settings, pool_config)
                await service.set_default_datasource("existing_ds")


# ============================================================
# DataSourceService 数据转换测试 - 补充
# ============================================================
class TestDataSourceServiceUpdateModel:
    """测试 _update_model_from_config 方法"""

    def test_update_model_from_config(
        self, service_settings, pool_config, sample_datasource_model
    ):
        """测试使用配置更新模型"""
        service = DataSourceService(service_settings, pool_config)

        new_config = DataSourceConfig(
            id=sample_datasource_model.id,
            name="updated_name",
            enabled=False,
            deploy_type="dmstandonle",
            read_only=True,
            dsn="newdsn",
            host="newhost",
            port=5237,
            user="NEWUSER",
            password=SecretStr("newpassword"),
            minsize=2,
            maxsize=20,
            timeout=60.0,
            weight=5,
        )

        service._update_model_from_config(sample_datasource_model, new_config)

        assert sample_datasource_model.enabled == False
        assert sample_datasource_model.read_only == True
        assert sample_datasource_model.host == "newhost"
        assert sample_datasource_model.port == 5237
        assert sample_datasource_model.user == "NEWUSER"
        assert sample_datasource_model.password == "newpassword"
        assert sample_datasource_model.minsize == 2
        assert sample_datasource_model.maxsize == 20
        assert sample_datasource_model.timeout == 60.0
        assert sample_datasource_model.weight == 5
