"""BasicAuth控制器模块

提供BasicAuth认证相关的API端点，包括登录、密码初始化、修改密码等。
"""

from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.common import messages
from dm_mcp.infra.web.error_codes import ErrorCode
from dm_mcp.api.base import BaseController
from dm_mcp.domain.auth.services.basic_auth import BasicAuthService


class BasicAuthController(BaseController):
    """BasicAuth控制器

    处理BasicAuth认证相关请求，包括登录、密码初始化、修改密码等。
    """

    def __init__(self, basic_auth_service: BasicAuthService) -> None:
        self.basic_auth_service = basic_auth_service

    async def handle_login(self, request: Request) -> JSONResponse:
        """处理BasicAuth登录请求"""
        auth_header = request.headers.get("Authorization", "")
        credentials = BasicAuthService.decode_basic_auth(auth_header)
        if credentials is None:
            return self.error(
                messages.MSG_AUTH_BASIC_AUTH_FORMAT_INVALID,
                code="INVALID_AUTH",
                status_code=401,
            )

        username, password = credentials

        if username != "admin":
            return self.error(
                messages.MSG_AUTH_USERNAME_INVALID,
                code="INVALID_USERNAME",
                status_code=401,
            )

        is_valid = await self.basic_auth_service.verify_password(password)
        if not is_valid:
            return self.error(
                messages.MSG_AUTH_PASSWORD_INVALID,
                code="INVALID_PASSWORD",
                status_code=401,
            )

        jwt_token = self.basic_auth_service.create_jwt_token()
        return self.success(data={"jwt": jwt_token})

    async def handle_init_password(self, request: Request) -> JSONResponse:
        """处理admin密码初始化请求"""
        try:
            body = await request.json()
            password = body.get("password", "")

            if not password:
                return self.error(
                    messages.MSG_AUTH_PASSWORD_REQUIRED,
                    code="MISSING_PASSWORD",
                )

            await self.basic_auth_service.init_password(password)

            return self.success(message=messages.MSG_AUTH_PASSWORD_INITIALIZED)
        except ValueError as e:
            return self.error(str(e), code="INVALID_PASSWORD")
        except Exception as e:
            return self.error(str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_change_password(self, request: Request) -> JSONResponse:
        """处理admin密码修改请求"""
        try:
            body = await request.json()
            old_password = body.get("old_password", "")
            new_password = body.get("new_password", "")

            if not old_password or not new_password:
                return self.error(
                    messages.MSG_AUTH_OLD_AND_NEW_PASSWORD_REQUIRED,
                    code="MISSING_PASSWORD",
                )

            await self.basic_auth_service.change_password(old_password, new_password)

            return self.success(message=messages.MSG_AUTH_PASSWORD_CHANGED)
        except ValueError as e:
            return self.error(str(e), code="INVALID_PASSWORD")
        except Exception as e:
            return self.error(str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)
