import logging
from typing import TYPE_CHECKING, Any, Union

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.web.error_codes import ErrorCode
from dm_mcp.infra.web.responses import error_response, success_response

if TYPE_CHECKING:
    from dm_mcp.domain.token.services.token import TokenService
    from dm_mcp.infra.config.token_auth_config import TokenConfig

logger = logging.getLogger(__name__)


class BaseController:
    """Controller 基类

    提供统一的成功/错误响应方法、认证上下文获取、以及公共辅助方法。
    所有业务 Controller 应继承此类。
    """

    # ---------------------------
    # 响应方法
    # ---------------------------

    @staticmethod
    def success(
        data: Any = None,
        message: str = "操作成功",
        status_code: int = 200,
    ) -> JSONResponse:
        return success_response(data=data, message=message, status_code=status_code)

    @staticmethod
    def error(
        error: str,
        code: Union[str, ErrorCode] = ErrorCode.OPERATION_FAILED,
        status_code: int = 400,
        details: Any = None,
    ) -> JSONResponse:
        return error_response(error=error, code=code, status_code=status_code, details=details)

    # ---------------------------
    # 认证辅助
    # ---------------------------

    @staticmethod
    def get_auth_context(request: Request) -> AuthContext:
        """从 Starlette request 中获取 AuthContext"""
        user = request.user
        auth_ctx = getattr(user, "auth_context", None)
        if auth_ctx:
            return auth_ctx
        return AuthContext(
            user_id="anonymous",
            auth_type="anonymous",
            token=None,
        )

    @staticmethod
    def get_current_user_id(request: Request) -> str:
        """获取当前用户 ID（无认证时返回 anonymous）"""
        return BaseController.get_auth_context(request).user_id

    @staticmethod
    def is_admin(request: Request) -> bool:
        """判断当前用户是否为 admin"""
        return BaseController.get_auth_context(request).auth_type == "basic_auth"

    # ---------------------------
    # token_id 解析辅助
    # ---------------------------

    @staticmethod
    async def resolve_token_from_id(
        token_id: str | None,
        token_service: "TokenService",
    ) -> "TokenConfig | None":
        """根据 token_id 解析 TokenConfig

        - token_id 为 None 或空字符串 → 返回 None（caller 视为"未传 token_id"）
        - token_id 已传但找不到 → 返回 None（caller 应回 404）

        caller 凭 token_id 是否已传 + 返回是否为 None 自行区分两种语义。
        """
        if not token_id:
            return None
        return await token_service.get_by_token_id(token_id)

    # ---------------------------
    # 校验辅助
    # ---------------------------

    @staticmethod
    def format_validation_error(error: ValidationError) -> str:
        """格式化 Pydantic ValidationError 为可读字符串"""
        details: list[str] = []
        for err in error.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            msg = err["msg"]
            details.append(f"{field}: {msg}")
        return "; ".join(details)
