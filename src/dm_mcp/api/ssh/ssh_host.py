"""SSH 主机控制器模块

提供 SSH 主机管理相关的 API 端点。
"""

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.infra.web.error_codes import ErrorCode
from dm_mcp.api.base import BaseController
from dm_mcp.domain.ssh.services.host import SSHHostService

logger = logging.getLogger(__name__)


class CreateSSHHostRequest(BaseModel):
    """创建 SSH 主机请求模型"""

    name: str = Field(..., min_length=1, description="唯一标识名")
    host: str = Field(..., min_length=1, description="IP 或域名")
    port: int = Field(default=22, ge=1, le=65535, description="SSH 端口")
    username: str = Field(..., min_length=1, description="登录用户名")
    key_based: bool = Field(default=False, description="False=密码认证, True=免密")
    password: str | None = Field(
        default=None, description="密码（key_based=False 时必填）"
    )
    description: str = Field(default="", description="描述")


class UpdateSSHHostRequest(BaseModel):
    """更新 SSH 主机请求模型（PATCH 语义）"""

    name: str | None = Field(default=None, min_length=1, description="唯一标识名")
    host: str | None = Field(default=None, min_length=1, description="IP 或域名")
    port: int | None = Field(default=None, ge=1, le=65535, description="SSH 端口")
    username: str | None = Field(default=None, min_length=1, description="登录用户名")
    key_based: bool | None = Field(
        default=None, description="False=密码认证, True=免密"
    )
    password: str | None = Field(default=None, description="密码（传入则更新加密）")
    description: str | None = Field(default=None, description="描述")


class SSHHostController(BaseController):
    """SSH 主机管理控制器"""

    def __init__(self, ssh_host_service: SSHHostService) -> None:
        self.ssh_host_service = ssh_host_service

    # ============================================================
    # 辅助方法
    # ============================================================

    def _host_to_dict(self, host, include_secret: bool = False) -> dict[str, Any]:
        """将 SSHHostModel 转换为响应字典"""
        return host.to_dict(include_secret=include_secret)

    # ============================================================
    # CRUD 操作
    # ============================================================

    @requires("authenticated")
    async def handle_create(self, request: Request) -> JSONResponse:
        """创建 SSH 主机"""
        try:
            body = await request.json()
            create_request = CreateSSHHostRequest(**body)

            if not create_request.key_based and not create_request.password:
                return self.error(
                    error="密码认证模式下 password 为必填项",
                    code=ErrorCode.VALIDATION_ERROR,
                    status_code=400,
                )

            config = await self.ssh_host_service.create_host(
                name=create_request.name,
                host=create_request.host,
                port=create_request.port,
                username=create_request.username,
                key_based=create_request.key_based,
                password=create_request.password,
                description=create_request.description,
            )

            return self.success(
                data={
                    "id": config.id,
                    "name": config.name,
                    "host": config.host,
                    "port": config.port,
                    "username": config.username,
                    "key_based": config.key_based,
                    "description": config.description,
                    "owner_id": config.owner_id,
                },
                message="SSH 主机创建成功",
                status_code=201,
            )

        except ValidationError as e:
            logger.error(f"创建 SSH 主机请求验证失败: {e}")
            return self.error(
                error=f"请求验证失败: {self.format_validation_error(e)}",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            return self.error(error=str(e), code=ErrorCode.OPERATION_FAILED, status_code=400)
        except Exception as e:
            logger.error(f"创建 SSH 主机失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_list(self, request: Request) -> JSONResponse:
        """列出当前用户可见的 SSH 主机"""
        try:
            hosts = await self.ssh_host_service.list_hosts()
            result = [self._host_to_dict(host) for host in hosts]
            return self.success(data=result, message="获取 SSH 主机列表成功")
        except Exception as e:
            logger.error(f"列出 SSH 主机失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_get(self, request: Request) -> JSONResponse:
        """获取单个 SSH 主机"""
        try:
            host_id = request.path_params["host_id"]
            host = await self.ssh_host_service.get_host(host_id)

            if not host:
                return self.error(
                    error=f"SSH 主机不存在: {host_id}",
                    code=ErrorCode.NOT_FOUND,
                    status_code=404,
                )

            return self.success(
                data=self._host_to_dict(host),
                message="获取 SSH 主机成功",
            )
        except Exception as e:
            logger.error(f"获取 SSH 主机失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_update(self, request: Request) -> JSONResponse:
        """更新 SSH 主机"""
        try:
            host_id = request.path_params["host_id"]
            body = await request.json()
            update_request = UpdateSSHHostRequest(**body)

            # 所有字段为 None 时直接返回
            if all(
                v is None
                for v in [
                    update_request.name,
                    update_request.host,
                    update_request.port,
                    update_request.username,
                    update_request.key_based,
                    update_request.password,
                    update_request.description,
                ]
            ):
                return self.error(
                    error="至少需要提供一个要更新的字段",
                    code=ErrorCode.VALIDATION_ERROR,
                    status_code=400,
                )

            config = await self.ssh_host_service.update_host(
                host_id=host_id,
                name=update_request.name,
                host=update_request.host,
                port=update_request.port,
                username=update_request.username,
                key_based=update_request.key_based,
                password=update_request.password,
                description=update_request.description,
            )

            return self.success(
                data={
                    "id": config.id,
                    "name": config.name,
                    "host": config.host,
                    "port": config.port,
                    "username": config.username,
                    "key_based": config.key_based,
                    "description": config.description,
                    "owner_id": config.owner_id,
                },
                message="SSH 主机更新成功",
            )

        except ValidationError as e:
            logger.error(f"更新 SSH 主机请求验证失败: {e}")
            return self.error(
                error=f"请求验证失败: {self.format_validation_error(e)}",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            error_msg = str(e)
            if "不存在" in error_msg:
                return self.error(
                    error=error_msg,
                    code=ErrorCode.NOT_FOUND,
                    status_code=404,
                )
            return self.error(error=error_msg, code=ErrorCode.OPERATION_FAILED, status_code=400)
        except Exception as e:
            logger.error(f"更新 SSH 主机失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_delete(self, request: Request) -> JSONResponse:
        """删除 SSH 主机"""
        try:
            host_id = request.path_params["host_id"]
            await self.ssh_host_service.delete_host(host_id)
            return self.success(
                data=None,
                message=f"SSH 主机删除成功: {host_id}",
            )
        except ValueError as e:
            error_msg = str(e)
            if "不存在" in error_msg:
                return self.error(
                    error=error_msg,
                    code=ErrorCode.NOT_FOUND,
                    status_code=404,
                )
            return self.error(error=error_msg, code=ErrorCode.OPERATION_FAILED, status_code=400)
        except Exception as e:
            logger.error(f"删除 SSH 主机失败: {e}", exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
