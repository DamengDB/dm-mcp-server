"""Pytest 配置和共享 fixtures

提供测试中常用的 fixtures，包括 Mock 配置、服务实例等。
"""

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator, TypeVar
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from pydantic import SecretStr

# 添加项目根目录到 Python 路径
# 使用 resolve() 来规范化路径，避免 Windows 路径问题
project_root = Path(__file__).parent.parent.resolve()
src_path = (project_root / "src").resolve()
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from dm_mcp.infra.config import Settings
from dm_mcp.infra.config.database_config import DatabaseConfig
from dm_mcp.infra.config.logging_config import LoggingConfig
from dm_mcp.infra.config.metrics_config import MetricsConfig
from dm_mcp.infra.persistence.pool_config import DmPoolConfig
from dm_mcp.infra.config.server_config import ServerConfig


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环用于异步测试"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_settings(monkeypatch) -> Settings:
    """创建 Mock 配置对象

    注意：使用 monkeypatch 来临时修改 sys.argv，避免 Settings 解析 pytest 的命令行参数
    """
    import sys

    # 保存原始 argv
    original_argv = sys.argv.copy()
    # 临时替换为只包含脚本名，避免解析 pytest 参数
    sys.argv = [sys.argv[0]]

    try:
        # 使用 _env_file=None 来禁用环境变量和命令行参数解析
        settings = Settings(
            _env_file=None,
            app_secret=SecretStr("test-app-secret-for-testing-only"),
            server=ServerConfig(),
            database=DatabaseConfig(),
            metrics=MetricsConfig(),
            logging=LoggingConfig(
                level="DEBUG",
                log_dir=Path("logs"),
                enable_file=False,  # 测试时禁用文件日志
            ),
            pool=DmPoolConfig(),
        )
        return settings
    finally:
        # 恢复原始 argv
        sys.argv = original_argv


@pytest.fixture
def mock_settings_attrs():
    """创建带有可写属性的 Mock Settings

    用于需要修改 settings.server.xxx 等属性的测试
    使用普通 MagicMock 而非 spec=Settings，因为 Pydantic 不允许动态添加属性
    """
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.server.host = "localhost"
    mock.server.port = 18081
    mock.server.debug = False
    mock.server.transport = "stdio"
    mock.server.workers = 1
    mock.server.frontend_url = ""
    mock.server.static_path = "/static"
    mock.metrics.enabled = False
    mock.database.url = "dm://localhost:5236"
    mock.database.db_type = "dm"
    mock.app_secret = MagicMock()
    mock.app_secret.get_secret_value.return_value = "test-app-secret"
    mock.pool.default_source = "primary"
    mock.pool.max_size = 10
    mock.pool.min_size = 1
    mock.logging.level = "INFO"
    mock.to_env = MagicMock(return_value={})
    return mock


@pytest.fixture
def mock_logging_service():
    """创建 Mock 日志服务"""
    service = MagicMock()
    service.startup = AsyncMock()
    service.shutdown = AsyncMock()
    return service


@pytest.fixture
def mock_metrics_service():
    """创建 Mock 指标服务"""
    service = MagicMock()
    service.startup = AsyncMock()
    service.shutdown = AsyncMock()
    service.record_counter = Mock()
    service.record_gauge = Mock()
    service.record_histogram = Mock()
    return service


@pytest.fixture
def mock_datasource_service():
    """创建 Mock 数据源服务"""
    service = MagicMock()
    service.startup = AsyncMock()
    service.shutdown = AsyncMock()
    service.get_data_source = Mock(return_value=None)
    service.list_data_sources = Mock(return_value=[])
    return service


@pytest.fixture
def mock_mcp_group_service():
    """创建 Mock MCP 分组服务（MCPService 依赖）。"""
    service = MagicMock()
    service.startup = AsyncMock()
    service.shutdown = AsyncMock()
    service.assert_paths_exist = AsyncMock()
    return service


@pytest.fixture
def mock_cache_backend():
    """创建 Mock 缓存后端"""
    backend = MagicMock()
    backend.get = AsyncMock(return_value=None)
    backend.set = AsyncMock(return_value=True)
    backend.delete = AsyncMock(return_value=True)
    backend.exists = AsyncMock(return_value=False)
    backend.clear = AsyncMock(return_value=True)
    return backend


