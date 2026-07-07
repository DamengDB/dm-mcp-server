"""InspectionMCPProvider SQL 函数"""

# ============================================================
# explain_plan 相关
# ============================================================


def check_schema_exists() -> str:
    """检查 schema 是否存在于实例中。"""
    return """
SELECT 1 AS X
FROM SYS.SYSOBJECTS SCH_OBJ
WHERE SCH_OBJ.TYPE$ = 'SCH' AND SCH_OBJ.NAME = ?
FETCH FIRST 1 ROWS ONLY
"""


def explain_for(sql: str) -> str:
    """为给定 SQL 生成 EXPLAIN FOR 语句（入参 sql 须已做安全校验）。"""
    return f"EXPLAIN FOR {sql}"


# bug 132053：会话级 ##PLAN_TABLE 在连接复用时会累积多次 EXPLAIN FOR 的行；只取 PLAN_ID 最大的一组（单次 EXPLAIN 的多行共享同一 PLAN_ID）。
def get_plan_details() -> str:
    """从临时表读取执行计划详情（当前会话最近一次 EXPLAIN FOR）。"""
    return """
SELECT P.*
FROM SYS."##PLAN_TABLE" P
WHERE P.PLAN_ID = (SELECT MAX(PLAN_ID) FROM SYS."##PLAN_TABLE")
ORDER BY P.LEVEL_ID
"""


def get_explain_session_parameters() -> str:
    """与 Hash/Sort/Hash Join 相关的 INI 参数（V$PARAMETER）。"""
    return """
SELECT
    NAME,
    TYPE,
    VALUE,
    SYS_VALUE,
    FILE_VALUE
FROM V$PARAMETER
WHERE NAME LIKE '%HAGR%'
   OR NAME LIKE '%SORT%'
   OR NAME LIKE '%HJ%'
ORDER BY NAME
"""


def enable_explain_monitor_sql() -> str:
    """开启 SQL 执行监控（explain trace 前一次执行）。"""
    return """
BEGIN
    SF_SET_SESSION_PARA_VALUE('MONITOR_SQL_EXEC', 1);
    SF_SET_SESSION_PARA_VALUE('ENABLE_MONITOR_DMSQL', 1);
END;
"""


_EXPLAIN_RUNTIME_STAT_COLUMNS = """
SELECT
    EXEC_TIME AS EXEC_TIME_MS,
    LOGIC_READ_CNT AS LOGICAL_READS,
    PHY_READ_CNT AS PHYSICAL_READS,
    DATA_PAGE_CHANGES_CNT AS DATA_PAGES_CHANGED,
    UNDO_PAGE_CHANGES_CNT AS UNDO_PAGES_CHANGED,
    NET_BYTES_SEND AS BYTES_SENT_TO_CLIENT,
    NET_BYTES_RECV AS BYTES_RECEIVED_FROM_CLIENT,
    NET_ROUNDTRIPS AS ROUNDTRIPS_TO_FROM_CLIENT,
    REDO_SIZE AS REDO_SIZE,
    IO_WAIT_TIME AS IO_WAIT_TIME_MS,
    TAB_SCAN_CNT AS TAB_SCAN_COUNT,
    EXEC_CPU AS EXEC_CPU_MS
"""


def get_sql_stat_by_exec_id() -> str:
    """按 EXEC_ID 查询 V$SQL_STAT 运行时统计。"""
    return f"{_EXPLAIN_RUNTIME_STAT_COLUMNS}\nFROM V$SQL_STAT\nWHERE EXEC_ID = ?"


def get_sql_stat_history_by_exec_id() -> str:
    """按 EXEC_ID 查询 V$SQL_STAT_HISTORY 运行时统计。"""
    return f"{_EXPLAIN_RUNTIME_STAT_COLUMNS}\nFROM V$SQL_STAT_HISTORY\nWHERE EXEC_ID = ?"


def get_sql_history_by_exec_id() -> str:
    """按 EXEC_ID 查询 V$SQL_HISTORY 运行时统计。"""
    return """
SELECT
    CAST(TIME_USED / 1000.0 AS DECIMAL(18, 3)) AS EXEC_TIME_MS,
    N_LOGIC_READ AS LOGICAL_READS,
    N_PHY_READ AS PHYSICAL_READS,
    AFFECTED_ROWS AS ROWS_PROCESSED
FROM V$SQL_HISTORY
WHERE EXEC_ID = ?
"""


