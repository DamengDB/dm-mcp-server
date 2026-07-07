"""资源 REST Controller"""

from typing import Any

from dm_mcp.api.mcp._base_entity import BaseMCPEntityController


class ResourceController(BaseMCPEntityController):
    """资源元数据与分组归属 Controller"""

    _entity_type = "resource"
    _label = "资源"

    async def _list(self) -> list[dict[str, Any]]:
        return await self.mcp_service.list_resources_with_metadata()

    async def _get(self, name: str) -> dict[str, Any]:
        return await self.mcp_service.get_resource_metadata(name)

    async def _upsert_override(
        self, original_name: str, **kwargs: Any
    ) -> dict[str, Any]:
        return await self.mcp_service.upsert_resource_metadata_override(
            original_name=original_name, **kwargs
        )

    async def _delete_override(self, name: str) -> None:
        await self.mcp_service.delete_resource_metadata_override(name)

    async def _assign(self, name: str, group_id: str) -> dict[str, Any]:
        return await self.mcp_group_service.assign_resource(name, group_id)

    async def _unassign(self, name: str) -> dict[str, Any]:
        return await self.mcp_group_service.unassign_resource(name)

    async def _batch_assign(
        self, names: list[str], group_id: str | None
    ) -> dict[str, Any]:
        return await self.mcp_group_service.batch_assign_resources(names, group_id)
