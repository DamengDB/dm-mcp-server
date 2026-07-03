"""
Metadata Provider

- Resource：拿“概览聚合”（table/view/schema/database）
- Tool：拿“单项明细”（schema list、object list、describe、comment、indexes、constraints 等）

说明：
1) 业务逻辑（SQL 拼装/聚合/格式化）全部在 Provider 内实现；
2) AsyncPoolService 仅作为通用执行器（execute_query）与连接池管理；
3) _register_routes/_register_resources/_register_tools 不放业务逻辑，仅做转发，避免臃肿。
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Mapping, Optional, cast

from dm_mcp.providers.base_datasource_provider import BaseDataSourceMCPProvider
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.services.datasource_service import DataSourceService

ObjectType = Literal["TABLE", "VIEW"]


class MetadataMCPProvider(BaseDataSourceMCPProvider):
    """DM8 元数据 Provider（Resource + Tool）"""

    def __init__(
        self, datasource_service: DataSourceService, pool_service: AsyncPoolService
    ) -> None:
        super().__init__(datasource_service)
        self._pool_service = pool_service
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
            "dm://table/{schema}/{table}", name="表 {schema}.{table} 的列、索引与元数据"
        )
        async def get_table(schema: str, table: str):
            """
            返回表 schema.table 的列、索引、所有者等元数据（不含完整 DDL）。
            适用场景：快速了解表结构、为后续 describe/索引/约束 工具调用做前置筛选。

            Args:
                schema: 表所属 schema 名称（如 SYSDBA）。
                table: 表名。

            Returns:
                Dict[str, Any]: 含 schema, table, table_info（所有者/创建时间）,
                    columns_preview（列名/类型/可空性）, indexes_preview（索引名/列/唯一性）。
            """
            return await self._res_get_table(schema=schema, table=table)

        # 模式概览：dm://schema/{schema}
        @self.mcp.resource(
            "dm://schema/{schema}", name="模式 {schema} 下的表与视图列表"
        )
        async def get_schema(schema: str):
            """
            返回 schema 下的所有表名、视图名列表（含 comment 摘要）。
            适用场景：浏览库结构、筛选要查看的表/视图、为 get_table/get_view 提供候选。

            Args:
                schema: 目标 schema 名称（如 SYSDBA）。

            Returns:
                Dict[str, Any]: 含 schema, schema_info, tables（表名+comment）,
                    views（视图名+comment）。
            """
            return await self._res_get_schema(schema=schema)

        # 视图概览：dm://view/{schema}/{view}
        @self.mcp.resource(
            "dm://view/{schema}/{view}", name="视图 {schema}.{view} 的定义与列信息"
        )
        async def get_view(schema: str, view: str):
            """
            返回视图 schema.view 的列信息、定义摘要、comment（不含完整 DDL）。
            适用场景：快速了解视图结构；需完整定义时调用 get_view_definition 工具。

            Args:
                schema: 视图所属 schema 名称。
                view: 视图名。

            Returns:
                Dict[str, Any]: 含 schema, view, view_info, definition_preview（截断）,
                    columns_preview（列名/类型）。
            """
            return await self._res_get_view(schema=schema, view=view)

        # 数据库概览（可选）：dm://database/{db}
        @self.mcp.resource(
            "dm://database/{db}", name="数据库 {db} 的 schema/表/视图 数量统计"
        )
        async def get_database(db: str):
            """
            返回数据库级统计：schema 数量、全库表数量、全库视图数量。
            适用场景：多实例/多库比对、了解实例规模、为后续 schema 级查询做入口。

            Args:
                db: 数据库/实例标识（用于结果回显，如实例名）。

            Returns:
                Dict[str, Any]: 含 db, schema_count, table_count, view_count。
            """
            return await self._res_get_database(db=db)

    def _register_tools(self) -> None:
        """注册 MCP Tool 路由（单项明细）"""

        @self.mcp.tool(requires_token_auth=True)
        async def get_db_schemas_list():
            """
            列出当前实例下所有可访问的 schema（模式）名称。
            适用场景：不知道有哪些 schema 时，先调用此工具获取列表，再选 schema 做后续查询。

            Returns:
                List[Dict[str, Any]]: 每项含 schema_name, owner_name, created_time。
            """
            return await self._tool_get_db_schemas_list()

        @self.mcp.tool(requires_token_auth=True)
        async def get_db_objects_list(
            schema: Optional[str] = None,
            object_type: Optional[ObjectType] = None,
            include_comments: bool = False,
        ):
            """
            列出 schema 下的表/视图名列表，可按类型过滤。
            适用场景：已知 schema 时获取表/视图列表；object_type 为 TABLE 或 VIEW 时只返回对应类型。

            Args:
                schema: 目标 schema 名称；None 表示全库。
                object_type: 过滤类型：TABLE 只返回表，VIEW 只返回视图，None 返回全部。
                include_comments: True 时返回对象含 comment 字段。

            Returns:
                Dict[str, Any]: 含 schema, object_type, objects/tables/views（对象名列表）。
            """
            return await self._tool_get_db_objects_list(
                schema=schema,
                object_type=object_type,
                include_comments=include_comments,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_table_describe(
            schema: Optional[str] = None,
            table: str = "",
            table_comment: Optional[str] = None,
        ):
            """
            返回表的完整列结构（列名、类型、可空性、默认值）及主键/外键/唯一/检查约束。
            适用场景：写 SQL 前需了解列结构；生成表结构说明；schema 和 table 必填。

            Args:
                schema: 表所属 schema 名称（必填）。
                table: 表名（必填）。
                table_comment: 若已从 resource 或 comment 工具获取，可透传避免重复查询。

            Returns:
                Dict[str, Any]: 含 schema, table, table_info, columns（列列表）, constraints（约束列表）。
            """
            return await self._tool_get_table_describe(
                schema=schema,
                table=table,
                table_comment=table_comment,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_view_describe(
            schema: Optional[str] = None,
            view: str = "",
            view_comment: Optional[str] = None,
        ):
            """
            返回视图的列结构（列名、类型、可空性），不含完整 DDL。
            适用场景：写 SQL 前需了解视图列；需完整定义时用 get_view_definition。

            Args:
                schema: 视图所属 schema 名称（必填）。
                view: 视图名（必填）。
                view_comment: 若已从 resource 或 comment 工具获取，可透传避免重复查询。

            Returns:
                Dict[str, Any]: 含 schema, view, view_info, columns（列列表）。
            """
            return await self._tool_get_view_describe(
                schema=schema,
                view=view,
                view_comment=view_comment,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_view_definition(
            schema: Optional[str] = None,
            view: str = "",
            view_comment: Optional[str] = None,
        ):
            """
            返回视图的完整 CREATE VIEW DDL 文本。
            适用场景：需要视图的完整定义或依赖关系；schema 和 view 必填。

            Args:
                schema: 视图所属 schema 名称（必填）。
                view: 视图名（必填）。
                view_comment: 若已获取，可透传避免重复查询。

            Returns:
                Dict[str, Any]: 含 schema, view, comment, definition（完整 DDL 文本）。
            """
            return await self._tool_get_view_definition(
                schema=schema,
                view=view,
                view_comment=view_comment,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_table_comment(
            schema: Optional[str] = None,
            table: str = "",
            table_comment: Optional[str] = None,
        ):
            """
            返回表的 comment（说明文字）。
            适用场景：需要表说明/注释；若已从 resource 或 describe 获取可透传 table_comment。

            Args:
                schema: 表所属 schema 名称（必填）。
                table: 表名（必填）。
                table_comment: 若已获取，可透传避免重复查询。

            Returns:
                Dict[str, Any]: 含 schema, table, comment（可能为 None）。
            """
            return await self._tool_get_table_comment(
                schema=schema,
                table=table,
                table_comment=table_comment,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_table_column_comments(
            schema: Optional[str] = None,
            table: str = "",
            table_comment: Optional[str] = None,
        ):
            """
            返回表各列的 comment（说明文字）。
            适用场景：需要列级注释；理解业务含义时使用。

            Args:
                schema: 表所属 schema 名称（必填）。
                table: 表名（必填）。
                table_comment: 表 comment，若已获取可透传用于结果回显。

            Returns:
                Dict[str, Any]: 含 schema, table, table_comment, column_comments（每项含 column, comment）。
            """
            return await self._tool_get_table_column_comments(
                schema=schema,
                table=table,
                table_comment=table_comment,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_table_indexes_list(
            schema: Optional[str] = None,
            table: str = "",
            table_comment: Optional[str] = None,
        ):
            """
            返回表的索引列表（索引名、包含列、是否唯一、类型）。
            适用场景：分析查询性能、优化索引、了解表约束。

            Args:
                schema: 表所属 schema 名称（必填）。
                table: 表名（必填）。
                table_comment: 若已获取，可透传用于结果回显。

            Returns:
                Dict[str, Any]: 含 schema, table, table_comment, indexes（索引列表）。
            """
            return await self._tool_get_table_indexes_list(
                schema=schema,
                table=table,
                table_comment=table_comment,
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_table_constraints_list(
            schema: Optional[str] = None,
            table: str = "",
            table_comment: Optional[str] = None,
        ):
            """
            返回表的约束列表（主键、外键、唯一、检查、非空等）。
            适用场景：了解表约束、写 INSERT/UPDATE 前校验、分析外键关系。

            Args:
                schema: 表所属 schema 名称（必填）。
                table: 表名（必填）。
                table_comment: 若已获取，可透传用于结果回显。

            Returns:
                Dict[str, Any]: 含 schema, table, table_comment, constraints（约束列表）。
            """
            return await self._tool_get_table_constraints_list(
                schema=schema,
                table=table,
                table_comment=table_comment,
            )

    # ============================================================
    # Provider 内：通用执行器（仅调用 AsyncPoolService.execute_query）
    # ============================================================

    async def _exec(
        self,
        *,
        sql: str,
        source: str = "auto",
        params: Optional[Any] = None,
        max_rows: int = 2000,
        timeout: Optional[float] = None,
    ) -> List[Any]:
        """
        统一执行入口（Provider 内封装）
        - 业务逻辑仍在 Provider：这里仅做 execute_query 调用与结果提取
        """
        r = cast(
            Mapping[str, Any],
            await self._pool_service.execute_query(
                sql=sql, source=source, params=params
            ),
        )
        rows_any = r.get("result", [])
        # 兼容：有些实现返回 list[list]，有些返回 list[dict]
        return rows_any if isinstance(rows_any, list) else []

    def _ensure_dict_rows(
        self, rows: List[Any], columns: List[str]
    ) -> List[Dict[str, Any]]:
        """当驱动返回 list[list] 时，按列顺序转为 list[dict]，避免 r['key'] 报错。"""
        if not rows:
            return []
        if isinstance(rows[0], dict):
            return cast(List[Dict[str, Any]], rows)
        return [dict(zip(columns, row)) for row in rows]

    def _normalize_schema(self, schema: Optional[str]) -> Optional[str]:
        if schema is None:
            return None
        s = schema.strip()
        return s if s else None

    # ============================================================
    # Resources：概览聚合（tools.md 1.1）
    # ============================================================

    async def _res_get_table(self, schema: str, table: str) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = schema.strip()
        table = table.strip()

        table_info = await self._query_table_info(
            source=source, schema=schema, table=table
        )
        columns = await self._query_table_columns(
            source=source, schema=schema, table=table, limit=60
        )
        indexes = await self._query_table_indexes(
            source=source, schema=schema, table=table, limit=30
        )

        return {
            "schema": schema,
            "table": table,
            "table_info": table_info,
            "columns_preview": columns,
            "indexes_preview": indexes,
        }

    async def _res_get_schema(self, schema: str) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = schema.strip()

        tables = await self._query_tables(
            source=source, schema=schema, include_comments=True, limit=200
        )
        views = await self._query_views(
            source=source, schema=schema, include_comments=True, limit=200
        )
        schema_info = await self._query_schema_info(source=source, schema=schema)

        return {
            "schema": schema,
            "schema_info": schema_info,
            "tables": tables,
            "views": views,
        }

    async def _res_get_view(self, schema: str, view: str) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = schema.strip()
        view = view.strip()

        view_info = await self._query_view_info(source=source, schema=schema, view=view)
        columns = await self._query_view_columns(
            source=source, schema=schema, view=view, limit=60
        )

        # definition 可能很长，resource 只给摘要
        definition = (
            (view_info.get("DEFINITION") or "") if isinstance(view_info, dict) else ""
        )
        definition_preview = definition[:2000] + (
            "..." if len(definition) > 2000 else ""
        )

        return {
            "schema": schema,
            "view": view,
            "view_info": (
                {k: v for k, v in view_info.items() if k != "DEFINITION"}
                if isinstance(view_info, dict)
                else {}
            ),
            "definition_preview": definition_preview,
            "columns_preview": columns,
        }

    async def _res_get_database(self, db: str) -> Dict[str, Any]:
        # DM8 一般一个实例下多 schema，这里做对象数量统计摘要
        source = await self._get_current_datasource_name()
        db = db.strip()

        schemas = await self._tool_get_db_schemas_list()
        schema_count = len(schemas)

        # 粗略统计：全库 tables/views 数
        tables = await self._query_tables(
            source=source, schema=None, include_comments=False, limit=2000
        )
        views = await self._query_views(
            source=source, schema=None, include_comments=False, limit=2000
        )

        return {
            "db": db,
            "schema_count": schema_count,
            "table_count": len(tables),
            "view_count": len(views),
        }

    # ============================================================
    # Tools：单项明细（tools.md 1.2）
    # ============================================================

    async def _tool_get_db_schemas_list(self) -> List[Dict[str, Any]]:
        source = await self._get_current_datasource_name()
        return await self._query_schemas(source=source)

    async def _tool_get_db_objects_list(
        self,
        schema: Optional[str],
        object_type: Optional[ObjectType],
        include_comments: bool,
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        object_type = object_type.upper() if object_type else None  # type: ignore[assignment]

        if object_type == "TABLE":
            tables = await self._query_tables(
                source=source,
                schema=schema,
                include_comments=include_comments,
                limit=2000,
            )
            return {"schema": schema, "object_type": "TABLE", "objects": tables}

        if object_type == "VIEW":
            views = await self._query_views(
                source=source,
                schema=schema,
                include_comments=include_comments,
                limit=2000,
            )
            return {"schema": schema, "object_type": "VIEW", "objects": views}

        # None：返回 tables + views
        tables = await self._query_tables(
            source=source, schema=schema, include_comments=include_comments, limit=2000
        )
        views = await self._query_views(
            source=source, schema=schema, include_comments=include_comments, limit=2000
        )
        return {
            "schema": schema,
            "object_type": None,
            "tables": tables,
            "views": views,
        }

    async def _tool_get_table_describe(
        self,
        schema: Optional[str],
        table: str,
        table_comment: Optional[str],
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError("table 不能为空")

        table_info = await self._query_table_info(
            source=source, schema=schema, table=table
        )
        cols = await self._query_table_columns(
            source=source, schema=schema, table=table, limit=500
        )

        # 约束（含主键等）
        constraints = await self._query_table_constraints(
            source=source, schema=schema, table=table, limit=300
        )

        # 如果上游已经传了 comment，则直接透传，避免重复查
        if table_comment is not None:
            table_info["COMMENT"] = table_comment

        return {
            "schema": schema,
            "table": table,
            "table_info": table_info,
            "columns": cols,
            "constraints": constraints,
        }

    async def _tool_get_view_describe(
        self,
        schema: Optional[str],
        view: str,
        view_comment: Optional[str],
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not view:
            raise ValueError("view 不能为空")

        view_info = await self._query_view_info(source=source, schema=schema, view=view)
        cols = await self._query_view_columns(
            source=source, schema=schema, view=view, limit=500
        )
        if view_comment is not None:
            view_info["COMMENT"] = view_comment

        return {
            "schema": schema,
            "view": view,
            "view_info": (
                {k: v for k, v in view_info.items() if k != "DEFINITION"}
                if isinstance(view_info, dict)
                else {}
            ),
            "columns": cols,
        }

    async def _tool_get_view_definition(
        self,
        schema: Optional[str],
        view: str,
        view_comment: Optional[str],
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not view:
            raise ValueError("view 不能为空")

        view_info = await self._query_view_info(source=source, schema=schema, view=view)
        if view_comment is not None:
            view_info["COMMENT"] = view_comment

        return {
            "schema": schema,
            "view": view,
            "comment": view_info.get("COMMENT"),
            "definition": view_info.get("DEFINITION"),
        }

    async def _tool_get_table_comment(
        self,
        schema: Optional[str],
        table: str,
        table_comment: Optional[str],
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError("table 不能为空")

        if table_comment is not None:
            return {"schema": schema, "table": table, "comment": table_comment}

        table_info = await self._query_table_info(
            source=source, schema=schema, table=table
        )
        return {"schema": schema, "table": table, "comment": table_info.get("COMMENT")}

    async def _tool_get_table_column_comments(
        self,
        schema: Optional[str],
        table: str,
        table_comment: Optional[str],
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError("table 不能为空")

        cols = await self._query_table_columns(
            source=source, schema=schema, table=table, limit=2000
        )
        # 只返回列名+comment，避免太大
        return {
            "schema": schema,
            "table": table,
            "table_comment": table_comment,
            "column_comments": [
                {"column": c.get("COLUMN_NAME"), "comment": c.get("COMMENT")}
                for c in cols
            ],
        }

    async def _tool_get_table_indexes_list(
        self,
        schema: Optional[str],
        table: str,
        table_comment: Optional[str],
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError("table 不能为空")

        indexes = await self._query_table_indexes(
            source=source, schema=schema, table=table, limit=2000
        )
        return {
            "schema": schema,
            "table": table,
            "table_comment": table_comment,
            "indexes": indexes,
        }

    async def _tool_get_table_constraints_list(
        self,
        schema: Optional[str],
        table: str,
        table_comment: Optional[str],
    ) -> Dict[str, Any]:
        source = await self._get_current_datasource_name()
        schema = self._normalize_schema(schema)
        if not table:
            raise ValueError("table 不能为空")

        constraints = await self._query_table_constraints(
            source=source, schema=schema, table=table, limit=2000
        )
        return {
            "schema": schema,
            "table": table,
            "table_comment": table_comment,
            "constraints": constraints,
        }

    # ============================================================
    # SQL：DM8 系统目录查询（Provider 内实现）
    # ============================================================

    async def _query_schemas(self, source: str) -> List[Dict[str, Any]]:
        sql = """
        SELECT
          SCH_OBJ.NAME  AS SCHEMA_NAME,
          USER_OBJ.NAME AS OWNER_NAME,
          SCH_OBJ.CRTDATE AS CREATED_TIME
        FROM SYS.SYSOBJECTS SCH_OBJ
        JOIN SYS.SYSOBJECTS USER_OBJ
          ON SCH_OBJ.PID = USER_OBJ.ID
        WHERE SCH_OBJ.TYPE$ = 'SCH'
        ORDER BY SCH_OBJ.NAME;
        """
        rows = await self._exec(sql=sql, source=source)
        return self._ensure_dict_rows(
            rows, ["SCHEMA_NAME", "OWNER_NAME", "CREATED_TIME"]
        )

    async def _query_schema_info(self, source: str, schema: str) -> Dict[str, Any]:
        sql = """
        SELECT
          SCH_OBJ.NAME    AS SCHEMA_NAME,
          USER_OBJ.NAME   AS OWNER,
          SCH_OBJ.CRTDATE AS CREATED_TIME
        FROM SYS.SYSOBJECTS SCH_OBJ
        JOIN SYS.SYSOBJECTS USER_OBJ
          ON SCH_OBJ.PID = USER_OBJ.ID
        WHERE SCH_OBJ.TYPE$ = 'SCH' AND SCH_OBJ.NAME = ?
        """
        rows = await self._exec(sql=sql, source=source, params=[schema])
        rows = self._ensure_dict_rows(rows, ["SCHEMA_NAME", "OWNER", "CREATED_TIME"])
        return rows[0] if rows else {}

    async def _query_tables(
        self,
        source: str,
        schema: Optional[str],
        include_comments: bool,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if schema:
            sql = """
            SELECT
              OWNER        AS SCHEMA_NAME,
              OBJECT_NAME  AS OBJECT_NAME,
              OBJECT_TYPE  AS OBJECT_TYPE
            FROM DBA_OBJECTS
            WHERE OBJECT_TYPE = 'TABLE' AND OWNER = ?
            ORDER BY OBJECT_TYPE, OBJECT_NAME;
            """
            params = [schema]
        else:
            sql = """
            SELECT
              OWNER        AS SCHEMA_NAME,
              OBJECT_NAME  AS OBJECT_NAME,
              OBJECT_TYPE  AS OBJECT_TYPE
            FROM DBA_OBJECTS
            WHERE OBJECT_TYPE = 'TABLE'
            ORDER BY OWNER, OBJECT_TYPE, OBJECT_NAME;
            """
            params = None

        rows = await self._exec(sql=sql, source=source, params=params, max_rows=limit)
        rows = self._ensure_dict_rows(
            rows, ["SCHEMA_NAME", "OBJECT_NAME", "OBJECT_TYPE"]
        )
        # 转换字段名以保持兼容性
        for r in rows:
            r["TABLE_NAME"] = r.pop("OBJECT_NAME")
            r["TABLE_TYPE"] = r.pop("OBJECT_TYPE")
            if not include_comments:
                r.pop("COMMENT", None)
        return rows[:limit]

    async def _query_table_info(
        self,
        source: str,
        schema: Optional[str],
        table: str,
    ) -> Dict[str, Any]:
        # schema 为空时：尝试按当前 schema/或全库匹配（这里先要求 schema 明确更安全）
        if not schema:
            raise ValueError("schema 不能为空（建议上游传入明确 schema）")

        sql = """
        SELECT
          OWNER       AS SCHEMA_NAME,
          OBJECT_NAME AS TABLE_NAME
        FROM DBA_OBJECTS
        WHERE OWNER = ? AND OBJECT_NAME = ? AND OBJECT_TYPE = 'TABLE'
        """
        rows = await self._exec(
            sql=sql, source=source, params=[schema, table], max_rows=1
        )
        rows = self._ensure_dict_rows(rows, ["SCHEMA_NAME", "TABLE_NAME"])
        return rows[0] if rows else {}

    async def _query_table_columns(
        self,
        source: str,
        schema: Optional[str],
        table: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not schema:
            raise ValueError("schema 不能为空（建议上游传入明确 schema）")

        sql = """
        SELECT
          c.OWNER       AS SCHEMA_NAME,
          c.TABLE_NAME  AS TABLE_NAME,
          c.COLUMN_ID   AS COLUMN_ID,
          c.COLUMN_NAME AS COLUMN_NAME,
          c.DATA_TYPE   AS DATA_TYPE,
          c.DATA_LENGTH AS DATA_LENGTH,
          c.DATA_PRECISION AS DATA_PRECISION,
          c.DATA_SCALE  AS DATA_SCALE,
          c.NULLABLE    AS NULLABLE,
          c.DATA_DEFAULT AS DEFAULT_VALUE,
          cc.COMMENTS   AS COLUMN_COMMENT
        FROM ALL_TAB_COLUMNS c
        LEFT JOIN ALL_COL_COMMENTS cc
          ON cc.OWNER = c.OWNER
         AND cc.TABLE_NAME = c.TABLE_NAME
         AND cc.COLUMN_NAME = c.COLUMN_NAME
        WHERE c.OWNER = ? AND c.TABLE_NAME = ?
        ORDER BY c.COLUMN_ID;
        """
        rows = await self._exec(
            sql=sql, source=source, params=[schema, table], max_rows=limit
        )
        rows = self._ensure_dict_rows(
            rows,
            [
                "SCHEMA_NAME",
                "TABLE_NAME",
                "COLUMN_ID",
                "COLUMN_NAME",
                "DATA_TYPE",
                "DATA_LENGTH",
                "DATA_PRECISION",
                "DATA_SCALE",
                "NULLABLE",
                "DEFAULT_VALUE",
                "COLUMN_COMMENT",
            ],
        )
        # 转换字段名以保持兼容性
        for r in rows:
            r["COMMENT"] = r.pop("COLUMN_COMMENT")
            r["POSITION"] = r["COLUMN_ID"]
        return rows[:limit]

    async def _query_views(
        self,
        source: str,
        schema: Optional[str],
        include_comments: bool,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if schema:
            sql = """
            SELECT
              OWNER        AS SCHEMA_NAME,
              OBJECT_NAME  AS OBJECT_NAME,
              OBJECT_TYPE  AS OBJECT_TYPE
            FROM DBA_OBJECTS
            WHERE OBJECT_TYPE = 'VIEW' AND OWNER = ?
            ORDER BY OBJECT_NAME;
            """
            params = [schema]
        else:
            sql = """
            SELECT
              OWNER        AS SCHEMA_NAME,
              OBJECT_NAME  AS OBJECT_NAME,
              OBJECT_TYPE  AS OBJECT_TYPE
            FROM DBA_OBJECTS
            WHERE OBJECT_TYPE = 'VIEW'
            ORDER BY OWNER, OBJECT_NAME;
            """
            params = None

        rows = await self._exec(sql=sql, source=source, params=params, max_rows=limit)
        rows = self._ensure_dict_rows(
            rows, ["SCHEMA_NAME", "OBJECT_NAME", "OBJECT_TYPE"]
        )
        # 转换字段名以保持兼容性
        for r in rows:
            r["VIEW_NAME"] = r.pop("OBJECT_NAME")
            if not include_comments:
                r.pop("COMMENT", None)
        return rows[:limit]

    async def _query_view_info(
        self,
        source: str,
        schema: Optional[str],
        view: str,
    ) -> Dict[str, Any]:
        if not schema:
            raise ValueError("schema 不能为空（建议上游传入明确 schema）")

        sql = """
        SELECT
          OWNER       AS SCHEMA_NAME,
          OBJECT_NAME AS VIEW_NAME,
          OBJECT_TYPE AS OBJECT_TYPE
        FROM DBA_OBJECTS
        WHERE OWNER = ? AND OBJECT_NAME = ? AND OBJECT_TYPE = 'VIEW'
        """
        rows = await self._exec(
            sql=sql, source=source, params=[schema, view], max_rows=1
        )
        rows = self._ensure_dict_rows(rows, ["SCHEMA_NAME", "VIEW_NAME", "OBJECT_TYPE"])
        if rows:
            view_info = rows[0]
            # 获取视图定义
            definition_sql = """
            SELECT b.*
            FROM SYS.SYSOBJECTS a
            JOIN SYS.SYSTEXTS  b
              ON a.ID = b.ID
            WHERE a.NAME = ?;
            """
            def_rows = await self._exec(
                sql=definition_sql, source=source, params=[view], max_rows=1
            )
            if def_rows:
                if isinstance(def_rows[0], dict):
                    view_info["DEFINITION"] = def_rows[0].get("TEXT", "")
                else:
                    # list 行：SYSTEXTS 通常为 (ID, TEXT)，取第二列
                    row0 = def_rows[0]
                    view_info["DEFINITION"] = (
                        row0[1] if len(row0) > 1 else (row0[0] if row0 else "")
                    )
            else:
                view_info["DEFINITION"] = ""
            return view_info
        return {}

    async def _query_view_columns(
        self,
        source: str,
        schema: Optional[str],
        view: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not schema:
            raise ValueError("schema 不能为空（建议上游传入明确 schema）")

        sql = """
        SELECT
          OWNER       AS SCHEMA_NAME,
          TABLE_NAME  AS VIEW_NAME,
          COLUMN_ID   AS COLUMN_ID,
          COLUMN_NAME AS COLUMN_NAME,
          DATA_TYPE   AS DATA_TYPE,
          DATA_LENGTH AS DATA_LENGTH,
          DATA_PRECISION AS DATA_PRECISION,
          DATA_SCALE  AS DATA_SCALE,
          NULLABLE    AS NULLABLE,
          DATA_DEFAULT AS DEFAULT_VALUE
        FROM DBA_TAB_COLUMNS
        WHERE OWNER = ? AND TABLE_NAME = ?
        ORDER BY COLUMN_ID;
        """
        rows = await self._exec(
            sql=sql, source=source, params=[schema, view], max_rows=limit
        )
        rows = self._ensure_dict_rows(
            rows,
            [
                "SCHEMA_NAME",
                "VIEW_NAME",
                "COLUMN_ID",
                "COLUMN_NAME",
                "DATA_TYPE",
                "DATA_LENGTH",
                "DATA_PRECISION",
                "DATA_SCALE",
                "NULLABLE",
                "DEFAULT_VALUE",
            ],
        )
        # 转换字段名以保持兼容性
        for r in rows:
            r["POSITION"] = r["COLUMN_ID"]
        return rows[:limit]

    async def _query_table_indexes(
        self,
        source: str,
        schema: Optional[str],
        table: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not schema:
            raise ValueError("schema 不能为空（建议上游传入明确 schema）")

        sql = """
        SELECT
          i.TABLE_OWNER  AS SCHEMA_NAME,
          i.TABLE_NAME   AS TABLE_NAME,
          i.INDEX_NAME   AS INDEX_NAME,
          i.UNIQUENESS   AS UNIQUENESS,
          i.INDEX_TYPE   AS INDEX_TYPE,
          c.COLUMN_POSITION AS COLUMN_POSITION,
          c.COLUMN_NAME  AS COLUMN_NAME
        FROM DBA_INDEXES i
        JOIN DBA_IND_COLUMNS c
          ON i.OWNER = c.INDEX_OWNER
         AND i.INDEX_NAME = c.INDEX_NAME
        WHERE i.TABLE_OWNER = ? AND i.TABLE_NAME = ?
        ORDER BY i.INDEX_NAME, c.COLUMN_POSITION;
        """
        rows = await self._exec(
            sql=sql, source=source, params=[schema, table], max_rows=limit
        )
        rows = self._ensure_dict_rows(
            rows,
            [
                "SCHEMA_NAME",
                "TABLE_NAME",
                "INDEX_NAME",
                "UNIQUENESS",
                "INDEX_TYPE",
                "COLUMN_POSITION",
                "COLUMN_NAME",
            ],
        )
        # 转换字段名以保持兼容性
        for r in rows:
            r["IS_UNIQUE"] = r["UNIQUENESS"]
            r["CREATED_TIME"] = None  # DBA_INDEXES 没有创建时间
        return rows[:limit]

    async def _query_table_constraints(
        self,
        source: str,
        schema: Optional[str],
        table: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not schema:
            raise ValueError("schema 不能为空（建议上游传入明确 schema）")

        sql = """
        SELECT
          c.OWNER            AS SCHEMA_NAME,
          c.TABLE_NAME       AS TABLE_NAME,
          c.CONSTRAINT_NAME  AS CONSTRAINT_NAME,
          c.CONSTRAINT_TYPE  AS CONSTRAINT_TYPE,
          c.STATUS           AS STATUS,
          cc.COLUMN_NAME     AS COLUMN_NAME,
          cc.POSITION        AS COLUMN_POSITION,
          c.R_OWNER          AS REF_OWNER,
          c.R_CONSTRAINT_NAME AS REF_CONSTRAINT_NAME
        FROM DBA_CONSTRAINTS c
        LEFT JOIN DBA_CONS_COLUMNS cc
          ON c.OWNER = cc.OWNER
         AND c.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
        WHERE c.OWNER = ? AND c.TABLE_NAME = ?
        ORDER BY c.CONSTRAINT_NAME, cc.POSITION;
        """
        rows = await self._exec(
            sql=sql, source=source, params=[schema, table], max_rows=limit
        )
        rows = self._ensure_dict_rows(
            rows,
            [
                "SCHEMA_NAME",
                "TABLE_NAME",
                "CONSTRAINT_NAME",
                "CONSTRAINT_TYPE",
                "STATUS",
                "COLUMN_NAME",
                "COLUMN_POSITION",
                "REF_OWNER",
                "REF_CONSTRAINT_NAME",
            ],
        )
        return rows[:limit]