def get_runtime_stat_by_exec_id() -> str:
    """按 EXEC_ID 合并 V$SQL_STAT / V$SQL_STAT_HISTORY / V$SQL_HISTORY（优先级同 merge_runtime_statistics）。"""
    return """
SELECT
    COALESCE(s.EXEC_TIME, sh.EXEC_TIME, CAST(h.TIME_USED / 1000.0 AS DECIMAL(18, 3))) AS EXEC_TIME_MS,
    COALESCE(s.LOGIC_READ_CNT, sh.LOGIC_READ_CNT, h.N_LOGIC_READ) AS LOGICAL_READS,
    COALESCE(s.PHY_READ_CNT, sh.PHY_READ_CNT, h.N_PHY_READ) AS PHYSICAL_READS,
    COALESCE(s.DATA_PAGE_CHANGES_CNT, sh.DATA_PAGE_CHANGES_CNT) AS DATA_PAGES_CHANGED,
    COALESCE(s.UNDO_PAGE_CHANGES_CNT, sh.UNDO_PAGE_CHANGES_CNT) AS UNDO_PAGES_CHANGED,
    COALESCE(s.NET_BYTES_SEND, sh.NET_BYTES_SEND) AS BYTES_SENT_TO_CLIENT,
    COALESCE(s.NET_BYTES_RECV, sh.NET_BYTES_RECV) AS BYTES_RECEIVED_FROM_CLIENT,
    COALESCE(s.NET_ROUNDTRIPS, sh.NET_ROUNDTRIPS) AS ROUNDTRIPS_TO_FROM_CLIENT,
    COALESCE(s.REDO_SIZE, sh.REDO_SIZE) AS REDO_SIZE,
    COALESCE(s.IO_WAIT_TIME, sh.IO_WAIT_TIME) AS IO_WAIT_TIME_MS,
    COALESCE(s.TAB_SCAN_CNT, sh.TAB_SCAN_CNT) AS TAB_SCAN_COUNT,
    COALESCE(s.EXEC_CPU, sh.EXEC_CPU) AS EXEC_CPU_MS,
    h.AFFECTED_ROWS AS ROWS_PROCESSED
FROM (SELECT ? AS EXEC_ID) e
LEFT JOIN V$SQL_STAT s ON s.EXEC_ID = e.EXEC_ID
LEFT JOIN V$SQL_STAT_HISTORY sh ON sh.EXEC_ID = e.EXEC_ID
LEFT JOIN V$SQL_HISTORY h ON h.EXEC_ID = e.EXEC_ID
"""


def get_sql_node_history_by_exec_id() -> str:
    """按 EXEC_ID 查询 V$SQL_NODE_HISTORY 算子级统计。"""
    return """
SELECT
    SEQ_NO,
    TYPE$,
    N_ENTER,
    MEM_USED,
    DISK_USED,
    HASH_USED_CELLS,
    HASH_CONFLICT,
    DHASH3_USED_CELLS,
    DHASH3_CONFLICT,
    TIME_USED
FROM V$SQL_NODE_HISTORY
WHERE EXEC_ID = ?
ORDER BY SEQ_NO
"""


def call_et(exec_id: int) -> str:
    """调用 ET 获取算子级耗时等统计。"""
    return f"CALL ET({int(exec_id)})"


# ============================================================
# 01 find_long_active_sessions(threshold_ms)
# ============================================================


def find_long_active_sessions() -> str:
    return """
SELECT
    SESS_ID AS SESS_ID,
    TRX_ID AS TRX_ID,
    SQL_ID AS SQL_ID,
    USER_NAME AS USER_NAME,
    STATE AS STATE,
    AUTO_CMT AS AUTO_COMMIT,
    ELAPSED_MS AS ELAPSED_MS,
    TO_CHAR(SF_GET_SESSION_SQL(SESS_ID)) AS SQL_TEXT,
    CLIENT_IP
FROM (
    SELECT
        SESS_ID,
        TRX_ID,
        (SELECT SQL_ID FROM V$SQL_STAT WHERE SESSID = S.SESS_ID AND ROWNUM = 1) AS SQL_ID,
        USER_NAME,
        STATE,
        AUTO_CMT,
        DATEDIFF(MS, LAST_RECV_TIME, SYSDATE) AS ELAPSED_MS,
        CLNT_IP AS CLIENT_IP
    FROM V$SESSIONS S
    WHERE STATE = 'ACTIVE'
      AND SESS_ID != SESSID()
)
WHERE ELAPSED_MS >= ?
ORDER BY ELAPSED_MS DESC
"""


