"""AsyncPoolService 单元测试（重构后）

测试范围：纯连接池管理（无配置/权限耦合）
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from dm_mcp.domain.datasource.events import (
    DataSourceCreated,
    DataSourceDeleted,
    DataSourceUpdated,
)
from dm_mcp.domain.datasource.services.pool import AsyncPoolService, AsyncPoolServiceFactory
from dm_mcp.domain.system.services.metrics import MetricsService
from dm_mcp.infra.persistence import DataSourceModel
from dm_mcp.infra.persistence.pool_config import DmPoolConfig


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_metrics_service():
    """Mock MetricsService"""
    service = MagicMock(spec=MetricsService)
    service.record_dataclass = MagicMock()
    return service


@pytest.fixture
def pool_config():
    return DmPoolConfig(
        enabled=True,
        default_source="primary",
        read_write_split=False,
        load_balancing_strategy="round_robin",
        max_retries=3,
        retry_backoff_ms=100,
    )


@pytest.fixture
def sample_datasource_config():
    return DataSourceModel(
        id=uuid.uuid4(),
        name="primary",
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
# 生命周期
# ============================================================
class TestAsyncPoolServiceLifecycle:
    @pytest.mark.asyncio
    async def test_startup_disabled(self, pool_config, mock_metrics_service):
        config = DmPoolConfig(enabled=False)
        service = AsyncPoolService(mock_metrics_service)
        await service.startup()
        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_startup_empty(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        await service.startup()
        assert service._initialized is True
        assert service._pools == {}

    @pytest.mark.asyncio
    async def test_shutdown(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        mock_pool = MagicMock()
        service._pools["primary"] = mock_pool
        await service.shutdown()
        mock_pool.close.assert_called_once()
        mock_pool.wait_closed.assert_called_once()
        assert service._pools == {}


# ============================================================
# Pool 管理
# ============================================================
class TestAsyncPoolServicePoolManagement:
    @pytest.mark.asyncio
    async def test_add_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._init_single_pool = AsyncMock(return_value=MagicMock())
        await service.add_pool(sample_datasource_config)
        assert "primary" in service._pools

    @pytest.mark.asyncio
    async def test_add_pool_duplicate(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._pools["primary"] = MagicMock()
        with pytest.raises(ValueError, match="已存在"):
            await service.add_pool(sample_datasource_config)

    @pytest.mark.asyncio
    async def test_remove_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        mock_pool = MagicMock()
        mock_pool.size = 0
        mock_pool.freesize = 0
        service._pools["primary"] = mock_pool
        await service.remove_pool("primary")
        assert "primary" not in service._pools

    @pytest.mark.asyncio
    async def test_remove_pool_not_exists(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        with pytest.raises(ValueError, match="不存在"):
            await service.remove_pool("nonexistent")

    @pytest.mark.asyncio
    async def test_reload_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        mock_pool = MagicMock()
        mock_pool.size = 0
        mock_pool.freesize = 0
        service._pools["primary"] = mock_pool
        service._init_single_pool = AsyncMock(return_value=MagicMock())
        await service.reload_pool(sample_datasource_config)
        assert "primary" in service._pools

    @pytest.mark.asyncio
    async def test_reload_all_pools(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._init_single_pool = AsyncMock(return_value=MagicMock())
        result = await service.reload_all_pools([sample_datasource_config])
        assert "created" in result
        assert sample_datasource_config.name in result["created"]

    @pytest.mark.asyncio
    async def test_get_or_create_pool_existing(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        mock_pool = MagicMock()
        service._pools["primary"] = mock_pool
        pool = await service.get_or_create_pool(sample_datasource_config)
        assert pool is mock_pool

    @pytest.mark.asyncio
    async def test_get_or_create_pool_new(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._init_single_pool = AsyncMock(return_value=MagicMock())
        pool = await service.get_or_create_pool(sample_datasource_config)
        assert pool is not None
        assert "primary" in service._pools


# ============================================================
# 查询执行
# ============================================================
class TestAsyncPoolServiceExecute:
    @pytest.mark.asyncio
    async def test_execute_with_params(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)

        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall = AsyncMock(return_value=[(1,)])
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = MagicMock()

        mock_conn = MagicMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_context)

        result = await service.execute(mock_pool, "SELECT 1", {"id": 1})
        assert result == [{"id": 1}]

    @pytest.mark.asyncio
    async def test_execute_with_schema(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)

        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall = AsyncMock(return_value=[(1,)])
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = MagicMock()

        mock_conn = MagicMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_context)

        result = await service.execute(mock_pool, "SELECT 1", schema="TEST")
        # 验证 SET SCHEMA 被执行
        mock_cursor.execute.assert_any_call("SET SCHEMA TEST")

    @pytest.mark.asyncio
    async def test_execute_no_description(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)

        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = MagicMock()

        mock_conn = MagicMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        mock_pool = MagicMock()
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_context)

        result = await service.execute(mock_pool, "INSERT INTO t VALUES(1)")
        assert result == []


# ============================================================
# Pool 状态
# ============================================================
class TestAsyncPoolServicePoolStatus:
    @pytest.mark.asyncio
    async def test_pool_status_empty(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        status = await service.pool_status()
        assert "status" in status
        assert status["status"] == {}

    @pytest.mark.asyncio
    async def test_pool_status_with_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        mock_pool = MagicMock()
        mock_pool.size = 10
        mock_pool.freesize = 8
        mock_pool.minsize = 1
        mock_pool.maxsize = 10
        service._pools["primary"] = mock_pool

        status = await service.pool_status()
        assert "primary" in status["status"]
        info = status["status"]["primary"]
        assert info["status"] == "active"
        assert info["active_connections"] == 2
        assert info["usage_rate"] == 20.0


# ============================================================
# 健康状态
# ============================================================
class TestAsyncPoolServiceHealth:
    def test_determine_pool_health_healthy(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        assert service._determine_pool_health(50.0, False) == "healthy"

    def test_determine_pool_health_warning(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        assert service._determine_pool_health(85.0, False) == "warning"

    def test_determine_pool_health_critical(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        assert service._determine_pool_health(96.0, False) == "critical"
        assert service._determine_pool_health(50.0, True) == "critical"


# ============================================================
# Bytes 转换
# ============================================================
class TestAsyncPoolServiceBytesConversion:
    def test_convert_bytes_string(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        assert service._convert_bytes_for_json("test") == "test"

    def test_convert_bytes_bytes(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        assert service._convert_bytes_for_json(b"test") == "test"

    def test_convert_bytes_list(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        assert service._convert_bytes_for_json([b"a", b"b"]) == ["a", "b"]

    def test_convert_bytes_dict(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        assert service._convert_bytes_for_json({"key": b"value"}) == {"key": "value"}

    def test_convert_bytes_non_utf8(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        result = service._convert_bytes_for_json(b"\xff\xfe")
        assert isinstance(result, str)


# ============================================================
# 连接测试
# ============================================================
class TestAsyncPoolServiceTestConnection:
    @pytest.mark.asyncio
    async def test_test_connection_failure(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._init_single_pool = AsyncMock(side_effect=Exception("Connection refused"))
        result = await service.test_connection(sample_datasource_config)
        assert result["success"] is False


# ============================================================
# 事件处理器
# ============================================================
class TestAsyncPoolServiceEventHandlers:
    @pytest.mark.asyncio
    async def test_on_created_enabled(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service.add_pool = AsyncMock()
        event = DataSourceCreated.from_model(sample_datasource_config)
        await service.on_datasource_created(event)
        service.add_pool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_created_disabled(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service.add_pool = AsyncMock()
        event = DataSourceCreated.from_model(sample_datasource_config).model_copy(update={"enabled": False})
        await service.on_datasource_created(event)
        service.add_pool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_deleted_has_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._pools["primary"] = MagicMock()
        service.remove_pool = AsyncMock()
        event = DataSourceDeleted(name="primary", datasource_id=uuid.uuid4())
        await service.on_datasource_deleted(event)
        service.remove_pool.assert_awaited_once_with("primary")

    @pytest.mark.asyncio
    async def test_on_deleted_no_pool(self, pool_config, mock_metrics_service):
        service = AsyncPoolService(mock_metrics_service)
        service.remove_pool = AsyncMock()
        event = DataSourceDeleted(name="orphan", datasource_id=uuid.uuid4())
        await service.on_datasource_deleted(event)
        service.remove_pool.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_on_updated_rename_enabled_had_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        mock_pool = MagicMock()
        mock_pool._host = sample_datasource_config.host
        mock_pool._port = sample_datasource_config.port
        mock_pool._user = sample_datasource_config.user
        mock_pool._password = sample_datasource_config.password
        mock_pool._dsn = sample_datasource_config.dsn or ""
        service._pools["old_name"] = mock_pool
        service.reload_pool = AsyncMock()

        event = DataSourceUpdated.from_model(
            sample_datasource_config, old_name="old_name"
        ).model_copy(update={"name": "new_name"})
        await service.on_datasource_updated(event)

        service.reload_pool.assert_awaited_once()
        assert "new_name" in service._pools
        assert "old_name" not in service._pools

    @pytest.mark.asyncio
    async def test_on_updated_same_name_enabled_had_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._pools["primary"] = MagicMock()
        service.reload_pool = AsyncMock()
        event = DataSourceUpdated.from_model(sample_datasource_config, old_name="primary")
        await service.on_datasource_updated(event)
        service.reload_pool.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_updated_same_name_disabled_had_pool(self, pool_config, mock_metrics_service, sample_datasource_config):
        service = AsyncPoolService(mock_metrics_service)
        service._pools["primary"] = MagicMock()
        service.remove_pool = AsyncMock()
        event = DataSourceUpdated.from_model(
            sample_datasource_config, old_name="primary"
        ).model_copy(update={"enabled": False})
        await service.on_datasource_updated(event)
        service.remove_pool.assert_awaited_once_with("primary")


# ============================================================
# Factory
# ============================================================
class TestAsyncPoolServiceFactory:
    def test_metadata(self):
        factory = AsyncPoolServiceFactory()
        metadata = factory.metadata()
        assert metadata.name == "async_pool_service"
        assert metadata.service_type == AsyncPoolService
        assert "metrics_service" in metadata.dependencies
        assert "datasource_service" not in metadata.dependencies

    def test_event_subscriptions(self):
        factory = AsyncPoolServiceFactory()
        metadata = factory.metadata()
        subs = metadata.event_subscriptions
        assert len(subs) == 3
        types = {s.event_type for s in subs}
        assert types == {DataSourceCreated, DataSourceUpdated, DataSourceDeleted}
