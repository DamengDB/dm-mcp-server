"""数据库元数据查询控制器

提供通过连接池查询数据源内数据库对象元数据的 REST API 端点，
包括模式、表、视图、列的名称与合并后配置信息。

返回合并后结果（comment + access_policy），不过滤任何对象。
"""

import logging
import re

from dm_mcp.api.base import BaseController
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.domain.db_metadata.services.db_metadata import DbMetadataService

logger = logging.getLogger(__name__)

_DM_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_#$]*$")


class DbMetadataController(BaseController):
    """数据库元数据查询控制器"""

    def __init__(
        self,
        db_metadata_service: DbMetadataService,
    ) -> None:
        self._svc = db_metadata_service

    # ============================================================
    # 辅助方法
    # ============================================================

    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        """校验名称是否为合法的 DM 标识符（防止 SQL 注入）"""
        return bool(_DM_IDENTIFIER_RE.match(name))

    # ============================================================
    # 模式列表
    # ============================================================

    @requires("authenticated")
    async def handle_list_schemas(self, request: Request) -> JSONResponse:
        """获取数据源中的模式列表（含合并后配置信息）"""
        try:
            name = request.path_params["name"]

            items = await self._svc.list_schemas_overview(name)

            return self.success(
                data=[item.model_dump() for item in items],
                message="获取模式列表成功",
            )

        except ValueError as e:
            error_msg = str(e)
            if "数据源不存在" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_FOUND", status_code=404
                )
            if "数据源未连接" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_CONNECTED", status_code=503
                )
            return self.error(error=error_msg, code="OPERATION_FAILED")
        except Exception as e:
            logger.error(f"获取模式列表失败: {e}", exc_info=True)
            return self.error(
                error=str(e), code="INTERNAL_ERROR", status_code=500
            )

    # ============================================================
    # 表列表
    # ============================================================

    @requires("authenticated")
    async def handle_list_tables(self, request: Request) -> JSONResponse:
        """获取指定模式下的表列表（含合并后配置信息）"""
        try:
            name = request.path_params["name"]
            schema = request.query_params.get("schema")

            if not schema:
                return self.error(
                    error="缺少 schema 查询参数",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )
            if not self._is_valid_identifier(schema):
                return self.error(
                    error=f"非法的 schema 名称: {schema}",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )

            items = await self._svc.list_tables_overview(name, schema)

            return self.success(
                data=[item.model_dump() for item in items],
                message="获取表列表成功",
            )

        except ValueError as e:
            error_msg = str(e)
            if "数据源不存在" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_FOUND", status_code=404
                )
            if "数据源未连接" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_CONNECTED", status_code=503
                )
            return self.error(error=error_msg, code="OPERATION_FAILED")
        except Exception as e:
            logger.error(f"获取表列表失败: {e}", exc_info=True)
            return self.error(
                error=str(e), code="INTERNAL_ERROR", status_code=500
            )

    # ============================================================
    # 视图列表
    # ============================================================

    @requires("authenticated")
    async def handle_list_views(self, request: Request) -> JSONResponse:
        """获取指定模式下的视图列表（含合并后配置信息）"""
        try:
            name = request.path_params["name"]
            schema = request.query_params.get("schema")

            if not schema:
                return self.error(
                    error="缺少 schema 查询参数",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )
            if not self._is_valid_identifier(schema):
                return self.error(
                    error=f"非法的 schema 名称: {schema}",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )

            items = await self._svc.list_views_overview(name, schema)

            return self.success(
                data=[item.model_dump() for item in items],
                message="获取视图列表成功",
            )

        except ValueError as e:
            error_msg = str(e)
            if "数据源不存在" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_FOUND", status_code=404
                )
            if "数据源未连接" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_CONNECTED", status_code=503
                )
            return self.error(error=error_msg, code="OPERATION_FAILED")
        except Exception as e:
            logger.error(f"获取视图列表失败: {e}", exc_info=True)
            return self.error(
                error=str(e), code="INTERNAL_ERROR", status_code=500
            )

    # ============================================================
    # 列列表
    # ============================================================

    @requires("authenticated")
    async def handle_list_columns(self, request: Request) -> JSONResponse:
        """获取指定表/视图下的列列表（含合并后配置信息）"""
        try:
            name = request.path_params["name"]
            schema = request.query_params.get("schema")
            table = request.query_params.get("table")

            if not schema:
                return self.error(
                    error="缺少 schema 查询参数",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )
            if not table:
                return self.error(
                    error="缺少 table 查询参数",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )
            if not self._is_valid_identifier(schema):
                return self.error(
                    error=f"非法的 schema 名称: {schema}",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )
            if not self._is_valid_identifier(table):
                return self.error(
                    error=f"非法的 table 名称: {table}",
                    code="VALIDATION_ERROR",
                    status_code=400,
                )

            items = await self._svc.list_columns_overview(name, schema, table)

            return self.success(
                data=[item.model_dump() for item in items],
                message="获取列列表成功",
            )

        except ValueError as e:
            error_msg = str(e)
            if "数据源不存在" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_FOUND", status_code=404
                )
            if "数据源未连接" in error_msg:
                return self.error(
                    error=error_msg, code="DATASOURCE_NOT_CONNECTED", status_code=503
                )
            return self.error(error=error_msg, code="OPERATION_FAILED")
        except Exception as e:
            logger.error(f"获取列列表失败: {e}", exc_info=True)
            return self.error(
                error=str(e), code="INTERNAL_ERROR", status_code=500
            )
