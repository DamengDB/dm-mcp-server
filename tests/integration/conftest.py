"""集成测试配置。"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import FakeEventService

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def patch_db_session():
    """自动 mock get_async_session，避免 MCPService 合并视图访问真实 DB。"""
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    session.flush = AsyncMock()

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("dm_mcp.domain.mcp.services.mcp.get_async_session", return_value=ctx):
        yield


def make_mcp_service(server_config):
    """创建测试用 MCPService 实例（与 unit test 构造方式一致）。"""
    from dm_mcp.domain.mcp.services.mcp import MCPService

    mock_metrics = MagicMock()
    mock_metrics.startup = AsyncMock()
    mock_metrics.shutdown = AsyncMock()

    mock_logging = MagicMock()
    mock_logging.startup = AsyncMock()
    mock_logging.shutdown = AsyncMock()

    return MCPService(
        server_config,
        mock_metrics,
        mock_logging,
        FakeEventService(),
    )