# ============================================================
# 02 find_sql_resource_hotspots(top_n)
# ============================================================


def find_sql_resource_hotspots() -> str:
    return """
WITH HIST_AGG AS (
    SELECT
        SQL_ID,
        MAX(SQL_TXT) AS SQL_TXT,
        SUM(IO_WAIT_TIME) AS IO_WAIT_TIME,
        SUM(LOGIC_READ_CNT) AS LOGIC_READ_CNT,
        SUM(EXEC_CPU) AS EXEC_CPU,
        SUM(PARSE_ELAPSD) AS PARSE_ELAPSD
    FROM V$SQL_STAT_HISTORY
    GROUP BY SQL_ID
),
CURR_STAT AS (
    SELECT
        SQL_ID, SQL_TXT, IO_WAIT_TIME, LOGIC_READ_CNT, EXEC_CPU, PARSE_ELAPSD
    FROM V$SQL_STAT
),
COMBINED AS (
    SELECT
        COALESCE(C.SQL_ID, H.SQL_ID) AS SQL_ID,
        COALESCE(C.SQL_TXT, H.SQL_TXT) AS SQL_TXT,
        GREATEST(COALESCE(C.IO_WAIT_TIME, 0), COALESCE(H.IO_WAIT_TIME, 0)) AS IO_WAIT_TIME,
        GREATEST(COALESCE(C.LOGIC_READ_CNT, 0), COALESCE(H.LOGIC_READ_CNT, 0)) AS LOGIC_READ_CNT,
        GREATEST(COALESCE(C.EXEC_CPU, 0), COALESCE(H.EXEC_CPU, 0)) AS EXEC_CPU,
        GREATEST(COALESCE(C.PARSE_ELAPSD, 0), COALESCE(H.PARSE_ELAPSD, 0)) AS PARSE_ELAPSD
    FROM CURR_STAT C
    FULL OUTER JOIN HIST_AGG H ON C.SQL_ID = H.SQL_ID
),
MAX_VALS AS (
    SELECT MAX(IO_WAIT_TIME) AS MAX_IO,
           MAX(LOGIC_READ_CNT) AS MAX_READ,
           MAX(EXEC_CPU) AS MAX_CPU,
           MAX(PARSE_ELAPSD) AS MAX_PARSE
    FROM COMBINED
),
IO_TOP AS (
    SELECT SQL_ID FROM (
        SELECT SQL_ID, ROW_NUMBER() OVER (ORDER BY IO_WAIT_TIME DESC) AS RN FROM COMBINED
    ) WHERE RN <= ?
),
READ_TOP AS (
    SELECT SQL_ID FROM (
        SELECT SQL_ID, ROW_NUMBER() OVER (ORDER BY LOGIC_READ_CNT DESC) AS RN FROM COMBINED
    ) WHERE RN <= ?
),
CPU_TOP AS (
    SELECT SQL_ID FROM (
        SELECT SQL_ID, ROW_NUMBER() OVER (ORDER BY EXEC_CPU DESC) AS RN FROM COMBINED
    ) WHERE RN <= ?
),
PARSE_TOP AS (
    SELECT SQL_ID FROM (
        SELECT SQL_ID, ROW_NUMBER() OVER (ORDER BY PARSE_ELAPSD DESC) AS RN FROM COMBINED
    ) WHERE RN <= ?
),
MERGED AS (
    SELECT SQL_ID FROM IO_TOP
    UNION SELECT SQL_ID FROM READ_TOP
    UNION SELECT SQL_ID FROM CPU_TOP
    UNION SELECT SQL_ID FROM PARSE_TOP
)
SELECT
    C.SQL_ID AS SQL_ID,
    C.SQL_TXT AS SQL_TEXT,
    C.PARSE_ELAPSD AS PARSE_ELAPSED_MS,
    C.IO_WAIT_TIME AS IO_WAIT_TIME_MS,
    C.LOGIC_READ_CNT AS LOGICAL_READS,
    C.EXEC_CPU AS EXEC_CPU_MS
FROM COMBINED C
JOIN MERGED M ON C.SQL_ID = M.SQL_ID
CROSS JOIN MAX_VALS MV
ORDER BY GREATEST(
    COALESCE(C.IO_WAIT_TIME / NULLIF(MV.MAX_IO, 0), 0),
    COALESCE(C.LOGIC_READ_CNT / NULLIF(MV.MAX_READ, 0), 0),
    COALESCE(C.EXEC_CPU / NULLIF(MV.MAX_CPU, 0), 0),
    COALESCE(C.PARSE_ELAPSD / NULLIF(MV.MAX_PARSE, 0), 0)
) DESC
"""


