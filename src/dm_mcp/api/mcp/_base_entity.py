"""MCP 实体 Controller 基类

三种资源（tool / resource / prompt）的 REST 操作高度重复。
基类封装 handler 流程（认证、校验、序列化、错误处理），
子类通过覆盖 ``_list`` / ``_get`` / ``_assign`` 等方法来提供具体的服务调用。
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from pydantic import BaseModel, Field, ValidationError, model_validator
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.api.base import BaseController
from dm_mcp.common.utils.serialization import jsonable_row
from dm_mcp.core.exceptions import DmMCPError
from dm_mcp.domain.mcp.services.group import MCPGroupService
from dm_mcp.domain.mcp.services.mcp import MCPService
from dm_mcp.infra.web.error_codes import ErrorCode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 请求体
# ---------------------------------------------------------------------------

class MCPMetadataOverrideUpdateBody(BaseModel):
    """元数据覆盖更新请求（描述 / disabled）"""

    description: str | None = Field(
        None, description="描述文本；首行为短描述，全文为长描述"
    )
    disabled: bool | None = Field(None)

    @model_validator(mode="after")
    def _require_at_least_one(self) -> "MCPMetadataOverrideUpdateBody":
        if self.description is None and self.disabled is None:
            raise ValueError("description 和 disabled 至少提供一个")
        return self

    def build_metadata_kwargs(self) -> dict[str, Any]:
        """根据已设置的字段构建传给 mcp_service 的 kwargs"""
        kwargs: dict[str, Any] = {}
        if self.description is not None:
            text = self.description.strip()
            lines = text.split("\n")
            kwargs["short_description"] = lines[0].strip() if lines else ""
            kwargs["long_description"] = text
        if self.disabled is not None:
            kwargs["disabled"] = self.disabled
        return kwargs


class MCPEntityAssignBody(BaseModel):
    """实体分组归属请求"""

    group_id: str | None = Field(
        ..., description="分组短 id；null/空字符串表示解除归属"
    )


class MCPBatchAssignGroupBody(BaseModel):
    """批量分组归属请求"""

    names: list[str] = Field(..., min_length=1)
    group_id: str | None = Field(None, description="分组短 id；null 表示批量解除")


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------

class BaseMCPEntityController(BaseController):
    """MCP 实体 Controller 基类

    子类必须覆盖以下方法以提供具体的服务调用：
    ``_list``、``_get``、``_upsert_override``、``_delete_override``、
    ``_assign``、``_unassign``、``_batch_assign``。

    同时需要声明 ``_label`` 用于日志和响应消息。
    """

    _entity_type: ClassVar[str]
    _label: ClassVar[str]

    def __init__(
        self,
        mcp_group_service: MCPGroupService,
        mcp_service: MCPService,
    ) -> None:
        self.mcp_group_service = mcp_group_service
        self.mcp_service = mcp_service

    # --- 子类必须覆盖的方法 ---

    async def _list(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def _get(self, name: str) -> dict[str, Any]:
        raise NotImplementedError

    async def _upsert_override(
        self, original_name: str, **kwargs: Any
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def _delete_override(self, name: str) -> None:
        raise NotImplementedError

    async def _assign(self, name: str, group_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def _unassign(self, name: str) -> dict[str, Any]:
        raise NotImplementedError

    async def _batch_assign(
        self, names: list[str], group_id: str | None
    ) -> dict[str, Any]:
        raise NotImplementedError

    # --- handlers ---

    @requires("authenticated")
    async def handle_list(self, request: Request) -> JSONResponse:
        try:
            entities = await self._list()
            return self.success(
                data=[jsonable_row(e) for e in entities],
                message=f"获取{self._label}列表成功",
            )
        except Exception as e:
            logger.error("列出%s失败: %s", self._label, e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_get(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            entity = await self._get(name)
            return self.success(
                data=jsonable_row(entity),
                message=f"获取{self._label}元数据成功",
            )
        except DmMCPError as e:
            return self.error(
                error=e.message,
                code=e.error_code,
                status_code=e.status_code,
                details=e.details,
            )
        except Exception as e:
            logger.error("获取%s元数据失败: %s", self._label, e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_update_override(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            body = await request.json()
            parsed = MCPMetadataOverrideUpdateBody.model_validate(body)
            row = await self._upsert_override(
                original_name=name,
                **parsed.build_metadata_kwargs(),
            )
            return self.success(
                data=jsonable_row(row),
                message=f"更新{self._label}元数据成功",
                status_code=200,
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
            logger.error("更新%s元数据失败: %s", self._label, e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_reset_override(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            await self._delete_override(name)
            return self.success(
                data=None,
                message=f"重置{self._label}元数据成功",
            )
        except DmMCPError as e:
            return self.error(
                error=e.message,
                code=e.error_code,
                status_code=e.status_code,
                details=e.details,
            )
        except Exception as e:
            logger.error("重置%s元数据失败: %s", self._label, e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_assign_group(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            body = await request.json()
            parsed = MCPEntityAssignBody.model_validate(body)
            if parsed.group_id:
                result = await self._assign(
                    name=name, group_id=parsed.group_id
                )
            else:
                result = await self._unassign(name=name)
            return self.success(
                data=jsonable_row(result),
                message=f"更新{self._label}分组成功",
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
            logger.error("更新%s分组失败: %s", self._label, e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_batch_assign_group(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
            parsed = MCPBatchAssignGroupBody.model_validate(body)
            result = await self._batch_assign(
                names=parsed.names,
                group_id=parsed.group_id,
            )
            return self.success(
                data={
                    "updated": [jsonable_row(e) for e in result["updated"]],
                },
                message=f"批量更新{self._label}分组成功",
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
            logger.error("批量更新%s分组失败: %s", self._label, e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
