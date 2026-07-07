import asyncio
import logging
import time
from typing import Annotated, Any

from pydantic import Field
from dm_mcp.core.exceptions import MCPExecutionError
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.datasource.services.pool import AsyncPoolService, _validate_identifier
from dm_mcp.domain.mcp.mappers import inspection_mapper as _mapper
from dm_mcp.domain.mcp.providers.base import BaseDataSourceMCPProvider
from dm_mcp.domain.mcp.providers.sql import inspection_sql as _sql

logger = logging.getLogger(__name__)


class InspectionMCPProvider(BaseDataSourceMCPProvider):
    """数据库巡检工具 Provider。"""

    _EXPLAIN_ALLOWED_PREFIXES = ("SELECT", "WITH")
    _EXPLAIN_SESSION_PARAMETER_CACHE_TTL_SEC = 300.0
    _explain_session_parameter_cache: dict[
        int, tuple[float, list[dict[str, Any]]]
    ] = {}

    def __init__(
        self,
        datasource_service: DataSourceService,
    ) -> None:
        super().__init__(datasource_service)
        self._register_routes()

    def _register_routes(self) -> None:
        """注册 MCP Tool 路由"""

        # 执行计划分析
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_sql_explain_plan(
            sql: Annotated[str, Field(description="要分析执行计划的 SQL")],
            schema: Annotated[str | None, Field(description="可选 schema；不传用数据源默认")] = None,
        ):
            """
            真实执行 SQL 后返回执行计划与 IO 统计（类似 disql AUTOTRACE TRACE）。

            响应字段：
            - exec_id：本次执行 ID，可在库内 CALL ET(exec_id)
            - origin_plan：dmPython Connection.explain 原始计划树文本
            - statistics.statement：语句级 logical_reads、physical_reads（含 0）
            - statistics.operators：按 seq 聚合 ET 与 node 统计（time_us、time_percent、rank、
              memory_kb、disk_kb、n_enter、hash_used_cells、hash_conflict、dhash3_used_cells、
              dhash3_conflict、hash_same_value）；相关算子附带 ini（V$PARAMETER 参数名 -> value）

            仅支持 SELECT；允许 /*+ Hint */、块注释与 -- 行注释；禁止分号（多语句）。
            """
            return await self._tool_get_sql_explain_plan(sql=sql, schema=schema)

        # 01 慢会话
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def find_long_active_sessions(
            threshold_ms: Annotated[int, Field(description="执行时间阈值，单位毫秒。仅返回运行时间达到或超过该值的活动会话")],
        ):
            """
            检索执行耗时超过预设阈值的活跃会话及核心关联标识。

            扫描底层动态性能视图 V$SESSIONS，过滤并提取当前处于活跃状态且单次运行时间达到或超过 threshold_ms 的数据库连接。执行完毕后，将返回定位性能瓶颈的关键锚点数据，主要包含会话 ID、引发异常资源消耗的事务与 SQL 上下文，以及会话所在的客户端 IP 和用户。

            作为宏观性能诊断的首选切入点，适用于排查系统整体负载突增、CPU/IO 资源饱和或业务大面积响应延迟等场景。侧重于捕获因执行计划不佳、全表扫描或复杂聚合计算等原因导致的慢查询实体。若故障表征已明确指向并发写入卡顿、事务排队等待或潜在死锁，则建议优先调用锁与阻塞相关的检测工具。
            """
            return await self._tool_find_long_active_sessions(threshold_ms=threshold_ms)

        # 02 SQL 资源热点
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def find_sql_resource_hotspots(
            top_n: Annotated[int, Field(description="每个维度返回的条数，默认 10。四个维度各自取前 top_n，合并去重后最终返回数量不超过 4 * top_n")] = 10,
        ):
            """
            检索资源消耗最高的 SQL 语句，覆盖 IO、读、CPU、解析四个维度。

            分别从 V$SQL_STAT 与 V$SQL_STAT_HISTORY 中按 IO_WAIT_TIME、LOGIC_READ_CNT、EXEC_CPU、PARSE_ELAPSD 四个维度各自取前 top_n 条，合并去重后按综合得分排序返回。无需预设阈值，自动适应不同系统的基线。

            适用于宏观性能诊断的入口工具。当系统整体负载升高但尚未定位到具体会话或事务时，优先调用此工具筛选出资源消耗最高的 SQL 列表，再结合 get_sql_execution_stats 做深度下钻。
            """
            return await self._tool_find_sql_resource_hotspots(top_n=top_n)

        # 03 长等待线程
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def find_long_waiting_threads(
            threshold_ms: Annotated[int, Field(description="线程等待时间阈值，单位毫秒。仅返回等待时间达到或超过该值的活动线程")],
        ):
            """
            检索处于长期等待状态的活动线程及其关联会话。

            扫描系统线程视图 V$THREADS，过滤并提取等待时间超过预设阈值或处于非正常等待状态的线程记录。执行后将返回异常线程 ID、线程描述、当前等待状态以及关联的会话 ID。

            适用于排查数据库实例整体 CPU 负载飙升、后台服务假死或系统响应全面迟缓等底层资源异常场景。当常规的慢查询或锁阻塞工具未能发现明显瓶颈点时，建议调用此工具从操作系统线程调度的维度切入，定位问题线程后，通过其关联的会话 ID 向上溯源至具体的业务会话。
            """
            return await self._tool_find_long_waiting_threads(threshold_ms=threshold_ms)

        # 04 阻塞链
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_blocking_chain(
            transaction_id: Annotated[int | None, Field(description="可选。指定事务 ID 进行定向溯源，不传则返回全局所有排队事务")] = None,
        ):
            """
            检索事务阻塞链条，附带锁资源详情与阻塞源头标识。

            解析底层事务等待视图 V$TRXWAIT 与锁视图 V$LOCK，提取当前受阻的事务及其等待的阻塞方，关联 V$SESSIONS 提取双方的可读业务信息（会话、SQL 文本），并过滤掉 IGNORABLE 标记非零的可忽略锁。支持输入特定事务 ID 进行定向溯源，不传参数则返回全局所有排队事务。

            适用于快速构建数据库内部的并发阻塞拓扑图。相比于分析零散的底层锁状态，此工具能直观暴露出"谁在等谁"的明确因果关系，并可通过 is_root_blocker 字段快速定位链条的源头节点。建议在确认系统存在事务卡顿或死锁风险时优先调用。
            """
            return await self._tool_get_blocking_chain(transaction_id=transaction_id)

        # 05 会话上下文
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_session_context(
            session_id: Annotated[int, Field(description="目标会话 ID")],
            delta_seconds: Annotated[int, Field(description="等待事件采样间隔。0（默认）返回当前累积值；大于 0 返回该时间窗口内的等待增量")] = 0,
        ):
            """
            获取指定会话的全维度上下文信息。

            以会话 ID 为锚点，聚合查询 V$SESSIONS、V$TRX、V$SQL_STAT、V$THREADS、V$SESSION_EVENT 及 V$SESSION_WAIT_HISTORY 等多个动态性能视图，返回该会话的完整运行画像。涵盖会话基本信息、当前绑定事务、正在执行的 SQL 及其资源开销、底层线程状态，以及等待事件信息。
            """
            return await self._tool_get_session_context(
                session_id=session_id, delta_seconds=delta_seconds
            )

        # 06 事务上下文
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_transaction_context(
            transaction_id: Annotated[int, Field(description="目标事务 ID。返回该事务的完整上下文信息，包括事务状态、关联会话、持有的锁、等待的锁以及在阻塞链中的位置")],
        ):
            """
            获取指定事务的全维度上下文信息。

            以事务 ID 为锚点，聚合查询 V$TRX、V$SESSIONS、V$LOCK 及 V$TRXWAIT 等视图，返回该事务的完整画像。涵盖事务自身状态、关联会话信息、当前持有的锁、正在等待的锁，以及在全局阻塞链中的位置（被谁阻塞 / 阻塞了谁）。

            作为事务级排障的核心下钻工具，适用于在诊断入口定位到异常事务（如持有阻塞锁的源头事务、长时间未提交的事务）后的深度分析。一次调用即可替代原先需要分别查询事务到会话、事务到锁等多个单维度工具的流程。
            """
            return await self._tool_get_transaction_context(
                transaction_id=transaction_id
            )

        # 07 对象锁上下文
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_object_lock_context(
            object_id: Annotated[int, Field(description="目标对象 ID。返回该对象上当前所有锁资源及并发拓扑")],
        ):
            """
            基于对象 ID 检索该对象上附加的所有锁资源与并发拓扑。

            接收特定对象 ID 作为参数，扫描全系统锁视图 V$LOCK，提取当前作用于该对象及其数据行上的所有锁记录，并按持有者（已上锁成功）与等待者（上锁等待中）分组。关联 V$SESSIONS 与 V$TRX 补充事务状态、用户名、客户端 IP 及当前 SQL 等业务上下文。

            适用于已知特定业务对象成为并发瓶颈时的定向排查。当监控告警指向某张核心表或字典对象读写停滞时，调用此工具可直观呈现该对象上的多事务排队情况，界定锁争用的具体形态（如对象级结构变更冲突或行级更新排队），为追溯阻塞源头事务提供直接的结构化依据。
            """
            return await self._tool_get_object_lock_context(object_id=object_id)

        # 08 SQL 执行统计
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_sql_execution_stats(
            sql_id: Annotated[int, Field(description="目标 SQL 语句 ID。返回该语句的执行统计与资源消耗详情")],
            delta_seconds: Annotated[int, Field(description="采样间隔，单位秒。0（默认）返回累积值；大于 0 返回该时间窗口内的增量数据")] = 0,
        ):
            """
            基于 SQL ID 获取目标语句的执行统计与资源消耗详情。

            接收特定 SQL ID 作为输入参数，解析底层动态性能视图 V$SQL_STAT 及历史执行记录 V$SQL_STAT_HISTORY，提取并返回该语句的执行计划、调用频次、执行耗时以及 CPU 和 I/O 资源占用等核心性能指标。

            作为慢查询排查链路的深度剖析工具，适用于在宏观层面定位到异常会话并提取出可疑 SQL ID 后的进一步诊断。调用此工具可明确特定语句是否存在执行计划突变、索引失效或资源过度消耗等问题，为评估性能瓶颈及后续的 SQL 调优提供直接的量化依据。当故障现象明确为单点查询缓慢而非全局锁等待时，该工具具有最高的使用优先级。
            """
            return await self._tool_get_sql_execution_stats(
                sql_id=sql_id, delta_seconds=delta_seconds
            )

        # 09 缓冲池统计
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_buffer_pool_stats():
            """
            检索页面缓冲区的工作负荷、缓存命中率及底层 I/O 读写统计。

            解析页面缓冲区动态视图 V$BUFFERPOOL，提取各缓冲池的内存容量分配以及空闲与脏页分布。核心逻辑包含自动计算并返回基于 64 位防溢出指标的真实缓存命中率以及逻辑与物理读总次数。

            适用于诊断数据库系统级 I/O 瓶颈和内存缓存效率问题。当排查链路已排除锁并发阻塞，但系统整体响应迟缓或底层磁盘 I/O 持续高企时，建议调用此工具。重点关注返回的缓存命中率，若该指标显著偏低（如低于 90%）或脏页堆积严重，可据此判定系统存在缓存击穿或写压力过载，为调整缓冲池配置或排查大批量全表扫描提供宏观依据。
            """
            return await self._tool_get_buffer_pool_stats()

        # 10 内存池使用
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_memory_pool_usage(
            delta_seconds: Annotated[int, Field(description="内存分配活动采样间隔。0（默认）返回当前大小分布；大于 0 返回该时间窗口内的增量数据")] = 0,
        ):
            """
            评估数据库全局及各类内存池的分配状态与空间使用率。

            扫描底层内存池视图 V$MEM_POOL，自动将零碎的共享池组件进行降噪与聚合处理，提取系统当前各核心内存模块的总大小、平均/最大分配值及目标建议大小。自动计算并返回各模块的真实分配使用占比。

            适用于排查数据库实例内存耗尽（OOM）、持续性内存泄漏或特定内部组件的分配瓶颈。当系统抛出内存不足异常，或监控发现数据库进程物理内存持续飙升且不释放时，应优先调用此工具。通过审查返回结果中分配占比逼近阈值（如超过 95%）或总分配量远超目标大小的模块，可快速锚定引发内存异常膨胀的具体区域。
            """
            return await self._tool_get_memory_pool_usage(delta_seconds=delta_seconds)

        # 11 系统统计增量
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_sysstat_delta(
            delta_seconds: Annotated[int, Field(description="采样间隔，单位秒。控制两次采样的时间窗口长度，据此计算各运行指标的增量与每秒速率。必须大于 0")],
        ):
            """
            采集系统全局运行指标，计算并返回指定时间窗口内的性能状态差值与速率。

            解析系统级统计对象视图 V$SYSSTAT，返回指定时间窗口内关键运行指标的增量与速率。支持按类别聚合，涵盖 SQL 执行、事务处理、I/O 读写、网络收发等核心维度。

            作为宏观负载诊断与基线评估的度量工具，适用于排查突发流量洪峰、性能瞬时抖动或物理资源瓶颈。当需要量化数据库当前真实的 QPS、TPS 或 IOPS，以确认系统整体是否触及硬件天花板时，应优先调用此工具。
            """
            return await self._tool_get_sysstat_delta(delta_seconds=delta_seconds)

        # 12 缓存热点对象
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_cache_hot_objects(
            delta_seconds: Annotated[int, Field(description="采样间隔，单位秒。0（默认）返回当前累积访问计数；大于 0 返回该时间窗口内的增量访问计数")] = 0,
        ):
            """
            检索系统缓存中的热点页，并将其映射汇总为具体的表或索引对象。

            解析系统热点页缓存视图 V$HOTPAGE，提取访问频次最高的内存页记录，将热点页映射为具体的字典对象。

            适用于 I/O 调优、内存挤占分析及异常 CPU 负载的根因溯源。当调用 get_buffer_pool_stats 发现逻辑读极高或命中率下降，亦或系统整体 CPU 利用率飙升但无明显锁阻塞时，建议调用此工具。通过审查返回的热点对象：若某表的数据页访问频次呈压倒性占比，提示极可能存在缺乏索引导致的大表全表扫描；若某索引页异常火热，则需关注是否存在由于高并发范围扫描导致的索引热点块争用。
            """
            return await self._tool_get_cache_hot_objects(delta_seconds=delta_seconds)

        # 13 缓存热点对象（索引版）
        @self.mcp.tool(group="inspect", requires_token_auth=True)
        async def get_cache_hot_objects_by_index(
            delta_seconds: Annotated[int, Field(description="采样间隔，单位秒。0（默认）返回当前累积访问计数；大于 0 返回该时间窗口内的增量访问计数")] = 0,
        ):
            """
            检索系统缓存中的热点页，通过索引元数据将其映射为具体的表或索引对象。

            解析系统热点页缓存视图 V$HOTPAGE，通过 INDEXID 关联 SYSOBJECTS 获取索引及所属表信息，并处理分区表场景（通过 SYSHPARTTABLEINFO 找到基表）。相比 get_cache_hot_objects，此工具不依赖 dbms_page.data_page_tname_get 函数，而是通过字典对象元数据直接解析热点页的归属关系，适用于函数不可用或需要精确获取表/索引 ID 的场景。

            适用于 I/O 调优、内存挤占分析及异常 CPU 负载的根因溯源。当调用 get_buffer_pool_stats 发现逻辑读极高或命中率下降，亦或系统整体 CPU 利用率飙升但无明显锁阻塞时，建议调用此工具。通过审查返回的热点对象：若某表的数据页访问频次呈压倒性占比，提示极可能存在缺乏索引导致的大表全表扫描；若某索引页异常火热，则需关注是否存在由于高并发范围扫描导致的索引热点块争用。
            """
            return await self._tool_get_cache_hot_objects_by_index(
                delta_seconds=delta_seconds
            )

    # ============================================================
    # 公共辅助方法
    # ============================================================

    async def _two_point_sample(
        self,
        sql: str,
        params: Any = None,
        delta_seconds: int = 0,
        max_rows: int = 2000,
    ) -> tuple[list[dict], list[dict] | None, str]:
        """两次采样。返回 (curr_rows, prev_rows_or_None, mode)"""
        if delta_seconds <= 0:
            rows = await self._exec(sql=sql, params=params, max_rows=max_rows)
            return rows, None, "cumulative"
        prev = await self._exec(sql=sql, params=params, max_rows=max_rows)
        await asyncio.sleep(delta_seconds)
        curr = await self._exec(sql=sql, params=params, max_rows=max_rows)
        return curr, prev, "delta"

    # ============================================================
    # 工具实现
    # ============================================================

    @staticmethod
    def _validate_explain_sql(sql: str) -> None:
        """EXPLAIN 入参校验：禁止多语句；允许优化器 Hint 与普通 SQL 注释。"""
        if ";" in sql:
            raise MCPExecutionError(
                "EXPLAIN_REJECTED", "SQL 包含分号（不允许多语句）"
            )
        if len(sql) > 10000:
            raise MCPExecutionError(
                "EXPLAIN_REJECTED", "SQL 长度超过限制（最大 10000 字符）"
            )
        i = 0
        n = len(sql)
        while i < n:
            if i + 1 < n and sql[i : i + 2] == "/*":
                end = sql.find("*/", i + 2)
                if end < 0:
                    raise MCPExecutionError(
                        "EXPLAIN_REJECTED", "SQL 包含未闭合的块注释（/* ... */）"
                    )
                i = end + 2
                continue
            if i + 1 < n and sql[i : i + 2] == "--":
                nl = sql.find("\n", i + 2)
                i = nl + 1 if nl >= 0 else n
                continue
            i += 1

    @staticmethod
    def _explain_row_to_dict(cur: Any, row: tuple[Any, ...]) -> dict[str, Any]:
        return dict(zip([d[0] for d in cur.raw.description], row))

    @staticmethod
    async def _explain_fetchone_dict(
        cur: Any, sql: str, params: list[Any] | None = None
    ) -> dict[str, Any] | None:
        await cur.execute(sql, params or [])
        if cur.raw.description:
            row = await cur.fetchone()
            if row:
                return InspectionMCPProvider._explain_row_to_dict(cur, row)
        return None

    @staticmethod
    async def _explain_fetchall_dicts(
        cur: Any, sql: str, params: list[Any] | None = None
    ) -> list[dict[str, Any]]:
        await cur.execute(sql, params or [])
        if not cur.raw.description:
            return []
        cols = [d[0] for d in cur.raw.description]
        return [dict(zip(cols, r)) for r in await cur.fetchall()]

    @staticmethod
    async def _explain_fetch_et_rows(cur: Any, exec_id: int) -> list[dict[str, Any]]:
        await cur.execute(_sql.call_et(exec_id))
        if not cur.raw.description:
            return []
        cols = [d[0] for d in cur.raw.description]
        return [dict(zip(cols, r)) for r in await cur.fetchall()]

    @classmethod
    async def _explain_get_session_parameters(
        cls,
        pool: Any,
        pool_service: AsyncPoolService,
        cur: Any,
    ) -> list[dict[str, Any]]:
        cache_key = id(pool)
        now = time.monotonic()
        cached = cls._explain_session_parameter_cache.get(cache_key)
        if cached and now - cached[0] < cls._EXPLAIN_SESSION_PARAMETER_CACHE_TTL_SEC:
            return cached[1]
        try:
            rows = await cls._explain_fetchall_dicts(
                cur, _sql.get_explain_session_parameters()
            )
            rows = pool_service.convert_bytes_for_json(rows)
        except Exception as exc:
            logger.debug("V$PARAMETER for explain trace: %s", exc)
            rows = []
        cls._explain_session_parameter_cache[cache_key] = (now, rows)
        return rows

    async def _collect_explain_on_connection(
        self,
        conn: Any,
        pool: Any,
        sql: str,
        *,
        schema: str | None,
        max_rows: int,
    ) -> dict[str, Any]:
        """单连接上采集 get_sql_explain_plan 所需的计划与运行时统计。"""
        pool_service = self.datasource_service.pool_service
        cur = await conn.cursor()
        try:
            if schema:
                _validate_identifier(schema)
                await cur.execute(f"SET SCHEMA {schema}")

            try:
                await cur.execute(_sql.enable_explain_monitor_sql())
            except Exception as exc:
                logger.debug("explain trace monitor block skipped: %s", exc)

            await cur.execute(sql)
            description = getattr(cur.raw, "description", None)
            if description:
                await cur.fetchmany(max_rows if max_rows > 0 else 200)

            exec_id = getattr(cur.raw, "execid", None)
            dm_conn = getattr(cur.raw, "connection", None)
            explain_task: asyncio.Task[str] | None = None
            if dm_conn is not None:
                explain_task = asyncio.create_task(
                    asyncio.to_thread(dm_conn.explain, sql)
                )

            sql_stat: dict[str, Any] | None = None
            node_rows: list[dict[str, Any]] = []
            et_rows: list[dict[str, Any]] = []

            if exec_id is not None:
                try:
                    sql_stat = await self._explain_fetchone_dict(
                        cur, _sql.get_runtime_stat_by_exec_id(), [exec_id]
                    )
                except Exception as exc:
                    logger.debug("runtime stat for explain trace: %s", exc)

                try:
                    et_rows = await self._explain_fetch_et_rows(cur, exec_id)
                except Exception as exc:
                    logger.debug("ET for explain trace: %s", exc)

                if not et_rows:
                    try:
                        node_rows = await self._explain_fetchall_dicts(
                            cur, _sql.get_sql_node_history_by_exec_id(), [exec_id]
                        )
                    except Exception as exc:
                        logger.debug(
                            "V$SQL_NODE_HISTORY for explain trace: %s", exc
                        )

            session_parameter_rows = await self._explain_get_session_parameters(
                pool, pool_service, cur
            )

            explain_text = ""
            if explain_task is not None:
                try:
                    explain_text = await explain_task
                except Exception as exc:
                    logger.debug("dmPython explain for trace: %s", exc)
            explain_text = explain_text or ""

            return {
                "explain_text": explain_text,
                "exec_id": exec_id,
                "sql_stat": sql_stat,
                "node_rows": pool_service.convert_bytes_for_json(node_rows),
                "et_rows": et_rows,
                "session_parameter_rows": session_parameter_rows,
            }
        finally:
            try:
                await cur.close()
            except Exception:
                pass

    async def _collect_explain_trace(
        self,
        *,
        sql: str,
        schema: str | None = None,
        max_rows: int = 200,
    ) -> dict[str, Any]:
        """真实执行 SQL 并在同连接上采集计划与运行时统计。"""
        source = await self._get_current_datasource_name()
        pool = await self.datasource_service.get_pool(source)
        pool_service = self.datasource_service.pool_service

        async def _run(conn: Any) -> dict[str, Any]:
            return await self._collect_explain_on_connection(
                conn,
                pool,
                sql,
                schema=schema,
                max_rows=max_rows,
            )

        return await pool_service.run_in_session(pool, _run)

    async def _tool_get_sql_explain_plan(
        self, sql: str, schema: str | None = None
    ) -> dict[str, Any]:
        """返回 SQL 执行计划或优化建议。"""
        self._validate_explain_sql(sql)
        stripped = sql.strip()
        if not stripped.upper().startswith(self._EXPLAIN_ALLOWED_PREFIXES):
            raise MCPExecutionError(
                "EXPLAIN_REJECTED", "EXPLAIN FOR 仅支持 SELECT 语句"
            )

        schema_for_exec: str | None = None
        if isinstance(schema, str) and schema.strip():
            rows = await self._exec(
                sql=_sql.check_schema_exists(), params=[schema.strip()], max_rows=1
            )
            if not rows:
                raise MCPExecutionError(
                    "SCHEMA_NOT_FOUND",
                    f"schema 不存在或当前用户无权访问: {schema.strip()}",
                )
            schema_for_exec = schema.strip()

        trace = await self._collect_explain_trace(
            sql=sql, schema=schema_for_exec, max_rows=200
        )
        statistics = _mapper.merge_runtime_statistics(trace.get("sql_stat"), None, None)
        return _mapper.explain_plan(
            explain_text=trace.get("explain_text"),
            statistics=statistics,
            exec_id=trace.get("exec_id"),
            et_rows=trace.get("et_rows"),
            node_rows=trace.get("node_rows"),
            session_parameter_rows=trace.get("session_parameter_rows"),
        )

    async def _tool_find_long_active_sessions(
        self, threshold_ms: int
    ) -> dict[str, Any]:
        rows = await self._exec(
            sql=_sql.find_long_active_sessions(), params=[threshold_ms], max_rows=2000
        )
        return _mapper.compact_table(rows)

    async def _tool_find_sql_resource_hotspots(self, top_n: int = 10) -> dict[str, Any]:
        rows = await self._exec(
            sql=_sql.find_sql_resource_hotspots(),
            params=[top_n, top_n, top_n, top_n],
            max_rows=2000,
        )
        return _mapper.compact_table(rows)

    async def _tool_find_long_waiting_threads(
        self, threshold_ms: int
    ) -> dict[str, Any]:
        rows = await self._exec(
            sql=_sql.find_long_waiting_threads(),
            params=[threshold_ms],
            max_rows=2000,
        )
        return _mapper.compact_table(rows)

    async def _tool_get_blocking_chain(
        self, transaction_id: int | None = None
    ) -> dict[str, Any]:
        tid = transaction_id
        rows = await self._exec(
            sql=_sql.get_blocking_chain(),
            params=[tid, tid, tid, tid],
            max_rows=2000,
        )
        return _mapper.compact_table(rows)

    async def _tool_get_session_context(
        self, session_id: int, delta_seconds: int = 0
    ) -> dict[str, Any]:
        # 5.1-5.3 并行执行
        session_rows, (events_curr, events_prev, _mode), history_rows = await asyncio.gather(
            self._exec(
                sql=_sql.get_session_context_info(), params=[session_id], max_rows=1
            ),
            self._two_point_sample(
                sql=_sql.get_session_wait_events(),
                params=[session_id],
                delta_seconds=delta_seconds,
                max_rows=2000,
            ),
            self._exec(
                sql=_sql.get_session_wait_history(),
                params=[session_id],
                max_rows=2000,
            ),
        )
        session_row = session_rows[0] if session_rows else None
        wait_events, mode = _mapper.map_session_wait_events(
            events_prev, events_curr, delta_seconds
        )
        wait_history = _mapper.compact_table(history_rows)

        return _mapper.map_session_context(
            session_row, wait_events, wait_history, delta_seconds, mode
        )

    async def _tool_get_transaction_context(
        self, transaction_id: int
    ) -> dict[str, Any]:
        # 6.1 事务基本信息
        trx_rows = await self._exec(
            sql=_sql.get_transaction_info(), params=[transaction_id], max_rows=1
        )
        trx_row = trx_rows[0] if trx_rows else None
        if not trx_row:
            return _mapper.map_transaction_context(None, [], [], [])

        # 6.2-6.4 并行执行
        holding, waiting, chain = await asyncio.gather(
            self._exec(
                sql=_sql.get_transaction_locks_holding(),
                params=[transaction_id],
                max_rows=2000,
            ),
            self._exec(
                sql=_sql.get_transaction_locks_waiting(),
                params=[transaction_id],
                max_rows=2000,
            ),
            self._exec(
                sql=_sql.get_transaction_wait_chain(),
                params=[transaction_id, transaction_id],
                max_rows=2000,
            ),
        )

        return _mapper.map_transaction_context(trx_row, holding, waiting, chain)

    async def _tool_get_object_lock_context(self, object_id: int) -> dict[str, Any]:
        rows = await self._exec(
            sql=_sql.get_object_lock_context(), params=[object_id], max_rows=2000
        )
        return _mapper.map_object_lock_context(object_id, rows)

    async def _tool_get_sql_execution_stats(
        self, sql_id: Any, delta_seconds: int = 0
    ) -> dict[str, Any]:
        rows, prev, _mode = await self._two_point_sample(
            sql=_sql.get_sql_execution_stats(),
            params=[sql_id, sql_id],
            delta_seconds=delta_seconds,
            max_rows=2000,
        )
        return _mapper.map_sql_execution_stats(rows, prev, delta_seconds, sql_id)

    async def _tool_get_buffer_pool_stats(self) -> dict[str, Any]:
        rows = await self._exec(sql=_sql.get_buffer_pool_stats(), max_rows=2000)
        return _mapper.map_buffer_pool_stats(rows)

    async def _tool_get_memory_pool_usage(
        self, delta_seconds: int = 0
    ) -> dict[str, Any]:
        rows, prev, mode = await self._two_point_sample(
            sql=_sql.get_memory_pool_usage(),
            delta_seconds=delta_seconds,
            max_rows=2000,
        )
        return _mapper.map_delta_result(
            rows,
            delta_seconds,
            mode,
            "modules",
            prev_rows=prev,
            key_cols=["MEMORY_MODULE"],
            delta_cols={"TOTAL_ALLOC": "delta_alloc", "TOTAL_MB": "delta_size_mb"},
        )

    async def _tool_get_sysstat_delta(self, delta_seconds: int) -> dict[str, Any]:
        if delta_seconds <= 0:
            raise MCPExecutionError("INVALID_PARAM", "delta_seconds 必须大于 0")

        rows, prev, mode = await self._two_point_sample(
            sql=_sql.get_sysstat_delta(),
            delta_seconds=delta_seconds,
            max_rows=5000,
        )

        return _mapper.map_sysstat_delta(rows, prev, delta_seconds)

    async def _tool_get_cache_hot_objects(
        self, delta_seconds: int = 0
    ) -> dict[str, Any]:
        await self._exec(sql=_sql.create_safe_page_tname_get(), read_only=False)

        rows, prev, mode = await self._two_point_sample(
            sql=_sql.get_cache_hot_objects(),
            delta_seconds=delta_seconds,
            max_rows=2000,
        )

        return _mapper.map_delta_result(
            rows,
            delta_seconds,
            mode,
            "hot_pages",
            prev_rows=prev,
            key_cols=["TS_ID", "FILE_ID", "PAGE_NO"],
            delta_cols={"ACCESS_CNT": "delta_access_cnt"},
            drop_nonpos=True,
            sort_key="delta_access_cnt",
        )

    async def _tool_get_cache_hot_objects_by_index(
        self, delta_seconds: int = 0
    ) -> dict[str, Any]:
        rows, prev, mode = await self._two_point_sample(
            sql=_sql.get_cache_hot_objects_by_index(),
            delta_seconds=delta_seconds,
            max_rows=2000,
        )

        return _mapper.map_delta_result(
            rows,
            delta_seconds,
            mode,
            "hot_pages",
            prev_rows=prev,
            key_cols=["TS_ID", "FILE_ID", "PAGE_NO"],
            delta_cols={"ACCESS_CNT": "delta_access_cnt"},
            drop_nonpos=True,
            sort_key="delta_access_cnt",
        )
