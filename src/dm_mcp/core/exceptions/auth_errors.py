"""认证相关异常模块

提供认证和授权相关的异常类定义。
"""

from dm_mcp.common import messages
from .base_error import DmMCPError


class AuthenticationError(DmMCPError):
    """认证失败异常

    当用户认证失败时抛出，HTTP状态码为401。
    """

    def __init__(
        self,
        message: str = messages.MSG_AUTH_FAILED,
        error_code: str = "AUTH_FAILED",
        **kwargs,
    ):
        status_code = kwargs.pop("status_code", 401)
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )


class AuthorizationError(DmMCPError):
    """授权失败异常

    当用户没有权限访问资源时抛出，HTTP状态码为403。
    """

    def __init__(
        self,
        message: str = messages.MSG_AUTH_FORBIDDEN,
        error_code: str = "AUTH_FORBIDDEN",
        **kwargs,
    ):
        status_code = kwargs.pop("status_code", 403)
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )


class TokenExpiredError(AuthenticationError):
    """Token过期异常

    当Token已过期时抛出，继承自AuthenticationError。
    """

    def __init__(self, message: str = messages.MSG_AUTH_TOKEN_EXPIRED, **kwargs):
        super().__init__(message=message, error_code="AUTH_TOKEN_EXPIRED", **kwargs)


class InvalidTokenError(AuthenticationError):
    """Token无效异常

    当Token格式不正确或无效时抛出，继承自AuthenticationError。
    """

    def __init__(self, message: str = messages.MSG_AUTH_TOKEN_INVALID, **kwargs):
        super().__init__(message=message, error_code="AUTH_INVALID_TOKEN", **kwargs)


class OAuthError(AuthenticationError):
    """OAuth认证错误异常

    当OAuth认证过程中发生错误时抛出，继承自AuthenticationError。
    """

    def __init__(self, message: str, provider: str | None = None, **kwargs):
        super().__init__(message=message, error_code="OAUTH_ERROR", **kwargs)
        if provider:
            self.details["provider"] = provider


class IpNotAllowedError(AuthorizationError):
    """IP不允许访问异常

    当客户端的IP地址不在白名单中或在黑名单中时抛出，继承自AuthorizationError。
    """

    def __init__(self, message: str = messages.MSG_AUTH_IP_NOT_ALLOWED_DEFAULT, **kwargs):
        super().__init__(message=message, error_code="IP_NOT_ALLOWED", **kwargs)


class TokenDatasourceNotFoundError(AuthenticationError):
    """Token 绑定的数据源不存在或不可用异常

    当 Token 绑定的数据源已经被删除或不可用时抛出，属于认证失败的一种。
    """

    def __init__(
        self,
        message: str = messages.MSG_AUTH_TOKEN_DATASOURCE_NOT_FOUND,
        **kwargs,
    ):
        super().__init__(
            message=message,
            error_code="AUTH_TOKEN_DATASOURCE_NOT_FOUND",
            **kwargs,
        )
