"""BasicAuth控制器模块

提供BasicAuth认证相关的API端点，包括登录、密码初始化、修改密码等。
"""

from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.services.basic_auth_service import BasicAuthService


class BasicAuthController(object):
    """BasicAuth控制器

    处理BasicAuth认证相关请求，包括登录、密码初始化、修改密码等。
    """

    def __init__(self, basic_auth_service: BasicAuthService) -> None:
        """初始化BasicAuth控制器

        Args:
            basic_auth_service: BasicAuth服务实例
        """
        self.basic_auth_service = basic_auth_service

    async def handle_login(self, request: Request) -> JSONResponse:
        """处理BasicAuth登录请求

        从Authorization头中解析Basic Auth凭据，验证用户名和密码，
        成功后返回JWT token。

        请求头：Authorization: Basic base64(admin:password)

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含JWT token的成功响应或错误响应
        """
        # 从请求头获取 Basic Auth
        auth_header = request.headers.get("Authorization", "")
        credentials = BasicAuthService.decode_basic_auth(auth_header)
        if credentials is None:
            return JSONResponse(
                {
                    "success": False,
                    "error": {
                        "code": "INVALID_AUTH",
                        "message": "Invalid Basic Auth format",
                    },
                },
                status_code=401,
            )

        username, password = credentials

        # 验证用户名
        if username != "admin":
            return JSONResponse(
                {
                    "success": False,
                    "error": {
                        "code": "INVALID_USERNAME",
                        "message": "Invalid username",
                    },
                },
                status_code=401,
            )

        # 验证密码
        is_valid = await self.basic_auth_service.verify_password(password)
        if not is_valid:
            return JSONResponse(
                {
                    "success": False,
                    "error": {
                        "code": "INVALID_PASSWORD",
                        "message": "Invalid password",
                    },
                },
                status_code=401,
            )

        # 生成 JWT token
        jwt_token = self.basic_auth_service.create_jwt_token()

        return JSONResponse({"success": True, "jwt": jwt_token})

    async def handle_init_password(self, request: Request) -> JSONResponse:
        """处理admin密码初始化请求

        仅在admin密码未初始化时可用。用于首次设置admin密码。

        请求体：{"password": "..."}

        Args:
            request: HTTP请求对象，包含password字段

        Returns:
            JSONResponse: 成功或错误响应
        """
        try:
            body = await request.json()
            password = body.get("password", "")

            if not password:
                return JSONResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "MISSING_PASSWORD",
                            "message": "Password is required",
                        },
                    },
                    status_code=400,
                )

            await self.basic_auth_service.init_password(password)

            return JSONResponse(
                {"success": True, "message": "Password initialized successfully"}
            )
        except ValueError as e:
            return JSONResponse(
                {
                    "success": False,
                    "error": {"code": "INVALID_PASSWORD", "message": str(e)},
                },
                status_code=400,
            )
        except Exception as e:
            return JSONResponse(
                {
                    "success": False,
                    "error": {"code": "INTERNAL_ERROR", "message": str(e)},
                },
                status_code=500,
            )

    @requires("authenticated")
    async def handle_change_password(self, request: Request) -> JSONResponse:
        """处理admin密码修改请求

        需要认证。验证旧密码后更新为新密码。

        请求体：{"old_password": "...", "new_password": "..."}

        Args:
            request: HTTP请求对象，包含old_password和new_password字段

        Returns:
            JSONResponse: 成功或错误响应
        """
        try:
            body = await request.json()
            old_password = body.get("old_password", "")
            new_password = body.get("new_password", "")

            if not old_password or not new_password:
                return JSONResponse(
                    {
                        "success": False,
                        "error": {
                            "code": "MISSING_PASSWORD",
                            "message": "Old password and new password are required",
                        },
                    },
                    status_code=400,
                )

            await self.basic_auth_service.change_password(old_password, new_password)

            return JSONResponse(
                {"success": True, "message": "Password changed successfully"}
            )
        except ValueError as e:
            return JSONResponse(
                {
                    "success": False,
                    "error": {"code": "INVALID_PASSWORD", "message": str(e)},
                },
                status_code=400,
            )
        except Exception as e:
            return JSONResponse(
                {
                    "success": False,
                    "error": {"code": "INTERNAL_ERROR", "message": str(e)},
                },
                status_code=500,
            )
