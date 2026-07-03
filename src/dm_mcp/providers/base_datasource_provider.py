"""MCP Provider基类模块

提供数据源相关Provider的抽象基类。
"""

from dm_mcp.core.mcp.provider import BaseMCPProvider
from dm_mcp.services.datasource_service import DataSourceService


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
            raise ValueError("数据源不存在")
        return datasource.name
