# 单元测试规划文档

## 测试目录结构

```
tests/
├── __init__.py
├── conftest.py                    # pytest 配置和共享 fixtures
├── README.md                      # 本文档
│
├── unit/                          # 单元测试
│   ├── __init__.py
│   ├── core/                      # 核心模块测试
│   │   ├── test_service_registry.py
│   │   ├── test_service_factory.py
│   │   ├── test_auth_context.py
│   │   ├── test_user.py
│   │   ├── cache/
│   │   │   ├── test_memory_backend.py
│   │   │   └── test_redis_backend.py
│   │   ├── db/
│   │   │   ├── test_models.py
│   │   │   └── test_session.py
│   │   ├── mcp/
│   │   │   ├── test_provider.py
│   │   │   ├── test_tool.py
│   │   │   ├── test_resource.py
│   │   │   ├── test_prompt.py
│   │   │   ├── test_router.py
│   │   │   └── test_middleware.py
│   │   └── metrics/
│   │       ├── test_metrics.py
│   │       └── test_metrics_context.py
│   │
│   ├── services/                  # 服务层测试
│   │   ├── test_base_service.py
│   │   ├── test_logging_service.py
│   │   ├── test_metrics_service.py
│   │   ├── test_jwt_service.py
│   │   ├── test_oauth_service.py
│   │   ├── test_basic_auth_service.py
│   │   ├── test_token_service.py
│   │   ├── test_cache_service.py
│   │   ├── test_datasource_service.py
│   │   ├── test_async_pool_service.py
│   │   └── test_mcp_service.py
│   │
│   ├── providers/                 # 提供者测试
│   │   ├── test_demo_provider.py
│   │   ├── test_function_provider.py
│   │   └── test_pool_provider.py
│   │
│   ├── middlewares/               # 中间件测试
│   │   ├── test_audit_middleware.py
│   │   ├── test_metrics_middleware.py
│   │   └── test_token_auth_middleware.py
│   │
│   ├── server/                    # 服务器模块测试
│   │   ├── controllers/
│   │   │   ├── test_auth_controller.py
│   │   │   ├── test_basic_auth_controller.py
│   │   │   ├── test_config_controller.py
│   │   │   ├── test_datasource_controller.py
│   │   │   ├── test_health_controller.py
│   │   │   ├── test_home_controller.py
│   │   │   ├── test_mcp_controller.py
│   │   │   ├── test_metrics_controller.py
│   │   │   └── test_token_controller.py
│   │   ├── middlewares/
│   │   │   ├── test_audit_http_middleware.py
│   │   │   ├── test_error_handler.py
│   │   │   └── test_utf8_middleware.py
│   │   ├── test_global_context.py
│   │   ├── test_mcp_registry.py
│   │   └── test_routes.py
│   │
│   ├── transport/                 # 传输层测试
│   │   ├── test_base_transport.py
│   │   ├── test_http_transport.py
│   │   └── test_stdio_transport.py
│   │
│   ├── utils/                     # 工具函数测试
│   │   └── test_encoding.py
│   │
│   └── exceptions/                # 异常测试
│       ├── test_base_error.py
│       ├── test_auth_errors.py
│       ├── test_db_errors.py
│       ├── test_service_errors.py
│       └── test_validation_errors.py
│
├── integration/                   # 集成测试
│   ├── __init__.py
│   ├── test_service_integration.py
│   ├── test_auth_flow.py
│   ├── test_mcp_protocol.py
│   └── test_database_connection.py
│
└── fixtures/                      # 测试数据
    ├── __init__.py
    ├── mock_settings.py
    ├── mock_services.py
    └── sample_data.py
```

## 测试覆盖目标

### 1. 核心模块 (core) - 目标覆盖率: 90%+

#### 1.1 服务注册表 (service)
- **test_service_registry.py**
  - 服务工厂注册和获取
  - 依赖解析和循环依赖检测
  - 单例模式验证
  - 懒加载功能
  - 优先级排序
  - 服务生命周期管理

- **test_service_factory.py**
  - 服务元数据定义
  - 服务创建流程
  - 依赖注入验证

#### 1.2 认证模块 (auth)
- **test_auth_context.py**
  - 认证上下文创建和管理
  - 用户信息存储和获取
  - 权限验证

- **test_user.py**
  - 用户模型验证
  - 用户属性访问
  - 用户序列化/反序列化

#### 1.3 缓存模块 (cache)
- **test_memory_backend.py**
  - 内存缓存基本操作（get/set/delete）
  - TTL 过期机制
  - 并发访问安全性

