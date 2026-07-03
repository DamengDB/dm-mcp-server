"""认证相关异常模块

提供认证和授权相关的异常类定义。
"""

from .base_error import DmMCPError


class AuthenticationError(DmMCPError):
    """认证失败异常

    当用户认证失败时抛出，HTTP状态码为401。
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        error_code: str = "AUTH_FAILED",
        **kwargs,
    ):
        """初始化认证异常

        Args:
            message: 错误消息（默认"Authentication failed"）
            error_code: 错误码（默认"AUTH_FAILED"）
            **kwargs: 其他参数传递给基类
        """
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
        message: str = "Authorization failed",
        error_code: str = "AUTH_FORBIDDEN",
        **kwargs,
    ):
        """初始化授权异常

        Args:
            message: 错误消息（默认"Authorization failed"）
            error_code: 错误码（默认"AUTH_FORBIDDEN"）
            **kwargs: 其他参数传递给基类
        """
        status_code = kwargs.pop("status_code", 403)
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )


class TokenExpiredError(AuthenticationError):
    """Token过期异常

    当Token已过期时抛出，继承自AuthenticationError。
    """

    def __init__(self, message: str = "Token expired", **kwargs):
        """初始化Token过期异常

        Args:
            message: 错误消息（默认"Token expired"）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(message=message, error_code="AUTH_TOKEN_EXPIRED", **kwargs)


class InvalidTokenError(AuthenticationError):
    """Token无效异常

    当Token格式不正确或无效时抛出，继承自AuthenticationError。
    """

    def __init__(self, message: str = "Invalid token", **kwargs):
        """初始化Token无效异常

        Args:
            message: 错误消息（默认"Invalid token"）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(message=message, error_code="AUTH_INVALID_TOKEN", **kwargs)


class OAuthError(AuthenticationError):
    """OAuth认证错误异常

    当OAuth认证过程中发生错误时抛出，继承自AuthenticationError。
    """

    def __init__(self, message: str, provider: str | None = None, **kwargs):
        """初始化OAuth异常

        Args:
            message: 错误消息
            provider: OAuth提供者名称（可选）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(message=message, error_code="OAUTH_ERROR", **kwargs)
        if provider:
            self.details["provider"] = provider


class IpNotAllowedError(AuthorizationError):
    """IP不允许访问异常

    当客户端的IP地址不在白名单中或在黑名单中时抛出，继承自AuthorizationError。
    """

    def __init__(self, message: str = "IP address not allowed", **kwargs):
        """初始化IP不允许异常

        Args:
            message: 错误消息（默认"IP address not allowed"）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(message=message, error_code="IP_NOT_ALLOWED", **kwargs)


class TokenDatasourceNotFoundError(AuthenticationError):
    """Token 绑定的数据源不存在或不可用异常

    当 Token 绑定的数据源已经被删除或不可用时抛出，属于认证失败的一种。
    """

    def __init__(
        self,
        message: str = "Token datasource not found or unavailable",
        **kwargs,
    ):
        """初始化 Token 绑定数据源不存在异常

        Args:
            message: 错误消息（默认"Token datasource not found or unavailable"）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=message,
            error_code="AUTH_TOKEN_DATASOURCE_NOT_FOUND",
            **kwargs,
        )
