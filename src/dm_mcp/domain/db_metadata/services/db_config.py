"""数据库元数据管理服务

提供 DataSource 对数据库对象（schema/table/view/column）的元数据覆盖 CRUD、
批量策略查询和内存缓存功能。

两层继承体系：
1. DataSource 级别（最高优先级）
2. 全局系统对象默认（仅 comment，系统对象 fallback）
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import delete, func, select
from sqlalchemy.sql import Select

# 哨兵值：区分"调用者没传字段" vs "调用者传了 None"
# 用于实现 PATCH 语义：只更新显式传入的字段
_UNSET = object()


def _build_object_config_where_clause(
    stmt: Select,
    datasource_id: Any,
    object_type: str,
    schema_name: str,
    table_name: str | None,
    column_name: str | None,
    model_cls: Any,
) -> Select:
    """构建元数据配置的 WHERE 查询条件（upsert/delete 共享）"""
    stmt = stmt.where(model_cls.datasource_id == datasource_id)
    stmt = stmt.where(model_cls.object_type == object_type)
    stmt = stmt.where(model_cls.schema_name == schema_name)
    stmt = stmt.where(
        model_cls.table_name == table_name
        if table_name is not None
        else model_cls.table_name.is_(None)
    )
    stmt = stmt.where(
        model_cls.column_name == column_name
        if column_name is not None
        else model_cls.column_name.is_(None)
    )
    return stmt

from dm_mcp.infra.persistence import (
    DBSystemObjectDefaultModel,
    DBObjectConfigModel,
    get_async_session,
)
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.core.service import BaseService
from dm_mcp.domain.token.services.token import TokenService

logger = logging.getLogger(__name__)

# 内置系统字典数据文件路径
_DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"

_BUILTIN_DICT_FILES = [
    ("dm_system_views.jsonl", "TABLE"),
    ("dm_system_tables.jsonl", "TABLE"),
]


@dataclass
class ObjectRule:
    """单条对象规则（内存结构）"""

    access_policy: Literal["allow", "deny"] | None = None
    comment_override: str | None = None


@dataclass
class DbMetadataPolicy:
    """元数据策略（内存结构，Provider 使用）

    两层继承：
    - ds_*: DataSource 级别（最高优先级）
    - global_*: 全局系统对象默认（仅 comment，最低优先级）
    """

    datasource_id: Any | None = None

    # DataSource 级别规则
    ds_schema_rules: dict[str, ObjectRule] = field(default_factory=dict)
    ds_table_rules: dict[tuple[str, str], ObjectRule] = field(default_factory=dict)
    ds_view_rules: dict[tuple[str, str], ObjectRule] = field(default_factory=dict)
    ds_column_rules: dict[tuple[str, str, str], ObjectRule] = field(default_factory=dict)

    # 全局系统对象默认 comment（仅 comment，无 access_policy）
    global_schema_comments: dict[str, ObjectRule] = field(default_factory=dict)
    global_table_comments: dict[tuple[str, str], ObjectRule] = field(default_factory=dict)
    global_column_comments: dict[tuple[str, str, str], ObjectRule] = field(
        default_factory=dict
    )


class DbConfigService(BaseService):
    """数据库元数据管理服务

    核心职责：
    1. 对 DataSource 的数据库元数据覆盖进行 CRUD
    2. 提供批量查询接口（供 Provider 在工具调用时一次性拉取策略）
    3. 维护本地缓存（5 分钟 TTL）
    """

    def __init__(
        self, token_service: TokenService, settings: Any = None
    ) -> None:
        self.token_service = token_service
        self.settings = settings
        self._lock = asyncio.Lock()
        # 缓存：datasource_id -> (MetadataPolicy, cached_at)
        self._policy_cache: dict[Any, tuple[MetadataPolicy, datetime]] = {}
        self._cache_ttl = timedelta(seconds=300)  # 5 分钟缓存 TTL

    # ============================================================
    # 服务生命周期
    # ============================================================

    async def startup(self) -> None:
        """服务启动：加载内置系统字典（仅首次）"""
        count = await self._count_system_object_defaults()
        if count == 0:
            loaded = await self._load_builtin_system_defaults()
            logger.info(f"已加载 {loaded} 条系统对象内置注释")
        else:
            logger.info(
                f"系统对象内置注释已存在（{count} 条），跳过加载"
            )

    async def _count_system_object_defaults(self) -> int:
        """检查全局系统对象默认是否已有记录"""
        async with get_async_session() as session:
            result = await session.execute(
                select(func.count()).select_from(DBSystemObjectDefaultModel)
            )
            return result.scalar_one() or 0

    async def _load_builtin_system_defaults(self) -> int:
        """从 JSONL 文件加载内置系统字典到数据库（批量插入）

        Returns:
            int: 加载的记录数
        """
        data_dir = _DATA_DIR
        if (
            self.settings
            and hasattr(self.settings, "builtin_system_dicts_dir")
            and self.settings.builtin_system_dicts_dir
        ):
            custom_dir = Path(self.settings.builtin_system_dicts_dir)
            if custom_dir.exists():
                data_dir = custom_dir

        records: list[DBSystemObjectDefaultModel] = []
        for filename, object_type in _BUILTIN_DICT_FILES:
            filepath = data_dir / filename
            if not filepath.exists():
                logger.warning(f"内置字典文件不存在: {filepath}")
                continue

            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    table_name = data.get("table")
                    comment = data.get("comment")
                    columns = data.get("columns", {})

                    if table_name and comment:
                        records.append(
                            DBSystemObjectDefaultModel(
                                object_type=object_type,
                                schema_name="SYS",
                                table_name=table_name,
                                comment_override=comment,
                            )
                        )

                    for col_name, col_comment in columns.items():
                        if col_comment:
                            records.append(
                                DBSystemObjectDefaultModel(
                                    object_type="COLUMN",
                                    schema_name="SYS",
                                    table_name=table_name,
                                    column_name=col_name,
                                    comment_override=col_comment,
                                )
                            )

        if not records:
            return 0

        # 同一会话批量插入，避免逐条创建会话
        async with get_async_session() as session:
            session.add_all(records)

        return len(records)

    # ============================================================
    # DataSource 级别 CRUD
    # ============================================================

    async def get_object_config(
        self,
        datasource_id: Any,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"],
        schema_name: str,
        table_name: str | None = None,
        column_name: str | None = None,
    ) -> DBObjectConfigModel | None:
        """获取单条 DataSource 对象配置"""
        async with get_async_session() as session:
            stmt = (
                select(DBObjectConfigModel)
                .where(DBObjectConfigModel.datasource_id == datasource_id)
                .where(DBObjectConfigModel.object_type == object_type)
                .where(DBObjectConfigModel.schema_name == schema_name)
                .where(
                    DBObjectConfigModel.table_name == table_name
                    if table_name is not None
                    else DBObjectConfigModel.table_name.is_(None)
                )
                .where(
                    DBObjectConfigModel.column_name == column_name
                    if column_name is not None
                    else DBObjectConfigModel.column_name.is_(None)
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_object_configs(
        self,
        datasource_id: Any,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"] | None = None,
        schema_name: str | None = None,
        table_name: str | None = None,
    ) -> list[DBObjectConfigModel]:
        """列出 DataSource 对象配置"""
        async with get_async_session() as session:
            stmt = select(DBObjectConfigModel).where(
                DBObjectConfigModel.datasource_id == datasource_id
            )
            if object_type is not None:
                stmt = stmt.where(
                    DBObjectConfigModel.object_type == object_type
                )
            if schema_name is not None:
                stmt = stmt.where(
                    DBObjectConfigModel.schema_name == schema_name
                )
            if table_name is not None:
                stmt = stmt.where(
                    DBObjectConfigModel.table_name == table_name
                )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def upsert_object_config(
        self,
        datasource_id: Any,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"],
        schema_name: str,
        table_name: str | None = None,
        column_name: str | None = None,
        access_policy: Literal["allow", "deny"] | None = _UNSET,
        comment_override: str | None = _UNSET,
    ) -> DBObjectConfigModel:
        """创建或更新 DataSource 对象配置

        PATCH 语义：只更新参数中显式传入的字段（包括传入 None）。
        使用哨兵值 _UNSET 来区分"用户没传字段" vs "用户传了 None"。
        """
        async with self._lock:
            async with get_async_session() as session:
                stmt = select(DBObjectConfigModel)
                stmt = _build_object_config_where_clause(
                    stmt,
                    datasource_id=datasource_id,
                    object_type=object_type,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=column_name,
                    model_cls=DBObjectConfigModel,
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    if access_policy is not _UNSET:
                        existing.access_policy = access_policy
                    if comment_override is not _UNSET:
                        existing.comment_override = comment_override
                else:
                    existing = DBObjectConfigModel(
                        datasource_id=datasource_id,
                        object_type=object_type,
                        schema_name=schema_name,
                        table_name=table_name,
                        column_name=column_name,
                        access_policy=access_policy
                        if access_policy is not _UNSET
                        else None,
                        comment_override=comment_override
                        if comment_override is not _UNSET
                        else None,
                    )
                    session.add(existing)

                await session.commit()
                # 重新查询确保获取数据库生成的时间戳
                result = await session.execute(
                    select(DBObjectConfigModel).where(
                        DBObjectConfigModel.id == existing.id
                    )
                )
                existing = result.scalar_one()

            await self.invalidate_cache(datasource_id)
            return existing

    async def delete_object_config(
        self,
        datasource_id: Any,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"],
        schema_name: str,
        table_name: str | None = None,
        column_name: str | None = None,
    ) -> None:
        """删除 DataSource 对象配置"""
        async with self._lock:
            async with get_async_session() as session:
                stmt = delete(DBObjectConfigModel)
                stmt = _build_object_config_where_clause(
                    stmt,
                    datasource_id=datasource_id,
                    object_type=object_type,
                    schema_name=schema_name,
                    table_name=table_name,
                    column_name=column_name,
                    model_cls=DBObjectConfigModel,
                )
                await session.execute(stmt)

            await self.invalidate_cache(datasource_id)

    async def batch_upsert_configs(
        self,
        datasource_id: Any,
        configs: list[dict[str, Any]],
    ) -> list[DBObjectConfigModel]:
        """批量 upsert DataSource 配置（PATCH 语义）

        configs 中包含哪些字段就更新哪些字段，不包含的字段保持不变。
        使用哨兵值 _UNSET 实现 PATCH 语义。
        """
        results = []
        for cfg in configs:
            try:
                kwargs = {
                    "datasource_id": datasource_id,
                    "object_type": cfg["object_type"],
                    "schema_name": cfg["schema_name"],
                    "table_name": cfg.get("table_name"),
                    "column_name": cfg.get("column_name"),
                }
                # 只传递 config dict 中实际包含的字段（值为 None 也要传，表示清除）
                if "access_policy" in cfg:
                    kwargs["access_policy"] = cfg["access_policy"]
                if "comment_override" in cfg:
                    kwargs["comment_override"] = cfg["comment_override"]

                result = await self.upsert_object_config(**kwargs)
                results.append(result)
            except ValueError:
                continue
        return results

    # ============================================================
    # 全局系统对象默认 CRUD
    # ============================================================

    async def get_system_object_default(
        self,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"],
        schema_name: str,
        table_name: str | None = None,
        column_name: str | None = None,
    ) -> DBSystemObjectDefaultModel | None:
        """获取单条系统对象默认配置"""
        async with get_async_session() as session:
            stmt = (
                select(DBSystemObjectDefaultModel)
                .where(DBSystemObjectDefaultModel.object_type == object_type)
                .where(DBSystemObjectDefaultModel.schema_name == schema_name)
                .where(
                    DBSystemObjectDefaultModel.table_name == table_name
                    if table_name is not None
                    else DBSystemObjectDefaultModel.table_name.is_(None)
                )
                .where(
                    DBSystemObjectDefaultModel.column_name == column_name
                    if column_name is not None
                    else DBSystemObjectDefaultModel.column_name.is_(None)
                )
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def list_system_object_defaults(
        self,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"] | None = None,
        schema_name: str | None = None,
    ) -> list[DBSystemObjectDefaultModel]:
        """列出系统对象默认配置"""
        async with get_async_session() as session:
            stmt = select(DBSystemObjectDefaultModel)
            if object_type is not None:
                stmt = stmt.where(
                    DBSystemObjectDefaultModel.object_type == object_type
                )
            if schema_name is not None:
                stmt = stmt.where(
                    DBSystemObjectDefaultModel.schema_name == schema_name
                )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def upsert_system_object_default(
        self,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"],
        schema_name: str,
        table_name: str | None = None,
        column_name: str | None = None,
        comment_override: str = "",
        data_type: str | None = None,
    ) -> DBSystemObjectDefaultModel:
        """创建或更新系统对象默认配置"""
        async with self._lock:
            async with get_async_session() as session:
                stmt = (
                    select(DBSystemObjectDefaultModel)
                    .where(DBSystemObjectDefaultModel.object_type == object_type)
                    .where(DBSystemObjectDefaultModel.schema_name == schema_name)
                    .where(
                        DBSystemObjectDefaultModel.table_name == table_name
                        if table_name is not None
                        else DBSystemObjectDefaultModel.table_name.is_(None)
                    )
                    .where(
                        DBSystemObjectDefaultModel.column_name == column_name
                        if column_name is not None
                        else DBSystemObjectDefaultModel.column_name.is_(None)
                    )
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.comment_override = comment_override
                    if data_type is not None:
                        existing.data_type = data_type
                else:
                    existing = DBSystemObjectDefaultModel(
                        object_type=object_type,
                        schema_name=schema_name,
                        table_name=table_name,
                        column_name=column_name,
                        comment_override=comment_override,
                        data_type=data_type,
                    )
                    session.add(existing)
                await session.commit()
                # 重新查询确保获取数据库生成的时间戳
                result = await session.execute(
                    select(DBSystemObjectDefaultModel).where(
                        DBSystemObjectDefaultModel.id == existing.id
                    )
                )
                existing = result.scalar_one()

            return existing

    async def delete_system_object_default(
        self,
        object_type: Literal["SCHEMA", "TABLE", "VIEW", "COLUMN"],
        schema_name: str,
        table_name: str | None = None,
        column_name: str | None = None,
    ) -> None:
        """删除系统对象默认配置"""
        async with self._lock:
            async with get_async_session() as session:
                stmt = (
                    delete(DBSystemObjectDefaultModel)
                    .where(DBSystemObjectDefaultModel.object_type == object_type)
                    .where(DBSystemObjectDefaultModel.schema_name == schema_name)
                    .where(
                        DBSystemObjectDefaultModel.table_name == table_name
                        if table_name is not None
                        else DBSystemObjectDefaultModel.table_name.is_(None)
                    )
                    .where(
                        DBSystemObjectDefaultModel.column_name == column_name
                        if column_name is not None
                        else DBSystemObjectDefaultModel.column_name.is_(None)
                    )
                )
                await session.execute(stmt)

    # ============================================================
    # 批量查询（Provider 使用）
    # ============================================================

    async def get_metadata_policy(
        self, datasource_id: Any
    ) -> DbMetadataPolicy:
        """一次性拉取指定 DataSource 的所有元数据策略

        返回内存结构供 Provider 过滤使用，含缓存机制。
        缓存按 datasource_id 维度维护。
        """
        now = datetime.now(timezone.utc)

        # 检查缓存（按 datasource_id）
        if datasource_id in self._policy_cache:
            cached_policy, cached_at = self._policy_cache[datasource_id]
            if now - cached_at < self._cache_ttl:
                return cached_policy
            del self._policy_cache[datasource_id]

        policy = DbMetadataPolicy(datasource_id=datasource_id)

        # 1. 加载 DataSource 级别配置
        if datasource_id is not None:
            ds_configs = await self.list_object_configs(datasource_id)
            for cfg in ds_configs:
                rule = ObjectRule(
                    access_policy=cfg.access_policy,
                    comment_override=cfg.comment_override,
                )
                if cfg.object_type == "SCHEMA":
                    policy.ds_schema_rules[cfg.schema_name] = rule
                elif cfg.object_type == "TABLE":
                    policy.ds_table_rules[(cfg.schema_name, cfg.table_name)] = rule
                elif cfg.object_type == "VIEW":
                    policy.ds_view_rules[(cfg.schema_name, cfg.table_name)] = rule
                elif cfg.object_type == "COLUMN":
                    policy.ds_column_rules[
                        (cfg.schema_name, cfg.table_name, cfg.column_name)
                    ] = rule

        # 2. 加载全局系统对象默认配置
        global_configs = await self.list_system_object_defaults()
        for cfg in global_configs:
            rule = ObjectRule(comment_override=cfg.comment_override)
            if cfg.object_type == "SCHEMA":
                policy.global_schema_comments[cfg.schema_name] = rule
            elif cfg.object_type == "TABLE":
                policy.global_table_comments[(cfg.schema_name, cfg.table_name)] = rule
            elif cfg.object_type == "VIEW":
                policy.global_table_comments[(cfg.schema_name, cfg.table_name)] = rule
            elif cfg.object_type == "COLUMN":
                policy.global_column_comments[
                    (cfg.schema_name, cfg.table_name, cfg.column_name)
                ] = rule

        # 写入缓存（按 datasource_id）
        self._policy_cache[datasource_id] = (policy, now)
        return policy

    async def get_metadata_policy_for_token(
        self, token: str
    ) -> DbMetadataPolicy:
        """一次性拉取该 Token 对应 DataSource 的所有元数据策略

        通过 Token 解析 datasource_id 后，复用 `get_metadata_policy` 的缓存逻辑。
        """
        token_config = await self.token_service.get_token(token)
        datasource_id = token_config.default_datasource_id if token_config else None
        return await self.get_metadata_policy(datasource_id)

    # ============================================================
    # 缓存管理
    # ============================================================

    async def invalidate_cache(self, datasource_id: Any) -> None:
        """清除指定数据源的策略缓存"""
        if datasource_id in self._policy_cache:
            del self._policy_cache[datasource_id]
            logger.debug(f"已清除数据源 {datasource_id} 的元数据策略缓存")

    # ============================================================
    # 可见性判断（工具方法，Provider 可直接调用）
    # ============================================================

    @staticmethod
    def is_visible(
        ds_policy: ObjectRule | None = None,
    ) -> bool:
        """判断对象是否可见

        规则：
        1. DataSource 级别：如果设置了 access_policy，直接生效
        2. 未设置则默认可见
        """
        if ds_policy is not None and ds_policy.access_policy is not None:
            return ds_policy.access_policy == "allow"
        return True

    @staticmethod
    def get_comment(
        original_comment: str | None,
        ds_rule: ObjectRule | None = None,
        global_rule: ObjectRule | None = None,
    ) -> str | None:
        """获取 comment（两层继承覆盖）

        优先级：DataSource > 全局默认 > 数据库原始
        """
        for rule in (ds_rule, global_rule):
            if rule is not None and rule.comment_override is not None:
                return rule.comment_override
        return original_comment


# =========================================================
# Factory
# =========================================================
class DbConfigServiceFactory(ServiceFactory):
    """DataSource 级数据库元数据管理服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="db_config_service",
            service_type=DbConfigService,
            description="数据库对象配置服务（CRUD + 缓存 + 策略查询）",
            dependencies=["token_service"],
            priority=15,
        )

    def create(self, settings, token_service, **deps) -> DbConfigService:
        return DbConfigService(token_service, settings)
