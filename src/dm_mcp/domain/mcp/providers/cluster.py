from typing import Annotated, Any

from pydantic import Field
from dm_mcp.common import messages
from dm_mcp.domain.mcp.providers.base import BaseDataSourceMCPProvider
from dm_mcp.domain.datasource.services.datasource import DataSourceService


class DpcClusterMCPProvider(BaseDataSourceMCPProvider):
    """DPC cluster tools provider."""

    def __init__(self, datasource_service: DataSourceService) -> None:
        super().__init__(datasource_service)
        self._register_routes()

    # ============================================================
    # MCP Tool registration
    # ============================================================

    def _register_routes(self) -> None:
        """
        注册 DPC 集群相关的 MCP Tools。

        该方法只负责将业务方法通过 `@self.mcp.tool` 暴露为 MCP 工具，
        不承载具体 SQL 与聚合逻辑，便于后续扩展和维护。
        """

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_sp_instances():
            """
            列出当前节点可见的 DPC SP（存储节点）实例列表。
            DPC 集群下查看 SP 实例；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_sp_instances()

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_instances():
            """
            返回 DPC 集群实例列表（IP、端口、模式、状态）。
            适用场景：DPC 集群拓扑查看、实例状态监控；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_instances()

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_raft_list():
            """
            返回 DPC RAFT 组列表（ID、模式、是否有效、任期等）。
            适用场景：DPC 高可用/一致性组查看；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_raft_list()

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_instance_raft_topology():
            """
            返回实例与 RAFT 组的映射拓扑。
            适用场景：理解 DPC 实例归属哪个 RAFT 组；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_instance_raft_topology()

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_esession_detail():
            """
            返回 DPC 内部会话（ESESSION）列表（站点、会话数、事务数等）。
            适用场景：DPC 分布式会话排查；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_esession_detail()

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_esession_summary():
            """
            返回按站点聚合的 ESESSION 汇总统计。
            适用场景：DPC 各站点会话分布概览；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_esession_summary()

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_stask_threads_by_exec_id(
            exec_id: Annotated[int, Field(description="目标执行的唯一标识 ID")],
        ):
            """
            按 exec_id 返回 STASK 线程运行信息。
            适用场景：DPC 执行追踪、线程级排查；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_stask_threads_by_exec_id(exec_id=exec_id)

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_stask_threads_top(
            top_n: Annotated[int, Field(description="返回条数，默认 50")] = 50,
        ):
            """
            返回按 TIME_USED 排序的 STASK 线程 Top N。
            适用场景：DPC 耗时最长线程排查；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_stask_threads_top(top_n=top_n)

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_sql_node_history_by_exec_id(
            exec_id: Annotated[int, Field(description="目标执行的唯一标识 ID")],
        ):
            """
            按 exec_id 返回 SQL 节点历史记录。
            适用场景：DPC SQL 执行路径分析；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_sql_node_history_by_exec_id(exec_id=exec_id)

        @self.mcp.tool(group="dpc", requires_token_auth=True)
        async def get_dpc_sql_node_top(
            top_n: Annotated[int, Field(description="返回条数，默认 50")] = 50,
        ):
            """
            返回按总 TIME_USED 聚合排序的 SQL 节点类型 Top N。
            适用场景：DPC SQL 节点耗时分析；仅 DPC 部署可用。
            """
            return await self._tool_get_dpc_sql_node_top(top_n=top_n)

    # ============================================================
    # Helpers
    # ============================================================

    async def _get_current_datasource(self):
        current_source_id = self.context.datasource.datasource_id
        datasource = await self.datasource_service.get_datasource_by_id(
            current_source_id
        )
        if datasource is None:
            raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND_BY_ID)
        return datasource

    async def _get_dpc_source(self) -> str:
        datasource = await self._get_current_datasource()
        if datasource.deploy_type != "dmdpc":
            raise ValueError(
                messages.MSG_DATASOURCE_DPC_TYPE_MISMATCH.format(deploy_type=datasource.deploy_type)
            )
        return datasource.name

    async def _exec(
        self,
        *,
        sql: str,
        params: Any | None = None,
        max_rows: int = 2000,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        source = await self._get_dpc_source()
        result = await self.datasource_service.execute_query(
            sql=sql,
            source=source,
            params=params,
            max_rows=max_rows,
            timeout=timeout,
        )
        rows = result.get("result", [])
        return rows if isinstance(rows, list) else []

    # ============================================================
    # Tools
    # ============================================================

    async def _tool_get_dpc_sp_instances(self) -> dict[str, Any]:
        sql = "SELECT * FROM V$DPC_EDCT_INSTANCE WHERE MODE = 'SP'"
        rows = await self._exec(sql=sql, max_rows=2000)
        return {"mode": "SP", "instances": rows, "count": len(rows)}

    async def _tool_get_dpc_instances(self) -> dict[str, Any]:
        sql = """
        SELECT
          RAFT_ID,
          INST_ID,
          NAME,
          MODE,
          IP_INTERNAL,
          IP_EXTERNAL,
          XMAL_PORT,
          INST_PORT,
          SYS_MODE,
          SYS_STATUS
        FROM V$DPC_EDCT_INSTANCE
        ORDER BY MODE, RAFT_ID, INST_ID
        """
        rows = await self._exec(sql=sql, max_rows=2000)
        return {"instances": rows, "count": len(rows)}

    async def _tool_get_dpc_raft_list(self) -> dict[str, Any]:
        sql = """
        SELECT
          RAFT_ID,
          DPC_MODE,
          IS_VALID,
          NAME,
          L_TERM_ID,
          DISCARD_TICK
        FROM V$DPC_EDCT_RAFT
        ORDER BY RAFT_ID
        """
        rows = await self._exec(sql=sql, max_rows=2000)
        return {"rafts": rows, "count": len(rows)}

    async def _tool_get_dpc_instance_raft_topology(self) -> dict[str, Any]:
        sql = """
        SELECT
          i.MODE,
          i.NAME        AS INSTANCE_NAME,
          i.RAFT_ID,
          r.NAME        AS RAFT_NAME,
          r.IS_VALID,
          r.L_TERM_ID,
          i.IP_INTERNAL,
          i.INST_PORT,
          i.SYS_STATUS
        FROM V$DPC_EDCT_INSTANCE i
        LEFT JOIN V$DPC_EDCT_RAFT r
          ON r.RAFT_ID = i.RAFT_ID
        ORDER BY i.MODE, i.RAFT_ID, i.INST_ID
        """
        rows = await self._exec(sql=sql, max_rows=2000)
        return {"topology": rows, "count": len(rows)}

    async def _tool_get_dpc_esession_detail(self) -> dict[str, Any]:
        sql = """
        SELECT
          EID,
          SRC_SITEID,
          SESS_ID,
          N_SITE,
          N_TRX_SITE,
          N_STMT,
          STHD_GRP_ID,
          THRD_ID
        FROM V$DPC_ESESS
        ORDER BY N_TRX_SITE DESC, N_STMT DESC
        """
        rows = await self._exec(sql=sql, max_rows=2000)
        return {"esessions": rows, "count": len(rows)}

    async def _tool_get_dpc_esession_summary(self) -> dict[str, Any]:
        sql = """
        SELECT
          SRC_SITEID,
          COUNT(*)          AS SAMPLES,
          SUM(TIME_USED)    AS TOTAL_TIME_USED,
          MAX(TIME_USED)    AS MAX_TIME_USED
        FROM V$DPC_STMT
        GROUP BY SRC_SITEID
        ORDER BY SAMPLES DESC
        """
        rows = await self._exec(sql=sql, max_rows=2000)
        return {"summary": rows, "count": len(rows)}

    async def _tool_get_dpc_stask_threads_by_exec_id(
        self, exec_id: int
    ) -> dict[str, Any]:
        if exec_id is None:
            raise ValueError(messages.MSG_EXEC_ID_REQUIRED)
        sql = """
        SELECT
          EXEC_ID,
          STASK_NO,
          THRD_NO,
          PLAN_NO,
          START_TIME,
          TIME_USED,
          FIRST_ROW_USED,
          N_ROWS_SEND,
          N_BYTES_SEND,
          N_ROWS_RECV,
          IS_OVER,
          THRD_ID,
          SESS_ID
        FROM V$DPC_STASK_THRD
        WHERE EXEC_ID = ?
        ORDER BY STASK_NO, THRD_NO
        """
        rows = await self._exec(sql=sql, params=[exec_id], max_rows=2000)
        return {"exec_id": exec_id, "threads": rows, "count": len(rows)}

    async def _tool_get_dpc_stask_threads_top(self, top_n: int = 50) -> dict[str, Any]:
        if top_n <= 0:
            raise ValueError(messages.MSG_TOP_N_MUST_BE_POSITIVE)
        sql = """
        SELECT
          EXEC_ID,
          STASK_NO,
          THRD_NO,
          TIME_USED,
          FIRST_ROW_USED,
          N_ROWS_SEND,
          N_BYTES_SEND,
          IS_OVER
        FROM V$DPC_STASK_THRD
        ORDER BY TIME_USED DESC
        FETCH FIRST ? ROWS ONLY
        """
        rows = await self._exec(sql=sql, params=[top_n], max_rows=top_n)
        return {"top_n": top_n, "threads": rows, "count": len(rows)}

    async def _tool_get_dpc_sql_node_history_by_exec_id(
        self, exec_id: int
    ) -> dict[str, Any]:
        if exec_id is None:
            raise ValueError(messages.MSG_EXEC_ID_REQUIRED)
        sql = """
        SELECT
          EXEC_ID,
          SEQ_NO,
          NODE,
          TYPE$,
          N_ENTER,
          TIME_USED,
          MEM_USED,
          DISK_USED,
          STASK_NO,
          THRD_NO
        FROM V$SQL_NODE_HISTORY
        WHERE EXEC_ID = ?
        ORDER BY TIME_USED DESC
        """
        rows = await self._exec(sql=sql, params=[exec_id], max_rows=2000)
        return {"exec_id": exec_id, "nodes": rows, "count": len(rows)}

    async def _tool_get_dpc_sql_node_top(self, top_n: int = 50) -> dict[str, Any]:
        if top_n <= 0:
            raise ValueError(messages.MSG_TOP_N_MUST_BE_POSITIVE)
        sql = """
        SELECT
          TYPE$,
          COUNT(*)          AS SAMPLES,
          SUM(TIME_USED)    AS TOTAL_TIME_USED,
          MAX(TIME_USED)    AS MAX_TIME_USED
        FROM V$SQL_NODE_HISTORY
        GROUP BY TYPE$
        ORDER BY TOTAL_TIME_USED DESC
        FETCH FIRST ? ROWS ONLY
        """
        rows = await self._exec(sql=sql, params=[top_n], max_rows=top_n)
        return {"top_n": top_n, "nodes": rows, "count": len(rows)}
