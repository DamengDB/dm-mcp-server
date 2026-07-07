"""数据库元数据配置控制器

提供数据库对象元数据配置的 REST API 端点，处理 DataSource 级配置。
路由：/datasources/{name}/metadata/configs
"""

import logging
from typing import Any

from pydantic import ValidationError
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.infra.web.error_codes import ErrorCode
from dm_mcp.infra.web.requests import (
    UpsertDBObjectConfigRequest,
    BatchUpsertDBObjectConfigRequest,
    DeleteDBObjectConfigRequest,
)
from dm_mcp.api.base import BaseController
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.db_metadata.services.db_config import DbConfigService
from dm_mcp.infra.web.dto import DBObjectConfigItem

logger = logging.getLogger(__name__)


def _map_policy_for_db(policy: Any) -> Any:
    """"inherit" 语义化值 -> 数据库存 None 表示继承"""
    return None if policy == "inherit" else policy


class DbMetadataConfigController(BaseController):
    """数据库元数据配置控制器（DS 级）"""

    def __init__(
        self,
        db_config_service: DbConfigService,
        datasource_service: DataSourceService,
    ) -> None:
        self._db_config = db_config_service
        self._ds = datasource_service

    async def _get_datasource_id(self, name: str) -> Any:
        """通过数据源名称获取数据源 ID"""
        ds = await self._ds.get_datasource(name)
        if not ds:
            raise ValueError(
                messages.MSG_DATASOURCE_NOT_FOUND.format(name=name)
            )
        return ds.id

    @requires("authenticated")
    async def handle_list(self, request: Request) -> JSONResponse:
        """列出 DS 级配置"""
        try:
            ds_name = request.path_params["name"]
            datasource_id = await self._get_datasource_id(ds_name)

            configs = await self._db_config.list_object_configs(
                datasource_id=datasource_id,
                object_type=request.query_params.get("object_type"),
                schema_name=request.query_params.get("schema"),
                table_name=request.query_params.get("table"),
            )
            data = [
                DBObjectConfigItem.from_model(
                    c, include_datasource_id=True
                ).model_dump(mode="json")
                for c in configs
            ]
            return self.success(data=data, message="获取配置列表成功")
        except ValueError as e:
            return self._handle_value_error(str(e))
        except Exception as e:
            logger.error(f"列出配置失败: {e}", exc_info=True)
            return self._handle_internal_error(str(e))

    @requires("authenticated")
    async def handle_upsert(self, request: Request) -> JSONResponse:
        """创建或更新 DS 级配置（PATCH 语义）"""
        try:
            ds_name = request.path_params["name"]
            datasource_id = await self._get_datasource_id(ds_name)
            body = await request.json()
            req = UpsertDBObjectConfigRequest(**body)

            self._validate_object_fields(req.object_type, req.table_name, req.column_name)

            upsert_kwargs = {
                "datasource_id": datasource_id,
                "object_type": req.object_type,
                "schema_name": req.schema_name,
                "table_name": req.table_name,
                "column_name": req.column_name,
            }
            # PATCH 语义：只更新请求中显式包含的字段
            if "access_policy" in body or "accessPolicy" in body:
                upsert_kwargs["access_policy"] = _map_policy_for_db(req.access_policy)
            if "comment_override" in body or "commentOverride" in body:
                upsert_kwargs["comment_override"] = req.comment_override

            config = await self._db_config.upsert_object_config(**upsert_kwargs)
            data = DBObjectConfigItem.from_model(
                config, include_datasource_id=True
            ).model_dump(mode="json")
            return self.success(data=data, message="配置已保存")
        except ValueError as e:
            return self._handle_value_error(str(e))
        except ValidationError as e:
            return self._handle_validation_error(e, "配置请求验证失败")
        except Exception as e:
            logger.error(f"保存配置失败: {e}", exc_info=True)
            return self._handle_internal_error(str(e))

    @requires("authenticated")
    async def handle_delete(self, request: Request) -> JSONResponse:
        """删除 DS 级配置"""
        try:
            ds_name = request.path_params["name"]
            datasource_id = await self._get_datasource_id(ds_name)
            body = await request.json()
            req = DeleteDBObjectConfigRequest(**body)

            await self._db_config.delete_object_config(
                datasource_id=datasource_id,
                object_type=req.object_type,
                schema_name=req.schema_name,
                table_name=req.table_name,
                column_name=req.column_name,
            )
            return self.success(data=None, message="配置已删除")
        except ValueError as e:
            return self._handle_value_error(str(e))
        except ValidationError as e:
            return self._handle_validation_error(e, "删除配置请求验证失败")
        except Exception as e:
            logger.error(f"删除配置失败: {e}", exc_info=True)
            return self._handle_internal_error(str(e))

    @requires("authenticated")
    async def handle_batch_upsert(self, request: Request) -> JSONResponse:
        """批量创建/更新 DS 级配置（PATCH 语义）"""
        try:
            ds_name = request.path_params["name"]
            datasource_id = await self._get_datasource_id(ds_name)
            body = await request.json()
            req = BatchUpsertDBObjectConfigRequest(**body)

            configs_for_svc = []
            for config in req.configs:
                config_dict = {
                    "object_type": config.object_type,
                    "schema_name": config.schema_name,
                    "table_name": config.table_name,
                    "column_name": config.column_name,
                }
                # PATCH 语义：只更新每个配置中显式设置的字段
                if "access_policy" in config.model_fields_set:
                    config_dict["access_policy"] = _map_policy_for_db(config.access_policy)
                if "comment_override" in config.model_fields_set:
                    config_dict["comment_override"] = config.comment_override
                configs_for_svc.append(config_dict)

            results = await self._db_config.batch_upsert_configs(
                datasource_id=datasource_id,
                configs=configs_for_svc,
            )
            data = [
                DBObjectConfigItem.from_model(
                    c, include_datasource_id=True
                ).model_dump(mode="json")
                for c in results
            ]
            return self.success(data=data, message="批量配置已保存")
        except ValueError as e:
            return self._handle_value_error(str(e))
        except ValidationError as e:
            return self._handle_validation_error(e, "批量配置请求验证失败")
        except Exception as e:
            logger.error(f"批量保存配置失败: {e}", exc_info=True)
            return self._handle_internal_error(str(e))

    def _validate_object_fields(
        self,
        object_type: str,
        table_name: str | None,
        column_name: str | None,
    ) -> None:
        """验证对象字段完整性"""
        if object_type in ("TABLE", "VIEW") and not table_name:
            raise ValueError(f"{object_type} 类型需要提供 table_name")
        if object_type == "COLUMN" and (not table_name or not column_name):
            raise ValueError("COLUMN 类型需要提供 table_name 和 column_name")

    def _handle_value_error(self, error_msg: str) -> JSONResponse:
        """处理业务逻辑错误"""
        if "数据源不存在" in error_msg:
            return self.error(
                error=error_msg,
                code=ErrorCode.DATASOURCE_NOT_FOUND,
                status_code=404,
            )
        return self.error(error=error_msg, code=ErrorCode.OPERATION_FAILED)

    def _handle_validation_error(self, e: ValidationError, context: str) -> JSONResponse:
        """处理请求验证错误"""
        logger.error(f"{context}: {e}")
        return self.error(
            error=f"请求验证失败: {e.error_count()} 个错误",
            code=ErrorCode.VALIDATION_ERROR,
            status_code=400,
        )

    def _handle_internal_error(self, error_msg: str) -> JSONResponse:
        """处理内部服务错误"""
        return self.error(
            error=error_msg,
            code=ErrorCode.INTERNAL_ERROR,
            status_code=500,
        )