@pytest.fixture
def mock_redis_client():
    """创建 Mock Redis 客户端"""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.exists = AsyncMock(return_value=False)
    client.flushdb = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_db_session():
    """创建 Mock 数据库会话"""
    session = MagicMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def mock_mcp_provider():
    """创建 Mock MCP Provider"""
    provider = MagicMock()
    provider.name = "test_provider"
    provider.get_tools = Mock(return_value=[])
    provider.get_resources = Mock(return_value=[])
    provider.get_prompts = Mock(return_value=[])
    provider.call_tool = AsyncMock()
    provider.read_resource = AsyncMock()
    provider.get_prompt = AsyncMock()
    return provider


@pytest.fixture
def sample_user_data():
    """示例用户数据"""
    return {
        "username": "testuser",
        "password": "testpassword",
        "email": "test@example.com",
        "roles": ["user"],
    }


@pytest.fixture
def sample_jwt_token():
    """示例 JWT Token"""
    return "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0dXNlciIsImV4cCI6OTk5OTk5OTk5OX0.test_signature"


@pytest.fixture
def sample_tool_definition():
    """示例 Tool 定义"""
    return {
        "name": "test_tool",
        "description": "A test tool",
        "inputSchema": {
            "type": "object",
            "properties": {
                "param1": {"type": "string"},
                "param2": {"type": "number"},
            },
            "required": ["param1"],
        },
    }


@pytest.fixture
def sample_resource_definition():
    """示例 Resource 定义"""
    return {
        "uri": "test://resource/1",
        "name": "Test Resource",
        "description": "A test resource",
        "mimeType": "application/json",
    }


@pytest.fixture
def sample_prompt_definition():
    """示例 Prompt 定义"""
    return {
        "name": "test_prompt",
        "description": "A test prompt",
        "arguments": [
            {
                "name": "arg1",
                "description": "First argument",
                "required": True,
            }
        ],
    }


@pytest.fixture
def temp_log_dir(tmp_path: Path) -> Path:
    """临时日志目录"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture(autouse=True)
def reset_mocks():
    """自动重置所有 Mock 对象（在每个测试前）"""
    yield
    # 测试后清理（如果需要）


@pytest.fixture
def mock_http_request():
    """Mock HTTP 请求对象"""
    request = MagicMock()
    request.method = "GET"
    request.url = MagicMock()
    request.url.path = "/test"
    request.headers = {}
    request.query_params = {}
    request.json = AsyncMock(return_value={})
    return request


@pytest.fixture
def mock_http_response():
    """Mock HTTP 响应对象"""
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    response.json = Mock(return_value={})
    return response


@pytest.fixture
def mock_async_pool():
    """Mock 异步连接池"""
    pool = MagicMock()
    pool.start = AsyncMock()
    pool.shutdown = AsyncMock()
    pool.get_connection = AsyncMock()
    pool.release_connection = AsyncMock()
    pool.health_check = AsyncMock(return_value=True)
    return pool


# ============================================================
# FakeEventService 测试工具(对照 MockDBSession 模式)
# ============================================================
from dm_mcp.core.events import Event, PublishResult
from dm_mcp.infra.messaging.event import EventService

_FE_E = TypeVar("_FE_E", bound=Event)


class FakeEventService(EventService):
    """测试用 EventService

    继承 EventService 保留 subscribe/publish 行为,额外维护 published 列表。

    使用示例:
        events = FakeEventService()
        service = SomeService(event_service=events)
        await service.do_something()
        events.assert_published(SomeEvent)
    """

    def __init__(self) -> None:
        super().__init__()
        self.published: list[Event] = []

    async def publish(self, event: Event) -> PublishResult:
        self.published.append(event)
        return await super().publish(event)

    async def publish_strict(self, event: Event) -> PublishResult:
        self.published.append(event)
        return await super().publish_strict(event)

    def assert_published(self, event_type: type[_FE_E]) -> _FE_E:
        """断言发布过指定类型的事件,返回最后一次发布的实例"""
        for e in reversed(self.published):
            if isinstance(e, event_type):
                return e  # type: ignore[return-value]
        raise AssertionError(
            f"未发布过 {event_type.__name__} 事件,已发布: "
            f"{[type(e).__name__ for e in self.published]}"
        )

    def assert_published_count(self, event_type: type[Event], expected: int) -> None:
        """断言指定类型事件的发布次数"""
        actual = sum(1 for e in self.published if isinstance(e, event_type))
        if actual != expected:
            raise AssertionError(
                f"事件 {event_type.__name__} 发布次数不符: "
                f"期望 {expected},实际 {actual}"
            )

    def get_events(self) -> list[Event]:
        """获取所有已发布的事件"""
        return self.published

    def reset(self) -> None:
        """清空发布记录"""
        self.published.clear()


@pytest.fixture
def fake_event_service() -> FakeEventService:
    """提供一个 FakeEventService 实例,用于断言事件发布"""
    return FakeEventService()