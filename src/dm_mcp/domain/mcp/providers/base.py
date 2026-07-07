"""MCP Provider基类模块

提供数据源相关Provider的抽象基类。
"""

from typing import Any

from dm_mcp.common import messages
from dm_mcp.core.mcp.provider import BaseMCPProvider
from dm_mcp.domain.datasource.services.datasource import DataSourceService


class BaseDataSourceMCPProvider(BaseMCPProvider):
    """数据源相关MCP Provider的基类

    提供数据源服务的公共功能，包括获取当前数据源名称等。
    """

    def __init__(self, datasource_service: DataSourceService) -> None:
        super().__init__()
        self.datasource_service = datasource_service

    async def _get_current_datasource_name(self) -> str:
        """获取当前上下文中的数据源名称"""
        current_source_id = self.context.datasource.datasource_id
        datasource = await self.datasource_service.get_datasource_by_id(
            current_source_id
        )
        if datasource is None:
            raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND_BY_ID)
        return datasource.name

    async def _exec(
        self,
        *,
        sql: str,
        params: Any | None = None,
        max_rows: int = 2000,
        timeout: float | None = None,
        read_only: bool = False,
        schema: str | None = None,
    ) -> list[Any]:
        """统一执行入口——调用 DataSourceService.execute_query 并提取结果"""
        source = await self._get_current_datasource_name()
        r = await self.datasource_service.execute_query(
            sql=sql,
            source=source,
            params=params,
            max_rows=max_rows,
            timeout=timeout,
            read_only=read_only,
            schema=schema,
        )
        return r.get("result", [])
