"""数据库元数据服务

统一查询数据库对象元数据 + DS 级 / 系统默认级 db-config，
对外暴露查询模式（过滤 + 合并）和概览模式（合并后结果）。
"""

import asyncio
import logging
import re
from typing import Any, Literal

from pydantic import BaseModel

from dm_mcp.common import messages
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.core.service import BaseService
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.db_metadata.services.db_config import DbConfigService
from dm_mcp.domain.db_metadata.services.sql import db_metadata_sql as _sql

logger = logging.getLogger(__name__)

_DM_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_#$]*$")


# ============================================================
# 元数据概览数据结构（Controller 用，返回合并后结果）
# ============================================================


class SchemaOverview(BaseModel):
    name: str
    comment: str = ""
    access_policy: str | None = None


class TableOverview(BaseModel):
    name: str
    comment: str = ""
    access_policy: str | None = None


class ViewOverview(BaseModel):
    name: str
    comment: str = ""
    access_policy: str | None = None


class ColumnOverview(BaseModel):
    name: str
    comment: str = ""
    access_policy: str | None = None


# ============================================================
# 查询模式数据结构（Provider 用，过滤后只返回 name + 合并 comment）
# ============================================================


class SchemaItem(BaseModel):
    name: str
    comment: str = ""


class TableItem(BaseModel):
    name: str
    comment: str = ""


class ViewItem(BaseModel):
    name: str
    comment: str = ""


class ColumnItem(BaseModel):
    name: str
    comment: str = ""


# ============================================================
# DbMetadataService
# ============================================================


