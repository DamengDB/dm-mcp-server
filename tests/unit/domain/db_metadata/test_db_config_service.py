"""DbConfigService 单元测试 — 覆盖工厂元数据和缓存机制"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from dm_mcp.domain.db_metadata.services.db_config import (
    DbConfigService,
    DbConfigServiceFactory,
    DbMetadataPolicy,
)


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture
def mock_token_service():
    """TokenService 桩"""
    return MagicMock()


@pytest.fixture
def service(mock_token_service):
    """构造 DbConfigService 实例"""
    return DbConfigService(token_service=mock_token_service, settings=None)


# ============================================================
# 缓存机制测试
# ============================================================
class TestDbConfigServiceCache:
    """覆盖 invalidate_cache：按 datasource_id 清理策略缓存"""

    @pytest.mark.asyncio
    async def test_invalidate_cache_removes_entry(self, service):
        """清除指定数据源的缓存条目"""
        ds_id = "ds-123"
        service._policy_cache[ds_id] = (
            DbMetadataPolicy(),
            datetime.now(timezone.utc),
        )
        assert ds_id in service._policy_cache

        await service.invalidate_cache(ds_id)

        assert ds_id not in service._policy_cache

    @pytest.mark.asyncio
    async def test_invalidate_cache_no_entry_is_safe(self, service):
        """缓存中没有该数据源时不应抛异常"""
        await service.invalidate_cache("non-existent")
        # 不抛即视为通过

    @pytest.mark.asyncio
    async def test_invalidate_cache_only_removes_target(self, service):
        """只清空目标数据源的缓存，不影响其它"""
        now = datetime.now(timezone.utc)
        service._policy_cache["ds-target"] = (DbMetadataPolicy(), now)
        service._policy_cache["ds-other"] = (DbMetadataPolicy(), now)

        await service.invalidate_cache("ds-target")

        assert "ds-target" not in service._policy_cache
        assert "ds-other" in service._policy_cache


# ============================================================
# Factory 元数据测试
# ============================================================
class TestDbConfigServiceFactory:
    """工厂元数据校验"""

    def test_metadata_no_event_subscriptions(self):
        """工厂不应声明事件订阅（缓存按 datasource_id，无需 TokenRevoked 清理）"""
        factory = DbConfigServiceFactory()
        meta = factory.metadata()

        assert meta.event_subscriptions == []