- **test_redis_backend.py**
  - Redis 连接管理
  - Redis 操作封装
  - 连接失败处理
  - 序列化/反序列化

#### 1.4 数据库模块 (db)
- **test_models.py**
  - 数据模型定义验证
  - 模型字段验证
  - 模型关系

- **test_session.py**
  - 数据库会话创建
  - 事务管理
  - 连接池管理

#### 1.5 MCP 协议模块 (mcp)
- **test_provider.py**
  - Provider 注册和发现
  - Provider 方法调用
  - 错误处理

- **test_tool.py**
  - Tool 定义和验证
  - Tool 调用流程
  - 参数验证

- **test_resource.py**
  - Resource 定义
  - Resource URI 匹配
  - Resource 内容获取

- **test_prompt.py**
  - Prompt 定义
  - Prompt 模板渲染
  - 变量替换

- **test_router.py**
  - 路由注册和匹配
  - 路由优先级
  - 路由参数解析

- **test_middleware.py**
  - 中间件链执行
  - 中间件顺序
  - 中间件异常处理

#### 1.6 指标模块 (metrics)
- **test_metrics.py**
  - 指标收集和记录
  - 指标类型（counter, gauge, histogram）
  - 指标聚合

- **test_metrics_context.py**
  - 指标上下文管理
  - 指标标签

### 2. 服务层 (services) - 目标覆盖率: 85%+

#### 2.1 基础服务
- **test_base_service.py**
  - 服务生命周期方法
  - 服务协议实现

#### 2.2 认证服务
- **test_jwt_service.py**
  - JWT Token 生成
  - JWT Token 验证
  - Token 过期处理
  - Token 刷新

- **test_oauth_service.py**
  - OAuth 授权流程
  - Token 交换
  - 用户信息获取

- **test_basic_auth_service.py**
  - 基础认证验证
  - 密码哈希和验证
  - 用户查找

- **test_token_service.py**
  - Token 生成和管理
  - Token 验证
  - Token 撤销

#### 2.3 数据服务
- **test_datasource_service.py**
  - 数据源配置管理
  - 数据源连接测试
  - 数据源列表和查询

- **test_async_pool_service.py**
  - 连接池初始化
  - 连接获取和释放
  - 连接池健康检查
  - 连接池关闭

#### 2.4 其他服务
- **test_logging_service.py**
  - 日志配置
  - 日志级别管理
  - 日志输出

- **test_metrics_service.py**
  - 指标服务初始化
  - 指标收集接口

- **test_cache_service.py**
  - 缓存操作封装
  - Key 前缀管理
  - Pydantic 模型支持
  - 异常安全

- **test_mcp_service.py**
  - MCP 服务初始化
  - Tool/Resource/Prompt 注册
  - Provider 管理
  - 中间件链执行

### 3. 提供者 (providers) - 目标覆盖率: 80%+

- **test_demo_provider.py**
  - Demo Provider 功能验证

- **test_function_provider.py**
  - 函数 Provider 注册
  - 函数调用

- **test_pool_provider.py**
  - 连接池 Provider
  - 数据库查询工具

### 4. 中间件 (middlewares) - 目标覆盖率: 85%+

- **test_audit_middleware.py**
  - 审计日志记录
  - 请求/响应捕获

- **test_metrics_middleware.py**
  - 指标收集
  - 性能监控

- **test_token_auth_middleware.py**
  - Token 验证
  - 用户上下文注入

### 5. 服务器模块 (server) - 目标覆盖率: 80%+

#### 5.1 控制器 (controllers)
- **test_auth_controller.py**
  - 认证端点
  - 登录/登出流程

- **test_basic_auth_controller.py**
  - 基础认证端点

- **test_config_controller.py**
  - 配置查询端点

- **test_datasource_controller.py**
  - 数据源管理端点
  - CRUD 操作

- **test_health_controller.py**
  - 健康检查端点

- **test_home_controller.py**
  - 首页端点

- **test_mcp_controller.py**
  - MCP 协议端点
  - Tool/Resource/Prompt 端点

- **test_metrics_controller.py**
  - 指标查询端点

- **test_token_controller.py**
  - Token 管理端点

#### 5.2 中间件 (middlewares)
- **test_audit_http_middleware.py**
  - HTTP 请求审计
  - 日志记录

- **test_error_handler.py**
  - 错误处理
  - 错误响应格式化

- **test_utf8_middleware.py**
  - 字符编码处理

#### 5.3 其他
- **test_global_context.py**
  - 全局上下文初始化
  - 服务注册和获取

