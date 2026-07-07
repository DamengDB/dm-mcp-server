"""集中消息常量模块

按领域分组定义所有用户面向的消息，消除硬编码字符串散落和重复。
静态消息用纯字符串常量，带变量的消息用 .format() 模板字符串。
"""


# ============================================================
# 认证 / 授权
# ============================================================
MSG_AUTH_BASIC_AUTH_FORMAT_INVALID = "Basic Auth 格式无效"
MSG_AUTH_USERNAME_INVALID = "用户名无效"
MSG_AUTH_PASSWORD_INVALID = "密码错误"
MSG_AUTH_PASSWORD_REQUIRED = "密码不能为空"
MSG_AUTH_PASSWORD_INITIALIZED = "密码初始化成功"
MSG_AUTH_PASSWORD_CHANGED = "密码修改成功"
MSG_AUTH_OLD_AND_NEW_PASSWORD_REQUIRED = "旧密码和新密码不能为空"
MSG_AUTH_PASSWORD_TOO_SHORT = "密码长度不能少于6位"
MSG_AUTH_NEW_PASSWORD_TOO_SHORT = "新密码长度不能少于6位"
MSG_AUTH_PASSWORD_ALREADY_INITIALIZED = "admin 密码已初始化，无法重复初始化"
MSG_AUTH_ADMIN_NOT_EXISTS = "admin 用户不存在，请先初始化密码"
MSG_AUTH_OLD_PASSWORD_INCORRECT = "旧密码错误"
MSG_AUTH_TOKEN_SERVICE_UNAVAILABLE = "Token 服务不可用"
MSG_AUTH_TOKEN_AUTH_REQUIRED = "MCP 端点需要认证"
MSG_AUTH_TOKEN_AUTH_REQUIRED_FOR_TOOL = "工具 '{name}' 需要 Token 认证，请在 Authorization 头中提供有效的 Token"
MSG_AUTH_TOKEN_EXPIRED_AT = "Token 已于 {expired_at} 过期"
MSG_AUTH_TOKEN_NOT_FOUND = "Token 未找到: {token_hint}"
MSG_AUTH_TOKEN_VALIDATION_FAILED = "Token 验证失败"
MSG_AUTH_TOKEN_AUTH_FAILED = "Token 认证失败: {error}"
MSG_AUTH_TOKEN_DATASOURCE_UNAVAILABLE = "Token 绑定的数据源 (ID: {datasource_id}) 不可用或不存在"
MSG_AUTH_IP_NOT_ALLOWED = "IP 地址 {client_ip} 不被此 Token 允许"
MSG_AUTH_NO_AUTH_CONTEXT = "未设置认证上下文"
MSG_AUTH_NO_METRICS_CONTEXT = "未设置指标上下文"
MSG_AUTH_DATASOURCE_ACCESS_DENIED = "无权访问数据源: {datasource_name}"
MSG_AUTH_NEXT_URL_INVALID = "无效的跳转 URL"

# 异常类默认值
MSG_AUTH_FAILED = "认证失败"
MSG_AUTH_FORBIDDEN = "授权失败"
MSG_AUTH_TOKEN_EXPIRED = "Token 已过期"
MSG_AUTH_TOKEN_INVALID = "无效的 Token"
MSG_AUTH_IP_NOT_ALLOWED_DEFAULT = "IP 地址不允许访问"
MSG_AUTH_TOKEN_DATASOURCE_NOT_FOUND = "Token 绑定的数据源不存在或不可用"
MSG_VALIDATION_FAILED = "验证失败"
MSG_INVALID_PARAMETER = "无效参数: {parameter}"
MSG_MISSING_PARAMETER = "缺少必需参数: {parameter}"
MSG_SERVICE_NOT_FOUND = "服务 '{service_name}' 未找到"
MSG_SERVICE_CIRCULAR_DEPENDENCY = "服务 '{service_name}' 存在循环依赖"
MSG_SERVICE_CIRCULAR_DEPENDENCY_WITH_PATH = "服务 '{service_name}' 存在循环依赖，路径: '{path}'"
MSG_DATASOURCE_NOT_FOUND_DEFAULT = "数据源 '{source_name}' 未找到"
MSG_PROVIDER_NOT_FOUND = "Provider '{provider_name}' 未找到"
MSG_CLI_GROUP_NOT_FOUND = "CLI 分组未找到: '{path}'"
MSG_CLI_GROUP_PATH_IN_USE = "CLI 分组路径 '{path}' 仍被 {count} 个工具引用: {names_preview}"
MSG_CLI_GROUP_MISSING_FOR_TOOLS = "数据库中缺少工具分组对应的 CLI 分组路径: {missing_paths}"
MSG_CLI_GROUP_CONFLICT = "CLI 分组路径已存在: '{path}'"
MSG_COMMAND_TREE_CONFLICT = "命令树冲突于 '{node_path}': {conflict_type}"
MSG_TOOL_NOT_FOUND_DEFAULT = "工具未找到: '{tool_name}'"
MSG_RESOURCE_NOT_FOUND_DEFAULT = "资源未找到: '{resource_uri}'"
MSG_PROMPT_NOT_FOUND_DEFAULT = "提示词未找到: '{prompt_name}'"

