from typing import Any

from pydantic import BaseModel
from starlette.responses import JSONResponse

from dm_mcp.infra.web.error_codes import ErrorCode


class BaseResponse(BaseModel):
    """统一响应基类"""

    success: bool
    data: Any = None
    message: str = ""
    error: str | None = None
    code: str | None = None

    def to_json_response(self, status_code: int = 200) -> JSONResponse:
        return JSONResponse(
            self.model_dump(mode="json", exclude_none=True),
            status_code=status_code,
        )


class SuccessResponse(BaseResponse):
    """成功响应"""

    success: bool = True


class ErrorResponse(BaseResponse):
    """错误响应"""

    success: bool = False
    data: Any = None
    details: Any = None


def success_response(
    data: Any = None,
    message: str = "操作成功",
    status_code: int = 200,
) -> JSONResponse:
    return SuccessResponse(data=data, message=message).to_json_response(status_code)


def error_response(
    error: str,
    code: ErrorCode = ErrorCode.OPERATION_FAILED,
    status_code: int = 400,
    details: Any = None,
) -> JSONResponse:
    code_str = code.value if isinstance(code, ErrorCode) else code
    return ErrorResponse(error=error, code=code_str, details=details).to_json_response(status_code)
