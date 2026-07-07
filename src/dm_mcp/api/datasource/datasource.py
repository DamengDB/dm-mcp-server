import logging
import uuid
from typing import Any

from pydantic import SecretStr, ValidationError
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.infra.persistence import DataSourceModel
from dm_mcp.infra.web.dto import DataSourceCreateDTO, DataSourceUpdateDTO
from dm_mcp.infra.web.error_codes import ErrorCode
from dm_mcp.api.base import BaseController
from dm_mcp.domain.datasource.services.pool import AsyncPoolService
from dm_mcp.domain.datasource.services.datasource import DataSourceService

logger = logging.getLogger(__name__)


def _dto_to_model(dto: DataSourceCreateDTO | DataSourceUpdateDTO, *, owner_id: str | None = None) -> DataSourceModel:
    """DTO -> DataSourceModel"""
    password_value = ""
    pw = dto.password
    if isinstance(pw, SecretStr):
        password_value = pw.get_secret_value()
    elif isinstance(pw, str):
        password_value = pw

    return DataSourceModel(
        id=uuid.uuid4(),
        name=dto.name,
        enabled=dto.enabled,
        deploy_type=dto.deploy_type,
        read_only=dto.read_only,
        dsn=dto.dsn,
        host=dto.host,
        port=dto.port,
        user=dto.user,
        password=password_value,
        minsize=dto.minsize,
        maxsize=dto.maxsize,
        timeout=dto.timeout,
        weight=dto.weight,
        owner_id=owner_id,
    )