# ============================================================
# 03 find_long_waiting_threads(threshold_ms)
# ============================================================


def find_long_waiting_threads() -> str:
    return """
SELECT
    T.ID AS THREAD_ID,
    T.THREAD_DESC AS DESCRIPTION,
    T.SESS_ID AS SESSION_ID,
    T.PROCESSOR_ID AS CPU_ID,
    T.WAIT_STATUS AS WAIT_STATUS,
    T.WAIT_TIME AS WAIT_TIME_MS,
    S.USER_NAME AS DB_USER
FROM V$THREADS T
LEFT JOIN V$SESSIONS S ON T.SESS_ID = S.SESS_ID
WHERE T.WAIT_TIME >= ?
ORDER BY T.WAIT_TIME DESC
"""


# ============================================================
# 04 get_blocking_chain(transaction_id?)
# ============================================================


def get_blocking_chain() -> str:
    return """
WITH WAIT_TREE AS (
    SELECT
        CONNECT_BY_ROOT(T.WAIT_FOR_ID) AS ROOT_BLOCKER_TRX_ID,
        LEVEL AS CHAIN_DEPTH,
        CONNECT_BY_ROOT(T.WAIT_FOR_ID) || SYS_CONNECT_BY_PATH(T.ID, ' <- ') AS WAIT_PATH_TEXT,
        T.WAIT_FOR_ID AS BLOCKING_TRX_ID,
        T.ID AS BLOCKED_TRX_ID,
        T.WAIT_TIME AS WAIT_TIME_MS,
        CONNECT_BY_ISCYCLE AS IS_DEADLOCK_CYCLE
    FROM V$TRXWAIT T
    START WITH (
        (? IS NULL AND T.WAIT_FOR_ID NOT IN (SELECT ID FROM V$TRXWAIT))
        OR (? IS NOT NULL AND (T.WAIT_FOR_ID = ? OR T.ID = ?))
    )
    CONNECT BY NOCYCLE PRIOR T.ID = T.WAIT_FOR_ID
)
SELECT
    W.ROOT_BLOCKER_TRX_ID,
    W.CHAIN_DEPTH,
    W.WAIT_PATH_TEXT,
    W.IS_DEADLOCK_CYCLE,
    W.BLOCKING_TRX_ID,
    S2.SESS_ID AS BLOCKING_SESSION_ID,
    S2.USER_NAME AS BLOCKING_USER,
    TO_CHAR(SF_GET_SESSION_SQL(S2.SESS_ID)) AS BLOCKING_SQL_TEXT,
    W.BLOCKED_TRX_ID,
    S1.SESS_ID AS BLOCKED_SESSION_ID,
    S1.USER_NAME AS BLOCKED_USER,
    TO_CHAR(SF_GET_SESSION_SQL(S1.SESS_ID)) AS BLOCKED_SQL_TEXT,
    W.WAIT_TIME_MS,
    L.LTYPE AS LOCK_TYPE,
    L.LMODE AS LOCK_MODE,
    L.TABLE_ID AS OBJECT_ID
FROM WAIT_TREE W
LEFT JOIN V$SESSIONS S1 ON W.BLOCKED_TRX_ID = S1.TRX_ID
LEFT JOIN V$SESSIONS S2 ON W.BLOCKING_TRX_ID = S2.TRX_ID
LEFT JOIN (
    SELECT TRX_ID, LTYPE, LMODE, TABLE_ID,
           ROW_NUMBER() OVER(PARTITION BY TRX_ID ORDER BY TABLE_ID) AS RN
    FROM V$LOCK WHERE BLOCKED = 1 AND IGN_FLAG = 0
) L ON W.BLOCKED_TRX_ID = L.TRX_ID AND L.RN = 1
ORDER BY W.ROOT_BLOCKER_TRX_ID, W.CHAIN_DEPTH
"""