class DbMetadataService(BaseService):
    """数据库元数据服务

    统一查询数据库对象元数据 + DS 级配置，对外暴露两种模式：
    - 概览模式（list_*_overview）：不过滤，返回合并后结果（Controller 用）
    - 查询模式（list_*）：过滤 deny 对象，返回合并 comment（Provider 用）
    """

    def __init__(
        self,
        datasource_service: DataSourceService,
        db_config_service: DbConfigService,
    ) -> None:
        self._ds = datasource_service
        self._db_config = db_config_service
        self._query_locks: dict[str, asyncio.Lock] = {}  # 每个数据源的查询锁

    # ============================================================
    # 辅助方法
    # ============================================================

    @staticmethod
    def _is_valid_identifier(name: str) -> bool:
        """校验名称是否为合法的 DM 标识符（防止 SQL 注入）"""
        return bool(_DM_IDENTIFIER_RE.match(name))

    async def _get_pool(self, name: str):
        """获取指定数据源的连接池"""
        return await self._ds.get_pool(name)

    async def _execute_query(
        self, pool, sql: str, params: tuple | None = None
    ) -> list[dict[str, Any]]:
        """通过连接池执行查询并返回字典列表"""
        logger.debug(f"准备执行查询，池对象: {id(pool)}, size={getattr(pool, 'size', 'N/A')}")
        async with pool.acquire() as conn:
            logger.debug(f"获取连接成功，连接对象: {id(conn)}")
            cur = await conn.cursor()
            try:
                if params:
                    await cur.execute(sql, params)
                else:
                    await cur.execute(sql)

                description = getattr(cur, "description", None)
                if not description:
                    return []

                rows = await cur.fetchall()
                col_names = [desc[0].lower() for desc in description]
                return [
                    {col_names[i]: row[i] for i in range(len(col_names))}
                    for row in rows
                ]
            finally:
                try:
                    cur.close()
                except Exception:
                    pass

    async def _get_ds_lock(self, datasource_name: str) -> asyncio.Lock:
        """获取指定数据源的查询锁（防止同一数据源的并行元数据查询）"""
        if datasource_name not in self._query_locks:
            self._query_locks[datasource_name] = asyncio.Lock()
        return self._query_locks[datasource_name]

    # ============================================================
    # 概览模式：不过滤，返回合并后结果（Controller 用）
    # ============================================================

    async def list_schemas_overview(
        self, datasource_name: str
    ) -> list[SchemaOverview]:
        """获取模式列表（合并后结果）"""
        lock = await self._get_ds_lock(datasource_name)
        async with lock:
            pool = await self._get_pool(datasource_name)
            ds = await self._ds.get_datasource(datasource_name)

            rows = await self._execute_query(pool, _sql.list_schemas())

        policy = await self._db_config.get_metadata_policy(
            ds.id if ds else None
        )

        result: list[SchemaOverview] = []
        for row in rows:
            name = row["schema_name"]
            ds_rule = policy.ds_schema_rules.get(name)
            global_rule = policy.global_schema_comments.get(name)
            comment = DbConfigService.get_comment("", ds_rule, global_rule) or ""
            access_policy = ds_rule.access_policy if ds_rule else None
            result.append(
                SchemaOverview(
                    name=name,
                    comment=comment,
                    access_policy=access_policy,
                )
            )
        return result

    async def list_tables_overview(
        self, datasource_name: str, schema: str
    ) -> list[TableOverview]:
        """获取表列表（合并后结果）"""
        if not self._is_valid_identifier(schema):
            raise ValueError(messages.MSG_DB_ILLEGAL_SCHEMA_NAME.format(schema=schema))

        ds = await self._ds.get_datasource(datasource_name)
        policy = await self._db_config.get_metadata_policy(
            ds.id if ds else None
        )

        # schema 级 deny 时直接返回空列表
        schema_rule = policy.ds_schema_rules.get(schema)
        if schema_rule and schema_rule.access_policy == "deny":
            return []

        lock = await self._get_ds_lock(datasource_name)
        async with lock:
            pool = await self._get_pool(datasource_name)

            rows = await self._execute_query(
                pool, _sql.list_tables(), (schema, schema)
            )

        result: list[TableOverview] = []
        for row in rows:
            name = row["table_name"]
            db_comment = row.get("comment") or ""
            ds_rule = policy.ds_table_rules.get((schema, name))
            global_rule = policy.global_table_comments.get((schema, name))
            comment = (
                DbConfigService.get_comment(db_comment, ds_rule, global_rule)
                or ""
            )
            # policy: 表级 > schema 级（向上继承）
            access_policy = ds_rule.access_policy if ds_rule else None
            if access_policy is None:
                access_policy = schema_rule.access_policy if schema_rule else None
            result.append(
                TableOverview(
                    name=name,
                    comment=comment,
                    access_policy=access_policy,
                )
            )
        return result

    async def list_views_overview(
        self, datasource_name: str, schema: str
    ) -> list[ViewOverview]:
        """获取视图列表（合并后结果）"""
        if not self._is_valid_identifier(schema):
            raise ValueError(messages.MSG_DB_ILLEGAL_SCHEMA_NAME.format(schema=schema))

        ds = await self._ds.get_datasource(datasource_name)
        policy = await self._db_config.get_metadata_policy(
            ds.id if ds else None
        )

        # schema 级 deny 时直接返回空列表
        schema_rule = policy.ds_schema_rules.get(schema)
        if schema_rule and schema_rule.access_policy == "deny":
            return []

        lock = await self._get_ds_lock(datasource_name)
        async with lock:
            pool = await self._get_pool(datasource_name)

            sql, params = _sql.list_views(schema)
            rows = await self._execute_query(pool, sql, params)

        result: list[ViewOverview] = []
        for row in rows:
            name = row["view_name"]
            db_comment = row.get("comment") or ""
            ds_rule = policy.ds_view_rules.get((schema, name))
            global_rule = policy.global_table_comments.get((schema, name))
            comment = (
                DbConfigService.get_comment(db_comment, ds_rule, global_rule)
                or ""
            )
            # policy: 视图级 > schema 级（向上继承）
            access_policy = ds_rule.access_policy if ds_rule else None
            if access_policy is None:
                access_policy = schema_rule.access_policy if schema_rule else None
            result.append(
                ViewOverview(
                    name=name,
                    comment=comment,
                    access_policy=access_policy,
                )
            )
        return result

    async def list_columns_overview(
        self,
        datasource_name: str,
        schema: str,
        table: str,
    ) -> list[ColumnOverview]:
        """获取列列表（合并后结果）"""
        if not self._is_valid_identifier(schema):
            raise ValueError(messages.MSG_DB_ILLEGAL_SCHEMA_NAME.format(schema=schema))
        if not self._is_valid_identifier(table):
            raise ValueError(messages.MSG_DB_ILLEGAL_TABLE_NAME.format(table=table))

        ds = await self._ds.get_datasource(datasource_name)
        policy = await self._db_config.get_metadata_policy(
            ds.id if ds else None
        )

        # schema 级 deny 时直接返回空列表
        schema_rule = policy.ds_schema_rules.get(schema)
        if schema_rule and schema_rule.access_policy == "deny":
            return []

        pool = await self._get_pool(datasource_name)

        rows = await self._execute_query(
            pool, _sql.list_columns(), (schema, table)
        )

        result: list[ColumnOverview] = []
        for row in rows:
            name = row["column_name"]
            db_comment = row.get("comment") or ""
            ds_rule = policy.ds_column_rules.get((schema, table, name))
            global_rule = policy.global_column_comments.get(
                (schema, table, name)
            )
            comment = (
                DbConfigService.get_comment(db_comment, ds_rule, global_rule)
                or ""
            )
            # policy: 列级 → 表级 → schema 级（向上继承）
            access_policy = ds_rule.access_policy if ds_rule else None
            if access_policy is None:
                table_rule = policy.ds_table_rules.get((schema, table))
                access_policy = table_rule.access_policy if table_rule else None
            if access_policy is None:
                access_policy = schema_rule.access_policy if schema_rule else None
            result.append(
                ColumnOverview(
                    name=name,
                    comment=comment,
                    access_policy=access_policy,
                )
            )
        return result

    # ============================================================
    # 查询模式：过滤 deny 对象，返回合并 comment（Provider 用）
    # ============================================================

    async def list_schemas(
        self, datasource_name: str, token: str | None = None  # noqa: ARG002
    ) -> list[SchemaItem]:
        """获取模式列表（过滤 deny，合并 comment）"""
        overview = await self.list_schemas_overview(datasource_name)
        return [
            SchemaItem(name=o.name, comment=o.comment)
            for o in overview
            if o.access_policy != "deny"
        ]

    async def list_tables(
        self, datasource_name: str, schema: str, token: str | None = None  # noqa: ARG002
    ) -> list[TableItem]:
        """获取表列表（过滤 deny，合并 comment）"""
        overview = await self.list_tables_overview(datasource_name, schema)
        return [
            TableItem(name=o.name, comment=o.comment)
            for o in overview
            if o.access_policy != "deny"
        ]

    async def list_views(
        self,
        datasource_name: str,
        schema: str,
        token: str | None = None,  # noqa: ARG002
    ) -> list[ViewItem]:
        """获取视图列表（过滤 deny，合并 comment）"""
        overview = await self.list_views_overview(datasource_name, schema)
        return [
            ViewItem(name=o.name, comment=o.comment)
            for o in overview
            if o.access_policy != "deny"
        ]

    async def list_columns(
        self,
        datasource_name: str,
        schema: str,
        table: str,
        token: str | None = None,  # noqa: ARG002
    ) -> list[ColumnItem]:
        """获取列列表（过滤 deny，合并 comment）"""
        overview = await self.list_columns_overview(datasource_name, schema, table)
        return [
            ColumnItem(name=o.name, comment=o.comment)
            for o in overview
            if o.access_policy != "deny"
        ]


# =========================================================
# Factory
# =========================================================
class DbMetadataServiceFactory(ServiceFactory):
    """数据库元数据服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="db_metadata_service",
            service_type=DbMetadataService,
            description="数据库元数据服务（元数据查询 + DS 级配置合并）",
            dependencies=[
                "datasource_service",
                "db_config_service",
            ],
            priority=25,
        )

    def create(
        self,
        settings,
        datasource_service,
        db_config_service,
        **deps,
    ) -> DbMetadataService:
        return DbMetadataService(
            datasource_service=datasource_service,
            db_config_service=db_config_service,
        )
