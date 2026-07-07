"""认证后端模块

提供Starlette认证后端实现，支持多种认证方式（Token、BasicAuth、OAuth）。
"""

import logging
from datetime import datetime, timezone

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
)
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from dm_mcp.common import messages
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.auth.user import MCPUser
from dm_mcp.core.exceptions.auth_errors import (
    InvalidTokenError,
    IpNotAllowedError,
    TokenDatasourceNotFoundError,
    TokenExpiredError,
)
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.auth.services.auth_config import AuthConfigService
from dm_mcp.domain.auth.services.oauth import OAuthService
from dm_mcp.domain.token.services.token import TokenService
from dm_mcp.infra.config import Settings

logger = logging.getLogger(__name__)


class AuthBackend(AuthenticationBackend):
    """认证后端

    实现Starlette的AuthenticationBackend接口，根据路由和配置选择认证策略。
    支持Token认证（用于MCP路由）和JWT认证（用于其他路由，来自BasicAuth或OAuth）。
    """

    def __init__(
        self,
        settings: Settings,
        oauth_service: OAuthService,
        auth_config_service: AuthConfigService,
        token_service: TokenService | None = None,
        datasource_service: DataSourceService | None = None,
    ):
        """初始化认证后端

        Args:
            settings: 服务器设置
            oauth_service: OAuth服务实例
            auth_config_service: 认证配置服务实例
            token_service: Token服务实例（可选）
        """
        self.settings = settings
        self.oauth_service = oauth_service
        self.auth_config_service = auth_config_service
        self.token_service = token_service
        # 数据源服务（可选，用于在 Token 认证时校验绑定的数据源是否存在/可用）
        self.datasource_service = datasource_service

    # 无需认证即可访问的公开路径（前缀匹配或精确匹配）
    # 注意：api_routes 挂载在 /api/v1 下，前缀需包含 /api/v1
    _PUBLIC_PATH_PREFIXES = (
        "/api/v1/health",
        "/api/v1/config",
        "/api/v1/auth/",
        "/api/v1/cli-metadata",
        "/cli-download/",
        "/docs",
    )

    def _is_public_path(self, path: str) -> bool:
        """判断请求路径是否为公开路由（无需认证）"""
        base = self.settings.server.base_url
        for prefix in self._PUBLIC_PATH_PREFIXES:
            full_prefix = f"{base}{prefix}"
            if path == f"{base}{prefix.rstrip('/')}" or path.startswith(full_prefix):
                return True
        # metrics 路径从配置读取
        if hasattr(self.settings, "metrics") and hasattr(self.settings.metrics, "http_path"):
            if path == f"{base}{self.settings.metrics.http_path}":
                return True
        return False

    async def authenticate(self, conn: HTTPConnection):
        """认证入口方法

        根据路由和配置选择认证策略：
        1. MCP路由 + Token验证启用 -> 必须使用Token认证 (Bearer sk-dmmcp-xxx)
        2. 其他路由 -> 尝试JWT (Bearer)认证（来自BasicAuth或OAuth）
           - 如果没有Authorization header，拒绝访问

        Args:
            conn: HTTP连接对象

        Returns:
            tuple[AuthCredentials, MCPUser] | None: 认证成功返回凭证和用户，失败返回None

        Raises:
            AuthenticationError: 当认证失败时
        """
        path = conn.url.path

        # 公开路由跳过认证
        if self._is_public_path(path):
            return None

        is_mcp_route = path.startswith(f"{self.settings.server.base_url}/mcp")
        has_auth_header = "Authorization" in conn.headers

        if not has_auth_header:
            logger.debug(f"请求缺少认证头: {path}")
            return None  # 拒绝访问（不再允许匿名访问）

        auth_info = self._extract_auth_info(conn)
        auth_scheme = auth_info.get("authorization", "").lower()
        token = auth_info.get("token", "")

        # 策略1: MCP 路由 + Token 验证启用 -> 必须使用 Token 认证
        if self.auth_config_service.token_auth_enabled and is_mcp_route:
            # 新格式: Bearer sk-dmmcp-xxx
            # 旧格式 (Deprecated): Token xxx
            is_mcp_token = (
                auth_scheme == "bearer" and token.startswith("sk-dmmcp-")
            ) or auth_scheme == "token"
            if is_mcp_token:
                if auth_scheme == "token":
                    logger.warning(
                        f"DEPRECATED: 'Token' authentication scheme is deprecated "
                        f"and will be removed in a future version. "
                        f"Use 'Bearer sk-dmmcp-<token>' instead. path={path}"
                    )
                return await self._authenticate_mcp_token(conn, token)
            logger.debug(f"MCP 路由认证失败: 不符合 Token 认证格式, path={path}")
            return None

        # 策略2: 其他路由 -> 尝试 JWT (Bearer) 认证（来自 BasicAuth 或 OAuth）
        if auth_scheme == "bearer":
            try:
                auth_context = self.oauth_service.authenticate_token(token)
                logger.debug(f"JWT 认证成功: {path}, 用户: {auth_context.user_id}")
                return AuthCredentials(["authenticated"]), MCPUser(auth_context)
            except Exception as e:
                logger.warning(f"JWT 认证失败: {path}, 错误: {e}")
                raise AuthenticationError(f"JWT 认证失败: {str(e)}")

        # 所有认证方式都失败
        logger.debug(f"认证失败: {path}, 认证方案: {auth_scheme}")
        return None

    async def _authenticate_mcp_token(self, conn: HTTPConnection, token: str):
        """MCP路由使用Token认证

        Args:
            conn: HTTP连接对象
            token: Token字符串（已提取，可能是 sk-dmmcp- 前缀格式或旧格式）

        Returns:
            tuple[AuthCredentials, MCPUser] | None: 认证成功返回凭证和用户，失败返回None

        Raises:
            AuthenticationError: 当Token无效或过期时
        """
        path = conn.url.path
        auth_info = self._extract_auth_info(conn)
        client_ip = auth_info.get("client_ip", "unknown")

        try:

            # 验证 Token 并获取 TokenConfig
            if not self.token_service:
                raise AuthenticationError(messages.MSG_AUTH_TOKEN_SERVICE_UNAVAILABLE)

            token_config = await self.token_service.validate_token(token)

            # 【改】校验 token 至少关联了一个数据源
            if not token_config.datasource_ids:
                logger.warning(
                    "MCP Token 认证失败: Token 未关联任何数据源: "
                    f"path={path}, token={token[:8]}..."
                )
                raise TokenDatasourceNotFoundError(
                    message="Token 未关联任何数据源"
                )

            # 验证 IP 地址
            if not TokenService._is_ip_allowed(
                client_ip, token_config.ip_whitelist, token_config.ip_blacklist
            ):
                logger.warning(
                    f"MCP Token IP 验证失败: {path}, IP: {client_ip}, "
                    f"Token: {token[:8]}..., 白名单: {token_config.ip_whitelist}, "
                    f"黑名单: {token_config.ip_blacklist}"
                )
                raise IpNotAllowedError(
                    messages.MSG_AUTH_IP_NOT_ALLOWED.format(client_ip=client_ip)
                )

            # 创建 AuthContext
            auth_context = await self._get_token_auth_context(token)
            logger.debug(
                f"MCP Token 认证成功: {path}, 用户: {auth_context.user_id}, "
                f"Token: {token[:8]}..., IP: {client_ip}"
            )
            # 【改】将 token 允许访问的数据源列表和默认数据源放到 MCPUser 上
            return AuthCredentials(["authenticated"]), MCPUser(
                auth_context,
                datasource_ids=token_config.datasource_ids,
                default_datasource_id=token_config.default_datasource_id,
            )
        except (InvalidTokenError, TokenExpiredError) as e:
            logger.warning(f"MCP Token 认证失败: {path}, 错误: {str(e)}")
            raise AuthenticationError(str(e))
        except IpNotAllowedError as e:
            logger.warning(f"MCP Token IP 验证失败: {path}, 错误: {str(e)}")
            raise
        except Exception as auth_error:
            logger.error(
                f"MCP Token 认证异常: {path}, 错误: {str(auth_error)}", exc_info=True
            )
            raise AuthenticationError(
                messages.MSG_AUTH_TOKEN_AUTH_FAILED.format(error=auth_error)
            )

    @classmethod
    def on_error(cls, request, exc: Exception):
        """统一错误响应格式

        当认证失败时，返回标准化的JSON错误响应。

        Args:
            request: 请求对象
            exc: 异常对象

        Returns:
            JSONResponse: 包含错误信息的JSON响应
        """
        from dm_mcp.core.exceptions import DmMCPError

        status_code = 401
        error_code = "AUTH_FAILED"
        message = str(exc)

        # 处理特定异常类型
        if isinstance(exc, InvalidTokenError):
            error_code = exc.error_code
            status_code = exc.status_code
        elif isinstance(exc, TokenExpiredError):
            error_code = exc.error_code
            status_code = exc.status_code
        elif isinstance(exc, IpNotAllowedError):
            error_code = exc.error_code
            status_code = exc.status_code
        elif isinstance(exc, DmMCPError):
            # DmMCPError 已经包含了 error_code 和 status_code
            error_code = exc.error_code
            status_code = exc.status_code
            message = exc.message

        return JSONResponse(
            {
                "success": False,
                "error": {
                    "code": error_code,
                    "message": message,
                },
            },
            status_code=status_code,
        )

    async def _get_token_auth_context(self, token: str) -> AuthContext:
        """使用Token认证创建AuthContext

        Args:
            token: Token字符串

        Returns:
            AuthContext: 认证上下文对象

        Raises:
            AuthenticationError: 当Token服务不可用或Token无效时
        """
        if not self.token_service:
            raise AuthenticationError(messages.MSG_AUTH_TOKEN_SERVICE_UNAVAILABLE)

        token_config = await self.token_service.validate_token(token)

        return AuthContext(
            user_id=token_config.user_id,
            token=token_config.token,
            auth_type="token",
            login_time=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
        )

    def _extract_auth_info(self, request: HTTPConnection):
        """从请求中提取认证信息

        从ASGI scope和HTTP头中提取认证信息，包括客户端IP和Authorization头。

        Args:
            request: HTTP连接对象

        Returns:
            dict: 包含认证信息的字典，包括client_ip、token、authorization等
        """
        auth_info = {}

        # Extract client IP
        auth_info["client_ip"] = self._get_client_ip(request)

        # Extract token from Authorization header
        authorization = request.headers.get("Authorization", "")
        if authorization:
            parts = authorization.split(maxsplit=1)
            if len(parts) == 2:
                scheme, token = parts
                auth_info["token"] = token
                auth_info["authorization"] = scheme
            else:
                auth_info["token"] = ""
                auth_info["authorization"] = ""
        else:
            auth_info["token"] = ""
            auth_info["authorization"] = ""

        # Extract token from query parameters (for compatibility)
        query_token = request.query_params.get("token")
        if query_token:
            auth_info["token"] = query_token

        return auth_info

    def _get_client_ip(self, request: HTTPConnection) -> str:
        """从请求中提取客户端IP

        考虑代理设置，优先从X-Forwarded-For头中获取，其次从X-Real-IP头，
        最后从直接连接的客户端地址获取。

        Args:
            request: HTTP连接对象

        Returns:
            str: 客户端IP地址，如果无法获取则返回"unknown"
        """
        # Check X-Forwarded-For header first (for proxy setups)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Direct connection: handle both request.client and request.client.host being None
        if request.client and request.client.host:
            return request.client.host

        return "unknown"