# ============================================================
# 05 get_session_context(session_id, delta_seconds)
# ============================================================


def get_session_context_info() -> str:
    """5.1 会话基本信息 + 当前事务 + SQL + 线程"""
    return """
SELECT
    S.SESS_ID AS SESSION_ID,
    S.STATE AS STATE,
    S.USER_NAME AS USER_NAME,
    S.CLNT_IP AS CLIENT_IP,
    S.CREATE_TIME AS CREATE_TIME,
    S.AUTO_CMT AS AUTO_COMMIT,
    S.TRX_ID AS TRX_ID,
    T.STATUS AS TRX_STATUS,
    T.LOCK_CNT AS LOCK_COUNT,
    T.N_PAGES AS N_UNDO_PAGES,
    SQ.SQL_ID AS SQL_ID,
    SQ.SQL_TXT AS SQL_TEXT,
    SQ.EXEC_TIME AS EXEC_TIME_MS,
    TH.ID AS THREAD_ID,
    TH.PROCESSOR_ID AS CPU_ID,
    TH.WAIT_STATUS AS WAIT_STATUS,
    TH.WAIT_TIME AS THREAD_WAIT_TIME_MS
FROM V$SESSIONS S
LEFT JOIN V$TRX T ON S.TRX_ID = T.ID
LEFT JOIN V$SQL_STAT SQ ON SQ.SESSID = S.SESS_ID AND SQ.SQL_ID = (
    SELECT SQL_ID FROM V$SESSIONS WHERE SESS_ID = S.SESS_ID AND SQL_TEXT IS NOT NULL
)
LEFT JOIN V$THREADS TH ON TH.SESS_ID = S.SESS_ID
WHERE S.SESS_ID = ?
"""


def get_session_wait_events() -> str:
    """5.2 等待事件（累积值，由服务端做 delta）"""
    return """
SELECT
    EVENT AS EVENT,
    WAIT_CLASS AS WAIT_CLASS,
    TOTAL_WAITS AS TOTAL_WAITS,
    TIME_WAITED_MICRO / 1000000.0 AS TIME_WAITED_SEC,
    AVERAGE_WAIT_MICRO / 1000.0 AS AVG_WAIT_MS,
    SMAX_TIME / 1000.0 AS MAX_WAIT_MS
FROM V$SESSION_EVENT
WHERE CAST(SESSADDR AS BIGINT) = ?
ORDER BY TIME_WAITED_MICRO DESC
"""


def get_session_wait_history() -> str:
    """5.3 最近等待轨迹（天然增量）"""
    return """
SELECT
    EVENT AS EVENT,
    WAIT_CLASS AS WAIT_CLASS,
    TIME_WAITED_MICRO/1000.0 AS WAIT_MS,
    SQL_ID AS SQL_ID,
    P1TEXT AS P1TEXT, P1 AS P1,
    P2TEXT AS P2TEXT, P2 AS P2,
    P3TEXT AS P3TEXT, P3 AS P3,
    P5TEXT AS P5TEXT, P5 AS P5
FROM V$SESSION_WAIT_HISTORY
WHERE CAST(SESSADDR AS BIGINT) = ?
ORDER BY ROWID DESC
"""


# ============================================================
# 06 get_transaction_context(transaction_id)
# ============================================================


def get_transaction_info() -> str:
    """6.1 事务基本信息 + 关联会话"""
    return """
SELECT
    T.ID AS TRX_ID,
    T.STATUS AS TRX_STATUS,
    T.READ_ONLY AS READ_ONLY,
    T.LOCK_CNT AS LOCK_COUNT,
    T.N_PAGES AS N_UNDO_PAGES,
    S.SESS_ID AS SESSION_ID,
    S.USER_NAME AS USER_NAME,
    TO_CHAR(SF_GET_SESSION_SQL(S.SESS_ID)) AS CURRENT_SQL
FROM V$TRX T
LEFT JOIN V$SESSIONS S ON T.SESS_ID = S.SESS_ID
WHERE T.ID = ?
"""


