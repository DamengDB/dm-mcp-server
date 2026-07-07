"""服务相关异常模块

提供服务管理相关的异常类定义，包括服务未找到、循环依赖等异常。
"""

from dm_mcp.common import messages
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
        super().__init__(
            message=messages.MSG_SERVICE_NOT_FOUND.format(service_name=service_name),
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
        if path:
            message = messages.MSG_SERVICE_CIRCULAR_DEPENDENCY_WITH_PATH.format(
                service_name=service_name, path=path
            )
        else:
            message = messages.MSG_SERVICE_CIRCULAR_DEPENDENCY.format(
                service_name=service_name
            )
        super().__init__(
            message=message,
            service_name=service_name,
            error_code="SERVICE_CIRCULAR_DEPENDENCY",
            status_code=503,
            **kwargs,
        )