# ============================================================
# JWT
# ============================================================
MSG_JWT_SECRET_TOO_SHORT = "JWT 密钥长度不能少于 32 个字符"
MSG_JWT_PAYLOAD_MISSING = "JWT 格式无效: 缺少 payload"
MSG_JWT_PAYLOAD_DECODE_FAILED = "JWT payload 解码失败: {error}"
MSG_JWT_TOKEN_FORMAT_INVALID = "JWT Token 格式无效: {error}"

# ============================================================
# Token
# ============================================================
MSG_TOKEN_NAME_REQUIRED = "Token name 不能为空"
MSG_TOKEN_NOT_FOUND_BY_ID = "Token 未找到: {token_id}"

# ============================================================
# OAuth
# ============================================================
MSG_OAUTH_DISABLED = "OAuth 已禁用"
MSG_OAUTH_PROVIDER_NOT_REGISTERED = "Provider '{provider_name}' 未注册"
MSG_OAUTH_PROVIDER_CONFIG_NOT_FOUND = "Provider '{provider_name}' 配置未找到"
MSG_OAUTH_AUTH_ENDPOINT_NOT_CONFIGURED = "授权端点未配置"
MSG_OAUTH_TOKEN_ENDPOINT_NOT_CONFIGURED = "Token 端点未配置"
MSG_OAUTH_STATE_COOKIE_MISSING = "OAuth state Cookie 未找到，会话可能已过期"
MSG_OAUTH_STATE_EXPIRED = "OAuth state 已过期，请重新登录"
MSG_OAUTH_STATE_SIGNATURE_INVALID = "OAuth state 签名无效，可能存在篡改"
MSG_OAUTH_STATE_INVALID_OR_EXPIRED = "OAuth state 无效或已过期: {error}"
MSG_OAUTH_STATE_PARAM_MISSING = "回调中缺少 state 参数"
MSG_OAUTH_STATE_MISMATCH = "OAuth state 不匹配，可能存在 CSRF 攻击"
MSG_OAUTH_USER_INFO_FAILED = "无法从 OAuth 提供商获取用户信息"
MSG_OAUTH_AUTH_CODE_MISSING = "缺少授权码"
MSG_OAUTH_AUTH_CODE_EXCHANGE_FAILED = "授权码交换失败: {error}"
MSG_OAUTH_CALLBACK_FAILED = "OAuth 回调处理失败: {error}"

# ============================================================
# MCP (工具 / 资源 / 提示词 / Provider / 分组)
# ============================================================
MSG_TOOL_NOT_FOUND = "未知工具: {name}"
MSG_TOOL_EXECUTION_FAILED = "工具执行失败: {error}"
MSG_RESOURCE_NOT_FOUND = "资源未找到: {uri}"
MSG_RESOURCE_READ_FAILED = "读取资源 {uri} 失败: {error}"
MSG_PROMPT_NOT_FOUND = "未知提示词: {name}"
MSG_PROMPT_GET_FAILED = "获取提示词失败: {error}"
MSG_GROUP_PATH_INVALID = "无效的分组路径: '{path}'，请使用小写字母、数字、下划线，段之间用 '.' 分隔（如 'db' 或 'db.mysql'）"
MSG_GROUP_PATH_SEGMENT_RESERVED = "无效的分组路径: '{path}'，段 '{segment}' 为 CLI 保留字"
MSG_GROUP_SEGMENT_INVALID = "无效的分组段名: '{name}'，单段名不能包含 '.'"
MSG_GROUP_CANNOT_MOVE_UNDER_SELF = "不能将分组移动到自身之下"
MSG_GROUP_CANNOT_MOVE_UNDER_DESCENDANT = "不能将分组移动到其子孙分组之下"
MSG_RESOURCE_IS_TEMPLATE = "资源 {uri} 是模板类型，无法转换为静态 Resource"
MSG_RESOURCE_NOT_TEMPLATE = "资源 {uri} 不是模板类型，无法转换为 ResourceTemplate"
MSG_RESOURCE_NAME_PARAM_MISMATCH = "资源 {uri}: 名称模板参数 '{param}' 必须在 uri template_params {template_params} 中"
MSG_RESOURCE_TEMPLATE_PARAM_NOT_IN_FN = "资源 {uri}: 模板参数 '{param}' 在函数 {fn_name} 的签名中未找到"
MSG_FN_ARGS_KWARGS_NOT_SUPPORTED = "函数 {fn_name}: 不支持 *args 和 **kwargs"
MSG_FN_EXCLUDED_ARG_NOT_FOUND = "函数 {fn_name}: 排除的参数 '{arg}' 在签名中未找到"