- **test_mcp_registry.py**
  - MCP 注册表管理

- **test_routes.py**
  - 路由注册
  - 路由匹配

### 6. 传输层 (transport) - 目标覆盖率: 75%+

- **test_base_transport.py**
  - 传输基类接口

- **test_http_transport.py**
  - HTTP 传输实现
  - 请求/响应处理

- **test_stdio_transport.py**
  - 标准输入输出传输
  - 消息序列化/反序列化

### 7. 工具函数 (utils) - 目标覆盖率: 90%+

- **test_encoding.py**
  - 编码/解码功能
  - 字符集转换

### 8. 异常 (exceptions) - 目标覆盖率: 95%+

- **test_base_error.py**
  - 基础异常类
  - 异常继承关系

- **test_auth_errors.py**
  - 认证相关异常

- **test_db_errors.py**
  - 数据库相关异常

- **test_service_errors.py**
  - 服务相关异常

- **test_validation_errors.py**
  - 验证相关异常

## 测试工具和框架

### 主要依赖
- **pytest**: 测试框架
- **pytest-asyncio**: 异步测试支持
- **pytest-cov**: 代码覆盖率
- **pytest-mock**: Mock 和 Fixture
- **pytest-xdist**: 并行测试执行

### Mock 库
- **unittest.mock**: Python 标准库 Mock
- **aioresponses**: 异步 HTTP Mock
- **fakeredis**: Redis Mock
- **sqlalchemy-mock**: 数据库 Mock

## 测试最佳实践

### 1. 测试命名规范
- 测试文件: `test_<module_name>.py`
- 测试类: `Test<ClassName>`
- 测试方法: `test_<functionality>_<expected_behavior>`

### 2. 测试结构 (AAA 模式)
```python
def test_example():
    # Arrange - 准备测试数据
    ...
    
    # Act - 执行被测试的操作
    ...
    
    # Assert - 验证结果
    ...
```

### 3. Fixtures 使用
- 在 `conftest.py` 中定义共享 fixtures
- 使用 fixtures 管理测试依赖
- 使用 `@pytest.fixture` 装饰器

### 4. Mock 使用原则
- Mock 外部依赖（数据库、Redis、HTTP 请求等）
- 使用 `pytest-mock` 的 `mocker` fixture
- 验证 Mock 调用次数和参数

### 5. 异步测试
- 使用 `@pytest.mark.asyncio` 标记异步测试
- 使用 `asyncio.create_task` 测试并发场景
- 使用 `asyncio.wait_for` 测试超时

### 6. 参数化测试
- 使用 `@pytest.mark.parametrize` 测试多个场景
- 覆盖边界条件和异常情况

## 测试执行

### 运行所有测试
```bash
pytest
```

### 运行特定模块测试
```bash
pytest tests/unit/services/
```

### 运行并生成覆盖率报告
```bash
pytest --cov=src/dm_mcp --cov-report=html --cov-report=term
```

### 并行运行测试
```bash
pytest -n auto
```

### 运行特定测试
```bash
pytest tests/unit/services/test_jwt_service.py::test_token_generation
```

## 持续集成

### CI/CD 配置建议
- 在 PR 时自动运行测试
- 覆盖率阈值: 80%+
- 测试失败阻止合并
- 生成测试报告和覆盖率报告

## 测试数据管理

### Fixtures 目录
- `fixtures/mock_settings.py`: Mock 配置
- `fixtures/mock_services.py`: Mock 服务
- `fixtures/sample_data.py`: 示例数据

### 测试数据库
- 使用内存数据库（SQLite）进行单元测试
- 使用测试配置文件
- 测试后清理数据

## 优先级

### 第一阶段（高优先级）
1. 核心服务层测试（services）
2. 服务注册表测试（core/service）
3. 认证服务测试（auth, jwt, oauth, basic_auth）
4. MCP 协议核心测试（core/mcp）

### 第二阶段（中优先级）
1. 控制器测试（server/controllers）
2. 中间件测试（middlewares）
3. 缓存和数据库测试（core/cache, core/db）
4. 提供者测试（providers）

### 第三阶段（低优先级）
1. 传输层测试（transport）
2. 工具函数测试（utils）
3. 异常测试（exceptions）
4. 集成测试（integration）

## 注意事项

1. **隔离性**: 每个测试应该独立，不依赖其他测试
2. **可重复性**: 测试结果应该一致，不依赖外部状态
3. **快速执行**: 单元测试应该快速执行（< 1 秒）
4. **清晰性**: 测试代码应该清晰易懂
5. **维护性**: 测试代码应该易于维护和更新

