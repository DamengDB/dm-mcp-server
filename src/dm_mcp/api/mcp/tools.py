"""工具 REST Controller"""

from typing import Any

from dm_mcp.api.mcp._base_entity import BaseMCPEntityController


class ToolController(BaseMCPEntityController):
    """工具元数据与分组归属 Controller"""

    _entity_type = "tool"
    _label = "工具"

    async def _list(self) -> list[dict[str, Any]]:
        return await self.mcp_service.list_tools_with_metadata()

    async def _get(self, name: str) -> dict[str, Any]:
        return await self.mcp_service.get_tool_metadata(name)

    async def _upsert_override(
        self, original_name: str, **kwargs: Any
    ) -> dict[str, Any]:
        return await self.mcp_service.upsert_tool_metadata_override(
            original_name=original_name, **kwargs
        )

    async def _delete_override(self, name: str) -> None:
        await self.mcp_service.delete_tool_metadata_override(name)

    async def _assign(self, name: str, group_id: str) -> dict[str, Any]:
        return await self.mcp_group_service.assign_tool(name, group_id)

    async def _unassign(self, name: str) -> dict[str, Any]:
        return await self.mcp_group_service.unassign_tool(name)

    async def _batch_assign(
        self, names: list[str], group_id: str | None
    ) -> dict[str, Any]:
        return await self.mcp_group_service.batch_assign_tools(names, group_id)
