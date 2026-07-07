"""验证相关异常模块

提供参数验证相关的异常类定义，包括参数无效、缺少参数等异常。
"""

from typing import Any

from dm_mcp.common import messages
from .base_error import DmMCPError


class ValidationError(DmMCPError):
    """验证错误异常

    所有验证相关异常的基类，HTTP状态码为400。
    """

    def __init__(
        self,
        message: str = messages.MSG_VALIDATION_FAILED,
        errors: list[dict[str, Any]] | None = None,
        **kwargs,
    ):
        error_code = kwargs.pop("error_code", "VALIDATION_ERROR")
        status_code = kwargs.pop("status_code", 400)
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )
        if errors:
            self.details["errors"] = errors


class InvalidParameterError(ValidationError):
    """参数无效异常

    当参数格式不正确或值不合法时抛出，继承自ValidationError。
    """

    def __init__(self, parameter: str, reason: str | None = None, **kwargs):
        message = messages.MSG_INVALID_PARAMETER.format(parameter=parameter)
        if reason:
            message += f" ({reason})"
        super().__init__(
            message=message, error_code="INVALID_PARAMETER", status_code=400, **kwargs
        )
        self.details["parameter"] = parameter


class MissingParameterError(ValidationError):
    """缺少参数异常

    当必需的参数缺失时抛出，继承自ValidationError。
    """

    def __init__(self, parameter: str, **kwargs):
        super().__init__(
            message=messages.MSG_MISSING_PARAMETER.format(parameter=parameter),
            error_code="MISSING_PARAMETER",
            status_code=400,
            **kwargs,
        )
        self.details["parameter"] = parameter
