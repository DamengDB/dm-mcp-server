"""认证后端模块

提供Starlette认证后端实现，支持多种认证方式（Token、BasicAuth、OAuth）。
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
)
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.auth.user import MCPUser
from dm_mcp.core.exceptions.auth_errors import (
    IpNotAllowedError,
    InvalidTokenError,
    TokenDatasourceNotFoundError,
    TokenExpiredError,
)
from dm_mcp.services.basic_auth_service import BasicAuthService
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.oauth_service import OAuthService
from dm_mcp.services.token_service import TokenService
from dm_mcp.settings import Settings

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
        basic_auth_service: BasicAuthService | None = None,
        token_service: TokenService | None = None,
        datasource_service: DataSourceService | None = None,
    ):
        """初始化认证后端

        Args:
            settings: 服务器设置
            oauth_service: OAuth服务实例
            basic_auth_service: BasicAuth服务实例（可选）
            token_service: Token服务实例（可选）
        """
        self.settings = settings
        self.oauth_service = oauth_service
        self.basic_auth_service = basic_auth_service
        self.token_service = token_service
        # 数据源服务（可选，用于在 Token 认证时校验绑定的数据源是否存在/可用）
        self.datasource_service = datasource_service

    async def authenticate(self, conn: HTTPConnection):
        """认证入口方法

        根据路由和配置选择认证策略：
        1. MCP路由 + Token验证启用 -> 必须使用Token认证
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
        is_mcp_route = path.startswith(f"{self.settings.server.base_url}/mcp")
        has_auth_header = "Authorization" in conn.headers

        # 策略1: MCP 路由 + Token 验证启用 -> 必须使用 Token
        if self.settings.token_auth.enabled and is_mcp_route:
            return await self._authenticate_mcp_token(conn, has_auth_header)

        # 策略2: 其他路由 -> 尝试 JWT (Bearer) 认证（来自 BasicAuth 或 OAuth）
        if not has_auth_header:
            logger.debug(f"请求缺少认证头: {path}")
            return None  # 拒绝访问（不再允许匿名访问）

        auth_info = self._extract_auth_info(conn)
        auth_scheme = auth_info.get("authorization", "").lower()

        # 尝试 JWT (Bearer) 认证（可能来自 BasicAuth 或 OAuth）
        if auth_scheme == "bearer":
            try:
                auth_context = self.oauth_service.authenticate_token(auth_info["token"])
                logger.debug(f"JWT 认证成功: {path}, 用户: {auth_context.user_id}")
                return AuthCredentials(["authenticated"]), MCPUser(auth_context)
            except Exception as e:
                logger.debug(f"JWT 认证失败: {path}, 错误: {e}")

        # 所有认证方式都失败
        logger.debug(f"认证失败: {path}, 认证方案: {auth_scheme}")
        return None

    async def _authenticate_mcp_token(
        self, conn: HTTPConnection, has_auth_header: bool
    ):
        """MCP路由使用Token认证

        Args:
            conn: HTTP连接对象
            has_auth_header: 是否包含Authorization头

        Returns:
            tuple[AuthCredentials, MCPUser] | None: 认证成功返回凭证和用户，失败返回None

        Raises:
            AuthenticationError: 当Token无效或过期时
        """
        path = conn.url.path
        if not has_auth_header:
            logger.debug(f"MCP Token 认证失败: {path}, 缺少认证头")
            return None  # 拒绝访问

        auth_info = self._extract_auth_info(conn)
        if auth_info.get("authorization") != "Token":
            logger.debug(f"MCP Token 认证失败: {path}, 认证方案不正确")
            return None  # 必须是 Token 格式

        try:
            token = auth_info["token"]
            client_ip = auth_info.get("client_ip", "unknown")

            # 验证 Token 并获取 TokenConfig
            if not self.token_service:
                raise AuthenticationError("Token service not available")

            token_config = await self.token_service.validate_token(token)

            # 验证 Token 绑定的数据源是否存在/可用（避免数据源被删除但 Token 仍然存在）
            if self.datasource_service is not None:
                ds = await self.datasource_service.get_datasource_by_id(
                    token_config.datasource_id
                )
                if not ds or not ds.enabled:
                    logger.warning(
                        "MCP Token 认证失败: 绑定数据源不可用或不存在: "
                        f"path={path}, datasource_id={token_config.datasource_id}, "
                        f"token={token[:8]}..."
                    )
                    raise TokenDatasourceNotFoundError(
                        message=(
                            f"Datasource (ID: {token_config.datasource_id}) bound to this token "
                            "is not available"
                        )
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
                    f"IP address {client_ip} is not allowed for this token"
                )

            # 创建 AuthContext
            auth_context = await self._get_token_auth_context(token)
            logger.debug(
                f"MCP Token 认证成功: {path}, 用户: {auth_context.user_id}, "
                f"Token: {token[:8]}..., IP: {client_ip}"
            )
            # 一 Token 一数据源：将 token 绑定的数据源 ID 放到 MCPUser 上
            return AuthCredentials(["authenticated"]), MCPUser(
                auth_context, datasource_id=token_config.datasource_id
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
            raise AuthenticationError(f"Token authentication failed: {auth_error}")

    async def _authenticate_basic_auth(self, conn: HTTPConnection, auth_info: dict):
        """BasicAuth认证

        Args:
            conn: HTTP连接对象
            auth_info: 认证信息字典

        Returns:
            tuple[AuthCredentials, MCPUser]: 认证成功返回凭证和用户

        Raises:
            AuthenticationError: 当认证失败时
        """
        if not self.basic_auth_service:
            raise AuthenticationError("BasicAuth service not available")

        # 解码 Basic Auth
        auth_header = conn.headers.get("Authorization", "")
        credentials = BasicAuthService.decode_basic_auth(auth_header)
        if credentials is None:
            raise AuthenticationError("Invalid Basic Auth format")

        username, password = credentials

        # 验证用户名
        if username != "admin":
            raise AuthenticationError("Invalid username")

        # 验证密码
        is_valid = await self.basic_auth_service.verify_password(password)
        if not is_valid:
            raise AuthenticationError("Invalid password")

        # 创建 AuthContext
        auth_context = AuthContext(
            user_id="admin",
            login_time=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            auth_type="basic_auth",
            token=None,
        )

        return AuthCredentials(["authenticated"]), MCPUser(auth_context)

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
            raise AuthenticationError("Token service not available")

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
        client_ip = self._get_client_ip(request)
        auth_info["client_ip"] = client_ip if client_ip else "unknown"

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
        query_string = request.query_params.get("query_string", "")
        if query_string and "token=" in query_string:
            import urllib.parse

            query_params = urllib.parse.parse_qs(query_string)
            if "token" in query_params:
                auth_info["token"] = query_params["token"][0]

        return auth_info

    def _get_client_ip(self, request: HTTPConnection) -> Optional[str]:
        """从请求中提取客户端IP

        考虑代理设置，优先从X-Forwarded-For头中获取，其次从X-Real-IP头，
        最后从直接连接的客户端地址获取。

        Args:
            request: HTTP连接对象

        Returns:
            Optional[str]: 客户端IP地址，如果无法获取则返回None
        """
        # Check X-Forwarded-For header first (for proxy setups)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            return forwarded_for.split(",")[0].strip()
        elif request.headers.get("X-Real-IP"):
            return request.headers.get("X-Real-IP")
        else:
            # Direct connection
            return request.client.host if request.client else "unknown"
