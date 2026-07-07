# 达梦数据库 MCP 服务

基于 Python 与 [模型上下文协议（MCP）](https://modelcontextprotocol.io/) 构建的数据库服务端，将达梦数据库的查询、元数据、巡检、DPC 集群监控等能力开放给兼容 MCP 的 AI 客户端。

完整用户文档见服务内置站点 `{base_url}/docs/`（默认 `/dm-mcp/docs/`），文档源码位于 [`dm-mcp-docs`](https://github.com/dameng/dm-mcp-docs) 工程。

## 功能概览

| 能力 | 说明 |
|------|------|
| **MCP 工具** | 元数据（`meta`）、SQL 执行（`query`）、数据分析（`data`）、数据库巡检（`inspect`）、DPC 集群（`dpc`）、动态 SQL 工具（`generic_sql`） |
| **多数据源** | 支持达梦、SQLite、MySQL、PostgreSQL；读写分离与连接池策略可通过 API 热更新 |
| **认证与安全** | MCP Token 认证、OAuth、管理员 Basic Auth、审计日志、IP 白/黑名单 |
| **Web 控制台** | 数据源、令牌、SSH 主机、元数据配置、工具分组管理 |
| **CLI 集成** | `cli-metadata` 元数据导出、`cli-download` 二进制分发，配合 dmctl / dmctlx |
| **可观测性** | 结构化日志（Loguru）、Prometheus 指标（可选） |

## 环境要求

- **Python** ≥ 3.12
- **[uv](https://github.com/astral-sh/uv)** 包管理器

## 快速开始

### 1. 准备配置

```bash
cp .env.example .env
```

编辑 `.env`，**必须**设置 `APP_SECRET`（长随机字符串，用于会话加密、OAuth 与数据源密码加密）：

```env
APP_SECRET=CHANGE_ME_TO_A_LONG_RANDOM_STRING
SERVER__TRANSPORT=http
SERVER__HOST=0.0.0.0
```

### 2. 安装依赖并启动

```bash
uv sync
uv run dm-mcp-server
```

等价的启动方式：

```bash
uv run python src/main.py
```

HTTP 模式（供 Web 控制台与 AI 客户端连接）：

```bash
uv run dm-mcp-server --server.transport http --server.host 0.0.0.0
```

### 3. 验证服务

```bash
curl -fsS http://localhost:18081/dm-mcp/api/v1/config
```

浏览器访问控制台：`http://localhost:18081/dm-mcp/`

## Docker 部署

```bash
cp .env.example .env
# 编辑 .env，设置 APP_SECRET

docker compose up --build
```

说明：

- 镜像：`dameng/dm-mcp-server:0.1.0`，入口命令为 `dm-mcp-server`
- 默认监听 `18081`，`base_url` 为 `/dm-mcp`
- `docker-compose.yml` 通过 `env_file: .env` 加载配置
- 数据卷：`./data`（SQLite）、`./logs`、`./metrics`
- 健康检查：`GET /dm-mcp/api/v1/config`（公开接口，无需鉴权）

连接外部达梦数据库时，在 `.env` 中修改：

```env
DATABASE__DB_TYPE=dameng
DATABASE__DAMENG__HOST=192.168.1.100
DATABASE__DAMENG__PORT=5236
DATABASE__DAMENG__USER=SYSDBA
DATABASE__DAMENG__PASSWORD=your-password
```

## 首次使用

1. 访问 Web 控制台 `http://localhost:18081/dm-mcp/`
2. 初始化管理员密码：`POST /dm-mcp/api/v1/auth/admin/init-password`
3. 在控制台配置 [数据源](/dm-mcp/docs/console/datasource) 与 [访问令牌](/dm-mcp/docs/console/token)
4. 在 AI 客户端中配置 MCP 端点与 Token（详见 [认证与数据源访问](/dm-mcp/docs/mcp/auth)）

## MCP 客户端接入

| 项目 | 值 |
|------|-----|
| HTTP 传输端点 | `http://<host>:<port>/dm-mcp/mcp` |
| 认证头部 | `Authorization: Bearer <token>` |
| 数据源切换（可选） | `X-DMMCP-DataSource: <数据源名称>` |
| stdio 模式 | `uv run dm-mcp-server --server.transport stdio` |

Claude / Cursor 配置示例：

```json
{
  "mcpServers": {
    "dm-mcp": {
      "url": "http://localhost:18081/dm-mcp/mcp",
      "headers": {
        "Authorization": "Bearer sk-dmmcp-xxxxxxxx"
      }
    }
  }
}
```

Dify 集成示例见 [`examples/dify/dify-dm-mcp-app.yml`](examples/dify/dify-dm-mcp-app.yml)。

## 常用配置

配置优先级（高 → 低）：命令行参数 → 环境变量 → `.env` 文件 → Docker secrets → 默认值。

| 参数 | ENV | 默认值 | 说明 |
|------|-----|--------|------|
| `app_secret` | `APP_SECRET` | （必填） | 加密主密钥 |
| `server.host` | `SERVER__HOST` | `localhost` | 监听地址 |
| `server.port` | `SERVER__PORT` | `18081` | 监听端口 |
| `server.transport` | `SERVER__TRANSPORT` | `stdio` | `stdio` 或 `http` |
| `server.base_url` | `SERVER__BASE_URL` | `/dm-mcp` | API 与 Web 基础路径 |
| `server.static_path` | `SERVER__STATIC_PATH` | `{cwd}/resources/web` | Web 控制台静态资源 |
| `database.db_type` | `DATABASE__DB_TYPE` | `sqlite` | `sqlite` / `dameng` / `mysql` / `postgresql` |
| `database.sqlite.db_path` | `DATABASE__SQLITE__DB_PATH` | `server.db` | SQLite 文件路径 |
| `logging.level` | `LOGGING__LEVEL` | `INFO` | 日志级别 |
| `metrics.enabled` | `METRICS__ENABLED` | `false` | 是否启用 Prometheus 指标 |

> OAuth、连接池行为、数据源等业务配置通过 REST API 运行时管理并持久化到数据库，不再通过环境变量预置。完整配置说明见 [配置参考](/dm-mcp/docs/configuration)。

## REST API 概览

所有 API 挂载在 `{base_url}/api/v1` 下（默认 `/dm-mcp/api/v1`）。

| 分组 | 路径前缀 | 说明 |
|------|----------|------|
| 系统 | `/health`、`/config`、`/metrics` | 健康检查、运行配置、指标 |
| 认证 | `/auth-config`、`/auth/*`、`/oauth/providers/*` | 认证配置与 OAuth |
| 管理员 | `/auth/admin/*` | 管理员登录与密码管理 |
| 数据源 | `/datasources/*` | 数据源 CRUD、测试、重载 |
| 元数据 | `/datasources/{name}/metadata/*` | Schema / 表 / 列查询与配置 |
| 连接池 | `/pool-config` | 读写分离、负载均衡策略 |
| MCP 元数据 | `/mcp-groups`、`/tools`、`/resources`、`/prompts` | 工具分组与描述覆盖 |
| 令牌 | `/tokens/*` | MCP 访问令牌管理 |
| SSH | `/ssh-hosts/*` | 远程主机管理 |
| CLI | `/cli-metadata`、`/cli-download/{program}/{platform}` | CLI 元数据与二进制下载 |

公开接口（无需鉴权）：`/health`、`/config`、`/auth/*`（OAuth 流程）、`/cli-metadata`、`/docs/`。

MCP 协议入口：`{base_url}/mcp`（需 Token 认证）。

## 内置 MCP 工具

| 分组 | Provider | 典型能力 |
|------|----------|----------|
| `meta` | MetadataMCPProvider | Schema、表/视图结构、索引与约束 |
| `query` | QueryExecMCPProvider | SQL 查询与风险分析 |
| `data` | DataMCPProvider | 表大小、列统计分析 |
| `inspect` | InspectionMCPProvider | 执行计划、会话/锁、缓冲池、热点 SQL |
| `dpc` | DpcClusterMCPProvider | DPC 实例、Raft、STask 线程 |
| `generic_sql` | GenericSqlMCPProvider | 可配置动态 SQL 工具 |

各工具详细说明见 [MCP 功能文档](/dm-mcp/docs/tools)。

## 架构简介

```
src/dm_mcp/
├── app/          # MCPServer 组装、路由、GlobalContext
├── api/          # HTTP 控制器
├── domain/       # 业务服务与 MCP Provider
├── infra/        # 配置、持久化、传输层、HTTP 中间件
└── core/         # MCP 协议抽象、服务注册表、异常体系
```

- **Service 层**（`domain/*/services/`）：业务逻辑与生命周期管理
- **Provider 层**（`domain/mcp/providers/`）：将 Service 能力暴露为 MCP Tool / Resource / Prompt
- **函数式注册**（`server.mcp`）：无需创建 Provider 类即可快速注册工具

扩展开发指南见 [扩展开发文档](/dm-mcp/docs/development)（文档源码：`dm-mcp-docs/content/development.mdx`）。

## 项目结构

```
dm-mcp-server/
├── src/
│   ├── main.py              # 应用入口
│   └── dm_mcp/              # 核心代码
├── resources/
│   ├── web/                 # Web 控制台（SPA）
│   ├── docs/                # 内置文档（由 dm-mcp-docs 构建）
│   └── cli/                 # CLI 二进制分发
├── examples/                # 集成示例（Dify 等）
├── scripts/                 # 工具脚本
├── tests/                   # 测试
├── .env.example             # 环境变量模板
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

## 许可证

本项目基于 [Mulan PSL v2](http://license.coscl.org.cn/MulanPSL2) 许可证发布。详见 [LICENCE](LICENCE)。