class DataSourceController(BaseController):
    """数据源管理控制器"""

    def __init__(
        self,
        datasource_service: DataSourceService,
        pool_service: AsyncPoolService,
    ) -> None:
        self.datasource_service = datasource_service
        self.pool_service = pool_service

    # ============================================================
    # 基础 CRUD
    # ============================================================

    @requires("authenticated")
    async def handle_list(self, request: Request) -> JSONResponse:
        try:
            datasources = await self.datasource_service.list_datasources()
            result = [ds.to_dict(include_password=False) for ds in datasources]
            return self.success(data=result, message="获取数据源列表成功")

        except Exception as e:
            logger.error(f"列出数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_get(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            ds = await self.datasource_service.get_datasource(name)

            if not ds:
                return self.error(error=f"数据源不存在: {name}", code=ErrorCode.DATASOURCE_NOT_FOUND, status_code=404)

            return self.success(data=ds.to_dict(include_password=False), message="获取数据源成功")

        except Exception as e:
            logger.error(f"获取数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_create(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
            dto = DataSourceCreateDTO(**body)

            auth_context = self.get_auth_context(request)
            model = _dto_to_model(dto, owner_id=auth_context.user_id)
            await self.datasource_service.add_datasource(model)

            return self.success(data={"name": model.name}, message=f"已添加数据源: {model.name}", status_code=201)

        except ValidationError as e:
            logger.error(f"数据源配置验证失败: {e}")
            return self.error(error=f"配置验证失败: {self.format_validation_error(e)}", code=ErrorCode.VALIDATION_ERROR, status_code=400)
        except ValueError as e:
            error_msg = str(e)
            code = ErrorCode.DATASOURCE_ALREADY_EXISTS if "已存在" in error_msg else ErrorCode.OPERATION_FAILED
            logger.error(f"添加数据源失败: {e}")
            return self.error(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"添加数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_update(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            body = await request.json()

            old_ds = await self.datasource_service.get_datasource(name)
            if not old_ds:
                return self.error(error=f"数据源不存在: {name}", code=ErrorCode.DATASOURCE_NOT_FOUND, status_code=404)

            # 处理密码：如果新密码是脱敏的或为空，保持旧密码
            new_password = body.get("password", "")
            if not new_password or (isinstance(new_password, str) and new_password.startswith("*")):
                body["password"] = old_ds.password
                logger.debug(f"更新数据源 {name}：密码未修改，保持原密码")

            body.pop("id", None)

            dto = DataSourceUpdateDTO(**body)
            new_model = _dto_to_model(dto)
            new_model.id = old_ds.id
            new_model.owner_id = old_ds.owner_id

            await self.datasource_service.update_datasource(name, new_model)

            return self.success(data={"name": new_model.name}, message=f"已更新数据源: {new_model.name}")

        except ValidationError as e:
            logger.error(f"数据源配置验证失败: {e}")
            return self.error(error=f"配置验证失败: {self.format_validation_error(e)}", code=ErrorCode.VALIDATION_ERROR, status_code=400)
        except ValueError as e:
            logger.error(f"更新数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.OPERATION_FAILED, status_code=400)
        except Exception as e:
            logger.error(f"更新数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_delete(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            await self.datasource_service.delete_datasource(name)
            return self.success(data={"name": name}, message=f"已删除数据源: {name}")

        except ValueError as e:
            error_msg = str(e)
            code = ErrorCode.DATASOURCE_NOT_FOUND if "不存在" in error_msg else ErrorCode.OPERATION_FAILED
            logger.error(f"删除数据源失败: {e}")
            return self.error(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"删除数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    # ============================================================
    # 启用/禁用
    # ============================================================

    @requires("authenticated")
    async def handle_enable(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            await self.datasource_service.enable_datasource(name)
            return self.success(data={"name": name}, message=f"已启用数据源: {name}")

        except ValueError as e:
            error_msg = str(e)
            code = ErrorCode.DATASOURCE_NOT_FOUND if "不存在" in error_msg else ErrorCode.OPERATION_FAILED
            logger.error(f"启用数据源失败: {e}")
            return self.error(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"启用数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_disable(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            await self.datasource_service.disable_datasource(name)
            return self.success(data={"name": name}, message=f"已禁用数据源: {name}")

        except ValueError as e:
            error_msg = str(e)
            code = ErrorCode.DATASOURCE_NOT_FOUND if "不存在" in error_msg else ErrorCode.OPERATION_FAILED
            logger.error(f"禁用数据源失败: {e}")
            return self.error(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"禁用数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    # ============================================================
    # 测试连接
    # ============================================================

    @requires("authenticated")
    async def handle_test_new(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
            if not body.get("name"):
                body["name"] = "_test_"
            dto = DataSourceCreateDTO(**body)
            model = _dto_to_model(dto)
            result = await self.pool_service.test_connection(model)

            if result.get("success"):
                return self.success(data={"name": model.name}, message=result.get("message", "连接测试成功"))
            else:
                return self.error(error=result.get("message", "连接测试失败"), code=ErrorCode.CONNECTION_TEST_FAILED, status_code=400)

        except ValidationError as e:
            logger.error(f"数据源配置验证失败: {e}")
            return self.error(error=f"配置验证失败: {self.format_validation_error(e)}", code=ErrorCode.VALIDATION_ERROR, status_code=400)
        except Exception as e:
            logger.error(f"测试连接失败: {e}")
            return self.error(error=str(e), code=ErrorCode.CONNECTION_TEST_FAILED, status_code=500)

    @requires("authenticated")
    async def handle_test_existing(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            ds = await self.datasource_service.get_datasource(name)
            if not ds:
                return self.error(error=f"数据源不存在: {name}", code=ErrorCode.DATASOURCE_NOT_FOUND, status_code=404)

            result = await self.pool_service.test_connection(ds)

            if result.get("success"):
                return self.success(data={"name": name}, message=result.get("message", "连接测试成功"))
            else:
                return self.error(error=result.get("message", "连接测试失败"), code=ErrorCode.CONNECTION_TEST_FAILED, status_code=400)

        except Exception as e:
            logger.error(f"测试连接失败: {e}")
            return self.error(error=str(e), code=ErrorCode.CONNECTION_TEST_FAILED, status_code=500)

    # ============================================================
    # Reload
    # ============================================================

    @requires("authenticated")
    async def handle_reload_one(self, request: Request) -> JSONResponse:
        try:
            name = request.path_params["name"]
            ds = await self.datasource_service.get_datasource(name)
            if not ds:
                return self.error(error=f"数据源不存在: {name}", code=ErrorCode.DATASOURCE_NOT_FOUND, status_code=404)

            if not ds.enabled:
                return self.error(error=f"数据源未启用: {name}", code=ErrorCode.OPERATION_FAILED, status_code=400)

            if self.pool_service.has_pool(name):
                await self.pool_service.reload_pool(ds)
            else:
                await self.pool_service.add_pool(ds)

            return self.success(data={"name": name}, message=f"已重载数据源: {name}")

        except Exception as e:
            logger.error(f"重载数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_reload_all(self, request: Request) -> JSONResponse:
        try:
            datasources = await self.datasource_service.list_datasources()
            result = await self.pool_service.reload_all_pools(datasources)

            return self.success(data={"closed": result["closed"], "created": result["created"], "errors": result["errors"]}, message="已重载所有数据源")

        except Exception as e:
            logger.error(f"重载所有数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    # ============================================================
    # 默认数据源管理
    # ============================================================

    @requires("authenticated")
    async def handle_get_default(self, request: Request) -> JSONResponse:
        try:
            default_ds = await self.datasource_service.get_default_datasource()
            return self.success(data={"default_datasource": default_ds}, message="获取默认数据源成功")

        except Exception as e:
            logger.error(f"获取默认数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    @requires("authenticated")
    async def handle_set_default(self, request: Request) -> JSONResponse:
        try:
            body = await request.json()
            ds_name = body.get("default_datasource")

            if not ds_name or not isinstance(ds_name, str):
                return self.error(error="请求体中必须包含 default_datasource 字段（字符串类型）", code=ErrorCode.VALIDATION_ERROR, status_code=400)

            await self.datasource_service.set_default_datasource(ds_name)
            return self.success(data={"default_datasource": ds_name}, message=f"已设置默认数据源: {ds_name}")

        except ValueError as e:
            error_msg = str(e)
            code = ErrorCode.DATASOURCE_NOT_FOUND if "不存在" in error_msg else ErrorCode.OPERATION_FAILED
            logger.error(f"设置默认数据源失败: {e}")
            return self.error(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"设置默认数据源失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)

    # ============================================================
    # 状态监控
    # ============================================================

    @requires("authenticated")
    async def handle_status(self, request: Request) -> JSONResponse:
        try:
            datasources = await self.datasource_service.list_datasources()
            pool_status = await self.pool_service.pool_status()
            status_info = pool_status.get("status", {})

            result = {}
            for ds in datasources:
                pool_info = status_info.get(ds.name, {})
                result[ds.name] = {
                    "enabled": ds.enabled,
                    "connected": self.pool_service.has_pool(ds.name),
                    "pool": pool_info,
                    "config": {
                        "deploy_type": ds.deploy_type,
                        "host": ds.host,
                        "port": ds.port,
                        "user": ds.user,
                        "minsize": ds.minsize,
                        "maxsize": ds.maxsize,
                        "read_only": ds.read_only,
                        "weight": ds.weight,
                    },
                }

            return self.success(data=result, message="获取连接池状态成功")

        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return self.error(error=str(e), code=ErrorCode.INTERNAL_ERROR, status_code=500)
