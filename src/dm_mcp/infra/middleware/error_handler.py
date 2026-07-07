"""全局异常处理中间件模块

提供全局异常处理中间件，统一捕获和处理所有未捕获的异常。
"""

import logging
import traceback

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dm_mcp.common import messages
from dm_mcp.core.exceptions import DmMCPError

logger = logging.getLogger(__name__)


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """全局异常处理中间件

    统一捕获和处理所有未捕获的异常，返回标准化的错误响应。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求并捕获异常

        Args:
            request: HTTP请求对象
            call_next: 下一个中间件或路由处理器

        Returns:
            Response: HTTP响应对象
        """
        try:
            response = await call_next(request)
            return response
        except DmMCPError as e:
            # 业务异常，已经包含完整的错误信息
            logger.warning(
                f"业务异常: {e.error_code}, 路径: {request.url.path}, 方法: {request.method}",
                extra={
                    "error_code": e.error_code,
                    "error_message": e.message,  # 避免与LogRecord的message字段冲突
                    "status_code": e.status_code,
                    "details": e.details,
                    "path": request.url.path,
                    "method": request.method,
                },
            )
            return self._create_error_response(e)

        except Exception as e:
            # 未预期的系统异常
            logger.error(
                f"未预期的系统异常: {type(e).__name__}, 路径: {request.url.path}, 方法: {request.method}, 错误: {str(e)}",
                extra={
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "path": request.url.path,
                    "method": request.method,
                },
                exc_info=True,
            )
            return self._create_error_response(
                DmMCPError(
                    message=messages.MSG_INTERNAL_SERVER_ERROR,
                    error_code="INTERNAL_SERVER_ERROR",
                    status_code=500,
                    details=(
                        {"original_error": str(e)}
                        if logger.isEnabledFor(logging.DEBUG)
                        else {}
                    ),
                )
            )

    def _create_error_response(self, error: DmMCPError) -> JSONResponse:
        """创建标准化的错误响应

        使用UTF-8编码支持中文，返回包含错误信息的JSON响应。

        Args:
            error: 业务异常对象

        Returns:
            JSONResponse: 包含错误信息的JSON响应
        """
        return JSONResponse(
            status_code=error.status_code,
            content={
                "success": False,
                "error": {
                    "code": error.error_code,
                    "message": error.message,
                    "details": error.details,
                },
            },
            media_type="application/json; charset=utf-8",
        )
