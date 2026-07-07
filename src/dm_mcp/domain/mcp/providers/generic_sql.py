"""通用SQL MCP Provider

提供从数据库加载SQL定义并动态注册为MCP工具或资源的功能。
"""

import inspect
import json
import logging
from typing import Any, Callable

from sqlalchemy import select

from dm_mcp.infra.persistence import GenericSqlDefinitionModel, get_async_session
from dm_mcp.domain.mcp.providers.base import BaseDataSourceMCPProvider
from dm_mcp.domain.datasource.services.datasource import DataSourceService

logger = logging.getLogger(__name__)


class GenericSqlMCPProvider(BaseDataSourceMCPProvider):
    """通用SQL MCP Provider

    从数据库加载SQL定义，动态注册为MCP工具或资源。
    """

    def __init__(self, datasource_service: DataSourceService):
        super().__init__(datasource_service)
        self._definitions: dict[str, GenericSqlDefinitionModel] = {}
        self._on_refresh_callback: Any = None

    def set_refresh_callback(self, callback: Any) -> None:
        """设置刷新回调函数，用于在刷新后清除缓存等操作

        Args:
            callback: 回调函数，无参数
        """
        self._on_refresh_callback = callback

    async def startup(self) -> None:
        """启动时加载SQL定义"""
        logger.info("开始加载通用SQL定义")
        await self._load_and_register_definitions()
        logger.info(f"通用SQL定义加载完成，共加载 {len(self._definitions)} 个定义")

    async def _load_and_register_definitions(self) -> None:
        """加载并注册所有启用的SQL定义"""
        definitions = await self._load_definitions()
        self._definitions = {d.name: d for d in definitions}
        await self._register_definitions(definitions)

    async def _load_definitions(self) -> list[GenericSqlDefinitionModel]:
        """从数据库加载所有启用的SQL定义"""
        async with get_async_session() as session:
            result = await session.execute(
                select(GenericSqlDefinitionModel).where(
                    GenericSqlDefinitionModel.enabled == True
                )
            )
            return list(result.scalars().all())

    async def _register_definitions(
        self, definitions: list[GenericSqlDefinitionModel]
    ) -> None:
        """注册SQL定义为工具或资源"""
        # 注意：这里我们不直接清空router，因为刷新工具也在这个router中
        # 实际使用时可能需要更精细的管理

        for definition in definitions:
            try:
                await self._register_single_definition(definition)
            except Exception as e:
                logger.error(
                    f"注册SQL定义失败: {definition.name}, 错误: {e}",
                    exc_info=True,
                )

    async def _register_single_definition(
        self, definition: GenericSqlDefinitionModel
    ) -> None:
        """注册单个SQL定义"""
        name = definition.name
        sql_template = definition.sql_template

        # 解析输入Schema
        input_schema = None
        if definition.input_schema:
            try:
                input_schema = json.loads(definition.input_schema)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"解析输入Schema失败: {name}, 使用默认Schema, 错误: {e}"
                )

        if definition.type == "tool":
            await self._register_as_tool(definition, input_schema)
        elif definition.type == "resource":
            await self._register_as_resource(definition)
        else:
            logger.warning(f"未知的定义类型: {definition.type}, 跳过: {name}")

    async def _register_as_tool(
        self,
        definition: GenericSqlDefinitionModel,
        input_schema: dict[str, Any] | None,
    ) -> None:
        """注册为工具"""
        name = definition.name
        sql_template = definition.sql_template

        # 动态创建工具函数
        async def generic_tool(**kwargs):
            return await self._execute_tool_sql(sql_template, kwargs)

        # 设置函数元数据
        generic_tool.__name__ = name
        generic_tool.__doc__ = (
            definition.long_description or definition.short_description
        )

        # 注册工具（直接传入 group，避免注册后再补丁）
        self.mcp.tool(
            name=name,
            description=definition.short_description,
            requires_token_auth=definition.requires_token_auth,
            group=definition.group,
        )(generic_tool)

        logger.debug(f"已注册SQL工具: {name}")

    async def _register_as_resource(
        self, definition: GenericSqlDefinitionModel
    ) -> None:
        """注册为资源"""
        name = definition.name
        sql_template = definition.sql_template
        uri = f"sql://{name}"

        # 动态创建资源函数
        async def generic_resource():
            return await self._execute_tool_sql(sql_template, {})

        # 设置函数元数据
        generic_resource.__name__ = name
        generic_resource.__doc__ = (
            definition.long_description or definition.short_description
        )

        # 注册资源（直接传入 group，避免注册后再补丁）
        self.mcp.resource(
            uri=uri,
            name=name,
            description=definition.short_description,
            group=definition.group,
            mime_type="application/json",
        )(generic_resource)

        logger.debug(f"已注册SQL资源: {name}")

    async def _execute_tool_sql(
        self, sql_template: str, params: dict[str, Any]
    ) -> Any:
        """执行工具SQL"""
        # 渲染SQL模板（简单的参数替换）
        # 注意：实际的参数化查询由pool_service处理
        return await self._exec(sql=sql_template, params=params, max_rows=200)

    async def refresh_definitions(self) -> dict[str, Any]:
        """
        刷新通用SQL定义，重新从数据库加载所有启用的定义并注册。

        调用此方法会清除现有的动态定义并重新加载。
        """
        logger.info("开始刷新通用SQL定义")
        await self._load_and_register_definitions()

        # 调用刷新回调（如果有）
        try:
            if self._on_refresh_callback:
                if inspect.iscoroutinefunction(self._on_refresh_callback):
                    await self._on_refresh_callback()
                else:
                    self._on_refresh_callback()
                logger.info("已执行刷新回调")
        except Exception as e:
            logger.warning(f"执行刷新回调失败: {e}")

        return {
            "message": f"已刷新 {len(self._definitions)} 个SQL定义",
            "count": len(self._definitions),
        }
