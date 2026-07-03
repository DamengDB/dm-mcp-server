import logging
from typing import Any, Dict, Optional

from pydantic import ValidationError
from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.services import AsyncPoolService
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.settings.datasource_config import DataSourceConfig

logger = logging.getLogger(__name__)


# 错误码常量
class ErrorCode:
    DATASOURCE_NOT_FOUND = "DATASOURCE_NOT_FOUND"
    DATASOURCE_ALREADY_EXISTS = "DATASOURCE_ALREADY_EXISTS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    OPERATION_FAILED = "OPERATION_FAILED"
    CONNECTION_TEST_FAILED = "CONNECTION_TEST_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class DataSourceController(object):
    """数据源管理控制器"""

    def __init__(
        self,
        datasource_service: DataSourceService,
        pool_service: AsyncPoolService,
    ) -> None:
        self.datasource_service = datasource_service
        self.pool_service = pool_service

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

    # ============================================================
    # 基础 CRUD
    # ============================================================

    @requires("authenticated")
    async def handle_list(self, request: Request) -> JSONResponse:
        """列出所有数据源

        返回所有数据源列表，密码字段会被移除（脱敏处理）。
        需要认证。

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含数据源列表的成功响应或错误响应
        """
        try:
            datasources = await self.datasource_service.list_datasources()

            # 脱敏：不返回密码字段
            result = []
            for ds in datasources:
                # 使用 mode='json' 确保 UUID 等类型被正确序列化
                ds_dict = ds.model_dump(mode="json")
                ds_dict.pop("password", None)  # 移除密码字段
                result.append(ds_dict)

            return self.success_response(data=result, message="获取数据源列表成功")

        except Exception as e:
            logger.error(f"列出数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_get(self, request: Request) -> JSONResponse:
        """获取单个数据源

        根据名称获取指定数据源信息，密码字段会被移除（脱敏处理）。
        需要认证。

        Args:
            request: HTTP请求对象，包含name路径参数

        Returns:
            JSONResponse: 包含数据源信息的成功响应或错误响应
        """
        try:
            name = request.path_params["name"]
            ds = await self.datasource_service.get_datasource(name)

            if not ds:
                return self.error_response(
                    error=f"数据源不存在: {name}",
                    code=ErrorCode.DATASOURCE_NOT_FOUND,
                    status_code=404,
                )

            # 脱敏：不返回密码字段
            ds_dict = ds.model_dump(mode="json")
            ds_dict.pop("password", None)

            return self.success_response(data=ds_dict, message="获取数据源成功")

        except Exception as e:
            logger.error(f"获取数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_create(self, request: Request) -> JSONResponse:
        """创建数据源

        根据请求体创建新数据源，如果数据源启用则自动创建连接池。
        需要认证。

        Args:
            request: HTTP请求对象，包含DataSourceConfig格式的请求体

        Returns:
            JSONResponse: 创建成功的响应或错误响应
        """
        try:
            body = await request.json()
            config = DataSourceConfig(**body)

            # 添加到配置文件
            await self.datasource_service.add_datasource(config)

            # 如果启用，创建连接池
            if config.enabled:
                await self.pool_service.add_pool(config)

            return self.success_response(
                data={"name": config.name},
                message=f"已添加数据源: {config.name}",
                status_code=201,
            )

        except ValidationError as e:
            logger.error(f"数据源配置验证失败: {e}")
            return self.error_response(
                error=f"配置验证失败: {e.error_count()} 个错误",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            error_msg = str(e)
            if "已存在" in error_msg:
                code = ErrorCode.DATASOURCE_ALREADY_EXISTS
            else:
                code = ErrorCode.OPERATION_FAILED
            logger.error(f"添加数据源失败: {e}")
            return self.error_response(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"添加数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_update(self, request: Request) -> JSONResponse:
        """更新数据源

        根据请求体更新数据源配置，如果密码未修改则保持原密码。
        如果数据源已启用，会自动重载连接池。
        需要认证。

        Args:
            request: HTTP请求对象，包含name路径参数和DataSourceConfig格式的请求体

        Returns:
            JSONResponse: 更新成功的响应或错误响应
        """
        try:
            name = request.path_params["name"]
            body = await request.json()

            # 获取旧配置
            old_ds = await self.datasource_service.get_datasource(name)
            if not old_ds:
                return self.error_response(
                    error=f"数据源不存在: {name}",
                    code=ErrorCode.DATASOURCE_NOT_FOUND,
                    status_code=404,
                )

            # 处理密码：如果新密码是脱敏的或为空，保持旧密码
            new_password = body.get("password", "")
            if not new_password or (
                isinstance(new_password, str) and new_password.startswith("*")
            ):
                # 保持旧密码
                body["password"] = old_ds.password
                logger.debug(f"更新数据源 {name}：密码未修改，保持原密码")

            # 向后兼容：忽略旧的 id 字段（如果请求中包含）
            body.pop("id", None)

            # 创建新配置
            config = DataSourceConfig(**body)

            # 更新配置文件
            await self.datasource_service.update_datasource(name, config)

            # 如果数据源已启用，重载连接池
            if config.enabled and name in self.pool_service._pools:
                await self.pool_service.reload_pool(config)
            elif config.enabled and name not in self.pool_service._pools:
                # 修改后启用了，但之前没有连接池，创建新池
                await self.pool_service.add_pool(config)
            elif not config.enabled and name in self.pool_service._pools:
                # 修改后禁用了，关闭连接池
                await self.pool_service.remove_pool(name)

            return self.success_response(
                data={"name": config.name},
                message=f"已更新数据源: {config.name}",
            )

        except ValidationError as e:
            logger.error(f"数据源配置验证失败: {e}")
            return self.error_response(
                error=f"配置验证失败: {e.error_count()} 个错误",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except ValueError as e:
            logger.error(f"更新数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.OPERATION_FAILED,
                status_code=400,
            )
        except Exception as e:
            logger.error(f"更新数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_delete(self, request: Request) -> JSONResponse:
        """删除数据源

        删除指定数据源，如果连接池存在则先关闭。
        需要认证。

        Args:
            request: HTTP请求对象，包含name路径参数

        Returns:
            JSONResponse: 删除成功的响应或错误响应
        """
        try:
            name = request.path_params["name"]

            # 如果连接池存在，先关闭
            if name in self.pool_service._pools:
                await self.pool_service.remove_pool(name)

            # 从配置文件删除
            await self.datasource_service.delete_datasource(name)

            return self.success_response(
                data={"name": name},
                message=f"已删除数据源: {name}",
            )

        except ValueError as e:
            error_msg = str(e)
            if "不存在" in error_msg:
                code = ErrorCode.DATASOURCE_NOT_FOUND
            else:
                code = ErrorCode.OPERATION_FAILED
            logger.error(f"删除数据源失败: {e}")
            return self.error_response(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"删除数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    # ============================================================
    # 启用/禁用
    # ============================================================

    @requires("authenticated")
    async def handle_enable(self, request: Request) -> JSONResponse:
        """启用数据源

        启用指定数据源，如果连接池不存在则自动创建。
        需要认证。

        Args:
            request: HTTP请求对象，包含name路径参数

        Returns:
            JSONResponse: 启用成功的响应或错误响应
        """
        try:
            name = request.path_params["name"]

            # 启用配置
            await self.datasource_service.enable_datasource(name)

            # 获取配置
            ds = await self.datasource_service.get_datasource(name)
            if not ds:
                return self.error_response(
                    error=f"数据源不存在: {name}",
                    code=ErrorCode.DATASOURCE_NOT_FOUND,
                    status_code=404,
                )

            # 创建连接池（如果不存在）
            if name not in self.pool_service._pools:
                await self.pool_service.add_pool(ds)

            return self.success_response(
                data={"name": name},
                message=f"已启用数据源: {name}",
            )

        except ValueError as e:
            error_msg = str(e)
            if "不存在" in error_msg:
                code = ErrorCode.DATASOURCE_NOT_FOUND
            else:
                code = ErrorCode.OPERATION_FAILED
            logger.error(f"启用数据源失败: {e}")
            return self.error_response(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"启用数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_disable(self, request: Request) -> JSONResponse:
        """禁用数据源

        禁用指定数据源，如果连接池存在则关闭。
        需要认证。

        Args:
            request: HTTP请求对象，包含name路径参数

        Returns:
            JSONResponse: 禁用成功的响应或错误响应
        """
        try:
            name = request.path_params["name"]

            # 禁用配置
            await self.datasource_service.disable_datasource(name)

            # 关闭连接池（如果存在）
            if name in self.pool_service._pools:
                await self.pool_service.remove_pool(name)

            return self.success_response(
                data={"name": name},
                message=f"已禁用数据源: {name}",
            )

        except ValueError as e:
            error_msg = str(e)
            if "不存在" in error_msg:
                code = ErrorCode.DATASOURCE_NOT_FOUND
            else:
                code = ErrorCode.OPERATION_FAILED
            logger.error(f"禁用数据源失败: {e}")
            return self.error_response(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"禁用数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    # ============================================================
    # 测试连接
    # ============================================================

    @requires("authenticated")
    async def handle_test_new(self, request: Request) -> JSONResponse:
        """测试新的数据源配置

        测试请求体中的数据源配置是否能成功连接数据库。
        不会实际创建数据源或连接池。
        需要认证。

        Args:
            request: HTTP请求对象，包含DataSourceConfig格式的请求体

        Returns:
            JSONResponse: 测试结果响应
        """
        try:
            body = await request.json()
            config = DataSourceConfig(**body)

            # 测试连接
            result = await self.pool_service.test_connection(config)

            if result.get("success"):
                return self.success_response(
                    data={"name": config.name},
                    message=result.get("message", "连接测试成功"),
                )
            else:
                return self.error_response(
                    error=result.get("message", "连接测试失败"),
                    code=ErrorCode.CONNECTION_TEST_FAILED,
                    status_code=400,
                )

        except ValidationError as e:
            logger.error(f"数据源配置验证失败: {e}")
            return self.error_response(
                error=f"配置验证失败: {e.error_count()} 个错误",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )
        except Exception as e:
            logger.error(f"测试连接失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.CONNECTION_TEST_FAILED,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_test_existing(self, request: Request) -> JSONResponse:
        """测试已有数据源

        测试已存在的数据源配置是否能成功连接数据库。
        需要认证。

        Args:
            request: HTTP请求对象，包含name路径参数

        Returns:
            JSONResponse: 测试结果响应
        """
        try:
            name = request.path_params["name"]

            # 获取配置
            ds = await self.datasource_service.get_datasource(name)
            if not ds:
                return self.error_response(
                    error=f"数据源不存在: {name}",
                    code=ErrorCode.DATASOURCE_NOT_FOUND,
                    status_code=404,
                )

            # 测试连接
            result = await self.pool_service.test_connection(ds)

            if result.get("success"):
                return self.success_response(
                    data={"name": name},
                    message=result.get("message", "连接测试成功"),
                )
            else:
                return self.error_response(
                    error=result.get("message", "连接测试失败"),
                    code=ErrorCode.CONNECTION_TEST_FAILED,
                    status_code=400,
                )

        except Exception as e:
            logger.error(f"测试连接失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.CONNECTION_TEST_FAILED,
                status_code=500,
            )

    # ============================================================
    # Reload
    # ============================================================

    @requires("authenticated")
    async def handle_reload_one(self, request: Request) -> JSONResponse:
        """重载单个数据源

        重载指定数据源的连接池，仅重载已启用的数据源。
        如果连接池不存在则创建新池。
        需要认证。

        Args:
            request: HTTP请求对象，包含name路径参数

        Returns:
            JSONResponse: 重载成功的响应或错误响应
        """
        try:
            name = request.path_params["name"]

            # 获取配置
            ds = await self.datasource_service.get_datasource(name)
            if not ds:
                return self.error_response(
                    error=f"数据源不存在: {name}",
                    code=ErrorCode.DATASOURCE_NOT_FOUND,
                    status_code=404,
                )

            # 仅重载已启用的数据源
            if not ds.enabled:
                return self.error_response(
                    error=f"数据源未启用: {name}",
                    code=ErrorCode.OPERATION_FAILED,
                    status_code=400,
                )

            # 重载连接池
            if name in self.pool_service._pools:
                await self.pool_service.reload_pool(ds)
            else:
                # 连接池不存在，创建新池
                await self.pool_service.add_pool(ds)

            return self.success_response(
                data={"name": name},
                message=f"已重载数据源: {name}",
            )

        except Exception as e:
            logger.error(f"重载数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_reload_all(self, request: Request) -> JSONResponse:
        """重载所有数据源

        重载所有已启用数据源的连接池，返回关闭、创建和错误信息。
        需要认证。

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含重载结果的响应
        """
        try:
            # 从 YAML 文件重新加载配置
            datasources = await self.datasource_service.list_datasources()

            # 重载所有连接池
            result = await self.pool_service.reload_all_pools(datasources)

            return self.success_response(
                data={
                    "closed": result["closed"],
                    "created": result["created"],
                    "errors": result["errors"],
                },
                message="已重载所有数据源",
            )

        except Exception as e:
            logger.error(f"重载所有数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    # ============================================================
    # 默认数据源管理
    # ============================================================

    @requires("authenticated")
    async def handle_get_default(self, request: Request) -> JSONResponse:
        """获取默认数据源

        返回当前设置的默认数据源名称。
        需要认证。

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含默认数据源名称的成功响应或错误响应
        """
        try:
            default_ds = await self.datasource_service.get_default_datasource()

            return self.success_response(
                data={"default_datasource": default_ds},
                message="获取默认数据源成功",
            )

        except Exception as e:
            logger.error(f"获取默认数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    @requires("authenticated")
    async def handle_set_default(self, request: Request) -> JSONResponse:
        """设置默认数据源

        根据请求体设置默认数据源名称。
        需要认证。设置后，stdio 和未开启 token 认证的 HTTP 模式将使用该默认数据源。

        Args:
            request: HTTP请求对象，包含 {"default_datasource": "数据源名称"} 格式的请求体

        Returns:
            JSONResponse: 设置成功的响应或错误响应
        """
        try:
            body = await request.json()
            ds_name = body.get("default_datasource")

            if not ds_name or not isinstance(ds_name, str):
                return self.error_response(
                    error="请求体中必须包含 default_datasource 字段（字符串类型）",
                    code=ErrorCode.VALIDATION_ERROR,
                    status_code=400,
                )

            # 设置默认数据源
            await self.datasource_service.set_default_datasource(ds_name)

            return self.success_response(
                data={"default_datasource": ds_name},
                message=f"已设置默认数据源: {ds_name}",
            )

        except ValueError as e:
            error_msg = str(e)
            if "不存在" in error_msg:
                code = ErrorCode.DATASOURCE_NOT_FOUND
            else:
                code = ErrorCode.OPERATION_FAILED
            logger.error(f"设置默认数据源失败: {e}")
            return self.error_response(error=error_msg, code=code, status_code=400)
        except Exception as e:
            logger.error(f"设置默认数据源失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )

    # ============================================================
    # 状态监控
    # ============================================================

    @requires("authenticated")
    async def handle_status(self, request: Request) -> JSONResponse:
        """获取所有数据源的连接池状态

        返回所有数据源的详细状态信息，包括配置信息、连接池状态等。
        密码字段会被移除（脱敏处理）。
        需要认证。

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含所有数据源状态信息的响应
        """
        try:
            # 获取配置
            datasources = await self.datasource_service.list_datasources()

            # 获取连接池状态（pool_status 返回 {"status": {name: pool_info}, "prometheus_metrics": "..."}）
            pool_status = await self.pool_service.pool_status()
            status_info = pool_status.get("status", {})

            # 组合详细信息
            result = {}
            for ds in datasources:
                ds_dict = ds.model_dump(mode="json")
                ds_dict.pop("password", None)  # 脱敏

                pool_info = status_info.get(ds.name, {})

                result[ds.name] = {
                    "enabled": ds.enabled,
                    "connected": ds.name in self.pool_service._pools,
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

            return self.success_response(data=result, message="获取连接池状态成功")

        except Exception as e:
            logger.error(f"获取状态失败: {e}")
            return self.error_response(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
