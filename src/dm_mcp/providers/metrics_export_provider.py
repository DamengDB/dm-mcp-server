from typing import Any, Dict, List, Optional

from dm_mcp.providers.base_datasource_provider import BaseDataSourceMCPProvider
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.metrics_service import MetricsService


class MetricsExportMCPProvider(BaseDataSourceMCPProvider):
    """指标导出工具 Provider。"""

    def __init__(
        self,
        datasource_service: DataSourceService,
        pool_service: AsyncPoolService,
        metrics_service: MetricsService,
    ) -> None:
        super().__init__(datasource_service)
        self._pool_service = pool_service
        self._metrics_service = metrics_service
        self._register_routes()

    def _register_routes(self) -> None:
        """注册 MCP Tool 路由"""

        # 原有的指标导出工具
        @self.mcp.tool(requires_token_auth=False)
        async def export_metrics():
            """
            导出当前进程的 Prometheus 指标快照（数值型）。
            适用场景：临时调试、无独立监控时排查问题。

            Returns:
                Dict[str, Any]: 含 metrics（指标名→数值）, timestamp 等。
            """
            return await self._export_metrics()

        # 诊断分析工具
        @self.mcp.tool(requires_token_auth=True)
        async def get_sql_explain_plan(sql: str, schema: Optional[str] = None):
            """
            返回 SQL 的执行计划（EXPLAIN 结果）。
            适用场景：分析慢 SQL、优化查询、理解执行路径。

            Args:
                sql: 要分析执行计划的 SQL。
                schema: 可选 schema；不传用数据源默认。

            Returns:
                Dict[str, Any]: 含 success, sql, schema, explain_plan（计划行列表）, plan_count, error。
            """
            return await self._tool_get_sql_explain_plan(sql=sql, schema=schema)

        @self.mcp.tool(requires_token_auth=True)
        async def get_sql_slow_queries_top(days: int = 7, top_n: int = 5):
            """
            返回最近 N 天内最慢的 Top N 条 SQL 列表。
            适用场景：性能优化、定位慢查询、容量规划。

            Args:
                days: 统计天数窗口，默认 7。
                top_n: 返回条数，默认 5。

            Returns:
                Dict[str, Any]: 含 success, days, top_n, slow_queries（慢 SQL 列表）, count, error。
            """
            return await self._tool_get_sql_slow_queries_top(days=days, top_n=top_n)

        @self.mcp.tool(requires_token_auth=True)
        async def get_audit_recent_logs(days: int = 7, limit: int = 100):
            """
            返回最近 N 天内的审计日志（按时间倒序）。
            适用场景：安全审计、操作追溯；需实例已开启审计。

            Args:
                days: 统计天数，默认 7。
                limit: 最多返回行数，默认 100。

            Returns:
                Dict[str, Any]: 含 success, audit_enabled, days, limit, audit_logs, count, error。
            """
            return await self._tool_get_audit_recent_logs(days=days, limit=limit)

        @self.mcp.tool(requires_token_auth=True)
        async def get_sql_profile(
            sql_id: Optional[str] = None,
            sql_text: Optional[str] = None,
            schema: Optional[str] = None,
        ):
            """
            返回指定 SQL 的执行统计（执行次数、耗时等）。
            适用场景：分析 SQL 性能；sql_id 精确匹配，sql_text 模糊匹配；未找到时自动查历史。

            Args:
                sql_id: SQL 唯一标识（优先）。
                sql_text: SQL 文本（模糊匹配）。
                schema: 可选，用于结果回显。

            Returns:
                Dict[str, Any]: 含 success, sql_id/sql_text/schema, execution_stats, count, source, error。
            """
            return await self._tool_get_sql_profile(
                sql_id=sql_id, sql_text=sql_text, schema=schema
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_table_data_size(schema_name: str, table_name: str):
            """
            返回表的数据与索引空间占用（数据页数、索引页数、MB 等）。
            适用场景：容量评估、大表识别、存储优化。

            Args:
                schema_name: 表所属 schema。
                table_name: 表名。

            Returns:
                Dict[str, Any]: 含 success, schema_name, table_name, data（页数/MB 等）, count, error。
            """
            return await self._tool_get_table_data_size(
                schema_name=schema_name, table_name=table_name
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_table_basic_info(schema_name: str, table_name: str):
            """
            返回表的统计信息（行数、块数、平均行长、是否分区等）；调用前自动 GATHER_TABLE_STATS。
            适用场景：优化器统计、执行计划分析、表规模评估。

            Args:
                schema_name: 表所属 schema。
                table_name: 表名。

            Returns:
                Dict[str, Any]: 含 success, schema_name, table_name, data（行数/块数等）, count, error。
            """
            return await self._tool_get_table_basic_info(
                schema_name=schema_name, table_name=table_name
            )

        @self.mcp.tool(requires_token_auth=True)
        async def analyze_columns(
            schema_name: str,
            table_name: str,
            top_n: int = 10,
        ):
            """
            分析表各列的统计特征（空值数、不重复值数、最大/最小值、Top N 取值频次）。
            适用场景：数据质量分析、索引设计、理解列分布。

            Args:
                schema_name: 表所属 schema。
                table_name: 表名。
                top_n: 每列 Top N 取值数量，默认 10。

            Returns:
                Dict[str, Any]: 含 success, schema_name, table_name, top_n, columns（含 basic_stats/top_values）, error。
            """
            return await self._tool_analyze_columns(
                schema_name=schema_name, table_name=table_name, top_n=top_n
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_memory_stats():
            """
            返回实例内存使用（缓冲池、缓存项、计划缓存、字典缓存等）。
            适用场景：性能排查、容量规划、内存瓶颈分析。

            Returns:
                Dict[str, Any]: 含 success, memory_stats（各组件占用列表）, count, error。
            """
            return await self._tool_get_memory_stats()

        # 监控与运维工具
        @self.mcp.tool(requires_token_auth=True)
        async def get_metrics(
            metric_names: Optional[List[str]] = None,
            time_range: Optional[str] = None,
        ):
            """
            返回服务器监控指标（QPS、错误率、连接池使用率等）。
            适用场景：监控大盘、性能评估；metric_names 为空时返回全部指标。

            Args:
                metric_names: 指标名列表（如 sessions, sql_stats）；None 返回全部。
                time_range: 时间范围描述（当前主要用“最近 1 小时”为窗口，

            Returns:
                Dict[str, Any]: 含 success, metrics（指标名→数据）, metric_names, time_range, timestamp, error。
            """
            return await self._tool_get_metrics(
                metric_names=metric_names, time_range=time_range
            )

        @self.mcp.tool(requires_token_auth=True)
        async def get_pool_status():
            """
            返回数据库连接池状态（基于 V$SESSIONS 近似：总连接数、活跃/空闲、状态分布）。
            适用场景：连接池健康度、负载评估、排障。

            Returns:
                Dict[str, Any]: 含 success, pool_status, connection_details（会话列表）, timestamp, error。
            """
            return await self._tool_get_pool_status()

        @self.mcp.tool(requires_token_auth=True)
        async def get_worker_status():
            """
            返回执行器/worker 运行状态（活跃数、空闲数、正在执行的 SQL 及耗时）。
            适用场景：排查执行线程瓶颈、观测并发负载。

            Returns:
                Dict[str, Any]: 含 success, worker_status, active_workers, current_executions, timestamp, error。
            """
            return await self._tool_get_worker_status()

    async def _export_metrics(self) -> Dict[str, Any]:
        """
        导出 Prometheus 指标快照
        """
        return self._metrics_service.export_metrics_snapshot()

    # ============================================================
    # 统一执行器（Provider 内封装）
    # ============================================================

    async def _exec(
        self,
        *,
        sql: str,
        source: str = "auto",
        params: Optional[Any] = None,
        max_rows: int = 2000,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        统一执行入口（Provider 内封装）
        - 业务逻辑仍在 Provider：这里仅做 execute_query 调用与结果提取
        """
        r = await self._pool_service.execute_query(
            sql=sql,
            source=source,
            params=params,
        )
        rows = r.get("result", [])
        # 兼容：有些实现返回 list[list]，有些返回 list[dict]
        return rows if isinstance(rows, list) else []

    # ============================================================
    # 诊断分析 Tools（tools.md 1.4）
    # ============================================================

    async def _tool_get_sql_explain_plan(
        self, sql: str, schema: Optional[str] = None
    ) -> Dict[str, Any]:
        """返回 SQL 执行计划或优化建议"""
        source = await self._get_current_datasource_name()

        # 使用 EXPLAIN FOR 获取执行计划
        explain_sql = f"EXPLAIN FOR {sql}"
        try:
            await self._exec(sql=explain_sql, source=source)
        except Exception as e:
            return {
                "success": False,
                "error": f"EXPLAIN 执行失败: {str(e)}",
                "sql": sql,
                "schema": schema,
            }

        # 从临时表获取计划详情
        plan_sql = """
        SELECT * FROM SYS."##PLAN_TABLE"
        ORDER BY PLAN_ID
        """
        try:
            plan_rows = await self._exec(sql=plan_sql, source=source, max_rows=1000)
            return {
                "success": True,
                "sql": sql,
                "schema": schema,
                "explain_plan": plan_rows,
                "plan_count": len(plan_rows),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取计划详情失败: {str(e)}",
                "sql": sql,
                "schema": schema,
            }

    async def _tool_get_sql_slow_queries_top(
        self, days: int = 7, top_n: int = 5
    ) -> Dict[str, Any]:
        """获取最近 N 天慢 SQL Top N"""
        source = await self._get_current_datasource_name()

        # 合并会话级和系统级慢 SQL
        sql = """
        SELECT *
        FROM (
            -- 会话级慢 SQL
            SELECT
                'SESSION'        AS SRC_TYPE,
                SQL_ID           AS SQL_ID,
                SESS_ID          AS SESS_ID,
                EXEC_TIME        AS EXEC_TIME,
                FINISH_TIME      AS FINISH_TIME,
                N_RUNS           AS N_RUNS,
                TRX_ID           AS TRX_ID,
                SQL_TEXT         AS SQL_TEXT
            FROM V$LONG_EXEC_SQLS
            WHERE FINISH_TIME >= (SYSDATE - ?)

            UNION ALL

            -- 系统级慢 SQL
            SELECT
                'SYSTEM'         AS SRC_TYPE,
                NULL             AS SQL_ID,
                SESS_ID          AS SESS_ID,
                EXEC_TIME        AS EXEC_TIME,
                FINISH_TIME      AS FINISH_TIME,
                N_RUNS           AS N_RUNS,
                TRX_ID           AS TRX_ID,
                SQL_TEXT         AS SQL_TEXT
            FROM V$SYSTEM_LONG_EXEC_SQLS
            WHERE FINISH_TIME >= (SYSDATE - ?)
        )
        ORDER BY
            EXEC_TIME DESC,
            N_RUNS DESC
        FETCH FIRST ? ROWS ONLY
        """

        try:
            rows = await self._exec(
                sql=sql, source=source, params=[days, days, top_n], max_rows=top_n
            )
            return {
                "success": True,
                "days": days,
                "top_n": top_n,
                "slow_queries": rows,
                "count": len(rows),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取慢 SQL 失败: {str(e)}",
                "days": days,
                "top_n": top_n,
            }

    async def _tool_get_audit_recent_logs(
        self, days: int = 7, limit: int = 100
    ) -> Dict[str, Any]:
        """获取最近的审计日志"""
        source = await self._get_current_datasource_name()

        # 检查审计是否开启
        check_sql = """
        SELECT PARA_VALUE AS ENABLE_AUDIT
        FROM V$DM_INI
        WHERE PARA_NAME = 'ENABLE_AUDIT'
        """

        try:
            audit_check = await self._exec(sql=check_sql, source=source, max_rows=1)
            if not audit_check or audit_check[0].get("ENABLE_AUDIT") != "1":
                return {
                    "success": False,
                    "error": "审计功能未开启",
                    "audit_enabled": False,
                    "days": days,
                    "limit": limit,
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"检查审计状态失败: {str(e)}",
                "days": days,
                "limit": limit,
            }

        # 获取审计日志
        audit_sql = """
        SELECT *
        FROM V$AUDITRECORDS
        WHERE OPTIME >= (SYSDATE - ?)
        ORDER BY OPTIME DESC
        FETCH FIRST ? ROWS ONLY
        """

        try:
            rows = await self._exec(
                sql=audit_sql, source=source, params=[days, limit], max_rows=limit
            )
            return {
                "success": True,
                "audit_enabled": True,
                "days": days,
                "limit": limit,
                "audit_logs": rows,
                "count": len(rows),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取审计日志失败: {str(e)}",
                "audit_enabled": True,
                "days": days,
                "limit": limit,
            }

    async def _tool_get_sql_profile(
        self,
        sql_id: Optional[str] = None,
        sql_text: Optional[str] = None,
        schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取指定 SQL 的执行统计信息"""
        source = await self._get_current_datasource_name()

        if not sql_id and not sql_text:
            return {
                "success": False,
                "error": "必须提供 sql_id 或 sql_text 中的至少一个",
                "sql_id": sql_id,
                "sql_text": sql_text,
                "schema": schema,
            }

        try:
            if sql_id:
                # 按 sql_id 查询当前执行统计
                sql = """
                SELECT
                    SQL_ID,
                    SQL_TEXT_ID,
                    SESSID        AS SESS_ID,
                    SQL_TXT       AS SQL_TEXT,
                    START_TIME,
                    END_TIME,
                    EXEC_TIME,
                    PARSE_CNT,
                    PARSE_TIME,
                    HARD_PARSE_CNT,
                    HARD_PARSE_TIME,
                    LOGIC_READ_CNT,
                    PHY_READ_CNT,
                    IO_WAIT_TIME,
                    NET_BYTES_RECV,
                    NET_BYTES_SEND,
                    REDO_SIZE,
                    EXEC_ID
                FROM V$SQL_STAT
                WHERE SQL_ID = ?
                ORDER BY START_TIME DESC
                """
                params = [sql_id]
            else:
                # 按 sql_text 模糊匹配
                sql = """
                SELECT
                    SQL_ID,
                    SQL_TEXT_ID,
                    SESSID        AS SESS_ID,
                    SQL_TXT       AS SQL_TEXT,
                    START_TIME,
                    END_TIME,
                    EXEC_TIME,
                    PARSE_CNT,
                    PARSE_TIME,
                    HARD_PARSE_CNT,
                    HARD_PARSE_TIME,
                    LOGIC_READ_CNT,
                    PHY_READ_CNT,
                    IO_WAIT_TIME,
                    NET_BYTES_RECV,
                    NET_BYTES_SEND,
                    REDO_SIZE,
                    EXEC_ID
                FROM V$SQL_STAT
                WHERE SQL_TXT LIKE '%' || ? || '%'
                ORDER BY START_TIME DESC
                FETCH FIRST 10 ROWS ONLY
                """
                params = [sql_text]

            rows = await self._exec(sql=sql, source=source, params=params, max_rows=50)

            # 如果当前没有找到，尝试历史统计
            if not rows and sql_id:
                history_sql = """
                SELECT
                    SQL_ID,
                    SQL_TEXT_ID,
                    SESSID        AS SESS_ID,
                    SQL_TXT       AS SQL_TEXT,
                    START_TIME,
                    END_TIME,
                    EXEC_TIME,
                    PARSE_TIME,
                    HARD_PARSE_TIME,
                    LOGIC_READ_CNT,
                    PHY_READ_CNT,
                    IO_WAIT_TIME,
                    NET_BYTES_RECV,
                    NET_BYTES_SEND,
                    REDO_SIZE,
                    EXEC_ID
                FROM V$SQL_STAT_HISTORY
                WHERE SQL_ID = ?
                ORDER BY END_TIME DESC
                FETCH FIRST 20 ROWS ONLY
                """
                rows = await self._exec(
                    sql=history_sql, source=source, params=[sql_id], max_rows=50
                )

            return {
                "success": True,
                "sql_id": sql_id,
                "sql_text": sql_text,
                "schema": schema,
                "execution_stats": rows,
                "count": len(rows),
                "source": "history" if not rows and sql_id else "current",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取 SQL 执行统计失败: {str(e)}",
                "sql_id": sql_id,
                "sql_text": sql_text,
                "schema": schema,
            }

    async def _tool_get_table_data_size(
        self,
        schema_name: str,
        table_name: str,
    ) -> Dict[str, Any]:
        """获取指定表的数据与索引空间占用情况"""
        source = await self._get_current_datasource_name()

        sql = """
        SELECT 
            S.NAME AS "模式名",
            T.NAME AS "表名",
            B.PAGE_SIZE AS "页大小字节",
            TABLE_USED_SPACE(S.NAME, T.NAME) AS "数据占用页数",
            (
                SELECT NVL(SUM(INDEX_USED_SPACE(I.ID)), 0) 
                FROM SYS.SYSOBJECTS I 
                WHERE I.PID = T.ID AND I.SUBTYPE$ = 'INDEX'
            ) AS "索引占用页数",
            TABLE_USED_SPACE(S.NAME, T.NAME) * B.PAGE_SIZE / 1024 / 1024 AS "数据占用MB",
            (
                SELECT NVL(SUM(INDEX_USED_SPACE(I.ID)), 0) * B.PAGE_SIZE / 1024 / 1024 
                FROM SYS.SYSOBJECTS I 
                WHERE I.PID = T.ID AND I.SUBTYPE$ = 'INDEX'
            ) AS "索引占用MB"
        FROM SYS.SYSOBJECTS T
        JOIN SYS.SYSOBJECTS S ON T.SCHID = S.ID
        CROSS JOIN (SELECT PAGE_SIZE FROM V$BUFFERPOOL WHERE ROWNUM = 1) B
        WHERE T.NAME = ?
            AND S.NAME = ?
            AND T.TYPE$ = 'SCHOBJ' 
            AND T.SUBTYPE$ = 'UTAB'
        """

        try:
            rows = await self._exec(
                sql=sql,
                source=source,
                params=[table_name, schema_name],
                max_rows=1,
            )
            return {
                "success": True,
                "schema_name": schema_name,
                "table_name": table_name,
                "data": rows[0] if rows else None,
                "count": len(rows),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取表空间占用失败: {str(e)}",
                "schema_name": schema_name,
                "table_name": table_name,
            }

    async def _tool_get_table_basic_info(
        self,
        schema_name: str,
        table_name: str,
    ) -> Dict[str, Any]:
        """获取指定表的基础统计信息与存储信息"""
        source = await self._get_current_datasource_name()

        # 在查询前强制收集最新统计信息
        gather_stats_sql = """
        CALL DBMS_STATS.GATHER_TABLE_STATS(?, ?, NULL, 100, TRUE);
        """

        query_sql = """
        SELECT
            OWNER,
            TABLE_NAME,
            TABLESPACE_NAME,
            NUM_ROWS,
            BLOCKS,
            EMPTY_BLOCKS,
            AVG_SPACE,
            CHAIN_CNT,
            AVG_ROW_LEN,
            SAMPLE_SIZE,
            ROW_MOVEMENT,
            PARTITIONED,
            GLOBAL_STATS,
            USER_STATS,
            TO_CHAR(LAST_ANALYZED, 'YYYY-MM-DD') AS LAST_ANALYZED
        FROM DBA_TABLES
        WHERE OWNER = ?
          AND TABLE_NAME = ?
        """

        try:
            # 先收集统计信息
            await self._exec(
                sql=gather_stats_sql,
                source=source,
                params=[schema_name, table_name],
                max_rows=1,
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"收集统计信息失败: {str(e)}",
                "schema_name": schema_name,
                "table_name": table_name,
            }

        try:
            # 再查询最新统计信息
            rows = await self._exec(
                sql=query_sql,
                source=source,
                params=[schema_name, table_name],
                max_rows=1,
            )
            return {
                "success": True,
                "schema_name": schema_name,
                "table_name": table_name,
                "data": rows[0] if rows else None,
                "count": len(rows),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取表基础信息失败: {str(e)}",
                "schema_name": schema_name,
                "table_name": table_name,
            }

    async def _tool_analyze_columns(
        self,
        schema_name: str,
        table_name: str,
        top_n: int = 10,
    ) -> Dict[str, Any]:
        """分析表中所有列的统计特征（行数、空值、不重复值、最大/最小值及 Top N 频次）"""
        source = await self._get_current_datasource_name()

        # 先从数据字典获取该表的所有列及数据类型
        columns_sql = """
        SELECT
            COLUMN_NAME,
            DATA_TYPE
        FROM ALL_TAB_COLUMNS
        WHERE OWNER = ?
          AND TABLE_NAME = ?
        ORDER BY COLUMN_ID
        """

        try:
            columns = await self._exec(
                sql=columns_sql,
                source=source,
                params=[schema_name, table_name],
                max_rows=500,
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"获取列信息失败: {str(e)}",
                "schema_name": schema_name,
                "table_name": table_name,
            }

        if not columns:
            return {
                "success": True,
                "schema_name": schema_name,
                "table_name": table_name,
                "columns": [],
                "top_n": top_n,
            }

        # 逐列统计
        qualified_table = f"{schema_name}.{table_name}"
        analyzed_columns: List[Dict[str, Any]] = []

        for col in columns:
            col_name = col.get("COLUMN_NAME")
            data_type = col.get("DATA_TYPE")
            if not col_name:
                continue

            # 基础统计：总行数、空值数、不重复值数、最大值、最小值
            stats_sql = f"""
            SELECT
                COUNT(*) AS TOTAL_ROWS,
                COUNT(CASE WHEN {col_name} IS NULL THEN 1 END) AS NULL_COUNT,
                COUNT(DISTINCT {col_name}) AS DISTINCT_COUNT,
                MAX({col_name}) AS MAX_VALUE,
                MIN({col_name}) AS MIN_VALUE
            FROM {qualified_table}
            """

            # Top N 值及其出现次数
            top_sql = f"""
            SELECT
                {col_name} AS VALUE,
                COUNT(*) AS OCCUR_COUNT
            FROM {qualified_table}
            WHERE {col_name} IS NOT NULL
            GROUP BY {col_name}
            ORDER BY occur_count DESC
            FETCH FIRST ? ROWS ONLY
            """

            try:
                stats_rows = await self._exec(
                    sql=stats_sql,
                    source=source,
                    max_rows=1,
                )
                top_rows = await self._exec(
                    sql=top_sql,
                    source=source,
                    params=[top_n],
                    max_rows=top_n,
                )

                analyzed_columns.append(
                    {
                        "column_name": col_name,
                        "data_type": data_type,
                        "basic_stats": stats_rows[0] if stats_rows else None,
                        "top_values": top_rows,
                    }
                )
            except Exception as e:
                analyzed_columns.append(
                    {
                        "column_name": col_name,
                        "data_type": data_type,
                        "error": f"分析该列失败: {str(e)}",
                    }
                )

        return {
            "success": True,
            "schema_name": schema_name,
            "table_name": table_name,
            "top_n": top_n,
            "columns": analyzed_columns,
        }

    async def _tool_get_memory_stats(self) -> Dict[str, Any]:
        """获取缓冲池、缓存项、计划缓存、字典缓存等内存使用情况"""
        source = await self._get_current_datasource_name()

        sql = """
        SELECT 
            '缓冲池' AS 监控项,
            B.NAME AS 名称,
            B.N_PAGES AS 数量,
            B.FREE AS 空闲,
            B.N_DIRTY AS 脏页,
            ROUND(B.N_PAGES * B.PAGE_SIZE / 1024 / 1024, 2) AS 内存MB,
            ROUND(B.FREE * 100.0 / B.N_PAGES, 2) AS 使用率
        FROM V$BUFFERPOOL B
        UNION ALL
        SELECT 
            '缓存项' AS 监控项,
            TYPE$ AS 名称,
            COUNT(*) AS 数量,
            (SELECT COUNT(*) FROM V$CACHEITEM WHERE IN_POOL = 'N') AS 空闲,
            0 AS 脏页,
            ROUND(COUNT(*) * 1024 / 1024, 2) AS 内存MB,
            0 AS 使用率
        FROM V$CACHEITEM
        GROUP BY TYPE$
        UNION ALL
        SELECT 
            '计划缓存' AS 监控项,
            TYPE$ AS 名称,
            COUNT(*) AS 数量,
            0 AS 空闲,
            0 AS 脏页,
            ROUND(COUNT(*) * 1024 / 1024, 2) AS 内存MB,
            0 AS 使用率
        FROM V$CACHEPLN
        GROUP BY TYPE$
        UNION ALL
        SELECT 
            '字典缓存' AS 监控项,
            'DICT' AS 名称,
            COUNT(*) AS 数量,
            0 AS 空闲,
            0 AS 脏页,
            ROUND(COUNT(*) * 1024 / 1024, 2) AS 内存MB,
            0 AS 使用率
        FROM V$DICT_CACHE
        ORDER BY 监控项
        """

        try:
            rows = await self._exec(sql=sql, source=source, max_rows=1000)
            return {
                "success": True,
                "memory_stats": rows,
                "count": len(rows),
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"获取内存使用情况失败: {str(e)}",
            }

    # ============================================================
    # 监控与运维 Tools（tools.md 1.5）
    # ============================================================

    async def _tool_get_metrics(
        self, metric_names: Optional[List[str]] = None, time_range: Optional[str] = None
    ) -> Dict[str, Any]:
        """获取服务器监控指标（QPS、错误率、连接池使用率等）"""
        source = await self._get_current_datasource_name()

        metrics = {}

        try:
            # 会话统计
            session_sql = """
            SELECT
                COUNT(*) AS TOTAL_SESSIONS,
                COUNT(CASE WHEN STATE = 'ACTIVE' THEN 1 END) AS ACTIVE_SESSIONS,
                COUNT(CASE WHEN STATE = 'IDLE' THEN 1 END) AS IDLE_SESSIONS
            FROM V$SESSIONS
            """
            session_stats = await self._exec(sql=session_sql, source=source, max_rows=1)
            if session_stats:
                metrics["sessions"] = session_stats[0]

            # SQL 执行统计（最近一段时间）
            sql_stats_sql = """
            SELECT
                COUNT(*) AS TOTAL_SQL_EXECUTIONS,
                SUM(EXEC_TIME) AS TOTAL_EXEC_TIME,
                AVG(EXEC_TIME) AS AVG_EXEC_TIME,
                MAX(EXEC_TIME) AS MAX_EXEC_TIME,
                MIN(EXEC_TIME) AS MIN_EXEC_TIME,
                AVG(PHY_READ_CNT + LOGIC_READ_CNT) AS AVG_SCAN_ROWS,
                SUM(PHY_READ_CNT + LOGIC_READ_CNT) AS TOTAL_SCAN_ROWS,
                AVG(NET_BYTES_RECV + NET_BYTES_SEND) AS AVG_SCAN_BYTES,
                SUM(NET_BYTES_RECV + NET_BYTES_SEND) AS TOTAL_SCAN_BYTES
            FROM V$SQL_STAT
            WHERE START_TIME >= (SYSDATE - INTERVAL '1' HOUR)
            """
            sql_stats = await self._exec(sql=sql_stats_sql, source=source, max_rows=1)
            if sql_stats:
                metrics["sql_stats"] = sql_stats[0]

            # 查询执行指标（单个查询的详细指标）
            query_execution_sql = """
            SELECT
                SQL_ID,
                EXEC_TIME AS EXECUTION_TIME,
                LOGIC_READ_CNT + PHY_READ_CNT AS SCAN_ROWS,
                NET_BYTES_RECV + NET_BYTES_SEND AS SCAN_BYTES,
                LOGIC_READ_CNT AS LOGIC_READS,
                PHY_READ_CNT AS PHYSICAL_READS
            FROM V$SQL_STAT
            WHERE START_TIME >= (SYSDATE - INTERVAL '1' HOUR)
            ORDER BY EXEC_TIME DESC
            FETCH FIRST 100 ROWS ONLY
            """
            query_execution_stats = await self._exec(
                sql=query_execution_sql, source=source, max_rows=100
            )
            if query_execution_stats:
                metrics["query_execution"] = query_execution_stats

            # 查询性能报告指标（聚合统计）
            performance_report_sql = """
            SELECT
                COUNT(*) AS TOTAL_QUERIES,
                AVG(EXEC_TIME) AS AVG_EXECUTION_TIME,
                MAX(EXEC_TIME) AS MAX_EXECUTION_TIME,
                MIN(EXEC_TIME) AS MIN_EXECUTION_TIME
            FROM V$SQL_STAT
            WHERE START_TIME >= (SYSDATE - INTERVAL '1' HOUR)
            """
            performance_report = await self._exec(
                sql=performance_report_sql, source=source, max_rows=1
            )
            if performance_report:
                metrics["performance_report"] = performance_report[0]

            # 查询分布统计（按执行时间范围分组）
            query_distribution_sql = """
            SELECT
                CASE
                    WHEN EXEC_TIME < 0.001 THEN '< 1ms'
                    WHEN EXEC_TIME < 0.01 THEN '1-10ms'
                    WHEN EXEC_TIME < 0.1 THEN '10-100ms'
                    WHEN EXEC_TIME < 1.0 THEN '100-1000ms'
                    WHEN EXEC_TIME < 10.0 THEN '1-10s'
                    ELSE '> 10s'
                END AS TIME_RANGE,
                COUNT(*) AS QUERY_COUNT
            FROM V$SQL_STAT
            WHERE START_TIME >= (SYSDATE - INTERVAL '1' HOUR)
            GROUP BY
                CASE
                    WHEN EXEC_TIME < 0.001 THEN '< 1ms'
                    WHEN EXEC_TIME < 0.01 THEN '1-10ms'
                    WHEN EXEC_TIME < 0.1 THEN '10-100ms'
                    WHEN EXEC_TIME < 1.0 THEN '100-1000ms'
                    WHEN EXEC_TIME < 10.0 THEN '1-10s'
                    ELSE '> 10s'
                END
            ORDER BY time_range
            """
            query_distribution = await self._exec(
                sql=query_distribution_sql, source=source
            )
            if query_distribution:
                metrics["query_distribution"] = query_distribution

            # 锁等待统计
            lock_sql = """
            SELECT
                COUNT(*) AS LOCK_WAITS,
                COUNT(DISTINCT TRX_ID) AS BLOCKED_TRANSACTIONS
            FROM V$LOCK
            WHERE LTYPE = 'TX' AND LMODE IN ('S', 'X')
            """
            lock_stats = await self._exec(sql=lock_sql, source=source, max_rows=1)
            if lock_stats:
                metrics["locks"] = lock_stats[0]

            # 连接池指标（如果有连接池相关的系统视图）
            pool_sql = """
            SELECT
                USER_NAME,
                CLNT_IP,
                SESS_ID,
                STATE,
                CREATE_TIME
            FROM V$SESSIONS
            WHERE STATE IN ('ACTIVE', 'IDLE')
            ORDER BY CREATE_TIME DESC
            FETCH FIRST 100 ROWS ONLY
            """
            pool_stats = await self._exec(sql=pool_sql, source=source, max_rows=100)
            metrics["pool_connections"] = pool_stats

            # 如果指定了特定的指标名称，返回过滤后的结果
            if metric_names:
                filtered_metrics = {}
                for name in metric_names:
                    if name in metrics:
                        filtered_metrics[name] = metrics[name]
                metrics = filtered_metrics

            return {
                "success": True,
                "metrics": metrics,
                "metric_names": metric_names,
                "time_range": time_range,
                "timestamp": "SYSDATE",
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"获取监控指标失败: {str(e)}",
                "metric_names": metric_names,
                "time_range": time_range,
            }

    async def _tool_get_pool_status(self) -> Dict[str, Any]:
        """获取数据库连接池状态"""
        # 注意：DM8 没有传统意义上的连接池，这里返回会话状态作为连接池状态的替代
        source = await self._get_current_datasource_name()

        try:
            # 会话状态统计
            status_sql = """
            SELECT
                STATE,
            COUNT(*) AS COUNT
            FROM V$SESSIONS
            GROUP BY STATE
            ORDER BY STATE
            """
            status_stats = await self._exec(sql=status_sql, source=source)

            # 详细会话信息
            detail_sql = """
            SELECT
                SESS_ID,
                USER_NAME,
                CLNT_IP,
                STATE,
                CREATE_TIME,
                LAST_RECV_TIME,
                LAST_SEND_TIME,
                SQL_TEXT
            FROM V$SESSIONS
            ORDER BY CREATE_TIME DESC
            FETCH FIRST 50 ROWS ONLY
            """
            detail_stats = await self._exec(sql=detail_sql, source=source, max_rows=50)

            # 计算连接池相关指标
            total_connections = sum(stat.get("COUNT", 0) for stat in status_stats)
            active_connections = next(
                (
                    stat.get("COUNT", 0)
                    for stat in status_stats
                    if stat.get("STATE") == "ACTIVE"
                ),
                0,
            )

            return {
                "success": True,
                "pool_status": {
                    "total_connections": total_connections,
                    "active_connections": active_connections,
                    "idle_connections": total_connections - active_connections,
                    "connection_states": status_stats,
                },
                "connection_details": detail_stats,
                "timestamp": "SYSDATE",
            }

        except Exception as e:
            return {"success": False, "error": f"获取连接池状态失败: {str(e)}"}

    async def _tool_get_worker_status(self) -> Dict[str, Any]:
        """获取执行器 / worker 运行状态"""
        source = await self._get_current_datasource_name()

        try:
            # DM8 的执行器状态（通过会话和SQL执行状态获取）
            worker_sql = """
            SELECT
                SESS_ID,
                USER_NAME,
                STATE,
                SQL_TEXT,
                CREATE_TIME,
                LAST_RECV_TIME
            FROM V$SESSIONS
            WHERE STATE = 'ACTIVE'
            FETCH FIRST 20 ROWS ONLY
            """
            workers = await self._exec(sql=worker_sql, source=source, max_rows=20)

            # SQL 执行统计
            exec_sql = """
            SELECT
                SESSID,
                SQL_ID,
                EXEC_TIME,
                START_TIME,
                END_TIME,
                PARSE_TIME,
                LOGIC_READ_CNT,
                PHY_READ_CNT,
                EXEC_TIME
            FROM V$SQL_STAT
            WHERE END_TIME IS NULL OR END_TIME >= (SYSDATE - INTERVAL '1' HOUR)
            ORDER BY START_TIME DESC
            FETCH FIRST 10 ROWS ONLY
            """
            executions = await self._exec(sql=exec_sql, source=source, max_rows=10)

            # 统计信息
            total_workers = len(workers)
            active_workers = len([w for w in workers if w.get("STATE") == "ACTIVE"])

            return {
                "success": True,
                "worker_status": {
                    "total_workers": total_workers,
                    "active_workers": active_workers,
                    "idle_workers": total_workers - active_workers,
                },
                "active_workers": workers,
                "current_executions": executions,
                "timestamp": "SYSDATE",
            }

        except Exception as e:
            return {"success": False, "error": f"获取执行器状态失败: {str(e)}"}