# ============================================================
# 数据源 / 数据库
# ============================================================
MSG_DATASOURCE_NOT_FOUND = "数据源不存在: {name}"
MSG_DATASOURCE_NOT_FOUND_BY_ID = "数据源未找到"
MSG_DATASOURCE_DISABLED = "数据源已禁用: {name}"
MSG_DATASOURCE_NONE_AVAILABLE = "没有可用的数据源"
MSG_DATASOURCE_NAME_EXISTS = "数据源名称已存在: {name}"
MSG_DATASOURCE_NAME_MUST_BE_UNIQUE = "数据源名称必须唯一"
MSG_DATASOURCE_DEPLOY_TYPE_INVALID = "无效的 deploy_type 值: {deploy_type}"
MSG_DATASOURCE_DPC_TYPE_MISMATCH = "当前数据源 deploy_type={deploy_type}，期望 dmdpc"
MSG_DATASOURCE_CONNECTION_TIMEOUT = "数据源 '{name}' 连接超时，请检查网络或数据库服务状态"
MSG_DB_ENGINE_NOT_INIT = "数据库引擎未初始化，请先调用 init_db()"
MSG_DB_SESSION_FACTORY_NOT_INIT = "数据库会话工厂未初始化，请先调用 init_db()"
MSG_DB_UNSUPPORTED_TYPE = "不支持的数据库类型: {db_type}"
MSG_DB_UNSAFE_SQL_IDENTIFIER = "不安全的 SQL {context}: '{name}'. 仅允许字母、数字和下划线，且不能以数字开头。"
MSG_DB_ILLEGAL_SQL_IDENTIFIER = "非法的 SQL 标识符: {name}"
MSG_DB_ILLEGAL_SCHEMA_NAME = "非法的 schema 名称: {schema}"
MSG_DB_ILLEGAL_TABLE_NAME = "非法的 table 名称: {table}"
MSG_DB_NO_DATASOURCE_CONTEXT = "未设置数据源上下文"
MSG_SCHEMA_INCOMPATIBLE = (
    "元数据库结构与 DM MCP v{version} 不兼容，服务无法启动。\n\n"
    "检测到的问题：\n"
    "{issues}\n\n"
    "说明：v{version} 不会自动升级旧版本元库结构。\n\n"
    "建议处置（任选其一）：\n"
    "  1. 清空当前 schema 下的元数据表后重新启动（将丢失配置）\n"
    "  2. 在 .env 中更换数据库/schema 配置，使用新的空 schema 初始化\n"
    "  3. 参考升级文档手动执行 DDL 后重启（需自行承担数据风险）\n\n"
    "当前 schema: {schema_hint}\n"
    "要求版本: v{version}"
)
MSG_SCHEMA_INCOMPATIBLE_ISSUE = "  - {issue}"
MSG_SCHEMA_INCOMPATIBLE_MISSING_TABLE = "缺少表: {table_name}"
MSG_SCHEMA_INCOMPATIBLE_MISSING_COLUMN = "表 {table_name} 缺少列: {column_name}"

# ============================================================
# 服务 / 通用
# ============================================================
MSG_INTERNAL_SERVER_ERROR = "服务器内部错误"
MSG_TYPE_NOT_SERIALIZABLE = "类型 {type} 不可序列化"
MSG_TRANSPORT_FACTORY_REF_MISSING = "缺少 DM_MCP_FACTORY_REF 环境变量，请通过 StreamableHttpTransport 启动"
MSG_TRANSPORT_FACTORY_LOAD_FAILED = "加载服务器工厂 '{factory_ref}' 失败: {error}"
MSG_TRANSPORT_FACTORY_TYPE_MISMATCH = "工厂返回了 {type}，期望 MCPServer"
MSG_UNKNOWN_TRANSPORT = "未知的传输方式: {transport}"
MSG_EXEC_ID_REQUIRED = "exec_id 不能为空"
MSG_TOP_N_MUST_BE_POSITIVE = "top_n 必须为正数"
MSG_PARAM_REQUIRED = "{param} 不能为空"
MSG_DECRYPTION_FAILED = "无法解密：密文无效或密钥不匹配"
