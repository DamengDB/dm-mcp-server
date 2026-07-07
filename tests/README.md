# 测试说明

## 概述

测试分为两层：**单元测试**与**集成测试**。单元测试使用 Mock，不依赖外部服务；集成测试在进程内启动 ASGI 应用，验证模块协作与 HTTP 接口。

## 测试架构

### 1. 单元测试

- **位置**：`tests/unit/`
- **目的**：验证单个模块的行为
- **特点**：Mock 外部依赖，目录结构与 `src/dm_mcp/` 对应

### 2. 集成测试

- **位置**：`tests/integration/`
- **目的**：验证服务组装、MCP 工作流、认证与 HTTP 端点
- **特点**：使用 `MCPServer` + `httpx.AsyncClient`，共享 fixture 见 `conftest.py`

## 共享 Fixture

根目录 `tests/conftest.py` 提供：

| Fixture | 用途 |
|---------|------|
| `mock_settings` | 测试用 `Settings` |
| `mock_*_service` | 各业务服务 Mock |
| `fake_event_service` | 断言事件发布 |
| `sample_*_definition` | MCP Tool / Resource / Prompt 样例 |

集成测试额外提供 `make_mcp_service()`（见 `tests/integration/conftest.py`），用于按当前 `MCPService` 签名构造实例。

## 运行方式

### 运行全部测试

```bash
pytest
```

### 按层运行

```bash
pytest tests/unit/
pytest tests/integration/
```

### 覆盖率

```bash
pytest --cov=src/dm_mcp --cov-report=html --cov-report=term
```

### 并行

```bash
pytest -n auto
```

### Windows 脚本

```bash
scripts/run_tests.bat
```

## 最佳实践

### 测试隔离

- 单元测试 Mock 数据库、Redis、HTTP 等外部依赖
- 集成测试使用独立 `MCPServer` 实例或 autouse fixture 隔离 DB session

### 异步测试

- 使用 `@pytest.mark.asyncio`
- 集成测试客户端使用 `pytest_asyncio.fixture`

### 断言 API 响应

HTTP 控制器统一返回 `{ "success": true, "data": { ... } }` 结构，集成测试应断言 `data["data"]` 字段。

### 命名规范

- 文件：`test_<module>.py`
- 类：`Test<ClassName>`
- 方法：`test_<行为>_<预期>`

## 故障排查

### ImportError

确认已安装开发依赖：

```bash
uv sync --extra dev
```

### 集成测试数据库错误

`tests/integration/conftest.py` 已 mock `get_async_session`；若新增集成测试直接访问 DB，需补充 mock 或使用内存库。

### Windows 路径

`conftest.py` 使用 `Path.resolve()` 规范化路径，避免 pytest 收集阶段的路径问题。
