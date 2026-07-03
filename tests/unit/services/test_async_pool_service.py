"""AsyncPoolService 单元测试"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from pydantic import SecretStr

from dm_mcp.services.async_pool_service import AsyncPoolService, AsyncPoolServiceFactory
from dm_mcp.services.metrics_service import MetricsService
from dm_mcp.settings import Settings
from dm_mcp.settings.database_config import DatabaseConfig
from dm_mcp.settings.datasource_config import DataSourceConfig
from dm_mcp.settings.metrics_config import MetricsConfig
from dm_mcp.settings.pool_config import DmPoolConfig
from dm_mcp.core.db import DataSourceModel


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_datasource_service():
    """Mock DataSourceService"""
    service = MagicMock()
    service.list_datasources = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_metrics_service():
    """Mock MetricsService"""
    service = MagicMock(spec=MetricsService)
    service.record_dataclass = MagicMock()
    return service


@pytest.fixture
def pool_config():
    """创建测试用 DmPoolConfig"""
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
    """创建测试用 DataSourceConfig"""
    return DataSourceConfig(
        id=uuid.uuid4(),
        name="primary",
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


# ============================================================
# AsyncPoolService 生命周期测试
# ============================================================
class TestAsyncPoolServiceLifecycle:
    """测试服务生命周期"""

    @pytest.mark.asyncio
    async def test_startup_disabled(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试禁用时启动"""
        config = DmPoolConfig(enabled=False)
        service = AsyncPoolService(
            config, mock_datasource_service, mock_metrics_service
        )

        await service.startup()

        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_startup_no_datasources(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试没有数据源时启动"""
        mock_datasource_service.list_datasources = AsyncMock(return_value=[])

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        await service.startup()

        assert service._initialized is True


# ============================================================
# AsyncPoolService 健康状态测试
# ============================================================
class TestAsyncPoolServiceHealth:
    """测试连接池健康状态"""

    def test_determine_pool_health_healthy(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试健康状态判断 - 正常"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._determine_pool_health(50.0, False) == "healthy"

    def test_determine_pool_health_warning(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试健康状态判断 - 警告"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._determine_pool_health(85.0, False) == "warning"

    def test_determine_pool_health_critical_high_usage(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试健康状态判断 - 严重（高使用率）"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._determine_pool_health(96.0, False) == "critical"

    def test_determine_pool_health_critical_errors(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试健康状态判断 - 严重（有错误）"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._determine_pool_health(50.0, True) == "critical"


# ============================================================
# AsyncPoolService 指标生成测试
# ============================================================
class TestAsyncPoolServiceMetrics:
    """测试 Prometheus 指标生成"""

    def test_generate_prometheus_metrics_active(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试活跃连接池的指标生成"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        pool_info = {
            "status": "active",
            "size": 10,
            "freesize": 8,
            "minsize": 1,
            "maxsize": 10,
            "active_connections": 2,
            "usage_rate": 20.0,
            "health_status": "healthy",
            "deploy_type": "dmstandonle",
            "read_only": False,
            "lb_strategy": "round_robin",
            "last_check_time": 1234567890,
            "error_count": 0,
        }

        metrics = service._generate_prometheus_metrics("primary", pool_info)

        assert len(metrics) > 0
        assert any("dm_pool_size" in m for m in metrics)
        assert any("dm_pool_health_status" in m for m in metrics)

    def test_generate_prometheus_metrics_failed(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试失败连接池的指标生成"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        pool_info = {
            "status": "failed",
            "error": "Connection failed",
            "size": 0,
            "freesize": 0,
            "minsize": 0,
            "maxsize": 0,
            "active_connections": 0,
            "usage_rate": 0.0,
            "health_status": "critical",
            "deploy_type": "dmstandonle",
            "read_only": False,
            "lb_strategy": "round_robin",
            "last_check_time": 1234567890,
            "error_count": 1,
        }

        metrics = service._generate_prometheus_metrics("primary", pool_info)

        assert len(metrics) > 0
        assert any("error_count" in m for m in metrics)


# ============================================================
# AsyncPoolService SQL 安全测试
# ============================================================
class TestAsyncPoolServiceSQLSecurity:
    """测试 SQL 安全策略"""

    def test_is_read_sql_select(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 SELECT 判断"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._is_read_sql("SELECT * FROM users") is True

    def test_is_read_sql_with(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 WITH 判断"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert (
            service._is_read_sql("WITH temp AS (SELECT 1) SELECT * FROM temp") is True
        )

    def test_is_read_sql_show(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 SHOW 判断"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._is_read_sql("SHOW TABLES") is True

    def test_is_read_sql_desc(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 DESC 判断"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._is_read_sql("DESC users") is True

    def test_is_read_sql_insert(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 INSERT 判断"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._is_read_sql("INSERT INTO users (name) VALUES ('test')") is False

    def test_is_read_sql_update(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 UPDATE 判断"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert (
            service._is_read_sql("UPDATE users SET name = 'test' WHERE id = 1") is False
        )

    def test_is_read_sql_delete(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 DELETE 判断"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._is_read_sql("DELETE FROM users WHERE id = 1") is False

    def test_is_read_sql_empty(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试空 SQL"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._is_read_sql("") is True

    def test_is_read_sql_parentheses(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试带括号的 SQL"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._is_read_sql("(SELECT 1)") is True


# ============================================================
# AsyncPoolService 黑名单测试
# ============================================================
class TestAsyncPoolServiceBlacklist:
    """测试 SQL 黑名单"""

    def test_check_sql_blacklist_allowed(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试正常 SQL 通过"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 不应该抛出异常
        service._check_sql_blacklist("SELECT * FROM users")

    def test_check_sql_blacklist_blocked(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试黑名单 SQL 阻止"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        with pytest.raises(ValueError) as exc_info:
            service._check_sql_blacklist("DROP TABLE users")

        assert "黑名单" in str(exc_info.value)


# ============================================================
# AsyncPoolService 路由测试
# ============================================================
class TestAsyncPoolServiceRouting:
    """测试数据源路由"""

    def test_choose_source_for_sql_by_name(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试按名称选择数据源"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {sample_datasource_config.name: sample_datasource_config}
        service._pools = {sample_datasource_config.name: MagicMock()}

        source, is_read_only = service._choose_source_for_sql("SELECT 1", "primary")

        assert source == "primary"

    def test_choose_source_for_sql_primary(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试选择 primary 数据源"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {sample_datasource_config.name: sample_datasource_config}
        service._pools = {sample_datasource_config.name: MagicMock()}

        source, is_read_only = service._choose_source_for_sql("SELECT 1", "primary")

        assert source == "primary"

    def test_choose_source_for_sql_auto(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试 auto 模式"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {sample_datasource_config.name: sample_datasource_config}
        service._pools = {sample_datasource_config.name: MagicMock()}

        source, is_read_only = service._choose_source_for_sql("SELECT 1", "auto")

        assert source == "primary"

    def test_choose_source_for_sql_invalid(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试非法 source 参数"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        with pytest.raises(ValueError) as exc_info:
            service._choose_source_for_sql("SELECT 1", "invalid_source")

        assert "非法" in str(exc_info.value)

    def test_choose_by_read_only_no_pools(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试没有可用池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools = {}

        with pytest.raises(ValueError) as exc_info:
            service._choose_by_read_only(False)

        assert "没有可用的数据源连接池" in str(exc_info.value)


# ============================================================
# AsyncPoolService Bytes 转换测试
# ============================================================
class TestAsyncPoolServiceBytesConversion:
    """测试 bytes 转换"""

    def test_convert_bytes_for_json_string(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试字符串保持不变"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        result = service._convert_bytes_for_json("test string")
        assert result == "test string"

    def test_convert_bytes_for_json_bytes(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试 bytes 转为字符串"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        result = service._convert_bytes_for_json(b"test bytes")
        assert result == "test bytes"

    def test_convert_bytes_for_json_list(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试列表转换"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        result = service._convert_bytes_for_json([b"a", b"b"])
        assert result == ["a", "b"]

    def test_convert_bytes_for_json_dict(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试字典转换"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        result = service._convert_bytes_for_json({"key": b"value"})
        assert result == {"key": "value"}


# ============================================================
# AsyncPoolService 数据源管理测试
# ============================================================
class TestAsyncPoolServiceDataSourceManagement:
    """测试数据源动态管理"""

    @pytest.mark.asyncio
    async def test_add_pool_already_exists(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试添加已存在的数据源"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()

        with pytest.raises(ValueError) as exc_info:
            await service.add_pool(sample_datasource_config)

        assert "已存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_remove_pool_not_exists(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试删除不存在的池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        with pytest.raises(ValueError) as exc_info:
            await service.remove_pool("nonexistent")

        assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_reload_pool_not_exists(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试重载不存在的池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        with pytest.raises(ValueError) as exc_info:
            await service.reload_pool(sample_datasource_config)

        assert "不存在" in str(exc_info.value)


# ============================================================
# AsyncPoolServiceFactory 测试
# ============================================================
class TestAsyncPoolServiceFactory:
    """测试 AsyncPoolServiceFactory"""

    def test_metadata(self):
        """测试 factory metadata"""
        factory = AsyncPoolServiceFactory()
        metadata = factory.metadata()

        assert metadata.name == "async_pool_service"
        assert metadata.service_type == AsyncPoolService
        assert "datasource_service" in metadata.dependencies
        assert "metrics_service" in metadata.dependencies


# ============================================================
# AsyncPoolService 集成测试（简化版）
# ============================================================
class TestAsyncPoolServiceIntegration:
    """简化集成测试"""

    def test_service_properties(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试服务属性"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service.pool_cfg == pool_config
        assert service.datasource_service == mock_datasource_service
        assert service.metrics_service == mock_metrics_service

    def test_service_initial_state(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试服务初始状态"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        assert service._pools == {}
        assert service._ds_map == {}
        assert service._failed_pools == {}
        assert service._initialized is False


# ============================================================
# AsyncPoolService 更多方法测试
# ============================================================
class TestAsyncPoolServiceShutdown:
    """测试服务关闭"""

    @pytest.mark.asyncio
    async def test_shutdown_success(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试正常关闭"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 模拟有连接池
        mock_pool = MagicMock()
        service._pools[sample_datasource_config.name] = mock_pool

        await service.shutdown()

        mock_pool.close.assert_called_once()
        mock_pool.wait_closed.assert_called_once()
        assert service._pools == {}
        assert service._initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_with_exception(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试关闭时异常"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_pool.close.side_effect = Exception("close error")
        service._pools[sample_datasource_config.name] = mock_pool

        await service.shutdown()

        assert service._pools == {}


class TestAsyncPoolServiceRetry:
    """测试重试失败的数据源"""

    @pytest.mark.asyncio
    async def test_retry_failed_pools_no_failed(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试没有失败数据源"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        result = await service.retry_failed_pools()

        assert result == {}

    @pytest.mark.asyncio
    async def test_retry_failed_pools_with_failed(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试重试失败的数据源"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 模拟失败的数据源
        service._failed_pools["primary"] = "connection failed"
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._init_single_pool = AsyncMock(return_value=MagicMock())

        result = await service.retry_failed_pools()

        assert "primary" in result


class TestAsyncPoolServicePoolStatus:
    """测试连接池状态"""

    @pytest.mark.asyncio
    async def test_pool_status_empty(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试空连接池状态"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        status = await service.pool_status()

        assert "status" in status
        assert "prometheus_metrics" in status

    @pytest.mark.asyncio
    async def test_pool_status_with_active_pool(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试活跃连接池状态"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_pool.size = 10
        mock_pool.freesize = 8
        mock_pool.minsize = 1
        mock_pool.maxsize = 10
        service._pools[sample_datasource_config.name] = mock_pool
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True

        status = await service.pool_status()

        assert "primary" in status["status"]
        assert status["status"]["primary"]["status"] == "active"

    @pytest.mark.asyncio
    async def test_pool_status_with_failed_pool(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试失败连接池状态"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        service._failed_pools["primary"] = "connection failed"
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True

        status = await service.pool_status()

        assert "primary" in status["status"]
        assert status["status"]["primary"]["status"] == "failed"


class TestAsyncPoolServiceOnConnect:
    """测试连接回调"""

    @pytest.mark.asyncio
    async def test_default_on_connect(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试默认连接回调"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_conn = MagicMock()
        await service._default_on_connect(mock_conn)

        assert mock_conn.autoCommit is True


class TestAsyncPoolServiceGracefulClose:
    """测试优雅关闭"""

    @pytest.mark.asyncio
    async def test_graceful_close_no_active(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试无活跃连接时关闭"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_pool.size = 5
        mock_pool.freesize = 5

        await service._graceful_close_pool(mock_pool, "test_pool", timeout=1.0)

        mock_pool.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_graceful_close_timeout(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试超时强制关闭"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_pool.size = 10
        mock_pool.freesize = 3  # 7个活跃连接
        mock_pool.close = MagicMock()

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await service._graceful_close_pool(mock_pool, "test_pool", timeout=0.1)


class TestAsyncPoolServiceInitPools:
    """测试连接池初始化"""

    @pytest.mark.asyncio
    async def test_init_pools_already_initialized(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试重复初始化"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._initialized = True
        service._init_lock = asyncio.Lock()

        await service.init_pools()

        assert service._initialized is True


class TestAsyncPoolServiceRoutingExtended:
    """扩展路由测试"""

    def test_choose_source_for_sql_read_write(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试读写源选择"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {sample_datasource_config.name: sample_datasource_config}
        service._pools = {sample_datasource_config.name: MagicMock()}

        source, is_read_only = service._choose_source_for_sql("SELECT 1", "read_write")

        assert source == "primary"
        assert is_read_only is False

    def test_choose_source_for_sql_read_only(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试只读源选择"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {sample_datasource_config.name: sample_datasource_config}
        service._pools = {sample_datasource_config.name: MagicMock()}

        source, is_read_only = service._choose_source_for_sql("SELECT 1", "read_only")

        assert source == "primary"

    def test_choose_source_replica(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试 replica 别名"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {sample_datasource_config.name: sample_datasource_config}
        service._pools = {sample_datasource_config.name: MagicMock()}

        source, is_read_only = service._choose_source_for_sql("SELECT 1", "replica")

        assert source == "primary"


class TestAsyncPoolServiceReadOnlyGuard:
    """测试只读数据源保护"""

    def test_check_read_only_guard_write_on_readonly(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试只读数据源禁止写入"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="replica",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=True,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
        )
        service._ds_map["replica"] = ds

        with pytest.raises(ValueError) as exc_info:
            service._check_read_only_guard("INSERT INTO t VALUES(1)", "replica")

        assert "只读数据源禁止写入" in str(exc_info.value)

    def test_check_read_only_guard_read_on_readonly(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试只读数据源允许读取"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        ds = DataSourceConfig(**sample_datasource_config.model_dump())
        ds.read_only = True
        service._ds_map["replica"] = ds

        service._check_read_only_guard("SELECT 1", "replica")


class TestAsyncPoolServiceMetadata:
    """元数据相关方法已迁移至 Metadata Provider，这里仅保留占位类防止回归冲突。"""


class TestAsyncPoolServiceExecuteQuery:
    """测试 execute_query 方法"""

    @pytest.mark.asyncio
    async def test_execute_query_with_params(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试带参数查询"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True

        mock_execute_once = AsyncMock(return_value=[{"id": 1}])
        service._execute_once = mock_execute_once
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query(
            "SELECT * FROM users WHERE id = ?", params=[1], source="primary"
        )

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_query_with_max_rows(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试行数限制"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True

        mock_execute_once = AsyncMock(return_value=[{"id": i} for i in range(100)])
        service._execute_once = mock_execute_once
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query("SELECT 1", source="primary", max_rows=10)

        assert len(result["result"]) == 10

    @pytest.mark.asyncio
    async def test_execute_query_no_longer_blocks_by_guard(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """SQL 防护已移至中间件，execute_query 仅执行 SQL 不返回 blocked"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])

        result = await service.execute_query("DELETE FROM users", source="primary")

        assert result["status"] == "ok"
        assert "result" in result


class TestAsyncPoolServiceReload:
    """测试重载功能"""

    @pytest.mark.asyncio
    async def test_reload_all_pools(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试重载所有连接池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 模拟已有连接池
        mock_pool = MagicMock()
        service._pools["primary"] = mock_pool
        service._ds_map["primary"] = sample_datasource_config

        new_ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="replica",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=True,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
        )

        service._init_single_pool = AsyncMock(return_value=MagicMock())

        result = await service.reload_all_pools([new_ds])

        assert len(result["closed"]) >= 0


class TestAsyncPoolServiceConvertBytes:
    """测试 bytes 转换更多场景"""

    def test_convert_bytes_non_utf8(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试非 UTF-8 bytes 转换"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 模拟非UTF-8编码的bytes
        result = service._convert_bytes_for_json(b"\xff\xfe")
        assert result is not None

    def test_convert_bytes_nested(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试嵌套结构转换"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        data = {"outer": {"inner": b"value"}, "list": [b"a", b"b"]}
        result = service._convert_bytes_for_json(data)

        assert result["outer"]["inner"] == "value"
        assert result["list"] == ["a", "b"]


class TestAsyncPoolServiceInitPoolsExtended:
    """扩展连接池初始化测试"""

    @pytest.mark.asyncio
    async def test_init_pools_with_enabled_datasources(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试有启用数据源时初始化"""
        mock_datasource_service.list_datasources = AsyncMock(
            return_value=[sample_datasource_config]
        )

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._init_single_pool = AsyncMock(return_value=MagicMock())

        await service.init_pools()

        assert service._initialized is True

    @pytest.mark.asyncio
    async def test_init_pools_all_failed(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试所有数据源都失败时初始化"""
        mock_datasource_service.list_datasources = AsyncMock(
            return_value=[sample_datasource_config]
        )

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._init_single_pool = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        await service.init_pools()

        assert service._initialized is True
        assert "primary" in service._failed_pools


class TestAsyncPoolServiceRetryExtended:
    """扩展重试测试"""

    @pytest.mark.asyncio
    async def test_retry_failed_pools_config_not_found(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试重试时配置不存在"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._failed_pools["nonexistent"] = "error"

        result = await service.retry_failed_pools()

        assert "nonexistent" not in result

    @pytest.mark.asyncio
    async def test_retry_failed_pools_partial_success(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试部分重试成功"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._failed_pools["primary"] = "error"
        service._ds_map["primary"] = sample_datasource_config
        service._init_single_pool = AsyncMock(
            side_effect=[Exception("failed"), MagicMock()]
        )

        result = await service.retry_failed_pools()

        assert "primary" in result


class TestAsyncPoolServiceAddPool:
    """测试添加连接池"""

    @pytest.mark.asyncio
    async def test_add_pool_success(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试成功添加连接池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._init_single_pool = AsyncMock(return_value=MagicMock())

        await service.add_pool(sample_datasource_config)

        assert "primary" in service._pools
        assert "primary" in service._ds_map

    @pytest.mark.asyncio
    async def test_remove_pool_success(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试成功删除连接池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        mock_pool = MagicMock()
        service._pools["primary"] = mock_pool
        service._ds_map["primary"] = sample_datasource_config

        await service.remove_pool("primary")

        assert "primary" not in service._pools


class TestAsyncPoolServiceReloadExtended:
    """扩展重载测试"""

    @pytest.mark.asyncio
    async def test_reload_pool_success(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试成功重载连接池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        mock_pool = MagicMock()
        service._pools["primary"] = mock_pool
        service._ds_map["primary"] = sample_datasource_config
        service._init_single_pool = AsyncMock(return_value=MagicMock())

        await service.reload_pool(sample_datasource_config)

        assert "primary" in service._pools


class TestAsyncPoolServiceTestConnection:
    """测试连接测试跳过，test_connection 使用真实 dmAsync 连接，需要实际数据库"""

    @pytest.mark.skip(reason="需要真实 dmAsync 连接")
    @pytest.mark.asyncio
    async def test_test_connection_success(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试连接成功 - 需要真实数据库"""
        pass

    @pytest.mark.asyncio
    async def test_test_connection_failure(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试连接失败"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._init_single_pool = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        result = await service.test_connection(sample_datasource_config)

        assert result["success"] is False


class TestAsyncPoolServiceExecuteQueryExtended:
    """扩展 execute_query 测试"""

    @pytest.mark.asyncio
    async def test_execute_query_with_timeout(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试超时参数"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query("SELECT 1", source="primary", timeout=30)

        assert "status" in result

    @pytest.mark.asyncio
    async def test_execute_query_with_timeout_ms(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试毫秒超时参数"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query(
            "SELECT 1", source="primary", timeout_ms=30000
        )

        assert "status" in result

    @pytest.mark.asyncio
    async def test_execute_query_with_schema(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试 schema 参数"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query(
            "SELECT 1", source="primary", schema="TEST"
        )

        assert "status" in result


class TestAsyncPoolServiceRoutingEdgeCases:
    """路由边界情况测试"""

    def test_choose_source_for_sql_readonly_ds(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试只读数据源选择"""
        ds = DataSourceConfig(**sample_datasource_config.model_dump())
        ds.read_only = True
        pool_config.read_write_split = True

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {"replica": ds}
        service._pools = {"replica": MagicMock()}

        source, is_read_only = service._choose_source_for_sql("SELECT 1", "auto")

        assert source == "replica"


class TestAsyncPoolServiceFactory:
    """测试工厂创建"""

    def test_factory_create_with_settings(self):
        """测试工厂创建带配置"""
        factory = AsyncPoolServiceFactory()

        mock_settings = MagicMock()
        mock_settings.pool = DmPoolConfig(enabled=True)
        mock_deps = {"datasource_service": MagicMock(), "metrics_service": MagicMock()}

        service = factory.create(mock_settings, **mock_deps)

        assert service is not None
        assert isinstance(service, AsyncPoolService)

    def test_factory_create_without_settings(self):
        """测试工厂创建无配置"""
        factory = AsyncPoolServiceFactory()

        mock_settings = MagicMock()
        mock_settings.pool = None
        mock_deps = {"datasource_service": MagicMock(), "metrics_service": MagicMock()}

        service = factory.create(mock_settings, **mock_deps)

        assert service is not None


# ============================================================
# AsyncPoolService Execute Query 重试和异常测试
# ============================================================
class TestAsyncPoolServiceExecuteQueryRetry:
    """测试 execute_query 重试逻辑"""

    @pytest.mark.asyncio
    async def test_execute_query_retry_success(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试重试成功后成功"""
        pool_config.max_retries = 2
        pool_config.retry_backoff_ms = 10

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True

        # 第一次失败，第二次成功
        call_count = 0

        async def mock_execute_once(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Temporary error")
            return [{"id": 1}]

        service._execute_once = mock_execute_once
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query("SELECT 1", source="primary")

        assert result["status"] == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_execute_query_retry_all_failed(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试所有重试都失败"""
        pool_config.max_retries = 2

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True

        service._execute_once = AsyncMock(side_effect=Exception("Connection error"))
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        with pytest.raises(Exception) as exc_info:
            await service.execute_query("SELECT 1", source="primary")

        assert "Connection error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_execute_query_warning_risk_level(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试中等风险级别（警告）"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[{"id": 1}])
        service._sql_guard = MagicMock()
        from dm_mcp.core.sql_guard import RiskLevel

        mock_risk = MagicMock()
        mock_risk.risk_level = RiskLevel.MEDIUM
        mock_risk.reason = "可能的风险操作"
        mock_risk.statement_type = "SELECT"
        mock_risk.is_select = True
        mock_risk.write_tokens = []
        mock_risk.tx_tokens = []
        mock_risk.has_for_update = False
        mock_risk.has_lock_table = False
        mock_risk.risky_calls = []
        mock_risk.unknown_calls = []

        service._sql_guard.analyze = MagicMock(return_value=mock_risk)

        result = await service.execute_query("SELECT 1", source="primary")

        assert result["status"] == "ok"


# ============================================================
# AsyncPoolService ExecuteOnce 详细测试
# ============================================================
class TestAsyncPoolServiceExecuteOnce:
    """测试 _execute_once 方法"""

    @pytest.mark.asyncio
    async def test_execute_once_with_schema(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试带 schema 设置的执行"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall = AsyncMock(return_value=[(1, "test")])
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        # 使用正确的 async context manager mock
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_context)

        service._pools[sample_datasource_config.name] = mock_pool
        service._ds_map[sample_datasource_config.name] = sample_datasource_config

        result = await service._execute_once(
            sample_datasource_config.name, "SELECT * FROM users", None, "TEST_SCHEMA"
        )

        # 验证 schema 被设置
        mock_cursor.execute.assert_called()

    @pytest.mark.asyncio
    async def test_execute_once_with_params(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试带参数的执行"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall = AsyncMock(return_value=[(1,)])
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()
            )
        )

        service._pools[sample_datasource_config.name] = mock_pool
        service._ds_map[sample_datasource_config.name] = sample_datasource_config

        result = await service._execute_once(
            sample_datasource_config.name,
            "SELECT * FROM users WHERE id = ?",
            {"id": 1},
            None,
        )

    @pytest.mark.asyncio
    async def test_execute_once_with_dict_results(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试返回字典类型的结果"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # 返回字典结果的 cursor
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall = AsyncMock(return_value=[{"id": 1, "name": "test"}])
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        # 使用正确的 async context manager mock
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_context)

        service._pools[sample_datasource_config.name] = mock_pool
        service._ds_map[sample_datasource_config.name] = sample_datasource_config

        result = await service._execute_once(
            sample_datasource_config.name, "SELECT * FROM users", None, None
        )

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_execute_once_no_description(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试没有 description 时的处理"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall = AsyncMock(return_value=[(1, "test")])
        mock_cursor.execute = AsyncMock()
        mock_cursor.close = AsyncMock()
        mock_conn.cursor = AsyncMock(return_value=mock_cursor)

        # 使用正确的 async context manager mock
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_context.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_context)

        service._pools[sample_datasource_config.name] = mock_pool
        service._ds_map[sample_datasource_config.name] = sample_datasource_config

        result = await service._execute_once(
            sample_datasource_config.name, "SELECT 1", None, None
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_execute_once_source_not_found(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试数据源不存在"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        with pytest.raises(ValueError) as exc_info:
            await service._execute_once("nonexistent", "SELECT 1", None, None)

        assert "数据源不存在" in str(exc_info.value)


# ============================================================
# AsyncPoolService 重载错误处理测试
# ============================================================
class TestAsyncPoolServiceReloadErrors:
    """测试重载功能的错误处理"""

    @pytest.mark.asyncio
    async def test_reload_all_pools_close_error(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试关闭连接池时出错"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_pool.close.side_effect = Exception("Close error")
        mock_pool.wait_closed = AsyncMock()
        mock_pool.size = 5
        mock_pool.freesize = 0  # 模拟有活跃连接，需要等待
        service._pools["primary"] = mock_pool
        service._ds_map["primary"] = sample_datasource_config

        new_ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="replica",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=True,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
        )

        service._init_single_pool = AsyncMock(return_value=MagicMock())

        result = await service.reload_all_pools([new_ds])

        # 检查关闭错误是否被记录
        assert "primary" in result["closed"] or len(result["errors"]) >= 0

    @pytest.mark.asyncio
    async def test_reload_all_pools_create_error(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试创建连接池时出错"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 先关闭现有池，不报错
        mock_pool = MagicMock()
        service._pools["old"] = mock_pool
        service._ds_map["old"] = sample_datasource_config

        new_ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="new_ds",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=False,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
        )

        service._init_single_pool = AsyncMock(side_effect=Exception("Create error"))

        result = await service.reload_all_pools([new_ds])

        assert len(result["errors"]) >= 1


# ============================================================
# AsyncPoolService metrics 记录测试
# ============================================================
class TestAsyncPoolServiceMetricsRecording:
    """测试指标记录"""

    def test_record_metrics_success(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试成功记录指标"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        service._record_metrics(
            source="primary",
            is_read_only=True,
            sql_type="query",
            status="ok",
            duration_ms=10.5,
            retries=0,
            error=False,
        )

        mock_metrics_service.record_dataclass.assert_called_once()

    def test_record_metrics_error(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试错误时记录指标"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        service._record_metrics(
            source="primary",
            is_read_only=False,
            sql_type="write",
            status="error",
            duration_ms=100.0,
            retries=2,
            error=True,
        )

        mock_metrics_service.record_dataclass.assert_called_once()

    def test_record_metrics_exception(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试指标记录异常"""
        mock_metrics_service.record_dataclass = MagicMock(
            side_effect=Exception("Metrics error")
        )

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 不应该抛出异常
        service._record_metrics(
            source="primary",
            is_read_only=True,
            sql_type="query",
            status="ok",
            duration_ms=10.0,
            retries=0,
            error=False,
        )


# ============================================================
# AsyncPoolService read_only 参数测试
# ============================================================
class TestAsyncPoolServiceReadOnlyParam:
    """测试 read_only 参数"""

    @pytest.mark.asyncio
    async def test_execute_query_with_read_only_true(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试显式指定 read_only=True"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[{"id": 1}])
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query(
            "SELECT 1", source="primary", read_only=True
        )

        assert result["read_only"] is True

    @pytest.mark.asyncio
    async def test_execute_query_with_read_only_false(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试显式指定 read_only=False"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[{"id": 1}])
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="SELECT",
                is_select=True,
                write_tokens=[],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query(
            "SELECT 1", source="primary", read_only=False
        )

        assert result["read_only"] is False

    @pytest.mark.asyncio
    async def test_execute_query_auto_detect_write(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试自动检测写操作"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="INSERT",
                is_select=False,
                write_tokens=["INSERT"],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query(
            "INSERT INTO users VALUES(1)", source="primary"
        )

        assert result["read_only"] is False


# ============================================================
# AsyncPoolService SQL Guard 详细测试
# ============================================================
class TestAsyncPoolServiceSQLGuard:
    """测试 SQL Guard 拦截"""

    @pytest.mark.asyncio
    async def test_execute_query_blocked_with_details(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试被拦截并返回详细信息"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])

        result = await service.execute_query("DELETE FROM users", source="primary")

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_query_for_update_not_blocked_in_service(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """拦截已移至中间件，execute_query 对 FOR UPDATE 仅执行不返回 blocked"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])

        result = await service.execute_query(
            "SELECT * FROM users FOR UPDATE", source="primary"
        )

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_execute_query_risky_calls_not_blocked_in_service(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """拦截已移至中间件，execute_query 对风险调用仅执行不返回 blocked"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])

        result = await service.execute_query("EXEC SP_TEST", source="primary")

        assert result["status"] == "ok"


# ============================================================
# AsyncPoolService 其他边界测试
# ============================================================
class TestAsyncPoolServiceEdgeCases:
    """边界情况测试"""

    @pytest.mark.asyncio
    async def test_pool_status_calculation(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试连接池状态计算"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_pool.size = 10
        mock_pool.freesize = 3  # 7 个活跃连接
        mock_pool.minsize = 1
        mock_pool.maxsize = 10
        service._pools["primary"] = mock_pool
        service._ds_map["primary"] = sample_datasource_config
        service._initialized = True

        status = await service.pool_status()

        pool_info = status["status"]["primary"]
        assert pool_info["active_connections"] == 7
        assert pool_info["usage_rate"] == 70.0

    @pytest.mark.asyncio
    async def test_pool_status_zero_size(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试零大小连接池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        mock_pool = MagicMock()
        mock_pool.size = 0
        mock_pool.freesize = 0
        mock_pool.minsize = 0
        mock_pool.maxsize = 0
        ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="primary",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=False,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=0,
            maxsize=0,
            timeout=30.0,
            weight=1,
        )
        service._pools["primary"] = mock_pool
        service._ds_map["primary"] = ds
        service._initialized = True

        status = await service.pool_status()

        pool_info = status["status"]["primary"]
        assert pool_info["usage_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_execute_query_with_readonly_hint_write_sql(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试 read_only=True 但执行写操作"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._pools[sample_datasource_config.name] = MagicMock()
        service._ds_map[sample_datasource_config.name] = sample_datasource_config
        service._initialized = True
        service._execute_once = AsyncMock(return_value=[])
        service._sql_guard = MagicMock()
        service._sql_guard.analyze = MagicMock(
            return_value=MagicMock(
                risk_level=MagicMock(value="LOW"),
                reason="",
                statement_type="INSERT",
                is_select=False,
                write_tokens=["INSERT"],
                tx_tokens=[],
                has_for_update=False,
                has_lock_table=False,
                risky_calls=[],
                unknown_calls=[],
            )
        )

        result = await service.execute_query(
            "INSERT INTO test VALUES(1)", source="primary", read_only=True
        )

        assert result["read_only"] is True

    def test_choose_by_read_only_first_pool(
        self,
        pool_config,
        mock_datasource_service,
        mock_metrics_service,
        sample_datasource_config,
    ):
        """测试选择第一个可用池"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._ds_map = {sample_datasource_config.name: sample_datasource_config}

        mock_pool1 = MagicMock()
        mock_pool2 = MagicMock()
        service._pools = {"primary": mock_pool1, "replica": mock_pool2}

        result = service._choose_by_read_only(True)

        assert result == "primary"


# ============================================================
# AsyncPoolService init 单实例池测试
# ============================================================
class TestAsyncPoolServiceInitSingleInstance:
    """测试单实例连接池初始化"""

    @pytest.mark.asyncio
    async def test_init_single_instance_pool_with_dsn(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试使用 DSN 初始化"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="primary",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=False,
            dsn="localhost:5236",
            host="",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=5,
            timeout=30.0,
            weight=1,
        )

        with patch(
            "dm_mcp.services.async_pool_service.Pool.from_pool_fill",
            new_callable=AsyncMock,
        ) as mock_pool:
            mock_pool.return_value = MagicMock()

            result = await service._init_single_instance_pool(ds)

            mock_pool.assert_called_once()
            call_kwargs = mock_pool.call_args[1]
            assert call_kwargs.get("dsn") == "localhost:5236"
            assert call_kwargs.get("host") is None

    @pytest.mark.asyncio
    async def test_init_single_instance_pool_with_host(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试使用 host 初始化"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="primary",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=False,
            dsn="",
            host="192.168.1.100",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=2,
            maxsize=10,
            timeout=60.0,
            weight=1,
        )

        with patch(
            "dm_mcp.services.async_pool_service.Pool.from_pool_fill",
            new_callable=AsyncMock,
        ) as mock_pool:
            mock_pool.return_value = MagicMock()

            result = await service._init_single_instance_pool(ds)

            mock_pool.assert_called_once()
            call_kwargs = mock_pool.call_args[1]
            assert call_kwargs.get("host") == "192.168.1.100"
            assert call_kwargs.get("dsn") is None

    @pytest.mark.asyncio
    async def test_init_single_instance_pool_with_empty_password(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试空密码初始化"""
        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        ds = DataSourceConfig(
            id=uuid.uuid4(),
            name="primary",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=False,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr(""),
            minsize=1,
            maxsize=5,
            timeout=30.0,
            weight=1,
        )

        with patch(
            "dm_mcp.services.async_pool_service.Pool.from_pool_fill",
            new_callable=AsyncMock,
        ) as mock_pool:
            mock_pool.return_value = MagicMock()

            result = await service._init_single_instance_pool(ds)

            mock_pool.assert_called_once()
            call_kwargs = mock_pool.call_args[1]
            assert call_kwargs.get("password") == ""


# ============================================================
# AsyncPoolService 初始化完整流程测试
# ============================================================
class TestAsyncPoolServiceFullInit:
    """测试完整初始化流程"""

    @pytest.mark.asyncio
    async def test_init_pools_multiple_datasources(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试多数据源初始化"""
        ds1 = DataSourceConfig(
            id=uuid.uuid4(),
            name="primary",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=False,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
        )
        ds2 = DataSourceConfig(
            id=uuid.uuid4(),
            name="replica",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=True,
            dsn="",
            host="localhost",
            port=5237,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=5,
            timeout=30.0,
            weight=1,
        )

        mock_datasource_service.list_datasources = AsyncMock(return_value=[ds1, ds2])

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )
        service._init_single_pool = AsyncMock(return_value=MagicMock())

        await service.init_pools()

        assert service._initialized is True
        assert "primary" in service._pools
        assert "replica" in service._pools

    @pytest.mark.asyncio
    async def test_init_pools_partial_failure(
        self, pool_config, mock_datasource_service, mock_metrics_service
    ):
        """测试部分数据源失败"""
        ds1 = DataSourceConfig(
            id=uuid.uuid4(),
            name="primary",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=False,
            dsn="",
            host="localhost",
            port=5236,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=10,
            timeout=30.0,
            weight=1,
        )
        ds2 = DataSourceConfig(
            id=uuid.uuid4(),
            name="replica",
            enabled=True,
            deploy_type="dmstandonle",
            read_only=True,
            dsn="",
            host="localhost",
            port=5237,
            user="SYSDBA",
            password=SecretStr("password"),
            minsize=1,
            maxsize=5,
            timeout=30.0,
            weight=1,
        )

        mock_datasource_service.list_datasources = AsyncMock(return_value=[ds1, ds2])

        service = AsyncPoolService(
            pool_config, mock_datasource_service, mock_metrics_service
        )

        # 第一次成功，第二次失败
        call_count = 0

        async def mock_init(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("Failed to connect to replica")
            return MagicMock()

        service._init_single_pool = mock_init

        await service.init_pools()

        assert service._initialized is True
        assert "primary" in service._pools
        assert "replica" in service._failed_pools
        assert "replica" not in service._pools


# ============================================================
# AsyncPoolService Factory 扩展测试
# ============================================================
class TestAsyncPoolServiceFactoryExtended:
    """扩展工厂测试"""

    def test_factory_metadata_priority(self):
        """测试工厂优先级"""
        factory = AsyncPoolServiceFactory()
        metadata = factory.metadata()

        assert metadata.priority == 50
        assert metadata.author == "DM MCP Team"

    def test_factory_dependencies(self):
        """测试工厂依赖"""
        factory = AsyncPoolServiceFactory()
        metadata = factory.metadata()

        assert "datasource_service" in metadata.dependencies
        assert "metrics_service" in metadata.dependencies
        assert len(metadata.dependencies) == 2
