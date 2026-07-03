"""Service 层测试专用 fixtures

提供数据库会话的 Mock 工具类，简化异步数据库操作的测试。
"""

import uuid
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from dm_mcp.core.db import AppSettingsModel, DataSourceModel
from dm_mcp.settings import Settings
from dm_mcp.settings.database_config import DatabaseConfig
from dm_mcp.settings.datasource_config import DataSourceConfig
from dm_mcp.settings.pool_config import DmPoolConfig


# ============================================================
# Settings Fixtures
# ============================================================
@pytest.fixture
def service_settings():
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
# MockDBSession 工具类
# ============================================================
class MockDBSession:
    """
    模拟数据库会话的辅助类

    用法:
        mock = MockDBSession()
        mock.add_datasource(name="test", deploy_type="dmstandonle")
        mock.setup_default_datasource("test")

        with patch("module.get_async_session", return_value=mock.create_context()):
            # 运行测试
    """

    def __init__(self):
        self._datasources: List[DataSourceModel] = []
        self._settings: List[AppSettingsModel] = []
        self._session = MagicMock()
        self._result = MagicMock()
        self._execute_calls: List[tuple] = []

        # 设置默认返回
        self._result.scalars.return_value.all.return_value = []
        self._result.scalars.return_value.one_or_none.return_value = None
        self._result.scalar_one_or_none.return_value = None

        # 设置 execute 跟踪调用
        def track_execute(return_value):
            self._execute_calls.append(return_value)
            return return_value

        self._session.execute = AsyncMock(side_effect=track_execute)

    def add_datasource(self, name: str, **kwargs) -> DataSourceModel:
        """添加一个数据源到 mock"""
        ds = DataSourceModel(
            id=kwargs.get("id", uuid.uuid4()),
            name=name,
            enabled=kwargs.get("enabled", True),
            deploy_type=kwargs.get("deploy_type", "dmstandonle"),
            read_only=kwargs.get("read_only", False),
            dsn=kwargs.get("dsn", ""),
            host=kwargs.get("host", "localhost"),
            port=kwargs.get("port", 5236),
            user=kwargs.get("user", "SYSDBA"),
            password=kwargs.get("password", "password"),
            minsize=kwargs.get("minsize", 1),
            maxsize=kwargs.get("maxsize", 10),
            timeout=kwargs.get("timeout", 30.0),
            weight=kwargs.get("weight", 1),
            dpc_cluster=kwargs.get("dpc_cluster", None),
        )
        self._datasources.append(ds)
        return ds

    def add_setting(self, key: str, value: str) -> AppSettingsModel:
        """添加设置项"""
        setting = AppSettingsModel(key=key, value=value)
        self._settings.append(setting)
        return setting

    def setup_query_results(self) -> "MockDBSession":
        """设置查询结果 - 在测试中调用"""
        self._result.scalars.return_value.all.return_value = self._datasources
        self._result.scalar_one_or_none.return_value = None
        return self

    def mock_execute_result(self, result: Any) -> "MockDBSession":
        """自定义 execute 返回结果"""
        self._session.execute = AsyncMock(return_value=result)
        return self

    def mock_scalar_result(self, model: Optional[Any]) -> "MockDBSession":
        """模拟单条查询结果 (scalar_one_or_none)"""
        self._result.scalar_one_or_none.return_value = model
        return self

    def mock_scalars_all(self, models: List[Any]) -> "MockDBSession":
        """模拟多条查询结果 (scalars().all())"""
        self._result.scalars.return_value.all.return_value = models
        return self

    def get_session(self) -> MagicMock:
        return self._session

    def get_execute_calls(self) -> List[tuple]:
        """获取 execute 调用列表，便于验证"""
        return self._execute_calls

    def clear_calls(self) -> "MockDBSession":
        """清除调用记录"""
        self._execute_calls = []
        return self

    def create_async_context(self) -> MagicMock:
        """创建异步上下文管理器"""
        from unittest.mock import AsyncMock

        # 每次创建新的 context 时，创建一个新的 result
        new_result = MagicMock()
        new_result.scalars.return_value.all.return_value = self._datasources.copy()

        # 创建一个可以保存状态的 session
        session = MagicMock()

        # 保存 result 引用以便后续修改
        self._current_result = new_result
        session.execute = AsyncMock(return_value=new_result)

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    def get_result(self):
        """获取当前的结果对象，用于在各测试中配置返回值"""
        return self._current_result


@pytest.fixture
def mock_db():
    """提供预配置的 Mock 数据库会话"""
    return MockDBSession()
