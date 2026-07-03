"""服务相关异常模块

提供服务管理相关的异常类定义，包括服务未找到、循环依赖等异常。
"""

from .base_error import DmMCPError


class ServiceError(DmMCPError):
    """服务基础异常

    所有服务相关异常的基类，HTTP状态码为500。
    """

    def __init__(
        self,
        message: str,
        service_name: str | None = None,
        error_code: str = "SERVICE_ERROR",
        status_code: int = 500,
        **kwargs,
    ):
        """初始化服务异常

        Args:
            message: 错误消息
            service_name: 服务名称（可选）
            error_code: 错误码（默认"SERVICE_ERROR"）
            status_code: HTTP状态码（默认500）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )
        if service_name:
            self.details["service"] = service_name


class ServiceNotFoundError(ServiceError):
    """服务未找到异常

    当指定的服务不存在时抛出，继承自ServiceError，HTTP状态码为404。
    """

    def __init__(self, service_name: str, **kwargs):
        """初始化服务未找到异常

        Args:
            service_name: 服务名称
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=f"Service '{service_name}' not found",
            service_name=service_name,
            error_code="SERVICE_NOT_FOUND",
            status_code=404,
            **kwargs,
        )


class ServiceCircularDependencyError(ServiceError):
    """服务循环依赖异常

    当检测到服务之间存在循环依赖时抛出，继承自ServiceError，HTTP状态码为503。
    """

    def __init__(self, service_name: str, path: str | None = None, **kwargs):
        """初始化服务循环依赖异常

        Args:
            service_name: 服务名称
            path: 循环依赖路径（可选）
            **kwargs: 其他参数传递给基类
        """
        message = f"Service '{service_name}' circular dependency"
        if path:
            message += f" with path '{path}'"
        super().__init__(
            message=message,
            service_name=service_name,
            error_code="SERVICE_CIRCULAR_DEPENDENCY",
            status_code=503,
            **kwargs,
        )
