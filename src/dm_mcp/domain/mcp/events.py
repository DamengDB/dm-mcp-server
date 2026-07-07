"""MCP 分组相关业务事件"""

from typing import Literal

from dm_mcp.core.events import Event


class MCPGroupChanged(Event):
    """分组结构发生变更"""

    group_id: str
    operation: Literal["created", "updated", "deleted", "renamed", "moved"]
    old_path: str | None = None
    new_path: str | None = None


class MCPEntityAssigned(Event):
    """实体被分配到分组（group_id=None 表示解除分配）"""

    object_type: Literal["tool", "resource", "prompt"]
    key: str
    group_id: str | None = None


class MCPProvidersStarted(Event):
    """所有 MCP Provider 已完成启动"""

    group_paths: list[str] = []
