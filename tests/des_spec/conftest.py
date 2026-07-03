"""des 设计项专用测试配置与基础 fixture。

本目录下的测试仅依赖 src/dm_mcp 代码，不依赖其他 tests 目录的 conftest/fixture，
以保证测试用例在复制出本目录时仍然可运行。
"""

import asyncio
import sys
from pathlib import Path
from typing import Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from dm_mcp.services import DataSourceService, LoggingService, MetricsService
from dm_mcp.settings import Settings
from dm_mcp.settings.database_config import DatabaseConfig
from dm_mcp.settings.datasource_config import DataSourcesConfig
from dm_mcp.settings.jwt_config import JwtConfig
from dm_mcp.settings.logging_config import LoggingConfig
from dm_mcp.settings.metrics_config import MetricsConfig
from dm_mcp.settings.oauth_config import OAuthConfig
from dm_mcp.settings.pool_config import DmPoolConfig
from dm_mcp.settings.server_config import ServerConfig
from dm_mcp.settings.token_auth_config import TokenAuthConfig


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """为 des 目录提供独立的异步事件循环。"""
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


@pytest.fixture
def mock_settings() -> Settings:
    """构造最小可用的 Settings，用于 Service/Controller 初始化。

    这里不依赖全局 tests/conftest.py，完全在本目录内自给自足。
    """
    # 避免 Settings 在初始化时解析 pytest 命令行参数
    original_argv = sys.argv.copy()
    sys.argv = [sys.argv[0]]
    try:
        return Settings(
            _env_file=None,
            server=ServerConfig(),
            database=DatabaseConfig(),
            metrics=MetricsConfig(),
            logging=LoggingConfig(
                level="DEBUG",
                log_dir=Path("tests/logs"),
                enable_file=False,
            ),
            oauth=OAuthConfig(),
            pool=DmPoolConfig(),
            datasources=DataSourcesConfig(),
            token_auth=TokenAuthConfig(),
            jwt=JwtConfig(
                secret=SecretStr("test-secret-key-for-des-spec"),
                token_expire_seconds=3600,
            ),
        )
    finally:
        sys.argv = original_argv


@pytest.fixture
def mock_datasource_service() -> DataSourceService:
    """最小化的数据源服务替身，仅用于被依赖注入。"""
    svc = MagicMock(spec=DataSourceService)
    svc.list_datasources = AsyncMock(return_value=[])
    svc.get_datasource_by_id = AsyncMock(return_value=None)
    return svc  # type: ignore[return-value]


@pytest.fixture
def mock_metrics_service() -> MetricsService:
    """最小化的指标服务替身，屏蔽真实 metrics 上报。"""
    svc = MagicMock(spec=MetricsService)
    svc.record_dataclass = MagicMock()
    return svc  # type: ignore[return-value]


@pytest.fixture
def mock_logging_service() -> LoggingService:
    """最小化的日志服务替身，仅提供审计 logger。"""
    svc = MagicMock(spec=LoggingService)
    audit_logger = MagicMock()
    svc.get_audit_logger.return_value = audit_logger
    return svc  # type: ignore[return-value]
