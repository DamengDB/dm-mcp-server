"""MCP 分组 REST 控制器（/api/v1/mcp-groups）。

所有 REST 操作使用 12 字符短 ``id``；path 仅用于展示/CLI 树。
控制器负责 id 校验与 404 映射，服务层内部仍使用 group_id。
"""

import logging

from pydantic import BaseModel, Field, ValidationError
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.core.exceptions import CliGroupNotFoundError, DmMCPError
from dm_mcp.infra.web.error_codes import ErrorCode
from dm_mcp.api.base import BaseController
from dm_mcp.domain.mcp.services.group import MCPGroupService
from dm_mcp.domain.mcp.services.mcp import MCPService
from dm_mcp.common.utils.serialization import jsonable_row, jsonable_value

logger = logging.getLogger(__name__)


class MCPGroupCreateBody(BaseModel):
    parent_id: str | None = Field(default=None)
    name: str = Field(..., min_length=1)
    description: str = Field(default="")


class MCPGroupUpdateBody(BaseModel):
    description: str = Field(default="")


class MCPGroupRenameBody(BaseModel):
    new_name: str = Field(..., min_length=1)


class MCPGroupMoveBody(BaseModel):
    new_parent_id: str | None = Field(default=None)


class MCPGroupController(BaseController):
    def __init__(
        self,
        mcp_group_service: MCPGroupService,
        mcp_service: MCPService,
    ) -> None:
        self.mcp_group_service = mcp_group_service
        self.mcp_service = mcp_service

    @requires("authenticated")
    async def handle_list(self, request: Request) -> JSONResponse:
        try:
            rows = await self.mcp_group_service.list_cli_groups()
            return self.success(
                data=[jsonable_row(r) for r in rows],
                message="获取 CLI 分组列表成功",
            )
        except Exception as e:
            logger.error("列出 CLI 分组失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_get(self, request: Request) -> JSONResponse:
        try:
            group_id = request.path_params["id"]
            row = await self.mcp_group_service.get_cli_group_by_id(group_id)
            if row is None:
                return self.error(
                    error=f"CLI 分组不存在: {group_id}",
                    code="CLI_GROUP_NOT_FOUND",
                    status_code=404,
                )
            return self.success(
                data=jsonable_row(row),
                message="获取 CLI 分组成功",
            )
        except Exception as e:
            logger.error("获取 CLI 分组失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_create(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
            parsed = MCPGroupCreateBody.model_validate(body)
            row = await self.mcp_group_service.create_cli_group(
                parent_id=parsed.parent_id,
                name=parsed.name,
                description=parsed.description,
            )
            return self.success(
                data=jsonable_row(row),
                message="创建 CLI 分组成功",
                status_code=201,
            )
        except ValidationError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except DmMCPError as e:
            return self.error(
                error=e.message,
                code=e.error_code,
                status_code=e.status_code,
                details=e.details,
            )
        except Exception as e:
            logger.error("创建 CLI 分组失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_update(self, request: Request) -> JSONResponse:
        try:
            group_id = request.path_params["id"]
            body = await request.json()
            parsed = MCPGroupUpdateBody.model_validate(body)
            row = await self.mcp_group_service.update_cli_group_description(
                group_id=group_id,
                description=parsed.description,
            )
            return self.success(
                data=jsonable_row(row),
                message="更新 CLI 分组成功",
            )
        except ValidationError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except DmMCPError as e:
            return self.error(
                error=e.message,
                code=e.error_code,
                status_code=e.status_code,
                details=e.details,
            )
        except Exception as e:
            logger.error("更新 CLI 分组失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_delete(self, request: Request) -> JSONResponse:
        try:
            group_id = request.path_params["id"]
            row = await self.mcp_group_service.get_cli_group_by_id(group_id)
            if row is None:
                return self.error(
                    error=f"CLI 分组不存在: {group_id}",
                    code="CLI_GROUP_NOT_FOUND",
                    status_code=404,
                )
            patch = await self.mcp_group_service.delete_cli_group(group_id)
            return self.success(
                data={k: jsonable_value(v) for k, v in patch.items()},
                message="删除 CLI 分组成功",
            )
        except DmMCPError as e:
            return self.error(
                error=e.message,
                code=e.error_code,
                status_code=e.status_code,
                details=e.details,
            )
        except Exception as e:
            logger.error("删除 CLI 分组失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_rename(self, request: Request) -> JSONResponse:
        try:
            group_id = request.path_params["id"]
            body = await request.json()
            parsed = MCPGroupRenameBody.model_validate(body)
            row = await self.mcp_group_service.rename_cli_group(
                group_id, parsed.new_name
            )
            return self.success(
                data=jsonable_row(row),
                message="重命名 CLI 分组成功",
            )
        except ValidationError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except DmMCPError as e:
            return self.error(
                error=e.message,
                code=e.error_code,
                status_code=e.status_code,
                details=e.details,
            )
        except Exception as e:
            logger.error("重命名 CLI 分组失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_move(self, request: Request) -> JSONResponse:
        try:
            group_id = request.path_params["id"]
            body = await request.json()
            parsed = MCPGroupMoveBody.model_validate(body)
            row = await self.mcp_group_service.move_cli_group(
                group_id, parsed.new_parent_id
            )
            return self.success(
                data=jsonable_row(row),
                message="移动 CLI 分组成功",
            )
        except ValidationError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except DmMCPError as e:
            return self.error(
                error=e.message,
                code=e.error_code,
                status_code=e.status_code,
                details=e.details,
            )
        except Exception as e:
            logger.error("移动 CLI 分组失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_tree(self, request: Request) -> JSONResponse:
        try:
            tree = await self.mcp_group_service.get_cli_group_tree()
            return self.success(
                data=tree,
                message="获取 CLI 分组树成功",
            )
        except Exception as e:
            logger.error("获取 CLI 分组树失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_list_entities(self, request: Request) -> JSONResponse:
        try:
            group_id = request.path_params["id"]
            types_param = request.query_params.get("types", "tool,resource,prompt")
            types = [t.strip() for t in types_param.split(",") if t.strip()]
            recursive = request.query_params.get("recursive", "false").lower() == "true"

            # 将 id 解析为 path 后再查询实体
            path = await self.mcp_group_service.path_of(group_id)
            if path is None:
                return self.error(
                    error=f"CLI 分组不存在: {group_id}",
                    code="CLI_GROUP_NOT_FOUND",
                    status_code=404,
                )
            entities = await self.mcp_service.get_cli_group_entities(
                path, types, recursive
            )
            return self.success(
                data={k: [jsonable_row(e) for e in v] for k, v in entities.items()},
                message="获取分组实体列表成功",
            )
        except ValueError as e:
            return self.error(
                error=str(e),
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except Exception as e:
            logger.error("获取分组实体列表失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