def get_transaction_locks_holding() -> str:
    """6.2 事务持有的锁"""
    return """
SELECT
    LTYPE AS LOCK_TYPE,
    LMODE AS LOCK_MODE,
    TABLE_ID AS OBJECT_ID,
    ROW_IDX AS ROW_IDX
FROM V$LOCK
WHERE TRX_ID = ? AND BLOCKED = 0 AND IGN_FLAG = 0
"""


def get_transaction_locks_waiting() -> str:
    """6.3 事务正在等待的锁"""
    return """
SELECT
    LTYPE AS LOCK_TYPE,
    LMODE AS LOCK_MODE,
    TABLE_ID AS OBJECT_ID,
    ROW_IDX AS ROW_IDX
FROM V$LOCK
WHERE TRX_ID = ? AND BLOCKED = 1 AND IGN_FLAG = 0
"""


def get_transaction_wait_chain() -> str:
    """6.4 事务在阻塞链中的位置"""
    return """
SELECT
    'BLOCKED_BY' AS CHAIN_ROLE,
    WAIT_FOR_ID AS PEER_TRX_ID,
    WAIT_TIME AS WAIT_MS
FROM V$TRXWAIT
WHERE ID = ?
UNION ALL
SELECT
    'BLOCKING' AS CHAIN_ROLE,
    ID AS PEER_TRX_ID,
    WAIT_TIME AS WAIT_MS
FROM V$TRXWAIT
WHERE WAIT_FOR_ID = ?
"""


# ============================================================
# 07 get_object_lock_context(object_id)
# ============================================================


def get_object_lock_context() -> str:
    return """
SELECT
    L.TRX_ID AS TRX_ID,
    L.LTYPE AS LOCK_TYPE,
    L.LMODE AS LOCK_MODE,
    L.BLOCKED AS IS_BLOCKED,
    L.ROW_IDX AS ROW_IDX,
    S.SESS_ID AS SESSION_ID,
    S.USER_NAME AS USER_NAME,
    TO_CHAR(SF_GET_SESSION_SQL(S.SESS_ID)) AS CURRENT_SQL,
    T.STATUS AS TRX_STATUS,
    T.LOCK_CNT AS TRX_TOTAL_LOCKS,
    CASE WHEN L.BLOCKED = 0 THEN 'HOLDER' ELSE 'WAITER' END AS LOCK_ROLE
FROM V$LOCK L
LEFT JOIN V$SESSIONS S ON L.TRX_ID = S.TRX_ID
LEFT JOIN V$TRX T ON L.TRX_ID = T.ID
WHERE L.TABLE_ID = ? AND L.IGN_FLAG = 0
ORDER BY L.BLOCKED DESC, L.TRX_ID
"""


# ============================================================
# 08 get_sql_execution_stats(sql_id, delta_seconds)
# ============================================================


