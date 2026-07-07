"""基础异常类模块

提供DM-MCP系统的异常基类，所有业务异常都继承此类。
"""

from typing import Any


class DmMCPError(Exception):
    """DM-MCP系统基础异常

    所有业务异常的基类，提供统一的错误码、状态码和上下文支持。
    便于错误处理和错误响应格式化。
    """

    def __init__(
        self,
        message: str,
        error_code: str = "DMCP_UNKNOWN_ERROR",
        status_code: int = 500,
        details: dict[str, Any] | None = None,
    ):
        """初始化异常

        Args:
            message: 错误消息
            error_code: 错误码（默认"DMCP_UNKNOWN_ERROR"）
            status_code: HTTP状态码（默认500）
            details: 额外的错误详情（可选）
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式，便于JSON响应

        Returns:
            dict[str, Any]: 包含错误信息的字典
        """
        return {
            "error": self.error_code,
            "message": self.message,
            "status_code": self.status_code,
            "details": self.details,
        }
