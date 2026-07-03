from unittest.mock import AsyncMock, MagicMock

import pytest

from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.settings.datasource_config import DataSourceConfig
from dm_mcp.settings.pool_config import DmPoolConfig


@pytest.fixture
def async_pool_service(mock_datasource_service, mock_metrics_service):
    pool_cfg = DmPoolConfig(enabled=True)
    service = AsyncPoolService(pool_cfg, mock_datasource_service, mock_metrics_service)
    return service


def _make_fake_pool(size: int, freesize: int, minsize: int, maxsize: int):
    pool = MagicMock()
    pool.size = size
    pool.freesize = freesize
    pool.minsize = minsize
    pool.maxsize = maxsize
    pool.close = MagicMock()
    pool.wait_closed = AsyncMock()
    return pool


@pytest.mark.asyncio
async def test_des_4_tc_01_pool_status_returns_metrics(
    async_pool_service: AsyncPoolService,
):
    """[DM_MCP-des-4] DES-4-TC-01 连接池状态返回结构化运维信息。"""
    ds = DataSourceConfig(name="primary", enabled=True, read_only=False)
    async_pool_service._ds_map = {"primary": ds}
    async_pool_service._pools = {"primary": _make_fake_pool(10, 7, 1, 10)}

    status = await async_pool_service.pool_status()

    assert "status" in status
    assert "prometheus_metrics" in status
    primary = status["status"]["primary"]
    assert primary["size"] == 10
    assert primary["freesize"] == 7
    assert primary["active_connections"] == 3
    assert primary["minsize"] == 1
    assert primary["maxsize"] == 10
    assert primary["health_status"] in {"healthy", "warning", "critical"}
    assert "dm_pool_size" in status["prometheus_metrics"]


@pytest.mark.asyncio
async def test_des_4_tc_02_retry_failed_pools(async_pool_service: AsyncPoolService):
    """[DM_MCP-des-4] DES-4-TC-02 失败连接池的重试逻辑。"""
    ds = DataSourceConfig(name="bad_ds", enabled=True, read_only=False)
    async_pool_service._ds_map = {"bad_ds": ds}
    async_pool_service._failed_pools = {"bad_ds": "init error"}

    # 第一次调用 _init_single_pool 成功
    async_pool_service._init_single_pool = AsyncMock(
        return_value=_make_fake_pool(1, 1, 1, 1)
    )

    results = await async_pool_service.retry_failed_pools()
    assert results == {"bad_ds": True}
    assert "bad_ds" not in async_pool_service._failed_pools
    assert "bad_ds" in async_pool_service._pools


@pytest.mark.parametrize(
    "usage, has_errors, expected",
    [
        (10.0, False, "healthy"),
        (85.0, False, "warning"),
        (96.0, False, "critical"),
        (10.0, True, "critical"),
    ],
)
def test_des_4_tc_03_pool_health_level(async_pool_service, usage, has_errors, expected):
    """[DM_MCP-des-4] DES-4-TC-03 连接池健康状态判定逻辑。"""
    health = async_pool_service._determine_pool_health(usage, has_errors)
    assert health == expected


@pytest.mark.asyncio
async def test_des_4_tc_04_test_connection_success_and_failure(
    async_pool_service: AsyncPoolService,
):
    """[DM_MCP-des-4] DES-4-TC-04 连接测试接口成功与失败路径。"""
    ds = DataSourceConfig(name="test", enabled=True, read_only=False)

    # 成功路径
    fake_pool = MagicMock()
    conn_ctx = MagicMock()
    conn = MagicMock()
    cur = MagicMock()

    conn_ctx.__aenter__ = AsyncMock(return_value=conn)
    conn_ctx.__aexit__ = AsyncMock(return_value=None)
    # acquire 返回异步上下文管理器对象，而不是协程
    fake_pool.acquire = MagicMock(return_value=conn_ctx)
    conn.cursor = AsyncMock(return_value=cur)
    cur.execute = AsyncMock(return_value=None)
    cur.fetchall = AsyncMock(return_value=[(1,)])
    fake_pool.close = MagicMock()
    fake_pool.wait_closed = AsyncMock()

    async_pool_service._init_single_pool = AsyncMock(return_value=fake_pool)

    ok = await async_pool_service.test_connection(ds)
    assert ok["success"] is True

    # 失败路径
    async_pool_service._init_single_pool = AsyncMock(side_effect=RuntimeError("boom"))
    failed = await async_pool_service.test_connection(ds)
    assert failed["success"] is False
    assert "连接测试失败" in failed["message"]