def get_sql_execution_stats() -> str:
    return """
WITH SQL_UNION AS (
    SELECT SQL_ID, SQL_TXT,
           PARSE_ELAPSD, PARSE_CNT, HARD_PARSE_CNT,
           PARSE_TIME, HARD_PARSE_TIME,
           LOGIC_READ_CNT, PHY_READ_CNT, HBUF_PHY_WRITE_CNT,
           IO_WAIT_TIME, EXEC_CPU, TAB_SCAN_CNT,
           MAX_MEM_USED, NET_BYTES_RECV, NET_BYTES_SEND,
           START_TIME, END_TIME,
           'CURRENT' AS SOURCE
    FROM V$SQL_STAT
    WHERE SQL_ID = ?
    UNION ALL
    SELECT SQL_ID, SQL_TXT,
           PARSE_ELAPSD, PARSE_CNT, HARD_PARSE_CNT,
           PARSE_TIME, HARD_PARSE_TIME,
           LOGIC_READ_CNT, PHY_READ_CNT, HBUF_PHY_WRITE_CNT,
           IO_WAIT_TIME, EXEC_CPU, TAB_SCAN_CNT,
           MAX_MEM_USED, NET_BYTES_RECV, NET_BYTES_SEND,
           START_TIME, END_TIME,
           'HISTORY' AS SOURCE
    FROM V$SQL_STAT_HISTORY
    WHERE SQL_ID = ?
)
SELECT
    SQL_TXT AS SQL_TEXT,
    PARSE_ELAPSD AS PARSE_ELAPSD_MS,
    EXEC_CPU AS EXEC_CPU_MS,
    PARSE_CNT AS PARSE_COUNT,
    HARD_PARSE_CNT AS HARD_PARSE_COUNT,
    PARSE_TIME AS PARSE_TIME_MS,
    HARD_PARSE_TIME AS HARD_PARSE_TIME_MS,
    LOGIC_READ_CNT AS LOGICAL_READS,
    PHY_READ_CNT AS PHYSICAL_READS,
    HBUF_PHY_WRITE_CNT AS PHYSICAL_WRITES,
    IO_WAIT_TIME AS IO_WAIT_TIME_MS,
    TAB_SCAN_CNT AS TAB_SCAN_COUNT,
    NET_BYTES_RECV AS NET_BYTES_RECV,
    NET_BYTES_SEND AS NET_BYTES_SEND,
    MAX_MEM_USED AS MAX_MEM_USED_KB,
    START_TIME,
    END_TIME,
    SOURCE
FROM SQL_UNION
ORDER BY SOURCE, START_TIME DESC
"""


# ============================================================
# 09 get_buffer_pool_stats()
# ============================================================


def get_buffer_pool_stats() -> str:
    return """
SELECT
    NAME AS POOL_NAME,
    ROUND(SUM(N_PAGES)*PAGE()/1024.0/1024, 2) AS SIZE_MB,
    ROUND(SUM(FREE)*PAGE()/1024.0/1024, 2) AS FREE_MB,
    ROUND(SUM(N_DIRTY)*PAGE()/1024.0/1024, 2) AS DIRTY_MB,
    SUM(N_FIXED) AS FIXED_PAGES,
    ROUND(AVG(RAT_HIT), 2) AS HIT_RATIO_PCT,
    SUM(N_LOGIC_READS) AS LOGIC_READS,
    SUM(N_PHY_READS64) AS PHY_READS,
    SUM(N_PHY_M_READS64) AS PHY_M_READS,
    SUM(N_PHY_WRITE64) AS PHY_WRITES,
    SUM(N_DISCARD64) AS DISCARD_PAGES
FROM V$BUFFERPOOL
GROUP BY NAME
"""


# ============================================================
# 10 get_memory_pool_usage(delta_seconds)
# ============================================================


def get_memory_pool_usage() -> str:
    return """
SELECT
    (CASE WHEN NAME LIKE 'SHARE POOL%' THEN 'SHARE_POOL_GROUP' ELSE NAME END) AS MEMORY_MODULE,
    ROUND(SUM(TOTAL_SIZE)/1024.0/1024, 2) AS TOTAL_MB,
    ROUND(SUM(RESERVED_SIZE)/1024.0/1024, 2) AS RESERVED_MB,
    ROUND(SUM(DATA_SIZE)/1024.0/1024, 2) AS DATA_MB,
    ROUND(AVG(TOTAL_SIZE)/1024.0/1024, 2) AS AVG_MB,
    ROUND(MAX(TOTAL_SIZE)/1024.0/1024, 2) AS MAX_MB,
    ROUND(SUM(TARGET_SIZE)/1024.0/1024, 2) AS TARGET_MB,
    MAX(CASE WHEN IS_OVERFLOW = 'Y' THEN 1 ELSE 0 END) AS IS_OVERFLOW,
    SUM(N_ALLOC) AS TOTAL_ALLOC
FROM V$MEM_POOL
GROUP BY (CASE WHEN NAME LIKE 'SHARE POOL%' THEN 'SHARE_POOL_GROUP' ELSE NAME END)
ORDER BY TOTAL_MB DESC
"""


# ============================================================
# 11 get_sysstat_delta(delta_seconds)
# ============================================================


def get_sysstat_delta() -> str:
    return """
SELECT
    CLASSID AS CLASS_ID,
    NAME AS STAT_NAME,
    STAT_VAL AS STAT_VALUE
FROM V$SYSSTAT
"""


