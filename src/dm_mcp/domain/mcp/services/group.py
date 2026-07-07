"""MCP 分组服务：分组结构 + 实体归属

提供 CLI 分组的 CRUD 与实体↔分组归属管理。
- 分组结构：身份由 12 字符 base62 短 ``id`` 表征，``name`` 仅是当前层级的段名。
  重命名/移动只动 1 行，与子孙数量无关。完整 path 由 id 链按需拼接（不持久化）。
- 实体归属：管理 tool / resource / prompt 与 CLI 分组的归属关系（分配/解除）。

所有 mutation 先写数据库，成功后通过事件通知查询侧刷新。
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from dm_mcp.common import messages
from dm_mcp.core.exceptions import (
    CliGroupConflictError,
    CliGroupNotFoundError,
)
from dm_mcp.core.events.subscription import EventSubscription
from dm_mcp.core.service import BaseService, ServiceFactory, ServiceMetadata
from dm_mcp.domain.mcp.events import (
    MCPGroupChanged,
    MCPEntityAssigned,
    MCPProvidersStarted,
)
from dm_mcp.domain.mcp.groups import CliGroupEntry, CliGroupRegistry
from dm_mcp.infra.persistence import (
    CliGroupModel,
    EntityGroupAssignmentModel,
    get_async_session,
)
from dm_mcp.infra.persistence.models import generate_short_id

logger = logging.getLogger(__name__)


def _validate_segment(name: str) -> None:
    """单段名校验：只允许 [a-z0-9_]，不能含点。"""
    CliGroupRegistry.validate_path(name)
    if "." in name:
        raise ValueError(messages.MSG_GROUP_SEGMENT_INVALID.format(name=name))


def _row_to_dict(model: CliGroupModel, path: str) -> dict[str, Any]:
    """将 CliGroupModel + 派生 path 转为 dict（含 path）。"""
    return {
        "id": model.id,
        "name": model.name,
        "parent_id": model.parent_id,
        "path": path,
        "short_description": model.short_description,
        "long_description": model.long_description,
        "created_at": model.created_at,
        "updated_at": model.updated_at,
    }


# 默认 CLI 分组描述（首次同步或描述为空时自动填充）
# 格式：第一行为 short_description，后续行为 long_description 的补充内容。
DEFAULT_GROUP_DESCRIPTIONS: dict[str, str] = {
    "inspect": (
        "数据库巡检与性能诊断工具集\n"
        "涵盖会话、锁、SQL、内存、缓冲池等维度的实时排查能力。"
        "适用于系统负载突增、响应延迟、并发阻塞等场景的深度诊断。"
    ),
    "meta": (
        "数据库元数据查询工具集\n"
        "提供 schema、表、视图、索引、约束等对象的结构信息。"
        "可用于写 SQL 前的结构确认、依赖分析及文档生成。"
    ),
    "data": (
        "表数据分析工具集\n"
        "支持空间占用统计、表统计信息及列级数据分布分析。"
        "用于容量评估、数据质量检查及索引设计辅助。"
    ),
    "dpc": (
        "DPC 集群管理工具集\n"
        "用于查看集群拓扑、实例状态、分布式会话及执行追踪。"
        "仅适用于 DPC 分布式部署环境。"
    ),
    "query": (
        "SQL 执行工具集\n"
        "支持任意 SQL 查询和只读 SELECT 语句的直接执行。"
        "用于临时数据查询、结果验证和快速探查。"
    ),
}


# =========================================================
# MCPGroupService
# =========================================================

class MCPGroupService(BaseService):
    """MCP 分组服务

    命令侧服务：负责 CLI 分组的 CRUD、树形结构，以及实体↔分组归属。
    维护 ``path ↔ id`` 的轻量缓存（全树一次 SELECT，每次 mutation 后失效）。
    """

    def __init__(self, event_service: Any) -> None:
        self._event_service = event_service
        # 轻量缓存（事件订阅 / 自身 mutation 后整体失效）
        self._rows_cache: list[CliGroupModel] | None = None
        self._path_to_id: dict[str, str] | None = None
        self._id_to_path: dict[str, str] | None = None
        self._id_to_row: dict[str, CliGroupModel] | None = None

    # ===================================================
    # 缓存
    # ===================================================
    async def _ensure_cache(self) -> None:
        if (
            self._rows_cache is not None
            and self._id_to_row is not None
            and self._path_to_id is not None
            and self._id_to_path is not None
        ):
            return
        async with get_async_session() as session:
            result = await session.execute(select(CliGroupModel))
            rows = list(result.scalars().all())

        id_to_row = {r.id: r for r in rows}
        path_to_id: dict[str, str] = {}
        id_to_path: dict[str, str] = {}

        def _path_of(row: CliGroupModel) -> str:
            parts: list[str] = []
            cur: CliGroupModel | None = row
            seen: set[str] = set()
            while cur is not None:
                if cur.id in seen:
                    break  # 循环保护
                seen.add(cur.id)
                parts.append(cur.name)
                if cur.parent_id is None:
                    break
                cur = id_to_row.get(cur.parent_id)
            return ".".join(reversed(parts))

        for r in rows:
            p = _path_of(r)
            path_to_id[p] = r.id
            id_to_path[r.id] = p

        self._rows_cache = rows
        self._id_to_row = id_to_row
        self._path_to_id = path_to_id
        self._id_to_path = id_to_path

    def _invalidate_cache(self) -> None:
        self._rows_cache = None
        self._id_to_row = None
        self._path_to_id = None
        self._id_to_path = None

    async def on_mcp_group_changed(self, event: MCPGroupChanged) -> None:
        """事件触发时整体失效缓存（兼容外部直写场景）。"""
        self._invalidate_cache()

    async def on_mcp_providers_started(
        self, event: MCPProvidersStarted
    ) -> None:
        """所有 Provider 启动完毕后，将缺失的硬编码分组同步到数据库，并填充默认描述。"""
        if not event.group_paths:
            return
        try:
            created = await self.sync_missing_group_paths(event.group_paths)
            logger.info(
                "Provider 分组同步完成：已创建 %d 个缺失分组",
                len(created),
            )
        except Exception:
            logger.warning("Provider 分组同步失败", exc_info=True)

        try:
            updated = await self.sync_group_descriptions()
            if updated:
                logger.info(
                    "分组描述同步完成：已更新 %d 个分组的默认描述",
                    len(updated),
                )
        except Exception:
            logger.warning("分组描述同步失败", exc_info=True)

    # ===================================================
    # 路径解析
    # ===================================================
    async def resolve_path(self, path: str) -> str | None:
        """``path`` → ``group_id``（不存在返回 None）。"""
        if not path:
            return None
        await self._ensure_cache()
        assert self._path_to_id is not None
        return self._path_to_id.get(path)

    async def path_of(self, group_id: str) -> str | None:
        """``group_id`` → 完整 ``path``（不存在返回 None）。"""
        await self._ensure_cache()
        assert self._id_to_path is not None
        return self._id_to_path.get(group_id)

    # ===================================================
    # 查询
    # ===================================================
    async def list_cli_groups(self) -> list[dict[str, Any]]:
        """列出所有分组（含派生 path）。"""
        await self._ensure_cache()
        assert self._rows_cache is not None
        assert self._id_to_path is not None
        return [
            _row_to_dict(r, self._id_to_path.get(r.id, r.name))
            for r in self._rows_cache
        ]

    async def get_cli_group_by_path(self, path: str) -> dict[str, Any] | None:
        """通过 path 查询单个分组。"""
        CliGroupRegistry.validate_path(path)
        gid = await self.resolve_path(path)
        if gid is None:
            return None
        return await self.get_cli_group_by_id(gid)

    async def get_cli_group_by_id(
        self, group_id: str
    ) -> dict[str, Any] | None:
        """通过 id 查询单个分组。"""
        await self._ensure_cache()
        assert self._id_to_row is not None
        assert self._id_to_path is not None
        row = self._id_to_row.get(group_id)
        if row is None:
            return None
        return _row_to_dict(row, self._id_to_path.get(group_id, row.name))

    async def get_cli_group_tree(self) -> dict[str, Any]:
        """获取嵌套分组树（不含实体计数）。"""
        await self._ensure_cache()
        assert self._rows_cache is not None
        assert self._id_to_path is not None
        rows = sorted(
            self._rows_cache,
            key=lambda r: self._id_to_path.get(r.id, r.name),
        )

        tree: dict[str, Any] = {}
        for row in rows:
            path = self._id_to_path.get(row.id)
            if not path:
                continue
            parts = path.split(".")
            current = tree
            for i, part in enumerate(parts):
                is_leaf = i == len(parts) - 1
                if part not in current:
                    current[part] = {
                        "id": row.id if is_leaf else "",
                        "path": ".".join(parts[: i + 1]),
                        "short_description": "",
                        "long_description": "",
                        "children": {},
                        "counts": {"tools": 0, "resources": 0, "prompts": 0},
                    }
                if is_leaf:
                    current[part]["id"] = row.id
                    current[part]["short_description"] = row.short_description
                    current[part]["long_description"] = row.long_description
                current = current[part]["children"]

        return tree

    async def sync_missing_group_paths(
        self, paths: list[str]
    ) -> list[dict[str, Any]]:
        """将 provider 硬编码的 group path 批量同步到数据库（缺失时自动创建）。

        例如传入 ``["db.dpc.cluster"]`` 时，会依次确保
        ``db`` → ``db.dpc`` → ``db.dpc.cluster`` 都存在。
        已存在的路径会被跳过，避免重复写入。
        """
        await self._ensure_cache()
        assert self._path_to_id is not None

        # 按层级排序，先短后长，保证父节点先创建
        unique_paths = sorted({p.strip() for p in paths if p.strip()})
        created: list[dict[str, Any]] = []
        # 本地缓存：create_cli_group 内部会 invalidate self._path_to_id，
        # 因此用本地 dict 跟踪已存在的 path -> id 映射
        local_path_to_id = dict(self._path_to_id)

        for path in unique_paths:
            if path in local_path_to_id:
                continue
            parts = path.split(".")
            for i in range(1, len(parts) + 1):
                sub = ".".join(parts[:i])
                if sub in local_path_to_id:
                    continue
                # 如果是顶层分组（不含点），先检查是否已存在同名分组（任意位置）
                # 防止用户已将 diag/dpc 移到其他分组下，重启后又在根目录重复创建
                name = parts[i - 1]
                is_top_level = i == 1
                if is_top_level:
                    name_exists = any(
                        p.split(".")[-1] == name for p in local_path_to_id
                    )
                    if name_exists:
                        continue
                parent_path = ".".join(parts[: i - 1]) if i > 1 else None
                parent_id = (
                    local_path_to_id.get(parent_path) if parent_path else None
                )
                try:
                    row = await self.create_cli_group(
                        parent_id=parent_id,
                        name=name,
                        description="",
                    )
                    created.append(row)
                    local_path_to_id[sub] = row["id"]
                except CliGroupConflictError:
                    # 并发/缓存略旧时可能冲突，直接跳过
                    pass

        return created

    async def sync_group_descriptions(self) -> list[dict[str, Any]]:
        """将 DEFAULT_GROUP_DESCRIPTIONS 中定义的默认描述同步到数据库。

        仅更新当前数据库中描述为空（short_description 和 long_description 均为空）
        且 path 命中 DEFAULT_GROUP_DESCRIPTIONS 的分组。
        返回实际被更新的分组列表。
        """
        await self._ensure_cache()
        if self._id_to_row is None or self._id_to_path is None:
            return []

        updated: list[dict[str, Any]] = []
        now = datetime.now()

        for gid, row in self._id_to_row.items():
            path = self._id_to_path.get(gid)
            if not path:
                continue
            desc = DEFAULT_GROUP_DESCRIPTIONS.get(path)
            if not desc:
                continue
            # 仅当当前描述为空时才填充（避免覆盖用户自定义描述）
            if row.short_description or row.long_description:
                continue

            entry = CliGroupEntry.from_description(path, desc)
            async with get_async_session() as session:
                result = await session.execute(
                    select(CliGroupModel).where(CliGroupModel.id == gid)
                )
                model = result.scalar_one_or_none()
                if model is None:
                    continue
                model.short_description = entry.short_description
                model.long_description = entry.long_description
                model.updated_at = now
                await session.flush()

            updated.append(
                {
                    "id": gid,
                    "path": path,
                    "short_description": entry.short_description,
                    "long_description": entry.long_description,
                }
            )

        if updated:
            self._invalidate_cache()
            # 批量发布一个变更事件，使查询侧刷新
            await self._event_service.publish(
                MCPGroupChanged(
                    group_id="__batch_sync_desc__",
                    operation="updated",
                )
            )

        return updated

    # ===================================================
    # 分组 CRUD
    # ===================================================
    async def create_cli_group(
        self,
        parent_id: str | None,
        name: str,
        description: str,
    ) -> dict[str, Any]:
        """创建新分组（按 parent_id + name 唯一约束）。"""
        _validate_segment(name)

        if parent_id is not None:
            await self._ensure_cache()
            assert self._id_to_row is not None
            if parent_id not in self._id_to_row:
                raise CliGroupNotFoundError(parent_id)

        parent_path = await self.path_of(parent_id) if parent_id else None
        full_path = f"{parent_path}.{name}" if parent_path else name
        entry = CliGroupEntry.from_description(full_path, description)
        now = datetime.now()

        async with get_async_session() as session:
            stmt = select(CliGroupModel).where(CliGroupModel.name == name)
            if parent_id is None:
                stmt = stmt.where(CliGroupModel.parent_id.is_(None))
            else:
                stmt = stmt.where(CliGroupModel.parent_id == parent_id)
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing is not None:
                raise CliGroupConflictError(full_path)

            model = CliGroupModel(
                id=generate_short_id(),
                name=name,
                parent_id=parent_id,
                short_description=entry.short_description,
                long_description=entry.long_description,
                created_at=now,
                updated_at=now,
            )
            session.add(model)
            await session.flush()
            new_id = model.id

        self._invalidate_cache()

        await self._event_service.publish(
            MCPGroupChanged(
                group_id=new_id,
                operation="created",
                new_path=full_path,
            )
        )

        return {
            "id": new_id,
            "name": name,
            "parent_id": parent_id,
            "path": full_path,
            "short_description": entry.short_description,
            "long_description": entry.long_description,
            "created_at": now,
            "updated_at": now,
        }

    async def update_cli_group_description(
        self,
        group_id: str,
        description: str,
    ) -> dict[str, Any]:
        """更新分组描述（仅 short/long description；不动 name/parent）。"""
        await self._ensure_cache()
        assert self._id_to_row is not None
        assert self._id_to_path is not None

        row = self._id_to_row.get(group_id)
        if row is None:
            raise CliGroupNotFoundError(group_id)

        path = self._id_to_path.get(group_id, row.name)
        entry = CliGroupEntry.from_description(path, description)
        now = datetime.now()

        async with get_async_session() as session:
            result = await session.execute(
                select(CliGroupModel).where(CliGroupModel.id == group_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise CliGroupNotFoundError(group_id)
            model.short_description = entry.short_description
            model.long_description = entry.long_description
            model.updated_at = now
            await session.flush()

        self._invalidate_cache()

        await self._event_service.publish(
            MCPGroupChanged(
                group_id=group_id,
                operation="updated",
                new_path=path,
            )
        )

        return await self.get_cli_group_by_id(group_id) or {
            "id": group_id,
            "name": row.name,
            "parent_id": row.parent_id,
            "path": path,
            "short_description": entry.short_description,
            "long_description": entry.long_description,
        }

    async def rename_cli_group(
        self, group_id: str, new_name: str
    ) -> dict[str, Any]:
        """重命名分组（只改 ``name``，1 行 UPDATE）。"""
        _validate_segment(new_name)

        await self._ensure_cache()
        assert self._id_to_row is not None
        assert self._id_to_path is not None

        row = self._id_to_row.get(group_id)
        if row is None:
            raise CliGroupNotFoundError(group_id)
        old_path = self._id_to_path.get(group_id)
        if row.name == new_name:
            return _row_to_dict(row, old_path or row.name)

        # 同一父级下不允许重名
        async with get_async_session() as session:
            stmt = select(CliGroupModel).where(
                CliGroupModel.name == new_name,
                CliGroupModel.id != group_id,
            )
            if row.parent_id is None:
                stmt = stmt.where(CliGroupModel.parent_id.is_(None))
            else:
                stmt = stmt.where(CliGroupModel.parent_id == row.parent_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                conflict_path = (
                    f"{old_path.rsplit('.', 1)[0]}.{new_name}"
                    if old_path and "." in old_path
                    else new_name
                )
                raise CliGroupConflictError(conflict_path)

            result = await session.execute(
                select(CliGroupModel).where(CliGroupModel.id == group_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise CliGroupNotFoundError(group_id)
            model.name = new_name
            await session.flush()

        self._invalidate_cache()
        new_path = (
            f"{old_path.rsplit('.', 1)[0]}.{new_name}"
            if old_path and "." in old_path
            else new_name
        )

        await self._event_service.publish(
            MCPGroupChanged(
                group_id=group_id,
                operation="renamed",
                old_path=old_path,
                new_path=new_path,
            )
        )

        return await self.get_cli_group_by_id(group_id) or {
            "id": group_id,
            "name": new_name,
            "path": new_path,
        }

    async def move_cli_group(
        self, group_id: str, new_parent_id: str | None
    ) -> dict[str, Any]:
        """移动分组（只改 ``parent_id``，1 行 UPDATE）。"""
        await self._ensure_cache()
        assert self._id_to_row is not None
        assert self._id_to_path is not None

        row = self._id_to_row.get(group_id)
        if row is None:
            raise CliGroupNotFoundError(group_id)
        old_path = self._id_to_path.get(group_id)

        if new_parent_id == group_id:
            raise ValueError(messages.MSG_GROUP_CANNOT_MOVE_UNDER_SELF)

        # 检查新父节点是否存在；并防止循环（不能把节点移到自己的子孙之下）
        if new_parent_id is not None:
            new_parent = self._id_to_row.get(new_parent_id)
            if new_parent is None:
                raise CliGroupNotFoundError(new_parent_id)
            cur: CliGroupModel | None = new_parent
            while cur is not None:
                if cur.id == group_id:
                    raise ValueError(
                        messages.MSG_GROUP_CANNOT_MOVE_UNDER_DESCENDANT
                    )
                if cur.parent_id is None:
                    break
                cur = self._id_to_row.get(cur.parent_id)

        if row.parent_id == new_parent_id:
            return _row_to_dict(row, old_path or row.name)

        # 同一父下重名校验
        async with get_async_session() as session:
            stmt = select(CliGroupModel).where(
                CliGroupModel.name == row.name,
                CliGroupModel.id != group_id,
            )
            if new_parent_id is None:
                stmt = stmt.where(CliGroupModel.parent_id.is_(None))
            else:
                stmt = stmt.where(CliGroupModel.parent_id == new_parent_id)
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is not None:
                new_parent_path = (
                    self._id_to_path.get(new_parent_id) if new_parent_id else ""
                )
                conflict_path = (
                    f"{new_parent_path}.{row.name}" if new_parent_path else row.name
                )
                raise CliGroupConflictError(conflict_path)

            result = await session.execute(
                select(CliGroupModel).where(CliGroupModel.id == group_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise CliGroupNotFoundError(group_id)
            model.parent_id = new_parent_id
            await session.flush()

        self._invalidate_cache()

        new_parent_path = (
            await self.path_of(new_parent_id) if new_parent_id else ""
        )
        new_path = f"{new_parent_path}.{row.name}" if new_parent_path else row.name

        await self._event_service.publish(
            MCPGroupChanged(
                group_id=group_id,
                operation="moved",
                old_path=old_path,
                new_path=new_path,
            )
        )

        return await self.get_cli_group_by_id(group_id) or {
            "id": group_id,
            "name": row.name,
            "path": new_path,
        }

    async def delete_cli_group(self, group_id: str) -> dict[str, Any]:
        """删除分组：DB 层 ``ON DELETE CASCADE`` 同时删除子分组与 assignment。"""
        await self._ensure_cache()
        assert self._id_to_row is not None
        assert self._id_to_path is not None

        row = self._id_to_row.get(group_id)
        if row is None:
            raise CliGroupNotFoundError(group_id)
        old_path = self._id_to_path.get(group_id)

        async with get_async_session() as session:
            result = await session.execute(
                select(CliGroupModel).where(CliGroupModel.id == group_id)
            )
            model = result.scalar_one_or_none()
            if model is None:
                raise CliGroupNotFoundError(group_id)
            await session.delete(model)
            await session.flush()

        self._invalidate_cache()

        await self._event_service.publish(
            MCPGroupChanged(
                group_id=group_id,
                operation="deleted",
                old_path=old_path,
            )
        )

        return {
            "id": group_id,
            "deleted_path": old_path,
        }

    # ===================================================
    # 实体↔分组归属
    # ===================================================
    async def _validate_group_id(self, group_id: str | None) -> None:
        """校验 group_id 是否存在；不存在抛 CliGroupNotFoundError"""
        if group_id is None:
            return
        row = await self.get_cli_group_by_id(group_id)
        if row is None:
            raise CliGroupNotFoundError(group_id)

    async def _upsert_assignment(
        self,
        object_type: str,
        key: str,
        group_id: str,
    ) -> None:
        """插入或更新单个 assignment 行。"""
        async with get_async_session() as session:
            result = await session.execute(
                select(EntityGroupAssignmentModel).where(
                    EntityGroupAssignmentModel.object_type == object_type,
                    EntityGroupAssignmentModel.key == key,
                )
            )
            model = result.scalar_one_or_none()
            if model is None:
                model = EntityGroupAssignmentModel(
                    object_type=object_type,
                    key=key,
                    group_id=group_id,
                )
                session.add(model)
            else:
                model.group_id = group_id
            await session.flush()

    async def _delete_assignment(self, object_type: str, key: str) -> bool:
        """删除单个 assignment 行；返回是否真的删除了。"""
        async with get_async_session() as session:
            result = await session.execute(
                select(EntityGroupAssignmentModel).where(
                    EntityGroupAssignmentModel.object_type == object_type,
                    EntityGroupAssignmentModel.key == key,
                )
            )
            if result.scalar_one_or_none() is None:
                return False
            await session.execute(
                delete(EntityGroupAssignmentModel).where(
                    EntityGroupAssignmentModel.object_type == object_type,
                    EntityGroupAssignmentModel.key == key,
                )
            )
        return True

    # 单实体 assign / unassign
    async def assign_tool(self, name: str, group_id: str) -> dict[str, Any]:
        return await self._assign("tool", name, group_id)

    async def assign_resource(self, name: str, group_id: str) -> dict[str, Any]:
        return await self._assign("resource", name, group_id)

    async def assign_prompt(self, name: str, group_id: str) -> dict[str, Any]:
        return await self._assign("prompt", name, group_id)

    async def unassign_tool(self, name: str) -> dict[str, Any]:
        return await self._unassign("tool", name)

    async def unassign_resource(self, name: str) -> dict[str, Any]:
        return await self._unassign("resource", name)

    async def unassign_prompt(self, name: str) -> dict[str, Any]:
        return await self._unassign("prompt", name)

    async def _assign(
        self, object_type: str, key: str, group_id: str
    ) -> dict[str, Any]:
        await self._validate_group_id(group_id)
        await self._upsert_assignment(object_type, key, group_id)
        group_path = await self.path_of(group_id)
        await self._event_service.publish(
            MCPEntityAssigned(
                object_type=object_type,  # type: ignore[arg-type]
                key=key,
                group_id=group_id,
            )
        )
        return {
            "object_type": object_type,
            "key": key,
            "group_id": group_id,
            "group_path": group_path,
        }

    async def _unassign(self, object_type: str, key: str) -> dict[str, Any]:
        await self._delete_assignment(object_type, key)
        await self._event_service.publish(
            MCPEntityAssigned(
                object_type=object_type,  # type: ignore[arg-type]
                key=key,
                group_id=None,
            )
        )
        return {"object_type": object_type, "key": key, "group_id": None}

    # 批量 assign（group_id=None ⇒ 批量 unassign）
    async def batch_assign_tools(
        self, names: list[str], group_id: str | None
    ) -> dict[str, Any]:
        return await self._batch_assign("tool", names, group_id)

    async def batch_assign_resources(
        self, names: list[str], group_id: str | None
    ) -> dict[str, Any]:
        return await self._batch_assign("resource", names, group_id)

    async def batch_assign_prompts(
        self, names: list[str], group_id: str | None
    ) -> dict[str, Any]:
        return await self._batch_assign("prompt", names, group_id)

    async def _batch_assign(
        self, object_type: str, names: list[str], group_id: str | None
    ) -> dict[str, Any]:
        if group_id is not None:
            await self._validate_group_id(group_id)

        group_path = None
        if group_id is not None:
            group_path = await self.path_of(group_id)

        updated: list[dict[str, Any]] = []
        for name in names:
            if group_id is not None:
                await self._upsert_assignment(object_type, name, group_id)
            else:
                await self._delete_assignment(object_type, name)
            updated.append(
                {
                    "name": name,
                    "group_id": group_id,
                    "group_path": group_path,
                }
            )
            await self._event_service.publish(
                MCPEntityAssigned(
                    object_type=object_type,  # type: ignore[arg-type]
                    key=name,
                    group_id=group_id,
                )
            )
        return {"updated": updated}

    # 查询
    async def list_assignments(
        self, object_type: str | None = None
    ) -> list[dict[str, Any]]:
        """列出所有 assignment（可按 object_type 过滤）"""
        async with get_async_session() as session:
            stmt = select(EntityGroupAssignmentModel)
            if object_type is not None:
                stmt = stmt.where(
                    EntityGroupAssignmentModel.object_type == object_type
                )
            result = await session.execute(stmt)
            return [m.to_dict() for m in result.scalars().all()]


# =========================================================
# Factory
# =========================================================
class MCPGroupServiceFactory(ServiceFactory):
    """MCP 分组服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="mcp_group_service",
            service_type=MCPGroupService,
            description="MCP 分组服务（分组结构 + 实体归属）",
            author="DM MCP Team",
            dependencies=["event_service"],
            priority=50,
            event_subscriptions=[
                EventSubscription(
                    MCPGroupChanged,
                    "on_mcp_group_changed",
                    priority=10,
                ),
                EventSubscription(
                    MCPProvidersStarted,
                    "on_mcp_providers_started",
                    priority=10,
                ),
            ],
        )

    def create(self, settings, **deps) -> MCPGroupService:
        return MCPGroupService(deps["event_service"])
