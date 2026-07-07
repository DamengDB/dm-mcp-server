"""Token控制器模块

提供Token管理相关的API端点，包括创建、查询、更新、删除Token等。
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.web.error_codes import ErrorCode
from dm_mcp.api.base import BaseController
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.ssh.services.host import SSHHostService
from dm_mcp.domain.token.services.token import TokenService
from dm_mcp.infra.config.token_auth_config import TokenConfig

logger = logging.getLogger(__name__)


# 请求模型
class CreateTokenRequest(BaseModel):
    """创建Token请求模型

    用于创建新Token的请求体。
    """

    datasource_names: list[str] = Field(
        ..., min_length=1, description="允许访问的数据源名称列表（如 ['primary', 'analytics']）"
    )
    default_datasource_name: str = Field(
        ..., description="默认数据源名称，必须是 datasource_names 中的一项"
    )
    name: str = Field(..., min_length=1, description="Token 名称（必填，非空）")
    expires_in: int | None = Field(None, description="有效期（秒），默认7天")
    ip_whitelist: list[str] | None = Field(
        None,
        description="IP 白名单列表（支持单个 IP 或 CIDR，如 '192.168.1.1' 或 '192.168.1.0/24'）",
    )
    ip_blacklist: list[str] | None = Field(
        None, description="IP 黑名单列表（支持单个 IP 或 CIDR，如 '203.0.113.0/24'）"
    )
    ssh_host_names: list[str] | None = Field(
        None, description="允许访问的 SSH 主机名称列表（如 ['web-01', 'db-01']）"
    )


class UpdateTokenRequest(BaseModel):
    """更新Token请求模型

    用于更新Token信息的请求体。
    """

    datasource_names: list[str] | None = Field(
        None, description="允许访问的数据源名称列表（如 ['primary', 'analytics']）"
    )
    default_datasource_name: str | None = Field(
        None, description="默认数据源名称，必须是 datasource_names 中的一项"
    )
    expires_at: str | None = Field(None, description="过期时间（ISO 格式）")
    name: str | None = Field(
        None, min_length=1, description="Token 名称（可选；传入时不能为空字符串）"
    )
    ip_whitelist: list[str] | None = Field(
        None,
        description="IP 白名单列表（支持单个 IP 或 CIDR，如 '192.168.1.1' 或 '192.168.1.0/24'）",
    )
    ip_blacklist: list[str] | None = Field(
        None, description="IP 黑名单列表（支持单个 IP 或 CIDR，如 '203.0.113.0/24'）"
    )
    ssh_host_names: list[str] | None = Field(
        None, description="允许访问的 SSH 主机名称列表（如 ['web-01', 'db-01']）"
    )


class TokenController(BaseController):
    """Token管理控制器

    处理Token相关的请求，包括创建、查询、更新、删除Token等操作。
    """

    def __init__(
        self,
        token_service: TokenService,
        datasource_service: DataSourceService | None = None,
        ssh_host_service: SSHHostService | None = None,
    ) -> None:
        """初始化Token控制器

        Args:
            token_service: Token服务实例
            datasource_service: 数据源服务实例（用于通过名称查找 UUID）
            ssh_host_service: SSH主机服务实例（用于通过名称查找 UUID）
        """
        self.token_service = token_service
        self.datasource_service = datasource_service
        self.ssh_host_service = ssh_host_service

    # ============================================================
    # 辅助方法
    # ============================================================

    async def _token_to_dict(
        self,
        token: TokenConfig,
        check_validity: bool = True,
        include_secret: bool = True,
    ) -> dict[str, Any]:
        """将TokenConfig转换为字典

        用于响应格式化，将Token配置对象转换为字典。
        对外展示数据源名称而非 UUID。

        Args:
            token: Token配置对象
            check_validity: 是否检查Token有效性（数据源是否存在且可用）
            include_secret: 是否在响应中包含明文 token 字段（默认 True，update 端点应传 False）

        Returns:
            dict[str, Any]: 包含Token信息的字典
        """
        result: dict[str, Any] = {
            "token_id": token.token_id,
            "user_id": token.user_id,
            "created_at": token.created_at.isoformat(),
            "expires_at": token.expires_at.isoformat(),
            "last_used_at": (
                token.last_used_at.isoformat() if token.last_used_at else None
            ),
            "name": token.name,
            "ip_whitelist": token.ip_whitelist,
            "ip_blacklist": token.ip_blacklist,
        }
        if include_secret:
            result["token"] = token.token

        # 解析数据源 UUID 列表到名称列表
        datasource_names: list[str] = []
        default_datasource_name: str | None = None
        invalid_count = 0

        if self.datasource_service:
            for ds_id in token.datasource_ids:
                try:
                    ds = await self.datasource_service.get_datasource_by_id(
                        ds_id, skip_authz=True
                    )
                    if ds and ds.enabled:
                        datasource_names.append(ds.name)
                    else:
                        invalid_count += 1
                except Exception:
                    invalid_count += 1

            # 反查默认数据源名称
            if token.default_datasource_id:
                try:
                    ds = await self.datasource_service.get_datasource_by_id(
                        token.default_datasource_id, skip_authz=True
                    )
                    default_datasource_name = ds.name if ds else None
                except Exception:
                    pass

        result["datasource_names"] = datasource_names
        result["default_datasource_name"] = default_datasource_name

        # 解析 SSH 主机 UUID 列表到名称列表
        ssh_host_names: list[str] = []
        ssh_invalid_count = 0

        if self.ssh_host_service:
            for host_id in token.ssh_host_ids:
                try:
                    host = await self.ssh_host_service.get_host(host_id, skip_authz=True)
                    if host:
                        ssh_host_names.append(host.name)
                    else:
                        ssh_invalid_count += 1
                except Exception:
                    ssh_invalid_count += 1

        result["ssh_host_names"] = ssh_host_names
        result["ssh_host_ids"] = token.ssh_host_ids

        # 检查Token有效性：只要有可用数据源即有效
        if check_validity and self.datasource_service:
            result["valid"] = len(datasource_names) > 0
            if invalid_count > 0:
                result["invalid_reason"] = (
                    f"{invalid_count} 个数据源不存在或已禁用"
                )
        else:
            result["valid"] = None

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
            auth_context = self.get_auth_context(request)
            user_id = auth_context.user_id

            # 校验并解析数据源名称列表为 UUID 列表
            if not self.datasource_service:
                return self.error(
                    error="数据源服务不可用",
                    code=ErrorCode.INTERNAL_ERROR,
                    status_code=500,
                )

            datasource_ids: list[str] = []
            for ds_name in create_request.datasource_names:
                ds = await self.datasource_service.get_datasource(ds_name)
                if not ds:
                    return self.error(
                        error=f"数据源不存在或无权限: {ds_name}",
                        code=ErrorCode.OPERATION_FAILED,
                        status_code=400,
                    )
                datasource_ids.append(str(ds.id))

            # 解析默认数据源名称
            default_ds = await self.datasource_service.get_datasource(
                create_request.default_datasource_name
            )
            if not default_ds:
                return self.error(
                    error=f"默认数据源不存在或无权限: {create_request.default_datasource_name}",
                    code=ErrorCode.OPERATION_FAILED,
                    status_code=400,
                )

            # 解析 SSH 主机名称列表为 UUID 列表
            ssh_host_ids: list[str] = []
            if create_request.ssh_host_names and self.ssh_host_service:
                for host_name in create_request.ssh_host_names:
                    host = await self.ssh_host_service.get_host_by_name(host_name)
                    if not host:
                        return self.error(
                            error=f"SSH 主机不存在或无权限: {host_name}",
                            code=ErrorCode.OPERATION_FAILED,
                            status_code=400,
                        )
                    ssh_host_ids.append(str(host.id))

            # 创建 Token
            token_config = await self.token_service.create_token(
                user_id=user_id,
                datasource_ids=datasource_ids,
                default_datasource_id=str(default_ds.id),
                name=create_request.name,
                expires_in=create_request.expires_in,
                ip_whitelist=create_request.ip_whitelist,
                ip_blacklist=create_request.ip_blacklist,
                ssh_host_ids=ssh_host_ids or None,
            )

            return self.success(
                data=await self._token_to_dict(token_config),
                message="Token 创建成功",
                status_code=201,
            )

        except ValidationError as e:
            logger.error(f"Token 创建请求验证失败: {e}")
            return self.error(
                error=f"请求验证失败: {e.error_count()} 个错误",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except Exception as e:
            logger.error(f"创建 Token 失败: {e}", exc_info=True)
            return self.error(
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
            auth_context = self.get_auth_context(request)
            user_id = auth_context.user_id

            # 只返回当前用户创建的 Token
            tokens = await self.token_service.list_tokens(user_id=user_id)
            result = [
                await self._token_to_dict(token)
                for token in tokens
            ]

            return self.success(data=result, message="获取 Token 列表成功")

        except Exception as e:
            logger.error(f"列出 Token 失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_get(self, request: Request) -> JSONResponse:
        """获取单个Token

        根据 token_id 获取 Token 信息，只能获取自己创建的 Token。
        需要认证。

        Args:
            request: HTTP请求对象，包含 token_id 路径参数

        Returns:
            JSONResponse: 包含Token信息的成功响应或错误响应
        """
        try:
            token_id = request.path_params["token_id"]
            auth_context = self.get_auth_context(request)
            current_user_id = auth_context.user_id

            token = await self.token_service.get_by_token_id(token_id)

            if not token:
                return self.error(
                    error=f"Token 不存在: {token_id}",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            # 检查权限：只能查看自己创建的 Token
            if token.user_id != current_user_id:
                return self.error(
                    error=f"Token 不存在: {token_id}",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            return self.success(
                data=await self._token_to_dict(token),
                message="获取 Token 成功"
            )

        except Exception as e:
            logger.error(f"获取 Token 失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_update(self, request: Request) -> JSONResponse:
        """更新 Token（只能更新自己创建的 Token）"""
        try:
            token_id = request.path_params["token_id"]
            auth_context = self.get_auth_context(request)
            current_user_id = auth_context.user_id

            # 通过 token_id 解析 TokenConfig，并校验所有权
            token = await self.token_service.get_by_token_id(token_id)
            if not token:
                return self.error(
                    error=f"Token 不存在: {token_id}",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            if token.user_id != current_user_id:
                return self.error(
                    error=f"Token 不存在: {token_id}",
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

            # 如果提供了数据源名称列表，解析为 UUID 列表
            datasource_ids = None
            if update_request.datasource_names is not None:
                if not self.datasource_service:
                    return self.error(
                        error="数据源服务不可用",
                        code=ErrorCode.INTERNAL_ERROR,
                        status_code=500,
                    )
                datasource_ids = []
                for ds_name in update_request.datasource_names:
                    ds = await self.datasource_service.get_datasource(ds_name)
                    if not ds:
                        return self.error(
                            error=f"数据源不存在或无权限: {ds_name}",
                            code=ErrorCode.OPERATION_FAILED,
                            status_code=400,
                        )
                    datasource_ids.append(str(ds.id))

            # 如果提供了默认数据源名称，解析为 UUID 字符串
            default_datasource_id = None
            if update_request.default_datasource_name is not None:
                if not self.datasource_service:
                    return self.error(
                        error="数据源服务不可用",
                        code=ErrorCode.INTERNAL_ERROR,
                        status_code=500,
                    )
                default_ds = await self.datasource_service.get_datasource(
                    update_request.default_datasource_name
                )
                if not default_ds:
                    return self.error(
                        error=f"默认数据源不存在或无权限: {update_request.default_datasource_name}",
                        code=ErrorCode.OPERATION_FAILED,
                        status_code=400,
                    )
                default_datasource_id = str(default_ds.id)

            # 如果提供了 SSH 主机名称列表，解析为 UUID 列表
            ssh_host_ids = None
            if update_request.ssh_host_names is not None:
                if not self.ssh_host_service:
                    return self.error(
                        error="SSH 主机服务不可用",
                        code=ErrorCode.INTERNAL_ERROR,
                        status_code=500,
                    )
                ssh_host_ids = []
                for host_name in update_request.ssh_host_names:
                    host = await self.ssh_host_service.get_host_by_name(host_name)
                    if not host:
                        return self.error(
                            error=f"SSH 主机不存在或无权限: {host_name}",
                            code=ErrorCode.OPERATION_FAILED,
                            status_code=400,
                        )
                    ssh_host_ids.append(str(host.id))

            # 更新 Token
            token_config = await self.token_service.update_token(
                token_id=token_id,
                datasource_ids=datasource_ids,
                default_datasource_id=default_datasource_id,
                expires_at=expires_at,
                name=update_request.name,
                ip_whitelist=update_request.ip_whitelist,
                ip_blacklist=update_request.ip_blacklist,
                ssh_host_ids=ssh_host_ids,
            )

            return self.success(
                data=await self._token_to_dict(token_config, include_secret=False),
                message="Token 更新成功",
            )

        except ValidationError as e:
            logger.error(f"Token 更新请求验证失败: {e}")
            return self.error(
                error=f"请求验证失败: {e.error_count()} 个错误",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg.lower():
                return self.error(
                    error=error_msg,
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )
            return self.error(error=error_msg, status_code=400)
        except Exception as e:
            logger.error(f"更新 Token 失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_delete(self, request: Request) -> JSONResponse:
        """删除Token

        根据 token_id 删除 Token，只能删除自己创建的 Token。
        需要认证。

        Args:
            request: HTTP请求对象，包含 token_id 路径参数

        Returns:
            JSONResponse: 删除成功的响应或错误响应
        """
        try:
            token_id = request.path_params["token_id"]
            auth_context = self.get_auth_context(request)
            current_user_id = auth_context.user_id

            # 通过 token_id 解析 TokenConfig，并校验所有权
            token = await self.token_service.get_by_token_id(token_id)
            if not token:
                return self.error(
                    error=f"Token 不存在: {token_id}",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            if token.user_id != current_user_id:
                return self.error(
                    error=f"Token 不存在: {token_id}",
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )

            await self.token_service.delete_token(token_id)

            return self.success(
                data=None, message=f"Token 删除成功: {token_id}"
            )

        except ValueError as e:
            error_msg = str(e)
            if "not found" in error_msg.lower():
                return self.error(
                    error=error_msg,
                    code=ErrorCode.TOKEN_NOT_FOUND,
                    status_code=404,
                )
            return self.error(error=error_msg, status_code=400)
        except Exception as e:
            logger.error(f"删除 Token 失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
