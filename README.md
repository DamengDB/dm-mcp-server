# 达梦数据库 MCP 服务

一个基于 Python 构建的模型上下文协议（Model Context Protocol，MCP）服务端项目。


## 功能特性

- **服务启动与管理**: 通过 `main.py` 启动 MCP 服务
- **日志管理**: 支持日志配置、格式化、清理策略和调度任务
- **多传输协议支持**: 提供 HTTP、流式 HTTP 和标准 IO（stdio）等多种通信传输方式
- **工具服务提供机制**: 可注册并调用各类工具类服务，支持动态解析函数

## 安装配置

### 必需工具

- [uv](https://github.com/astral-sh/uv)（必须预先安装）

### 环境搭建

1. 安装 uv: `pip install uv` 或参考官方文档获取二进制版本
2. 克隆项目到本地目录
3. 在项目根目录执行：
   ```bash
   uv sync
   ```
4. 启动项目：
   ```bash
   uv run python main.py
   ```

## 使用方法

启动服务：
```bash
uv run python main.py
```

## Docker 部署

本项目支持使用 Docker 部署。在 Docker/compose 中默认使用 `HTTP` 传输方式启动服务，监听 `18081`，`base_url` 默认为 `/dm-mcp`。

### 一键启动（SQLite 默认可跑通）

```bash
docker compose up --build
```

容器就绪/健康检查建议访问：

```bash
curl -fsS http://localhost:18081/dm-mcp/api/v1/config
```

说明：
- `/dm-mcp/api/v1/health`、`/dm-mcp/api/v1/metrics` 需要鉴权（接口内部使用了 `requires("authenticated")`）
- MCP HTTP 入口为 `/dm-mcp/mcp`

### 外部达梦数据库示例

默认 `docker-compose.yml` 使用 `.env.sqlite.example`。

如需连接外部达梦，请将 `docker-compose.yml` 中的 `env_file` 从：
- `.env.sqlite.example`

改为：
- `.env.external-dameng.example`

然后重新启动：

```bash
docker compose up --build
```

### 参数配置列表

本系统支持通过多种方式配置参数，配置优先级从高到低依次为：

1. **命令行参数**（最高优先级）
2. **环境变量**（ENV）
3. **.env 文件**
4. **Docker secrets 等文件**
5. **默认值**（最低优先级）

**配置格式说明：**

- **命令行参数**：使用 `--` 前缀，嵌套配置使用 `.` 分隔，例如 `--server.port 18081`
- **环境变量**：使用大写字母，嵌套配置使用 `__`（双下划线）分隔，例如 `SERVER__PORT=18081`
- **.env 文件**：格式与环境变量相同，例如 `SERVER__PORT=18081`

**参数配置表：**

#### 服务器配置 (ServerConfig)

| 参数名称         | 类型    | 默认值               | 命令行格式                                    | ENV 格式                                     | 说明                        |
| ---------------- | ------- | -------------------- | --------------------------------------------- | -------------------------------------------- | --------------------------- |
| `host`           | string  | `localhost`          | `--server.host localhost`                     | `SERVER__HOST=localhost`                     | 服务器监听地址              |
| `port`           | integer | `18081`              | `--server.port 18081`                         | `SERVER__PORT=18081`                         | 服务器监听端口（1-65535）   |
| `transport`      | string  | `stdio`              | `--server.transport http`                     | `SERVER__TRANSPORT=http`                     | 传输模式：`stdio` 或 `http` |
| `static_path`    | string  | `./resources/static` | `--server.static_path ./static`               | `SERVER__STATIC_PATH=./static`               | 静态资源路径                |
| `base_url`       | string  | `/dm-mcp`            | `--server.base_url /api`                      | `SERVER__BASE_URL=/api`                      | API 基础路径                |
| `frontend_url`   | string  | `""`                 | `--server.frontend_url http://localhost:3000` | `SERVER__FRONTEND_URL=http://localhost:3000` | 前端地址（可选）            |
| `workers`        | integer | `1`                  | `--server.workers 4`                          | `SERVER__WORKERS=4`                          | Worker 进程数               |
| `session_secret` | string  | `(随机生成)`         | `--server.session_secret your-secret`         | `SERVER__SESSION_SECRET=your-secret`         | 会话密钥                    |
| `debug`          | boolean | `true`               | `--server.debug false`                        | `SERVER__DEBUG=false`                        | 是否启用调试模式            |
| `audit_enabled`  | boolean | `true`               | `--server.audit_enabled false`                | `SERVER__AUDIT_ENABLED=false`                | 是否启用审计日志            |

#### 数据库配置 (DatabaseConfig)

| 参数名称        | 类型    | 默认值   | 命令行格式                       | ENV 格式                        | 说明                                                  |
| --------------- | ------- | -------- | -------------------------------- | ------------------------------- | ----------------------------------------------------- |
| `db_type`       | string  | `sqlite` | `--database.db_type dameng`      | `DATABASE__DB_TYPE=dameng`      | 数据库类型：`sqlite`、`dameng`、`mysql`、`postgresql` |
| `echo`          | boolean | `false`  | `--database.echo true`           | `DATABASE__ECHO=true`           | 是否打印 SQL 语句                                     |
| `pool_pre_ping` | boolean | `true`   | `--database.pool_pre_ping false` | `DATABASE__POOL_PRE_PING=false` | 连接池预检查                                          |

**SQLite 配置：**

| 参数名称         | 类型   | 默认值      | 命令行格式                            | ENV 格式                              | 说明                  |
| ---------------- | ------ | ----------- | ------------------------------------- | ------------------------------------- | --------------------- |
| `sqlite.db_path` | string | `server.db` | `--database.sqlite.db_path ./data.db` | `DATABASE__SQLITE__DB_PATH=./data.db` | SQLite 数据库文件路径 |

**达梦数据库配置：**

| 参数名称          | 类型    | 默认值      | 命令行格式                                 | ENV 格式                                   | 说明                      |
| ----------------- | ------- | ----------- | ------------------------------------------ | ------------------------------------------ | ------------------------- |
| `dameng.host`     | string  | `localhost` | `--database.dameng.host 192.168.1.100`     | `DATABASE__DAMENG__HOST=192.168.1.100`     | 达梦数据库主机地址        |
| `dameng.port`     | integer | `5236`      | `--database.dameng.port 5236`              | `DATABASE__DAMENG__PORT=5236`              | 达梦数据库端口（1-65535） |
| `dameng.user`     | string  | `SYSDBA`    | `--database.dameng.user SYSDBA`            | `DATABASE__DAMENG__USER=SYSDBA`            | 达梦数据库用户名          |
| `dameng.password` | string  | `SYSDBA`    | `--database.dameng.password your-password` | `DATABASE__DAMENG__PASSWORD=your-password` | 达梦数据库密码            |
| `dameng.database` | string  | `""`        | `--database.dameng.database DMMCP`         | `DATABASE__DAMENG__DATABASE=DMMCP`         | 数据库名/模式名（可选）   |

**MySQL 配置：**

| 参数名称         | 类型    | 默认值      | 命令行格式                                | ENV 格式                                  | 说明                  |
| ---------------- | ------- | ----------- | ----------------------------------------- | ----------------------------------------- | --------------------- |
| `mysql.host`     | string  | `localhost` | `--database.mysql.host localhost`         | `DATABASE__MYSQL__HOST=localhost`         | MySQL 主机地址        |
| `mysql.port`     | integer | `3306`      | `--database.mysql.port 3306`              | `DATABASE__MYSQL__PORT=3306`              | MySQL 端口（1-65535） |
| `mysql.user`     | string  | `root`      | `--database.mysql.user root`              | `DATABASE__MYSQL__USER=root`              | MySQL 用户名          |
| `mysql.password` | string  | `""`        | `--database.mysql.password your-password` | `DATABASE__MYSQL__PASSWORD=your-password` | MySQL 密码            |
| `mysql.database` | string  | `DMMCP`     | `--database.mysql.database mydb`          | `DATABASE__MYSQL__DATABASE=mydb`          | MySQL 数据库名        |
| `mysql.charset`  | string  | `utf8mb4`   | `--database.mysql.charset utf8`           | `DATABASE__MYSQL__CHARSET=utf8`           | 字符集                |

**PostgreSQL 配置：**

| 参数名称              | 类型    | 默认值      | 命令行格式                                     | ENV 格式                                       | 说明                       |
| --------------------- | ------- | ----------- | ---------------------------------------------- | ---------------------------------------------- | -------------------------- |
| `postgresql.host`     | string  | `localhost` | `--database.postgresql.host localhost`         | `DATABASE__POSTGRESQL__HOST=localhost`         | PostgreSQL 主机地址        |
| `postgresql.port`     | integer | `5432`      | `--database.postgresql.port 5432`              | `DATABASE__POSTGRESQL__PORT=5432`              | PostgreSQL 端口（1-65535） |
| `postgresql.user`     | string  | `postgres`  | `--database.postgresql.user postgres`          | `DATABASE__POSTGRESQL__USER=postgres`          | PostgreSQL 用户名          |
| `postgresql.password` | string  | `""`        | `--database.postgresql.password your-password` | `DATABASE__POSTGRESQL__PASSWORD=your-password` | PostgreSQL 密码            |
| `postgresql.database` | string  | `DMMCP`     | `--database.postgresql.database mydb`          | `DATABASE__POSTGRESQL__DATABASE=mydb`          | PostgreSQL 数据库名        |

#### 日志配置 (LoggingConfig)

| 参数名称         | 类型    | 默认值    | 命令行格式                         | ENV 格式                          | 说明                                                                       |
| ---------------- | ------- | --------- | ---------------------------------- | --------------------------------- | -------------------------------------------------------------------------- |
| `level`          | string  | `INFO`    | `--logging.level DEBUG`            | `LOGGING__LEVEL=DEBUG`            | 日志级别：`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`                  |
| `log_dir`        | string  | `logs`    | `--logging.log_dir ./logs`         | `LOGGING__LOG_DIR=./logs`         | 日志文件存储目录                                                           |
| `enable_console` | boolean | `true`    | `--logging.enable_console false`   | `LOGGING__ENABLE_CONSOLE=false`   | 是否启用控制台输出                                                         |
| `enable_file`    | boolean | `true`    | `--logging.enable_file false`      | `LOGGING__ENABLE_FILE=false`      | 是否启用文件日志                                                           |
| `enable_audit`   | boolean | `true`    | `--logging.enable_audit false`     | `LOGGING__ENABLE_AUDIT=false`     | 是否启用审计日志                                                           |
| `rotation`       | string  | `10 MB`   | `--logging.rotation "100 MB"`      | `LOGGING__ROTATION="100 MB"`      | 日志切割大小（如 `10 MB`、`500 MB`、`12:00`）                              |
| `retention`      | string  | `30 days` | `--logging.retention "7 days"`     | `LOGGING__RETENTION="7 days"`     | 日志保留时间（如 `1 week`、`30 days`）                                     |
| `compression`    | string  | `zip`     | `--logging.compression gz`         | `LOGGING__COMPRESSION=gz`         | 压缩格式：`zip`、`gz`、`bz2`、`xz`、`lzma`、`tar` 等，设为 `null` 则不压缩 |
| `audit_file`     | string  | `null`    | `--logging.audit_file ./audit.log` | `LOGGING__AUDIT_FILE=./audit.log` | 自定义审计日志路径（可选）                                                 |

#### 指标配置 (MetricsConfig)

| 参数名称        | 类型    | 默认值     | 命令行格式                          | ENV 格式                           | 说明                  |
| --------------- | ------- | ---------- | ----------------------------------- | ---------------------------------- | --------------------- |
| `enabled`       | boolean | `false`    | `--metrics.enabled true`            | `METRICS__ENABLED=true`            | 是否启用指标监控      |
| `multiproc_dir` | string  | `metrics`  | `--metrics.multiproc_dir ./metrics` | `METRICS__MULTIPROC_DIR=./metrics` | Prometheus 多进程目录 |
| `http_port`     | integer | `3001`     | `--metrics.http_port 3001`          | `METRICS__HTTP_PORT=3001`          | 指标 HTTP 服务器端口  |
| `http_path`     | string  | `/metrics` | `--metrics.http_path /metrics`      | `METRICS__HTTP_PATH=/metrics`      | 指标 HTTP 路径        |

#### OAuth 配置 (OAuthConfig)

| 参数名称                        | 类型    | 默认值                           | 命令行格式                                          | ENV 格式                                           | 说明                                            |
| ------------------------------- | ------- | -------------------------------- | --------------------------------------------------- | -------------------------------------------------- | ----------------------------------------------- |
| `enabled`                       | boolean | `false`                          | `--oauth.enabled true`                              | `OAUTH__ENABLED=true`                              | 是否启用 OAuth 认证                             |
| `google_client_id`              | string  | `""`                             | `--oauth.google_client_id your-id`                  | `OAUTH__GOOGLE_CLIENT_ID=your-id`                  | Google OAuth Client ID                          |
| `google_client_secret`          | string  | `""`                             | `--oauth.google_client_secret your-secret`          | `OAUTH__GOOGLE_CLIENT_SECRET=your-secret`          | Google OAuth Client Secret                      |
| `microsoft_client_id`           | string  | `""`                             | `--oauth.microsoft_client_id your-id`               | `OAUTH__MICROSOFT_CLIENT_ID=your-id`               | Microsoft OAuth Client ID                       |
| `microsoft_client_secret`       | string  | `""`                             | `--oauth.microsoft_client_secret your-secret`       | `OAUTH__MICROSOFT_CLIENT_SECRET=your-secret`       | Microsoft OAuth Client Secret                   |
| `github_client_id`              | string  | `""`                             | `--oauth.github_client_id your-id`                  | `OAUTH__GITHUB_CLIENT_ID=your-id`                  | GitHub OAuth Client ID                          |
| `github_client_secret`          | string  | `""`                             | `--oauth.github_client_secret your-secret`          | `OAUTH__GITHUB_CLIENT_SECRET=your-secret`          | GitHub OAuth Client Secret                      |
| `custom_provider`               | string  | `custom`                         | `--oauth.custom_provider my-provider`               | `OAUTH__CUSTOM_PROVIDER=my-provider`               | 自定义 OAuth 提供者名称                         |
| `custom_client_id`              | string  | `""`                             | `--oauth.custom_client_id your-id`                  | `OAUTH__CUSTOM_CLIENT_ID=your-id`                  | 自定义 OAuth Client ID                          |
| `custom_client_secret`          | string  | `""`                             | `--oauth.custom_client_secret your-secret`          | `OAUTH__CUSTOM_CLIENT_SECRET=your-secret`          | 自定义 OAuth Client Secret                      |
| `custom_scopes`                 | string  | `["openid", "email", "profile"]` | `--oauth.custom_scopes '["openid", "email"]'`       | `OAUTH__CUSTOM_SCOPES=["openid", "email"]`         | 自定义 OAuth 权限范围（JSON 数组）              |
| `custom_discovery_url`          | string  | `null`                           | `--oauth.custom_discovery_url https://...`          | `OAUTH__CUSTOM_DISCOVERY_URL=https://...`          | OAuth 发现端点 URL（可选）                      |
| `custom_authorization_endpoint` | string  | `null`                           | `--oauth.custom_authorization_endpoint https://...` | `OAUTH__CUSTOM_AUTHORIZATION_ENDPOINT=https://...` | OAuth 授权端点（未设置 discovery_url 时必填）   |
| `custom_token_endpoint`         | string  | `null`                           | `--oauth.custom_token_endpoint https://...`         | `OAUTH__CUSTOM_TOKEN_ENDPOINT=https://...`         | OAuth Token 端点（未设置 discovery_url 时必填） |
| `custom_userinfo_endpoint`      | string  | `null`                           | `--oauth.custom_userinfo_endpoint https://...`      | `OAUTH__CUSTOM_USERINFO_ENDPOINT=https://...`      | OAuth 用户信息端点（可选）                      |
| `custom_jwks_uri`               | string  | `null`                           | `--oauth.custom_jwks_uri https://...`               | `OAUTH__CUSTOM_JWKS_URI=https://...`               | OAuth JWKS URI（可选）                          |

**注意：** 如果未设置 `custom_discovery_url`，则必须提供 `custom_authorization_endpoint` 和 `custom_token_endpoint`。

#### 达梦连接池配置 (DmPoolConfig)

| 参数名称                  | 类型    | 默认值                        | 命令行格式                                   | ENV 格式                                    | 说明                                                                     |
| ------------------------- | ------- | ----------------------------- | -------------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------ |
| `enabled`                 | boolean | `true`                        | `--pool.enabled false`                       | `POOL__ENABLED=false`                       | 是否启用连接池                                                           |
| `read_write_split`        | boolean | `true`                        | `--pool.read_write_split false`              | `POOL__READ_WRITE_SPLIT=false`              | 是否启用读写分离                                                         |
| `load_balancing_strategy` | string  | `least_connections`           | `--pool.load_balancing_strategy round_robin` | `POOL__LOAD_BALANCING_STRATEGY=round_robin` | 负载均衡策略：`round_robin`、`least_connections`、`weighted_round_robin` |
| `default_source`          | string  | `primary`                     | `--pool.default_source primary`              | `POOL__DEFAULT_SOURCE=primary`              | 默认数据源名称                                                           |
| `max_retries`             | integer | `1`                           | `--pool.max_retries 3`                       | `POOL__MAX_RETRIES=3`                       | 最大重试次数                                                             |
| `retry_backoff_ms`        | integer | `100`                         | `--pool.retry_backoff_ms 200`                | `POOL__RETRY_BACKOFF_MS=200`                | 重试退避时间（毫秒）                                                     |
 
说明：
- SQL 黑名单关键字已在代码内静态配置，不再通过 `--pool.sql_blacklist` / `POOL__SQL_BLACKLIST` 配置。
- 数据源配置通过 API 管理（使用 `/datasources` 相关接口创建/更新/启用/禁用），不再通过环境变量预置。

#### Token 认证配置 (TokenAuthConfig)

| 参数名称             | 类型    | 默认值   | 命令行格式                              | ENV 格式                               | 说明                             |
| -------------------- | ------- | -------- | --------------------------------------- | -------------------------------------- | -------------------------------- |
| `enabled`            | boolean | `false`  | `--token_auth.enabled true`             | `TOKEN_AUTH__ENABLED=true`             | 是否启用 Token 认证              |
| `cleanup_interval`   | integer | `3600`   | `--token_auth.cleanup_interval 1800`    | `TOKEN_AUTH__CLEANUP_INTERVAL=1800`    | 清理过期 token 的间隔（秒，≥60） |
| `auto_cleanup`       | boolean | `true`   | `--token_auth.auto_cleanup false`       | `TOKEN_AUTH__AUTO_CLEANUP=false`       | 是否自动清理过期 token           |
| `default_expires_in` | integer | `604800` | `--token_auth.default_expires_in 86400` | `TOKEN_AUTH__DEFAULT_EXPIRES_IN=86400` | 默认有效期（秒，≥60，默认 7 天） |

#### JWT 配置 (JwtConfig)

| 参数名称               | 类型    | 默认值       | 命令行格式                        | ENV 格式                         | 说明                              |
| ---------------------- | ------- | ------------ | --------------------------------- | -------------------------------- | --------------------------------- |
| `secret`               | string  | `(随机生成)` | `--jwt.secret your-secret-key`    | `JWT__SECRET=your-secret-key`    | JWT 签名密钥                      |
| `token_expire_seconds` | integer | `3600`       | `--jwt.token_expire_seconds 7200` | `JWT__TOKEN_EXPIRE_SECONDS=7200` | Token 过期时间（秒，默认 1 小时） |

**配置示例：**

**方式一：命令行参数**

```bash
uv run python main.py --server.port 8080 --server.transport http --logging.level DEBUG
```

**方式二：环境变量**

```bash
export SERVER__PORT=8080
export SERVER__TRANSPORT=http
export LOGGING__LEVEL=DEBUG
uv run python main.py
```

**方式三：.env 文件**

创建 `.env` 文件：

```env
SERVER__PORT=8080
SERVER__TRANSPORT=http
SERVER__HOST=0.0.0.0
LOGGING__LEVEL=DEBUG
LOGGING__LOG_DIR=./logs
DATABASE__DB_TYPE=dameng
DATABASE__DAMENG__HOST=192.168.1.100
DATABASE__DAMENG__PORT=5236
DATABASE__DAMENG__USER=SYSDBA
DATABASE__DAMENG__PASSWORD=your-password
```

**混合使用示例：**

环境变量设置了默认值，命令行参数覆盖特定配置：

```bash
# .env 文件
SERVER__PORT=18081
SERVER__TRANSPORT=http
LOGGING__LEVEL=INFO

# 命令行（覆盖端口和日志级别）
uv run python main.py --server.port 8080 --logging.level DEBUG
# 最终结果：port=8080（命令行覆盖），transport=http（.env），level=DEBUG（命令行覆盖）
```

## 维护与扩展方法

本节主要面向本系统的维护者，用于指导对于本项目源码的扩展与维护。

本系统采用分层架构设计，将 MCP 协议适配层和业务逻辑层分离：

- **Service 层（业务逻辑层）**：提供实际的业务能力，如数据库连接池、认证服务、缓存服务等。Service 专注于业务逻辑的实现，不关心如何对外暴露功能，具有完整的生命周期管理，通过服务注册表进行统一管理。
- **Provider 层（MCP 协议适配层）**：负责将 Service 的业务能力暴露为 MCP 协议的工具（Tool）、资源（Resource）和提示词（Prompt）。Provider 不包含业务逻辑，仅作为协议适配器，通过调用 Service 来提供 MCP 功能。

这种设计的优势在于：

- **职责分离**：Service 专注业务逻辑，Provider 专注协议适配，各司其职
- **可扩展性**：通过新增 Provider 可以快速扩展 MCP 功能，而无需修改 Service 层
- **可复用性**：同一个 Service 可以被多个 Provider 复用，实现不同协议层面的暴露
- **可维护性**：业务逻辑变更只需修改 Service，MCP 接口变更只需修改 Provider，互不影响

在实际使用中，Provider 通过依赖注入的方式获取所需的 Service，在工具函数中调用 Service 的方法来完成业务逻辑，然后将结果返回给 MCP 客户端。

### 扩展 MCP Provider

`BaseMCPProvider` 基类包含一个 `mcp` 成员属性，这是 `MCPRouter` 的实例，用于注册工具、资源和提示词。

#### MCP Router 装饰器

`MCPRouter` 提供三个装饰器用于注册 MCP 功能：

- `**@self.mcp.tool**` - 工具装饰器，用于注册可调用的工具函数。

- - `name`：工具名称（可选，默认使用函数名）
  - `description`：工具描述（可选，默认使用函数的 docstring）
  - `exclude_args`：要从输入 schema 中排除的参数列表
  - `requires_token_auth`：是否需要 Token 认证（默认 False）

工具函数的参数会自动解析为 JSON Schema，函数的返回值会序列化为 JSON。

- `**@self.mcp.resource**` - 资源装饰器，用于注册静态资源或资源模板。

- - `uri`：资源 URI（静态资源）或 URI 模板（动态资源，支持 parse 库语法，如 `{param}`、`{param:d}`、`{param:f}` 等）
  - `description`：资源描述（可选）
  - `mime_type`：MIME 类型（默认 text/plain）

静态资源通过完整 URI 匹配，资源模板通过 URI 模式匹配并提取参数。资源函数应返回字符串内容。

- `**@self.mcp.prompt**` - 提示词装饰器，用于注册对话模板。

- - `name`：提示词名称（可选，默认使用函数名）
  - `description`：提示词描述（可选，默认使用函数的 docstring）

提示词函数接收参数并返回格式化后的提示内容或消息列表。

#### 扩展新的 Provider

（1） 在 `src/dm_mcp/providers/` 目录下创建新的 Provider 文件，继承 `BaseMCPProvider` 类：

```python
from dm_mcp.core.mcp import BaseMCPProvider

class MyProvider(BaseMCPProvider):
    def __init__(self, dependency_service) -> None:
        super().__init__()
        self.dependency_service = dependency_service
        self._register_routes()

    async def my_tool(self):
        return self.dependency_service.do_something()

    async def my_resource(self, name: str):
        return f"hello {name}"

    async def my_prompt(self, name: str):
        return f"say hello to {name}"
    
    def _register_routes(self):
        @self.mcp.tool()
        async def my_tool():
            """自定义工具"""
            return await self.my_tool()

        @self.mcp.resource("dameng://{name}/value")
        async def my_resource(name: str):
            """自定义资源"""
            return await self.my_resource(name)

        @self.mcp.prompt()
        async def my_prompt(name: str):
            """自定义提示词模板"""
            return await self.my_prompt(name)
```

最佳实践：将所有工具的装载通过 `_register_routes` 实现，并且具体逻辑单独在 Provider 中定义成员函数实现，防止 `_register_routes` 过长，导致结构不清晰而不好维护。

（2）在服务器类中注册 Provider。修改 `src/dm_mcp/server/server.py` 中的 `_load_mcp_providers()` 方法，添加新的 Provider：

```python
def _load_mcp_providers(self) -> None:
    """加载 MCP 提供者"""
    self.add_mcp_providers(
        [
            # ... 其他 
            MyProvider(self.context.my_service),  # 追加新 Provider
        ]
    )
```

#### 扩展 MCP 中间件

中间件采用责任链模式，用于实现横切关注点，如认证、日志、监控、审计等。中间件在 MCP 操作的执行过程中提供拦截点，可以在操作执行前后进行处理，而无需修改 Provider 或 Service 的代码。

中间件通过 `MCPMiddlewareStack` 组织成调用链，按照注册顺序依次执行。每个中间件可以：

- 在操作执行前进行预处理（如权限检查、参数验证）
- 在操作执行后进行后处理（如结果转换、指标记录）
- 决定是否继续执行后续中间件或直接返回

这种设计使得系统功能可以模块化扩展，新增的横切关注点只需添加新的中间件即可，无需修改现有代码。具体步骤如下：

（1）创建中间件类。在 `src/dm_mcp/middlewares/` 目录下创建新的中间件文件，继承 `BaseMCPMiddleware` 类：

```python
from dm_mcp.core.mcp import BaseMCPMiddleware

class MyMiddleware(BaseMCPMiddleware):
    async def on_call_tool(self, call_next, name: str, arguments: dict):
        # 前置处理
        result = await call_next(name, arguments)
        # 后置处理
        return result
```

（2）在服务器类中注册中间件。修改 `src/dm_mcp/server/server.py` 中的 `_load_mcp_middlewares()` 方法，添加新的中间件：

```python
def _load_mcp_middlewares(self) -> None:
    self.add_mcp_middlewares(
        [
            # ... 其他中间件
            MyMiddleware(),  # 添加新中间件
        ]
    )
```

### 扩展业务服务

Service 是系统的业务逻辑核心，负责实现具体的业务功能，如数据库连接池管理、认证授权、缓存操作等。Service 通过服务注册表（ServiceRegistry）进行统一管理，支持依赖注入和生命周期管理。

每个 Service 需要：

- 实现 `ServiceFactory` 协议，定义服务的元数据（名称、依赖、优先级等）
- 继承 `BaseService` 基类，实现 `startup()` 和 `shutdown()` 方法管理资源生命周期
- 在 `GlobalContext` 中注册，通过服务注册表进行依赖解析和实例创建

服务注册表使用拓扑排序自动解决服务间的依赖关系，确保服务按正确顺序初始化。这种设计使得服务可以声明式地管理依赖，系统自动处理依赖注入和初始化顺序。具体步骤如下：

（2）创建服务类。在 `src/dm_mcp/services/` 目录下创建新的服务文件，继承 `BaseService` 类：

```python
from dm_mcp.services import BaseService

class MyService(BaseService):
    def __init__(self, settings, dependency_service):
        self.settings = settings
        self.dependency = dependency_service
    
    async def startup(self):
        # 服务启动逻辑
        pass
    
    async def shutdown(self):
        # 服务关闭逻辑
        pass
```

（2）创建服务工厂。在同一文件中实现 `ServiceFactory` 协议：

```python
from dm_mcp.core.service import ServiceFactory, ServiceMetadata

class MyServiceFactory(ServiceFactory):
    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="my_service",
            service_type=MyService,
            dependencies=["dependency_service"],  # 声明依赖
            priority=50,  # 初始化优先级
        )
    
    def create(self, settings, **deps) -> MyService:
        return MyService(settings, deps["dependency_service"])
```

（3）在 GlobalContext 中注册服务。修改 `src/dm_mcp/server/global_context.py` 中的 `_register_builtin_services()` 方法：

```python
def _register_builtin_services(self) -> None:
    """注册所有内置服务"""
    builtin_factories = [
        # ... 其他服务工厂
        MyServiceFactory(),  # 添加新服务工厂
    ]
    self.registry.register_factories(builtin_factories)
```

（4）在 GlobalContext 中添加服务访问属性（可选）。如果需要通过 `context.my_service` 访问服务，在 `GlobalContext` 类中添加属性：

```python
@property
def my_service(self) -> MyService:
    """获取自定义服务"""
    return self.registry.get_service("my_service")
```

### 配置管理

#### 扩展配置类

修改 `src/dm_mcp/settings/settings.py` 中的 `Settings` 类，添加新的配置项：

```python
from pydantic import Field

class Settings:
    # ... 现有配置项
    
    # 添加新配置项
    my_config: str = Field(default="default_value", description="配置说明")
```

#### 使用配置项

在需要使用配置的服务或组件中，通过 `settings` 对象访问配置：

```python
class MyService(BaseService):
    def __init__(self, settings: Settings):
        self.my_config = settings.my_config
```

### 日志与审计日志使用

#### 普通日志

在 Provider 或服务中，可以直接使用 Python 标准库的 `logging` 模块进行日志记录：

```python
import logging

logger = logging.getLogger(__name__)

class MyProvider(BaseMCPProvider):
    def __init__(self):
        suprt().__init__()
        self._register_routes()

    async def example_tool(self, param: str):
        logger.info(f"执行工具，参数: {param}")
        try:
            result = self._process(param)
            logger.debug(f"处理完成，结果: {result}")
            return result
        except Exception as e:
            logger.error(f"处理失败: {e}", exc_info=True)
            raise
    
    def _register_routes(self):
        @self.mcp.tool()
        async def example_tool(param: str):
            """示例工具"""
            return await self.example_tool(param)
```

日志系统会自动将标准库的 `logging` 调用重定向到 Loguru，并支持日志级别、文件输出、日志轮转等功能。

#### 审计日志

审计日志用于记录用户的关键操作行为，会单独存储到独立的审计日志文件中。系统已通过 `AuditMCPMiddleware` 中间件实现了默认的审计日志功能，会自动记录 MCP 操作的审计信息。如需在 Provider 中自定义审计日志，可以直接注入 `LoggingService`：

```python
from dm_mcp.services.logging_service import LoggingService

class MyProvider(BaseMCPProvider):
    def __init__(self, logging_service: LoggingService) -> None:
        super().__init__()
        self.logging_service = logging_service
        self._register_routes()

    async def example_tool(self, param: str):
        audit_logger = self.logging_service.get_audit_logger()
        audit_logger.info(f"执行操作: {param}")
        
        result = self._process(param)
        return result
    
    def _register_routes(self):
        @self.mcp.tool()
        async def example_tool(param: str):
            """获取审计日志器并记录"""
            return await self.example_tool(param)
```

审计日志的特点：

- **独立存储**：写入独立的审计日志文件（`dm_mcp_server_audit.log`），与普通应用日志分离
- **用户追踪**：记录操作用户信息，便于追踪用户行为
- **关键操作**：主要用于记录敏感操作，如数据删除、权限变更等

### 指标使用

在 Provider 中使用指标需要先定义指标类，然后在工具中记录指标数据：

```python
from dataclasses import dataclass
from dm_mcp.core.mcp import BaseMCPProvider
from dm_mcp.core.metrics.metrics import metric_field

@dataclass
class CalculatorMetrics:
    """计算器指标"""
    calculation_count: int = metric_field("计算次数", "counter")

class CalculatorProvider(BaseMCPProvider):
    def __init__(self) -> None:
        super().__init__()
        self._register_routes()

    async def add(self, a: int, b: int) -> int:
        # 创建指标实例
        metrics = CalculatorMetrics()
        metrics.calculation_count = 1
        
        # 记录指标
        if self.metrics:
            self.metrics.record(metrics)
        
        return a + b

    def _register_routes(self):
        @self.mcp.tool()
        async def add(a: int, b: int) -> int:
            """计算两数之和"""
            return await self.add(a, b)
```

指标会自动收集并可通过 Prometheus 格式导出，用于监控和可观测性。

### 服务依赖管理

服务依赖通过以下方式管理：

1. **声明依赖**：在 `ServiceMetadata` 的 `dependencies` 字段中声明依赖的服务名称
2. **自动注入**：服务工厂的 `create()` 方法会收到依赖的服务实例
3. **依赖解析**：`ServiceRegistry` 使用拓扑排序自动解决依赖顺序
4. **循环检测**：注册表会检测并阻止循环依赖

### 最佳实践原则

- **单一职责**：每个 Provider 或服务只负责一个明确的功能域
- **依赖注入**：服务通过 `GlobalContext` 和 `ServiceRegistry` 实现依赖注入，避免硬编码依赖
- **接口抽象**：使用基类和协议定义接口，保持扩展性
- **配置驱动**：通过配置类管理可变参数，支持不同环境部署
- **生命周期管理**：实现 `startup()` 和 `shutdown()` 方法，确保资源的正确初始化和清理
- **错误处理**：使用统一的异常体系，提供清晰的错误信息
- **可观测性**：通过日志和指标记录服务运行状态，便于问题排查

## 基于本框架的二次开发方法

框架提供了 `server.mcp` 函数式注册器，这是一种简洁、类似 FastMCP 风格的 API，特别适合快速开发和原型设计。本节介绍如何使用 `server.mcp` 进行二次开发。

二次开发也可以基于 Provider 实现，并通过 `server.add_mcp_provider`或`server.add_mcp_providers`添加

### 什么是 server.mcp

`server.mcp` 是 `MCPServer` 实例的一个属性，类型为 `MCPFunctionRegistry`。它提供了函数式的装饰器 API，允许开发者直接在应用代码中使用装饰器注册 MCP 工具、资源和提示词，而无需创建 Provider 类。

### 函数式注册 vs Provider 类方式

**函数式注册（**`server.mcp`**）的优势：**

- **简洁直观**：代码更少，语法更清晰
- **快速开发**：无需创建类，适合快速原型和小型功能
- **统一 API**：所有功能集中在 `server.mcp` 对象中
- **便于测试**：函数式代码更容易测试
- **灵活组织**：通过模块化文件组织，同样适用于大型项目（见下文最佳实践）

**Provider 类方式的优势：**

- **更好的封装**：可以在类中维护状态和依赖
- **代码复用**：可以继承和扩展 Provider 类
- **清晰的边界**：每个 Provider 负责一个功能域
- **OOP 风格**：适合面向对象编程习惯

**选择建议：**

- **快速原型和小型功能**：使用 `server.mcp` 函数式注册
- **项目适用规模**：两种方式都可以构建复杂项目，函数式注册通过合理的目录组织同样能实现良好的模块化管理（见下文最佳实践）
- **需要类状态管理**：使用 Provider 类方式
- **混合使用**：两种方式可以同时使用，框架会自动合并

### server.mcp API 概览

`server.mcp` 提供了以下 API：

**装饰器方法：**

- `@server.mcp.tool()` - 注册工具函数
- `@server.mcp.resource()` - 注册资源函数
- `@server.mcp.prompt()` - 注册提示词函数

**便捷属性：**

- `server.mcp.auth` - 访问认证上下文（`AuthContext`）
- `server.mcp.metrics` - 访问指标上下文（`MetricsContext`）

**依赖注入方法：**

- `server.mcp.get_service(name)` - 获取服务依赖

### 快速开始

创建一个简单的 MCP 服务器：

```python
from dm_mcp.server import MCPServer

# 创建服务器实例
def create_server():
    server = MCPServer()
    
    # 使用装饰器注册工具
    @server.mcp.tool()
    async def add(a: int, b: int) -> int:
        """加法运算"""
        return a + b
    
    return server

# 启动服务器
if __name__ == "__main__":
    MCPServer.run(create_server)
```

### 使用示例

注：以下所有示例代码均需要创建一个服务器实例为前提

#### 基本工具注册

```python
@server.mcp.tool()
async def add(a: int, b: int) -> int:
    """加法运算"""
    return a + b

@server.mcp.tool(
    requires_token_auth=True  # 需要 Token 认证
)
async def multiply(a: int, b: int) -> int:
    """乘法运算"""
    return a * b
```

#### 访问认证上下文

```python
@server.mcp.tool()
async def get_current_user():
    """获取当前登录用户的信息"""
    # 访问认证上下文
    auth = server.mcp.auth
    user_id = auth.user_id
    token = auth.token
    
    return {
        "user_id": user_id,
        "token": token,
    }
```

#### 使用服务依赖

```python
@server.mcp.tool()
async def query_datasource(sql: str, source: str = "auto"):
    """执行 SQL 查询"""
    # 获取服务依赖
    datasource_service = server.mcp.get_service("datasource_service")
    
    # 使用服务
    result = await datasource_service.query(
        sql=sql,
        source=source
    )
    
    return result
```

#### 记录指标

```python
from dataclasses import dataclass
from dm_mcp.core.metrics.metrics import metric_field

@dataclass
class QueryMetrics:
    """查询指标"""
    query_count: int = metric_field("查询次数", "counter")
    query_time: float = metric_field("查询耗时", "histogram")

@server.mcp.tool()
async def query_with_metrics(sql: str):
    """执行查询并记录指标"""
    import time
    
    start_time = time.time()
    
    # 执行查询
    datasource_service = server.mcp.get_service("datasource_service")
    result = await datasource_service.query(sql=sql)
    
    # 记录指标
    metrics = QueryMetrics()
    metrics.query_count = 1
    metrics.query_time = time.time() - start_time
    
    server.mcp.metrics.record(metrics)
    
    return result
```

#### 注册资源

```python
@server.mcp.resource("resource://config/{config_key}")
async def get_config(config_key: str) -> str:
    """获取配置项的值"""
    settings = server.mcp.get_service("registry").get_service("settings")
    # 假设配置存储在 settings 中
    value = getattr(settings, config_key, None)
    import json
    return json.dumps({"key": config_key, "value": value})
```

#### 注册提示词

```python
@server.mcp.prompt()
async def data_analysis_prompt(query: str) -> str:
    """数据分析助手提示词"""
    return f"""
你是一个专业的数据分析助手。请根据以下查询进行分析：

查询: {query}

请提供详细的数据分析结果和建议。
"""
```

### 完整示例：自定义服务器

创建一个完整的自定义服务器，使用 `server.mcp` 进行函数式注册：

```python
from dataclasses import dataclass
from dm_mcp.core.metrics.metrics import metric_field
from dm_mcp.server import MCPServer

# 定义指标
@dataclass
class CalculatorMetrics:
    """计算器指标"""
    calculation_count: int = metric_field("计算次数", "counter")

# 创建服务器
def create_server():
    server = MCPServer()
    
    # 注册计算工具
    @server.mcp.tool()
    async def add(a: int, b: int) -> int:
        """加法运算"""
        # 记录指标
        metrics = CalculatorMetrics()
        metrics.calculation_count = 1
        server.mcp.metrics.record(metrics)
        
        return a + b
    
    @server.mcp.tool()
    async def multiply(a: int, b: int) -> int:
        """乘法运算"""
        metrics = CalculatorMetrics()
        metrics.calculation_count = 1
        server.mcp.metrics.record(metrics)
        
        return a * b
    
    # 注册资源
    @server.mcp.resource("resource://calculator/history")
    async def get_history() -> str:
        """获取计算历史"""
        return "计算历史记录..."
    
    return server

# 启动服务器
if __name__ == "__main__":
    MCPServer.run(create_server)
```

### 复杂项目组织最佳实践

函数式注册不仅适用于小型项目，通过合理的目录组织和模块化设计，同样可以很好地支持复杂项目。本节展示如何在复杂项目中使用函数式注册，将功能目标一致的工具、资源、提示词聚集在一起。

#### 推荐的目录结构

对于大型项目，建议采用按功能模块组织的扁平化目录结构。每个模块将相关的工具、资源、提示词整合在一个文件中，与 Provider 类的方式保持一致：

```plain
my-mcp-service/
├── src/
│   ├── main.py                    # 应用入口
│   └── my_mcp_service/
│       ├── __init__.py
│       ├── server.py              # 服务器创建和配置
│       ├── modules/               # 功能模块目录
│       │   ├── __init__.py
│       │   ├── calculator.py      # 计算器模块（工具、资源、提示词）
│       │   └── file_manager.py    # 文件管理模块（工具、资源、提示词）
│       ├── services/              # 业务服务（可选）
│       │   ├── __init__.py
│       │   └── my_service.py      # 自定义业务服务
│       ├── middlewares/           # MCP 中间件（可选）
│       │   ├── __init__.py
│       │   └── my_middleware.py
│       └── utils/                 # 工具函数
│           └── ...
├── tests/                         # 测试文件
├── pyproject.toml
└── README.md
```

#### 模块化组织方式

每个功能模块将相关的工具、资源、提示词整合在一个文件中，通过统一的注册函数在服务器中注册。这种方式与 Provider 类类似，但使用函数式风格。

**（1）功能模块示例：计算器模块**

`modules/calculator.py` - 计算器模块（整合工具、资源、提示词）：

```python
"""
计算器功能模块
将计算器相关的工具、资源、提示词整合在一个文件中
"""
from dataclasses import dataclass
from dm_mcp.core.metrics.metrics import metric_field

# 定义指标
@dataclass
class CalculatorMetrics:
    """计算器指标"""
    calculation_count: int = metric_field("计算次数", "counter")

# 存储计算历史（简单示例）
_calculation_history = []

def register_calculator_module(server):
    """注册计算器模块的所有功能"""
    mcp = server.mcp
    
    # ===== 工具 =====
    
    @mcp.tool()
    async def add(a: int, b: int) -> int:
        """加法运算"""
        result = a + b
        _calculation_history.append({"operation": "add", "a": a, "b": b, "result": result})
        
        # 记录指标
        metrics = CalculatorMetrics()
        metrics.calculation_count = 1
        mcp.metrics.record(metrics)
        
        return result
    
    @mcp.tool()
    async def multiply(a: int, b: int) -> int:
        """乘法运算"""
        result = a * b
        _calculation_history.append({"operation": "multiply", "a": a, "b": b, "result": result})
        
        # 记录指标
        metrics = CalculatorMetrics()
        metrics.calculation_count = 1
        mcp.metrics.record(metrics)
        
        return result
    
    @mcp.tool()
    async def subtract(a: int, b: int) -> int:
        """减法运算"""
        result = a - b
        _calculation_history.append({"operation": "subtract", "a": a, "b": b, "result": result})
        
        metrics = CalculatorMetrics()
        metrics.calculation_count = 1
        mcp.metrics.record(metrics)
        
        return result
    
    # ===== 资源 =====
    
    @mcp.resource("calc://history")
    async def get_calculation_history() -> str:
        """获取计算历史记录"""
        import json
        return json.dumps(_calculation_history[-10:], indent=2, ensure_ascii=False)
    
    @mcp.resource("calc://stats")
    async def get_calculator_stats() -> str:
        """获取计算器统计信息"""
        import json
        stats = {
            "total_calculations": len(_calculation_history),
            "operations": {
                "add": len([h for h in _calculation_history if h["operation"] == "add"]),
                "multiply": len([h for h in _calculation_history if h["operation"] == "multiply"]),
                "subtract": len([h for h in _calculation_history if h["operation"] == "subtract"]),
            }
        }
        return json.dumps(stats, indent=2, ensure_ascii=False)
    
    # ===== 提示词 =====
    
    @mcp.prompt()
    async def calculator_helper(question: str) -> str:
        """计算器助手提示词
        
        帮助用户理解如何使用计算器工具
        """
        return f"""你是一个友好的计算器助手。

用户问题: {question}

我可以帮助你进行以下计算：
1. 加法：使用 add(a, b) 工具
2. 乘法：使用 multiply(a, b) 工具
3. 减法：使用 subtract(a, b) 工具

你还可以查看计算历史（calc://history）和统计信息（calc://stats）。

请告诉我你需要进行什么计算？"""
    
    @mcp.prompt()
    async def calculation_summary(operation: str, a: int, b: int, result: int) -> str:
        """计算摘要提示词
        
        生成计算结果的摘要说明
        """
        return f"""计算完成！

操作: {operation}
输入: {a} 和 {b}
结果: {result}

这是{'加法' if operation == 'add' else '乘法' if operation == 'multiply' else '减法'}运算的结果。
"""
```

**（2）功能模块示例：文件管理模块**

`modules/file_manager.py` - 文件管理模块（整合工具、资源、提示词）：

```python
"""
文件管理功能模块
将文件管理相关的工具、资源、提示词整合在一个文件中
"""
from pathlib import Path

# 文件存储目录（简单示例，实际应从配置读取）
_STORAGE_DIR = Path("./storage")

def register_file_manager_module(server):
    """注册文件管理模块的所有功能"""
    mcp = server.mcp
    
    # 确保存储目录存在
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    
    # ===== 工具 =====
    
    @mcp.tool(requires_token_auth=True)
    async def read_file(filename: str) -> str:
        """读取文件内容
        
        Args:
            filename: 文件名（相对路径）
        """
        file_path = _STORAGE_DIR / filename
        
        # 安全检查：防止路径遍历攻击
        if not str(file_path.resolve()).startswith(str(_STORAGE_DIR.resolve())):
            raise ValueError("无效的文件路径")
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {filename}")
        
        return file_path.read_text(encoding="utf-8")
    
    @mcp.tool(requires_token_auth=True)
    async def write_file(filename: str, content: str) -> dict:
        """写入文件内容
        
        Args:
            filename: 文件名（相对路径）
            content: 文件内容
        """
        file_path = _STORAGE_DIR / filename
        
        # 安全检查
        if not str(file_path.resolve()).startswith(str(_STORAGE_DIR.resolve())):
            raise ValueError("无效的文件路径")
        
        # 确保目录存在
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_path.write_text(content, encoding="utf-8")
        
        return {"status": "success", "filename": filename, "size": len(content)}
    
    @mcp.tool(requires_token_auth=True)
    async def list_files(path: str = ".") -> list:
        """列出目录中的文件
        
        Args:
            path: 目录路径（相对路径）
        """
        dir_path = _STORAGE_DIR / path
        
        # 安全检查
        if not str(dir_path.resolve()).startswith(str(_STORAGE_DIR.resolve())):
            raise ValueError("无效的目录路径")
        
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"目录不存在: {path}")
        
        files = []
        for item in dir_path.iterdir():
            files.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None
            })
        
        return files
    
    # ===== 资源 =====
    
    @mcp.resource("file://{filename}")
    async def get_file_resource(filename: str) -> str:
        """获取文件资源内容"""
        file_path = _STORAGE_DIR / filename
        
        # 安全检查
        if not str(file_path.resolve()).startswith(str(_STORAGE_DIR.resolve())):
            raise ValueError("无效的文件路径")
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {filename}")
        
        return file_path.read_text(encoding="utf-8")
    
    # ===== 提示词 =====
    
    @mcp.prompt()
    async def file_manager_guide(operation: str) -> str:
        """文件管理指南提示词
        
        提供文件操作的使用指南
        """
        guides = {
            "read": "使用 read_file(filename) 工具读取文件内容。文件名应为相对路径。",
            "write": "使用 write_file(filename, content) 工具写入文件。如果文件不存在会自动创建。",
            "list": "使用 list_files(path) 工具列出目录中的文件。path 参数可选，默认为当前目录。"
        }
        
        guide = guides.get(operation, "可用的文件操作：读取、写入、列出文件。")
        
        return f"""文件管理助手

操作类型: {operation}

指南:
{guide}

注意事项:
- 所有文件路径都是相对路径，基于存储目录
- 出于安全考虑，不允许访问存储目录之外的文件
- 文件路径会被自动验证，防止路径遍历攻击"""
```

**（3）服务器入口整合**

`server.py` - 服务器创建和模块注册：

```python
"""
服务器配置和模块注册
"""
from dm_mcp.server import MCPServer
from dm_mcp.settings import Settings

# 导入功能模块
from my_mcp_service.modules.calculator import register_calculator_module
from my_mcp_service.modules.file_manager import register_file_manager_module

def create_server():
    """创建并配置 MCP 服务器"""
    server = MCPServer()
    
    # 按模块注册功能
    # 每个模块将相关的工具、资源、提示词聚集在一起
    register_calculator_module(server)      # 注册计算器模块
    register_file_manager_module(server)    # 注册文件管理模块
    
    return server
```

`main.py` - 应用入口：

```python
"""
应用入口
"""
from my_mcp_service.server import create_server
from dm_mcp.server import MCPServer
from dm_mcp.settings import Settings

def main():
    """启动 MCP 服务器"""
    MCPServer.run(create_server, Settings)

if __name__ == "__main__":
    main()
```

**（4）自定义业务服务（可选）**

如果项目需要自定义业务服务，可以在 `services/` 目录下创建服务。自定义服务通过 `GlobalContext` 注册，可以在模块中通过 `server.mcp.get_service()` 获取。

`services/my_service.py` - 自定义业务服务：

```python
"""
自定义业务服务示例
"""
from dm_mcp.services import BaseService
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.settings import Settings

class MyService(BaseService):
    """自定义业务服务"""
    
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.data_store = {}  # 简单的数据存储
    
    async def startup(self) -> None:
        """服务启动时执行"""
        # 初始化资源
    
    async def shutdown(self) -> None:
        """服务关闭时执行"""
        # 清理资源
    
    def store_data(self, key: str, value: str):
        """存储数据"""
        self.data_store[key] = value
    
    def get_data(self, key: str) -> str | None:
        """获取数据"""
        return self.data_store.get(key)


class MyServiceFactory(ServiceFactory):
    """自定义服务工厂"""
    
    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="my_service",
            service_type=MyService,
            description="自定义业务服务",
            dependencies=[],  # 声明依赖的服务
            priority=50,  # 初始化优先级
        )
    
    def create(self, settings: Settings, **deps) -> MyService:
        """创建服务实例"""
        return MyService(settings)
```

**（5）自定义 GlobalContext** - 注册自定义服务：

`context.py` - 自定义全局上下文：

```python
"""
自定义全局上下文
注册自定义服务
"""
from dm_mcp.server.global_context import GlobalContext
from dm_mcp.settings import Settings
from my_mcp_service.services.my_service import MyServiceFactory

class MyGlobalContext(GlobalContext[Settings]):
    """自定义全局上下文"""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        # 注册自定义服务
        self.registry.register_factory(MyServiceFactory())
    
    @property
    def my_service(self):
        """访问自定义服务"""
        return self.registry.get_service("my_service")
```

**（6）在模块中使用自定义服务**：

`modules/file_manager.py` - 使用自定义服务：

```python
"""
文件管理功能模块
使用自定义服务
"""

def register_file_manager_module(server):
    """注册文件管理模块的所有功能"""
    mcp = server.mcp
    
    # ===== 工具 =====
    
    @mcp.tool(description="使用自定义服务存储数据", requires_token_auth=True)
    async def store_with_service(key: str, value: str) -> dict:
        """使用自定义服务存储数据"""
        # 获取自定义服务
        my_service = mcp.get_service("my_service")
        
        # 使用服务
        my_service.store_data(key, value)
        
        return {"status": "success", "key": key}
    
    @mcp.tool(description="使用自定义服务获取数据", requires_token_auth=True)
    async def get_with_service(key: str) -> str | None:
        """使用自定义服务获取数据"""
        # 获取自定义服务
        my_service = mcp.get_service("my_service")
        
        # 使用服务
        return my_service.get_data(key)
```

**（7）更新服务器创建函数** - 使用自定义 GlobalContext：

`server.py` - 使用自定义上下文：

```python
"""
服务器配置和模块注册
"""
from dm_mcp.server import MCPServer
from dm_mcp.settings import Settings
from my_mcp_service.context import MyGlobalContext

# 导入功能模块
from my_mcp_service.modules.calculator import register_calculator_module
from my_mcp_service.modules.file_manager import register_file_manager_module

def create_server():
    """创建并配置 MCP 服务器"""
    # 使用自定义 GlobalContext（会自动注册自定义服务）
    server = MCPServer(Settings, MyGlobalContext)
    
    # 按模块注册功能
    register_calculator_module(server)
    register_file_manager_module(server)
    
    return server
```

#### 组织原则

1. **按功能域划分模块**：每个模块负责一个明确的功能域（如计算器、文件管理等）
2. **工具、资源、提示词整合**：在同一个模块文件内，将相关的工具、资源、提示词整合在一起，便于管理
3. **统一入口函数**：每个模块提供一个统一的注册函数（如 `register_xxx_module`），便于管理
4. **依赖明确**：通过 `server.mcp.get_service()` 明确声明依赖，避免隐式依赖
5. **指标和日志独立**：每个模块可以定义自己的指标类，独立管理日志

#### 优势

采用这种组织方式，函数式注册同样可以实现：

- **模块化管理**：每个功能域独立管理
- **清晰的边界**：相关功能聚集在一起
- **易于扩展**：新增功能只需添加新模块
- **便于测试**：可以单独测试每个模块
- **代码复用**：模块可以独立复用

这种方式结合了函数式编程的简洁性和面向对象编程的组织性，非常适合大型项目的开发。

### 注意事项

- **注册时机**：装饰器在模块加载时执行，确保在使用 `server.mcp` 之前创建了 `MCPServer` 实例。
- **与服务注册的关系**：`server.mcp` 内部使用 `FunctionMCPProvider`，它会自动注册到 MCP 服务中，无需手动调用 `add_mcp_providers()`。
- **与 Provider 类的兼容性**：函数式注册和 Provider 类注册可以同时使用，框架会自动合并所有工具、资源和提示词。
- **依赖注入**：使用 `server.mcp.get_service()` 获取服务时，确保服务已经在 `GlobalContext` 中注册。
- **性能考虑**：对于高频调用的工具，建议考虑缓存和异步优化。
- **安全性**：始终进行输入验证和权限检查，特别是涉及文件系统或数据库操作时。

### 高级用法

#### 自定义配置

可以通过自定义 `Settings` 和 `GlobalContext` 来扩展功能：

```python
from pydantic import Field
from dm_mcp.settings import Settings
from dm_mcp.server.global_context import GlobalContext

class MySettings(Settings):
    """自定义配置"""
    my_arg: str = Field(default="", description="自定义参数")

class MyGlobalContext(GlobalContext[MySettings]):
    """自定义上下文"""
    pass

# 创建服务器时使用自定义类
server = MCPServer(MySettings, MyGlobalContext)
```

#### 生命周期钩子

使用启动和关闭钩子进行初始化：

```python
server = MCPServer()

@server.on_startup
async def startup_hook():
    """服务器启动时执行"""
    logger.info("服务器启动中...")
    # 初始化资源

@server.on_shutdown
async def shutdown_hook():
    """服务器关闭时执行"""
    logger.info("服务器关闭中...")
    # 清理资源
```

#### 使用 MCP 中间件

在函数式注册的项目中，可以通过 `server.add_mcp_middleware()` 或 `server.add_mcp_middlewares()` 注册自定义中间件：

`middlewares/my_middleware.py` - 自定义中间件：

```python
"""
自定义 MCP 中间件示例
"""
from dm_mcp.core.mcp import BaseMCPMiddleware
import logging

logger = logging.getLogger(__name__)

class LoggingMCPMiddleware(BaseMCPMiddleware):
    """日志记录中间件
    
    记录所有 MCP 工具调用的日志
    """
    
    async def on_call_tool(self, call_next, name: str, arguments: dict):
        """工具调用拦截"""
        logger.info(f"调用工具: {name}, 参数: {arguments}")
        
        try:
            result = await call_next(name, arguments)
            logger.info(f"工具调用成功: {name}, 结果: {result}")
            return result
        except Exception as e:
            logger.error(f"工具调用失败: {name}, 错误: {e}", exc_info=True)
            raise
    
    async def on_read_resource(self, call_next, uri: str):
        """资源读取拦截"""
        logger.info(f"读取资源: {uri}")
        
        try:
            result = await call_next(uri)
            logger.info(f"资源读取成功: {uri}")
            return result
        except Exception as e:
            logger.error(f"资源读取失败: {uri}, 错误: {e}", exc_info=True)
            raise
```

`server.py` - 注册中间件：

```python
"""
服务器配置和模块注册
"""
from dm_mcp.server import MCPServer
from dm_mcp.settings import Settings

# 导入功能模块
from my_mcp_service.modules.calculator import register_calculator_module
from my_mcp_service.modules.file_manager import register_file_manager_module

# 导入中间件
from my_mcp_service.middlewares.my_middleware import LoggingMCPMiddleware

def create_server():
    """创建并配置 MCP 服务器"""
    server = MCPServer()
    
    # 注册中间件（在注册模块之前）
    server.add_mcp_middleware(LoggingMCPMiddleware())
    
    # 或者注册多个中间件
    # server.add_mcp_middlewares([
    #     LoggingMCPMiddleware(),
    #     AnotherMCPMiddleware(),
    # ])
    
    # 按模块注册功能
    register_calculator_module(server)
    register_file_manager_module(server)
    
    return server
```

**中间件执行顺序**：中间件按照注册顺序执行，先注册的中间件在外层（先执行前置处理，后执行后置处理）。

**中间件使用场景**：

- **日志记录**：记录所有 MCP 操作
- **性能监控**：测量操作执行时间
- **权限验证**：额外的权限检查
- **请求限流**：控制调用频率
- **结果转换**：修改返回结果

### 开发建议

1. **遵循框架设计原则**：保持 Service 和 Provider 的职责分离
2. **充分利用扩展点**：优先使用框架提供的扩展机制，避免直接修改核心代码
3. **代码规范**：遵循项目的代码风格和规范
4. **性能考虑**：注意异步操作和资源管理，避免阻塞和泄漏
5. **安全性**：注意输入验证、权限控制和敏感信息保护
6. **错误处理**：使用统一的异常体系，提供清晰的错误信息
7. **可观测性**：通过日志和指标记录服务运行状态，便于问题排查