# ============================================================
# 12 get_cache_hot_objects(delta_seconds)
# ============================================================


def get_cache_hot_objects() -> str:
    return """
WITH PAGE_MAPPED AS (
    SELECT
        H.TS_ID, H.FILE_ID, H.PAGE_NO,
        H.ACCESS_CNT, H.PAGETYPE,
        SAFE_PAGE_TNAME_GET(H.TS_ID, H.FILE_ID, H.PAGE_NO) AS FULL_NAME
    FROM V$HOTPAGE H
),
PARSED AS (
    SELECT
        TS_ID, FILE_ID, PAGE_NO,
        ACCESS_CNT, PAGETYPE,
        CASE WHEN FULL_NAME LIKE '%.%' THEN
            SUBSTR(FULL_NAME, 1, INSTR(FULL_NAME, '.') - 1)
        END AS SCHEMA_NAME,
        CASE WHEN FULL_NAME LIKE '%.%' THEN
            SUBSTR(FULL_NAME, INSTR(FULL_NAME, '.') + 1)
        ELSE FULL_NAME END AS OBJ_NAME
    FROM PAGE_MAPPED
    WHERE FULL_NAME IS NOT NULL
)
SELECT
    P.TS_ID AS TS_ID,
    P.FILE_ID AS FILE_ID,
    P.PAGE_NO AS PAGE_NO,
    P.ACCESS_CNT AS ACCESS_CNT,
    P.PAGETYPE AS PAGE_TYPE,
    SO.ID AS OBJECT_ID,
    P.SCHEMA_NAME,
    SO.NAME AS OBJECT_NAME,
    SO.SUBTYPE$ AS OBJECT_TYPE
FROM PARSED P
LEFT JOIN SYSOBJECTS SO ON SO.NAME = P.OBJ_NAME AND SO.TYPE$ = 'SCHOBJ'
ORDER BY P.ACCESS_CNT DESC
"""


# ============================================================
# 13 get_cache_hot_objects_by_index(delta_seconds)
# ============================================================


def get_cache_hot_objects_by_index() -> str:
    return """
SELECT
    H.TS_ID AS TS_ID,
    H.FILE_ID AS FILE_ID,
    H.PAGE_NO AS PAGE_NO,
    H.ACCESS_CNT AS ACCESS_CNT,
    H.INDEXID AS INDEX_ID,
    H.PAGETYPE AS PAGE_TYPE,
    COALESCE(P.BASE_TABLE_ID, IDX.PID) AS TABLE_ID,
    COALESCE(BT.NAME, T.NAME) AS TABLE_NAME,
    COALESCE(BT.SUBTYPE$, T.SUBTYPE$) AS TABLE_TYPE,
    COALESCE(BS.NAME, S.NAME) AS SCHEMA_NAME
FROM V$HOTPAGE H
LEFT JOIN SYSOBJECTS IDX
    ON IDX.ID = H.INDEXID
    AND IDX.TYPE$ = 'TABOBJ'
    AND IDX.SUBTYPE$ = 'INDEX'
LEFT JOIN SYSOBJECTS T ON T.ID = IDX.PID
LEFT JOIN SYSOBJECTS S ON S.ID = T.SCHID
LEFT JOIN SYSHPARTTABLEINFO P ON P.PART_TABLE_ID = IDX.PID
LEFT JOIN SYSOBJECTS BT ON BT.ID = P.BASE_TABLE_ID
LEFT JOIN SYSOBJECTS BS ON BS.ID = BT.SCHID
WHERE H.INDEXID != 0
ORDER BY H.ACCESS_CNT DESC
"""


# ============================================================
# 辅助：创建 safe_page_tname_get 函数（#12 使用）
# ============================================================


def create_safe_page_tname_get() -> str:
    return """
    CREATE OR REPLACE FUNCTION SAFE_PAGE_TNAME_GET(TS_ID INT, FILE_ID INT, PAGE_NO INT)
    RETURN VARCHAR(256)
    AS
        V_RESULT VARCHAR(256);
    BEGIN
        V_RESULT := DBMS_PAGE.DATA_PAGE_TNAME_GET(TS_ID, FILE_ID, PAGE_NO);
        RETURN V_RESULT;
    EXCEPTION
        WHEN OTHERS THEN
            RETURN NULL;
    END;
    """
