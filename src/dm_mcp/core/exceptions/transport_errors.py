"""传输层相关异常模块

提供传输层相关的异常类定义，包括配置错误等异常。
"""

from .base_error import DmMCPError


class TransportError(DmMCPError):
    """传输层基础异常

    所有传输层相关异常的基类，HTTP状态码为500。
    """

    def __init__(self, message: str, **kwargs):
        """初始化传输层异常

        Args:
            message: 错误消息
            **kwargs: 其他参数传递给基类
        """
        error_code = kwargs.pop("error_code", "TRANSPORT_ERROR")
        status_code = kwargs.pop("status_code", 500)
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )


class TransportConfigError(TransportError):
    """传输层配置错误异常

    当传输层配置错误时抛出，继承自TransportError。
    """

    def __init__(self, message: str, **kwargs):
        """初始化传输层配置异常

        Args:
            message: 错误消息
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=message,
            error_code="TRANSPORT_CONFIG_ERROR",
            status_code=500,
            **kwargs,
        )
