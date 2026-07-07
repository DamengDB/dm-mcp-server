"""
Metadata Provider

- Resource：拿“概览聚合”（table/view/schema/database）
- Tool：拿“单项明细”（schema list、object list、describe、comment、indexes、constraints 等）

说明：
1) 业务逻辑（SQL 拼装/聚合/格式化）全部在 Provider 内实现；
2) SQL 执行通过 DataSourceService.execute_query() 统一入口；
3) _register_routes/_register_resources/_register_tools 不放业务逻辑，仅做转发，避免臃肿。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Mapping

from pydantic import Field
from dm_mcp.common import messages
from dm_mcp.core.exceptions import MCPExecutionError
from dm_mcp.domain.mcp.entities import (
    ColumnEntity,
    ConstraintEntity,
    SchemaEntity,
    TableEntity,
)
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.mcp.mappers import metadata_mapper as _mapper
from dm_mcp.domain.mcp.providers.base import BaseDataSourceMCPProvider
from dm_mcp.domain.mcp.providers.sql import metadata_sql as _sql
from dm_mcp.domain.db_metadata.services.db_config import DbConfigService
from dm_mcp.domain.db_metadata.services.db_metadata import DbMetadataService

ObjectType = Literal["TABLE", "VIEW"]


class MetadataMCPProvider(BaseDataSourceMCPProvider):
    """DM8 元数据 Provider（Resource + Tool）"""

    def __init__(
        self,
        datasource_service: DataSourceService,
        db_config_service: DbConfigService | None = None,
        db_metadata_service: DbMetadataService | None = None,
    ) -> None:
        super().__init__(datasource_service)
        self._db_config_service = db_config_service
        self._db_metadata_service = db_metadata_service
        self._register_routes()

    # ============================================================
    # MCP 注入 & 路由注册
    # ============================================================

    def _register_routes(self) -> None:
        """注册 MCP 路由"""
        self._register_resources()
        self._register_tools()

    def _register_resources(self) -> None:
        """注册 MCP Resource 路由（概览聚合）"""

        # 表概览：dm://table/{schema}/{table}
        @self.mcp.resource(
            "dm://table/{schema}/{table}",
            name="get_table_metadata",
            group="meta",
        )
        async def get_table(
            schema: Annotated[str, Field(description="表所属 schema 名称（如 SYSDBA）")],
            table: Annotated[str, Field(description="表名")],
        ):
            """
            返回表 schema.table 的列、索引、所有者等元数据（不含完整 DDL）。
            快速了解表结构、为后续 describe/索引/约束 工具调用做前置筛选。
            """
            return await self._res_get_table(schema=schema, table=table)

        # 模式概览：dm://schema/{schema}
        @self.mcp.resource(
            "dm://schema/{schema}",
            name="get_objects_in_schema",
            group="meta",
        )
        async def get_schema(
            schema: Annotated[str, Field(description="目标 schema 名称（如 SYSDBA）")],
        ):
            """
            返回 schema 下的所有表名、视图名列表（含 comment 摘要）。
            浏览库结构、筛选要查看的表/视图、为 get_table/get_view 提供候选。
            """
            return await self._res_get_schema(schema=schema)

        # 视图概览：dm://view/{schema}/{view}
        @self.mcp.resource(
            "dm://view/{schema}/{view}",
            name="get_view_metadata",
            group="meta",
        )
        async def get_view(
            schema: Annotated[str, Field(description="视图所属 schema 名称")],
            view: Annotated[str, Field(description="视图名")],
        ):
            """
            返回视图 schema.view 的列信息、定义摘要、comment（不含完整 DDL）。
            快速了解视图结构；需完整定义时调用 get_view_definition 工具。
            """
            return await self._res_get_view(schema=schema, view=view)

        # 数据库概览（可选）：dm://database/{db}
        @self.mcp.resource(
            "dm://database/{db}",
            name="get_metadata_statistics",
            group="meta",
        )
        async def get_database(
            db: Annotated[str, Field(description="数据库/实例标识（用于结果回显，如实例名）")],
        ):
            """
            返回数据库级统计：schema 数量、全库表数量、全库视图数量。
            多实例/多库比对、了解实例规模、为后续 schema 级查询做入口。
            """
            return await self._res_get_database(db=db)

    def _register_tools(self) -> None:
        """注册 MCP Tool 路由（单项明细）"""

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_db_schemas_list():
            """
            列出当前实例下所有可访问的 schema（模式）名称。
            不知道有哪些 schema 时，先调用此工具获取列表，再选 schema 做后续查询。
            """
            return await self._tool_get_db_schemas_list()

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_db_objects_list(
            schema: Annotated[str | None, Field(description="目标 schema 名称；None 表示全库")] = None,
            object_type: Annotated[ObjectType | None, Field(description="过滤类型：TABLE 只返回表，VIEW 只返回视图，None 返回全部")] = None,
            include_comments: Annotated[bool, Field(description="True 时返回对象含 comment 字段")] = False,
        ):
            """
            列出 schema 下的表/视图名列表，可按类型过滤。
            已知 schema 时获取表/视图列表；object_type 为 TABLE 或 VIEW 时只返回对应类型。
            """
            return await self._tool_get_db_objects_list(
                schema=schema,
                object_type=object_type,
                include_comments=include_comments,
            )

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_table_describe(
            schema: Annotated[str | None, Field(description="表所属 schema 名称（必填）")] = None,
            table: Annotated[str, Field(description="表名（必填）")] = "",
        ):
            """
            返回表的完整列结构（列名、类型、可空性、默认值）及主键/外键/唯一/检查约束。
            写 SQL 前需了解列结构；生成表结构说明；schema 和 table 必填。
            """
            return await self._tool_get_table_describe(
                schema=schema,
                table=table,
            )

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_view_describe(
            schema: Annotated[str | None, Field(description="视图所属 schema 名称（必填）")] = None,
            view: Annotated[str, Field(description="视图名（必填）")] = "",
            view_comment: Annotated[str | None, Field(description="若已从 resource 或 comment 工具获取，可透传避免重复查询")] = None,
        ):
            """
            返回视图的列结构（列名、类型、可空性），不含完整 DDL。
            写 SQL 前需了解视图列；需完整定义时用 get_view_definition。
            """
            return await self._tool_get_view_describe(
                schema=schema,
                view=view,
                view_comment=view_comment,
            )

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_view_definition(
            schema: Annotated[str | None, Field(description="视图所属 schema 名称（必填）")] = None,
            view: Annotated[str, Field(description="视图名（必填）")] = "",
            view_comment: Annotated[str | None, Field(description="若已获取，可透传避免重复查询")] = None,
        ):
            """
            返回视图的完整 CREATE VIEW DDL 文本。
            需要视图的完整定义或依赖关系；schema 和 view 必填。
            """
            return await self._tool_get_view_definition(
                schema=schema,
                view=view,
                view_comment=view_comment,
            )

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_table_columns_list(
            schema: Annotated[str | None, Field(description="表所属 schema 名称（必填）")] = None,
            table: Annotated[str, Field(description="表名（必填）")] = "",
        ):
            """
            返回表的列名及注释字典。
            快速了解列构成时使用；需完整结构用 get_table_describe。
            """
            return await self._tool_get_table_columns_list(
                schema=schema,
                table=table,
            )

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_table_indexes_list(
            schema: Annotated[str | None, Field(description="表所属 schema 名称（必填）")] = None,
            table: Annotated[str, Field(description="表名（必填）")] = "",
        ):
            """
            返回表的索引列表（索引名、包含列、是否唯一、类型）。
            分析查询性能、优化索引、了解表约束。
            """
            return await self._tool_get_table_indexes_list(
                schema=schema,
                table=table,
            )

        @self.mcp.tool(group="meta", requires_token_auth=True)
        async def get_table_constraints_list(
            schema: Annotated[str | None, Field(description="表所属 schema 名称（必填）")] = None,
            table: Annotated[str, Field(description="表名（必填）")] = "",
        ):
            """
            返回表的约束列表（主键、外键、唯一、检查、非空等）。
            了解表约束、写 INSERT/UPDATE 前校验、分析外键关系。
            """
            return await self._tool_get_table_constraints_list(
                schema=schema,
                table=table,
            )

    def _normalize_schema(self, schema: str | None) -> str | None:
        if schema is None:
            return None
        s = schema.strip()
        return s if s else None

    # ============================================================
    # 元数据策略（DataSource 级过滤 + comment 覆盖）
    # ============================================================

    def _get_current_token(self) -> str | None:
        """从 MCP 上下文中获取当前 Token"""
        ctx = self.context
        if ctx.auth is None:
            return None
        return ctx.auth.token

    async def _get_policy(self):
        """获取当前 Token 的元数据策略（含缓存）"""
        if self._db_config_service is None:
            return None
        token = self._get_current_token()
        if token is None:
            return None
        return await self._db_config_service.get_metadata_policy_for_token(token)

    def _is_schema_visible(self, policy, schema_name: str) -> bool:
        """判断 schema 是否可见（DS 级 access_policy）"""
        if policy is None:
            return True
        ds_rule = policy.ds_schema_rules.get(schema_name)
        return self._db_config_service.is_visible(ds_rule)

    def _is_table_visible(self, policy, schema_name: str, table_name: str) -> bool:
        """判断 table 是否可见

        细粒度优先（同层级内）：table > schema
        """
        if policy is None:
            return True
        ds_table = policy.ds_table_rules.get((schema_name, table_name))
        ds_schema = policy.ds_schema_rules.get(schema_name)
        ds_policy = ds_table or ds_schema
        return self._db_config_service.is_visible(ds_policy)

    def _is_column_visible(
        self, policy, schema_name: str, table_name: str, column_name: str
    ) -> bool:
        """判断 column 是否可见

        细粒度优先（同层级内）：column > table > schema
        """
        if policy is None:
            return True
        ds_col = policy.ds_column_rules.get((schema_name, table_name, column_name))
        ds_table = policy.ds_table_rules.get((schema_name, table_name))
        ds_schema = policy.ds_schema_rules.get(schema_name)
        ds_policy = ds_col or ds_table or ds_schema
        return self._db_config_service.is_visible(ds_policy)

    def _get_schema_comment(
        self, policy, schema_name: str, original: str | None
    ) -> str | None:
        """获取 schema comment（DS > 全局默认 > 数据库原始）"""
        if policy is None or self._db_config_service is None:
            return original
        ds_rule = policy.ds_schema_rules.get(schema_name)
        global_rule = policy.global_schema_comments.get(schema_name)
        return self._db_config_service.get_comment(
            original, ds_rule, global_rule
        )

    def _get_table_comment(
        self, policy, schema_name: str, table_name: str, original: str | None
    ) -> str | None:
        """获取 table comment（DS > 全局默认 > 数据库原始）"""
        if policy is None or self._db_config_service is None:
            return original
        ds_rule = policy.ds_table_rules.get((schema_name, table_name))
        global_rule = policy.global_table_comments.get((schema_name, table_name))
        return self._db_config_service.get_comment(
            original, ds_rule, global_rule
        )

    def _get_column_comment(
        self,
        policy,
        schema_name: str,
        table_name: str,
        column_name: str,
        original: str | None,
    ) -> str | None:
        """获取 column comment（DS > 全局默认 > 数据库原始）"""
        if policy is None or self._db_config_service is None:
            return original
        ds_rule = policy.ds_column_rules.get((schema_name, table_name, column_name))
        global_rule = policy.global_column_comments.get(
            (schema_name, table_name, column_name)
        )
        return self._db_config_service.get_comment(
            original, ds_rule, global_rule
        )

    # ============================================================
    # Resources：概览聚合
    # ============================================================

    async def _res_get_table(self, schema: str, table: str) -> dict[str, Any]:
        schema = schema.strip()
        table = table.strip()

        policy = await self._get_policy()

        # schema 或 table 不可见时抛出异常
        if not self._is_schema_visible(policy, schema):
            raise MCPExecutionError("SCHEMA_NOT_ACCESSIBLE", f"Schema '{schema}' 不可访问")
        if not self._is_table_visible(policy, schema, table):
            raise MCPExecutionError("TABLE_NOT_ACCESSIBLE", f"Table '{schema}.{table}' 不可访问")

        table_info = await self._query_table_info(
            schema=schema, table=table
        )
        columns = await self._query_table_columns(
            schema=schema, table=table, limit=60
        )
        indexes = await self._query_table_indexes(
            schema=schema, table=table, limit=30
        )

        # 过滤不可见列 + 覆盖 comment
        visible_columns = []
        for c in columns:
            if self._is_column_visible(policy, schema, table, c.column_name):
                c.comment = self._get_column_comment(
                    policy, schema, table, c.column_name, c.comment
                )
                visible_columns.append(_mapper.dump_column(c))

        return _mapper.table_resource(
            schema, table, table_info, visible_columns, indexes
        )

    async def _res_get_schema(self, schema: str) -> dict[str, Any]:
        schema = schema.strip()

        policy = await self._get_policy()

        # 如果 schema 不可见，抛出异常
        if not self._is_schema_visible(policy, schema):
            raise MCPExecutionError("SCHEMA_NOT_ACCESSIBLE", f"Schema '{schema}' 不可访问")

        tables = await self._query_tables(
            schema=schema, include_comments=True, limit=200
        )
        views = await self._query_views(
            schema=schema, include_comments=True, limit=200
        )
        schema_info = await self._query_schema_info(schema=schema)

        # 过滤不可见的表/视图 + 覆盖 comment
        visible_tables = []
        for t in tables:
            if self._is_table_visible(policy, schema, t.table_name):
                t.comment = self._get_table_comment(
                    policy, schema, t.table_name, t.comment
                )
                visible_tables.append(t.model_dump(exclude_none=True))

        visible_views = []
        for v in views:
            if self._is_table_visible(policy, schema, v.table_name):
                v.comment = self._get_table_comment(
                    policy, schema, v.table_name, v.comment
                )
                visible_views.append(v.model_dump(exclude_none=True))

        return _mapper.schema_resource(
            schema, schema_info, visible_tables, visible_views
        )

    async def _res_get_view(self, schema: str, view: str) -> dict[str, Any]:
        schema = schema.strip()
        view = view.strip()

        policy = await self._get_policy()

        # schema 或 view 不可见时抛出异常
        if not self._is_schema_visible(policy, schema):
            raise MCPExecutionError("SCHEMA_NOT_ACCESSIBLE", f"Schema '{schema}' 不可访问")
        if not self._is_table_visible(policy, schema, view):
            raise MCPExecutionError("VIEW_NOT_ACCESSIBLE", f"View '{schema}.{view}' 不可访问")

        view_info = await self._query_view_info(schema=schema, view=view)
        columns = await self._query_view_columns(
            schema=schema, view=view, limit=60
        )

        # 过滤不可见列 + 覆盖 comment
        visible_columns = []
        for c in columns:
            if self._is_column_visible(policy, schema, view, c.column_name):
                c.comment = self._get_column_comment(
                    policy, schema, view, c.column_name, c.comment
                )
                visible_columns.append(_mapper.dump_column(c))

        # definition 可能很长，resource 只给摘要
        definition = (
            (view_info.get("DEFINITION") or "") if isinstance(view_info, dict) else ""
        )
        definition_preview = _mapper.truncate_definition(definition)

        cleaned_view_info = (
            {k: v for k, v in view_info.items() if k != "DEFINITION"}
            if isinstance(view_info, dict)
            else {}
        )

        return _mapper.view_resource(
            schema, view, cleaned_view_info, definition_preview, visible_columns
        )

    async def _res_get_database(self, db: str) -> dict[str, Any]:
        # DM8 一般一个实例下多 schema，这里做对象数量统计摘要
        db = db.strip()

        schemas = await self._tool_get_db_schemas_list()
        schema_count = len(schemas)

        # 粗略统计：全库 tables/views 数
        tables = await self._query_tables(
            schema=None, include_comments=False, limit=2000
        )
        views = await self._query_views(
            schema=None, include_comments=False, limit=2000
        )

        return _mapper.database_resource(
            db, schema_count, len(tables), len(views)
        )

    # ============================================================
    # Tools：单项明细（tools.md 1.2）
    # ============================================================

    async def _tool_get_db_schemas_list(self) -> dict[str, str]:
        source = await self._get_current_datasource_name()
        token = self._get_current_token()
        items = await self._db_metadata_service.list_schemas(source, token=token)
        return {item.name: item.comment for item in items}

    async def _tool_get_db_objects_list(
        self,
        schema: str | None,
        object_type: ObjectType | None,
        include_comments: bool,
    ) -> dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        object_type = object_type.upper() if object_type else None  # type: ignore[assignment]
        token = self._get_current_token()

        if object_type == "TABLE":
            items = await self._db_metadata_service.list_tables(
                source, schema, token=token
            )
            return {item.name: item.comment for item in items}

        if object_type == "VIEW":
            items = await self._db_metadata_service.list_views(
                source, schema, token=token
            )
            return {item.name: item.comment for item in items}

        # None：返回 {"TABLE": {...}, "VIEW": {...}}
        tables = await self._db_metadata_service.list_tables(
            source, schema, token=token
        )
        views = await self._db_metadata_service.list_views(source, schema, token=token)
        return {
            "TABLE": {item.name: item.comment for item in tables},
            "VIEW": {item.name: item.comment for item in views},
        }

    async def _tool_get_table_describe(
        self,
        schema: str | None,
        table: str,
    ) -> dict[str, Any]:
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="table"))

        policy = await self._get_policy()

        # schema 或 table 不可见
        if not self._is_schema_visible(policy, schema):
            raise MCPExecutionError("SCHEMA_NOT_ACCESSIBLE", f"Schema '{schema}' 对当前 Token 不可访问")
        if not self._is_table_visible(policy, schema, table):
            raise MCPExecutionError("TABLE_NOT_ACCESSIBLE", f"Table '{schema}.{table}' 对当前 Token 不可访问")

        cols = await self._query_table_columns(
            schema=schema, table=table
        )

        # 约束（含主键等）
        constraints = await self._query_table_constraints(
            schema=schema, table=table
        )

        # 表级 comment
        table_info = await self._query_table_info(
            schema=schema, table=table
        )
        table_comment = self._get_table_comment(
            policy, schema, table, table_info.get("COMMENT")
        )

        # 过滤不可见列 + 覆盖 comment，去掉冗余字段
        visible_cols = []
        for c in cols:
            if self._is_column_visible(policy, schema, table, c.column_name):
                c.comment = self._get_column_comment(
                    policy, schema, table, c.column_name, c.comment
                )
                visible_cols.append(
                    _mapper.dump_column(
                        c, exclude={"schema_name", "table_name", "column_id"}
                    )
                )

        return _mapper.table_describe(
            schema, table, table_comment, visible_cols, constraints
        )

    async def _tool_get_view_describe(
        self,
        schema: str | None,
        view: str,
        view_comment: str | None,
    ) -> dict[str, Any]:
        schema = self._normalize_schema(schema)
        if not view:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="view"))

        policy = await self._get_policy()

        # schema 或 view 不可见
        if not self._is_schema_visible(policy, schema):
            raise MCPExecutionError("SCHEMA_NOT_ACCESSIBLE", f"Schema '{schema}' 对当前 Token 不可访问")
        if not self._is_table_visible(policy, schema, view):
            raise MCPExecutionError("VIEW_NOT_ACCESSIBLE", f"View '{schema}.{view}' 对当前 Token 不可访问")

        view_info = await self._query_view_info(schema=schema, view=view)
        cols = await self._query_view_columns(schema=schema, view=view)
        if view_comment is not None:
            view_info["COMMENT"] = view_comment
        else:
            view_info["COMMENT"] = self._get_table_comment(
                policy, schema, view, view_info.get("COMMENT")
            )

        # 过滤不可见列 + 覆盖 comment
        visible_cols = []
        for c in cols:
            if self._is_column_visible(policy, schema, view, c.column_name):
                c.comment = self._get_column_comment(
                    policy, schema, view, c.column_name, c.comment
                )
                visible_cols.append(_mapper.dump_column(c))

        return _mapper.view_describe(schema, view, view_info, visible_cols)

    async def _tool_get_view_definition(
        self,
        schema: str | None,
        view: str,
        view_comment: str | None,
    ) -> dict[str, Any]:
        schema = self._normalize_schema(schema)
        if not view:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="view"))

        policy = await self._get_policy()

        # schema 或 view 不可见
        if not self._is_schema_visible(policy, schema):
            raise MCPExecutionError("SCHEMA_NOT_ACCESSIBLE", f"Schema '{schema}' 对当前 Token 不可访问")
        if not self._is_table_visible(policy, schema, view):
            raise MCPExecutionError("VIEW_NOT_ACCESSIBLE", f"View '{schema}.{view}' 对当前 Token 不可访问")

        view_info = await self._query_view_info(schema=schema, view=view)
        if view_comment is not None:
            view_info["COMMENT"] = view_comment
        else:
            view_info["COMMENT"] = self._get_table_comment(
                policy, schema, view, view_info.get("COMMENT")
            )

        return _mapper.view_definition(
            schema, view, view_info.get("COMMENT"), view_info.get("DEFINITION")
        )

    async def _tool_get_table_columns_list(
        self,
        schema: str | None,
        table: str,
    ) -> dict[str, str]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="table"))

        token = self._get_current_token()
        items = await self._db_metadata_service.list_columns(
            source, schema, table, token=token
        )
        return {item.name: item.comment for item in items}

    async def _tool_get_table_indexes_list(
        self,
        schema: str | None,
        table: str,
    ) -> list[dict[str, Any]]:
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="table"))

        rows = await self._query_table_indexes(
            schema=schema, table=table, limit=2000
        )

        return _mapper.table_indexes_list(rows)

    async def _tool_get_table_constraints_list(
        self,
        schema: str | None,
        table: str,
    ) -> list[dict[str, Any]]:
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="table"))

        constraints = await self._query_table_constraints(
            schema=schema, table=table, limit=2000
        )
        return _mapper.table_constraints_list(constraints)

    # ============================================================
    # SQL：DM8 系统目录查询（Provider 内实现）
    # ============================================================

    async def _query_schemas(self) -> list[SchemaEntity]:
        rows = await self._exec(sql=_sql.list_schemas())
        return _mapper.parse_schemas(rows)

    async def _query_schema_info(self, schema: str) -> dict[str, Any]:
        rows = await self._exec(sql=_sql.get_schema_info(), params=[schema])
        return _mapper.parse_schema_info(rows)

    async def _query_tables(
        self,
        schema: str | None,
        include_comments: bool,
        limit: int,
    ) -> list[TableEntity]:
        # bug 131935 ：include_comments=True 时关联 SYSTABLECOMMENTS，使 get_db_objects_list 返回 COMMENT
        sql, params = _sql.list_tables(include_comments=include_comments, schema=schema)
        rows = await self._exec(sql=sql, params=params, max_rows=limit)
        return _mapper.parse_tables(rows, include_comments)

    async def _query_table_info(
        self,
        schema: str | None,
        table: str,
    ) -> dict[str, Any]:
        # schema 为空时：尝试按当前 schema/或全库匹配（这里先要求 schema 明确更安全）
        if not schema:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="schema"))

        rows = await self._exec(
            sql=_sql.get_table_info(), params=[schema, table], max_rows=1
        )
        return _mapper.parse_table_info(rows)

    async def _query_table_columns(
        self,
        schema: str | None,
        table: str,
        limit: int = 10000,
    ) -> list[ColumnEntity]:
        if not schema:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="schema"))

        rows = await self._exec(
            sql=_sql.get_table_columns(), params=[schema, table], max_rows=limit
        )
        return _mapper.parse_table_columns(rows)

    async def _query_views(
        self,
        schema: str | None,
        include_comments: bool,
        limit: int,
    ) -> list[TableEntity]:
        # bug 131935 ：include_comments=True 时关联 SYSTABLECOMMENTS，使 get_db_objects_list 返回 COMMENT
        sql, params = _sql.list_views(include_comments=include_comments, schema=schema)
        rows = await self._exec(sql=sql, params=params, max_rows=limit)
        return _mapper.parse_views(rows, include_comments)

    async def _query_view_info(
        self,
        schema: str | None,
        view: str,
    ) -> dict[str, Any]:
        if not schema:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="schema"))

        basic_rows = await self._exec(
            sql=_sql.get_view_info(), params=[schema, view], max_rows=1
        )
        def_rows = await self._exec(
            sql=_sql.get_view_definition(), params=[schema, view], max_rows=1
        )
        return _mapper.parse_view_info(basic_rows, def_rows)

    async def _query_view_columns(
        self,
        schema: str | None,
        view: str,
        limit: int = 10000,
    ) -> list[ColumnEntity]:
        if not schema:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="schema"))

        rows = await self._exec(
            sql=_sql.get_view_columns(), params=[schema, view], max_rows=limit
        )
        return _mapper.parse_view_columns(rows)

    async def _query_table_indexes(
        self,
        schema: str | None,
        table: str,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        if not schema:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="schema"))

        rows = await self._exec(
            sql=_sql.get_table_indexes(), params=[schema, table], max_rows=limit
        )
        return _mapper.parse_table_indexes(rows)[:limit]

    async def _query_table_constraints(
        self,
        schema: str | None,
        table: str,
        limit: int = 10000,
    ) -> list[ConstraintEntity]:
        if not schema:
            raise ValueError(messages.MSG_PARAM_REQUIRED.format(param="schema"))

        constraint_rows = await self._exec(
            sql=_sql.get_table_constraints(), params=[schema, table], max_rows=limit
        )
        nn_rows = await self._exec(
            sql=_sql.get_not_null_constraints(), params=[schema, table], max_rows=limit
        )
        return _mapper.parse_table_constraints(constraint_rows, nn_rows, limit)
