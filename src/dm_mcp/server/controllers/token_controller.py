"""Token控制器模块

提供Token管理相关的API端点，包括创建、查询、更新、删除Token等。
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.token_service import TokenService
from dm_mcp.settings.token_auth_config import TokenConfig

logger = logging.getLogger(__name__)


# 请求模型
class CreateTokenRequest(BaseModel):
    """创建Token请求模型

    用于创建新Token的请求体。
    """

    datasource: str = Field(..., description="绑定的数据源名称（如 'primary'）")
    expires_in: Optional[int] = Field(None, description="有效期（秒），默认7天")
    description: Optional[str] = Field(None, description="描述信息")
    ip_whitelist: Optional[List[str]] = Field(
        None,
        description="IP 白名单列表（支持单个 IP 或 CIDR，如 '192.168.1.1' 或 '192.168.1.0/24'）",
    )
    ip_blacklist: Optional[List[str]] = Field(
        None, description="IP 黑名单列表（支持单个 IP 或 CIDR，如 '203.0.113.0/24'）"
    )


class UpdateTokenRequest(BaseModel):
    """更新Token请求模型

    用于更新Token信息的请求体。
    """

    datasource: Optional[str] = Field(
        None, description="绑定的数据源名称（如 'primary'）"
    )
    expires_at: Optional[str] = Field(None, description="过期时间（ISO 格式）")
    description: Optional[str] = Field(None, description="描述信息")
    ip_whitelist: Optional[List[str]] = Field(
        None,
        description="IP 白名单列表（支持单个 IP 或 CIDR，如 '192.168.1.1' 或 '192.168.1.0/24'）",
    )
    ip_blacklist: Optional[List[str]] = Field(
        None, description="IP 黑名单列表（支持单个 IP 或 CIDR，如 '203.0.113.0/24'）"
    )


# 错误码常量
class ErrorCode:
    """错误码常量类

    定义Token相关的错误码。
    """

    TOKEN_NOT_FOUND = "TOKEN_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    OPERATION_FAILED = "OPERATION_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class TokenController(object):
    """Token管理控制器

    处理Token相关的请求，包括创建、查询、更新、删除Token等操作。
    """

    def __init__(
        self,
        token_service: TokenService,
        datasource_service: Optional[DataSourceService] = None,
    ) -> None:
        """初始化Token控制器

        Args:
            token_service: Token服务实例
            datasource_service: 数据源服务实例（用于通过名称查找 UUID）
        """
        self.token_service = token_service
        self.datasource_service = datasource_service

    # ============================================================
    # 辅助方法
    # ============================================================

    def success_response(
        self, data: Any = None, message: str = "操作成功", status_code: int = 200
    ) -> JSONResponse:
        """统一成功响应格式"""
        return JSONResponse(
            {"success": True, "data": data, "message": message},
            status_code=status_code,
        )

    def error_response(
        self,
        error: str,
        code: str = ErrorCode.OPERATION_FAILED,
        status_code: int = 400,
    ) -> JSONResponse:
        """统一错误响应格式"""
        return JSONResponse(
            {"success": False, "error": error, "code": code},
            status_code=status_code,
        )

    def _get_auth_context(self, request: Request) -> AuthContext:
        """从请求中获取 AuthContext"""
        if not request.user or not hasattr(request.user, "auth_context"):
            return AuthContext(
                user_id="anonymous",
                auth_type="anonymous",
                token=None,
            )
        return request.user.auth_context

    async def _token_to_dict(
        self, token: TokenConfig, check_validity: bool = True
    ) -> Dict[str, Any]:
        """将TokenConfig转换为字典

        用于响应格式化，将Token配置对象转换为字典。

        Args:
            token: Token配置对象
            check_validity: 是否检查Token有效性（数据源是否存在且可用）

        Returns:
            Dict[str, Any]: 包含Token信息的字典
        """
        result = {
            "token": token.token,
            "user_id": token.user_id,
            "datasource_id": str(token.datasource_id),
            "created_at": token.created_at.isoformat(),
            "expires_at": token.expires_at.isoformat(),
            "last_used_at": (
                token.last_used_at.isoformat() if token.last_used_at else None
            ),
            "description": token.description,
            "ip_whitelist": token.ip_whitelist,
            "ip_blacklist": token.ip_blacklist,
        }

        # 检查Token有效性：验证绑定的数据源是否存在且可用
        if check_validity and self.datasource_service:
            try:
                ds = await self.datasource_service.get_datasource_by_id(
                    token.datasource_id
                )
                if ds and ds.enabled:
                    result["valid"] = True
                    result["datasource_name"] = (
                        ds.name
                    )  # 同时返回数据源名称，方便前端显示
                else:
                    result["valid"] = False
                    result["datasource_name"] = None
                    result["invalid_reason"] = (
                        "数据源不存在或已禁用" if ds else "数据源不存在"
                    )
            except Exception as e:
                logger.warning(f"检查Token有效性失败: {token.token[:8]}..., 错误: {e}")
                result["valid"] = False
                result["datasource_name"] = None
                result["invalid_reason"] = "无法验证数据源状态"
        else:
            # 如果没有数据源服务或不检查有效性，默认标记为未知状态
            result["valid"] = None
            result["datasource_name"] = None

        return result

    # ============================================================
    # CRUD 操作
    # ============================================================

    @requires("authenticated")
    async def handle_create(self, request: Request) -> JSONResponse:
        """创建Token

        根据请求体创建新Token，Token的所有者从认证上下文中获取。
        需要认证。

        Args:
            request: HTTP请求对象，包含CreateTokenRequest格式的请求体

        Returns:
            JSONResponse: 包含新创建Token信息的成功响应或错误响应
        """
        try:
            body = await request.json()
            create_request = CreateTokenRequest(**body)

            # 从 AuthContext 获取用户信息
            auth_context = self._get_auth_context(request)
            user_id = auth_context.user_id

            # 通过数据源名称查找 UUID
            if not self.datasource_service:
                return self.error_response(
                    error="数据源服务不可用",
                    code=ErrorCode.INTERNAL_ERROR,
                    status_code=500,
                )

            ds = await self.datasource_service.get_datasource(create_request.datasource)
            if not ds:
                return self.error_response(
                    error=f"数据源不存在: {create_request.datasource}",
                    code=ErrorCode.OPERATION_FAILED,
                    status_code=400,
                )

            # 创建 Token
            token_config = await self.token_service.create_token(
                user_id=user_id,
                datasource_id=ds.id,
                expires_in=create_request.expires_in,
                description=create_request.description,
                ip_whitelist=create_request.ip_whitelist,
                ip_blacklist=create_request.ip_blacklist,
            )

            return self.success_response(
                data=await self._token_to_dict(token_config),
                message="Token 创建成功",
                status_code=201,
            )

        except ValidationError as e:
            logger.error(f"Token 创建请求验证失败: {e}")
            return self.error_response(
                error=f"请求验证失败: {e.error_count()} 个错误",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except Exception as e:
            logger.error(f"创建 Token 失败: {e}", exc_info=True)
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_list(self, request: Request) -> JSONResponse:
        """列出当前用户创建的所有Token

        返回当前认证用户创建的所有Token列表。
        需要认证。

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含Token列表的成功响应或错误响应
        """
        try:
            # 从 AuthContext 获取当前用户 ID
            auth_context = self._get_auth_context(request)
            user_id = auth_context.user_id

            # 只返回当前用户创建的 Token
            tokens = await self.token_service.list_tokens(user_id=user_id)
            result = [await self._token_to_dict(token) for token in tokens]

            return self.success_response(data=result, message="获取 Token 列表成功")

        except Exception as e:
            logger.error(f"列出 Token 失败: {e}", exc_info=True)
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_get(self, request: Request) -> JSONResponse:
        """获取单个Token

        根据Token值获取Token信息，只能获取自己创建的Token。
        需要认证。

        Args:
            request: HTTP请求对象，包含token路径参数

        Returns:
            JSONResponse: 包含Token信息的成功响应或错误响应
        """
        try:
            token_value = request.path_params["token"]
            auth_context = self._get_auth_context(request)
            current_user_id = auth_context.user_id

            token = await self.token_service.get_token(token_value)

            if not token:
                return self.error_response(
                    error=f"Token 不存在: {token_value[:8]}...",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            # 检查权限：只能查看自己创建的 Token
            if token.user_id != current_user_id:
                return self.error_response(
                    error=f"Token 不存在: {token_value[:8]}...",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            return self.success_response(
                data=await self._token_to_dict(token), message="获取 Token 成功"
            )

        except Exception as e:
            logger.error(f"获取 Token 失败: {e}", exc_info=True)
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_update(self, request: Request) -> JSONResponse:
        """更新 Token（只能更新自己创建的 Token）"""
        try:
            token_value = request.path_params["token"]
            auth_context = self._get_auth_context(request)
            current_user_id = auth_context.user_id

            # 先检查 Token 是否存在且属于当前用户
            token = await self.token_service.get_token(token_value)
            if not token:
                return self.error_response(
                    error=f"Token 不存在: {token_value[:8]}...",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            if token.user_id != current_user_id:
                return self.error_response(
                    error=f"Token 不存在: {token_value[:8]}...",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            body = await request.json()
            update_request = UpdateTokenRequest(**body)

            # 解析 expires_at
            expires_at = None
            if update_request.expires_at:
                expires_at = datetime.fromisoformat(
                    update_request.expires_at.replace("Z", "+00:00")
                )
                # 确保 expires_at 是 aware datetime（如果是 naive，假设是 UTC）
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)

            # 如果提供了数据源名称，查找对应的 UUID
            datasource_id = None
            if update_request.datasource:
                if not self.datasource_service:
                    return self.error_response(
                        error="数据源服务不可用",
                        code=ErrorCode.INTERNAL_ERROR,
                        status_code=500,
                    )
                ds = await self.datasource_service.get_datasource(
                    update_request.datasource
                )
                if not ds:
                    return self.error_response(
                        error=f"数据源不存在: {update_request.datasource}",
                        code=ErrorCode.OPERATION_FAILED,
                        status_code=400,
                    )
                datasource_id = ds.id

            # 更新 Token
            token_config = await self.token_service.update_token(
                token=token_value,
                datasource_id=datasource_id,
                expires_at=expires_at,
                description=update_request.description,
                ip_whitelist=update_request.ip_whitelist,
                ip_blacklist=update_request.ip_blacklist,
            )

            return self.success_response(
                data=await self._token_to_dict(token_config),
                message="Token 更新成功",
            )

        except ValidationError as e:
            logger.error(f"Token 更新请求验证失败: {e}")
            return self.error_response(
                error=f"请求验证失败: {e.error_count()} 个错误",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg.lower():
                return self.error_response(
                    error=error_msg,
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )
            return self.error_response(error=error_msg, status_code=400)
        except Exception as e:
            logger.error(f"更新 Token 失败: {e}", exc_info=True)
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_delete(self, request: Request) -> JSONResponse:
        """删除Token

        根据Token值删除Token，只能删除自己创建的Token。
        需要认证。

        Args:
            request: HTTP请求对象，包含token路径参数

        Returns:
            JSONResponse: 删除成功的响应或错误响应
        """
        try:
            token_value = request.path_params["token"]
            auth_context = self._get_auth_context(request)
            current_user_id = auth_context.user_id

            # 先检查 Token 是否存在且属于当前用户
            token = await self.token_service.get_token(token_value)
            if not token:
                return self.error_response(
                    error=f"Token 不存在: {token_value[:8]}...",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            if token.user_id != current_user_id:
                return self.error_response(
                    error=f"Token 不存在: {token_value[:8]}...",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            await self.token_service.delete_token(token_value)

            return self.success_response(
                data=None, message=f"Token 删除成功: {token_value[:8]}..."
            )

        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg.lower():
                return self.error_response(
                    error=error_msg,
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )
            return self.error_response(error=error_msg, status_code=400)
        except Exception as e:
            logger.error(f"删除 Token 失败: {e}", exc_info=True)
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
