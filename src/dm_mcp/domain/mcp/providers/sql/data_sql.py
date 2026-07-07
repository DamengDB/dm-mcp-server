"""DataMCPProvider SQL 函数"""


def get_table_data_size() -> str:
    """查询表的数据与索引空间占用（页数、MB）。"""
    return """
SELECT
    S.NAME AS SCHEMA_NAME,
    T.NAME AS TABLE_NAME,
    B.PAGE_SIZE AS PAGE_SIZE_BYTES,
    TABLE_USED_SPACE(S.NAME, T.NAME) AS DATA_PAGES,
    (
        SELECT NVL(SUM(INDEX_USED_SPACE(I.ID)), 0)
        FROM SYS.SYSOBJECTS I
        WHERE I.PID = T.ID AND I.SUBTYPE$ = 'INDEX'
    ) AS INDEX_PAGES,
    TABLE_USED_SPACE(S.NAME, T.NAME) * B.PAGE_SIZE / 1024 / 1024 AS DATA_MB,
    (
        SELECT NVL(SUM(INDEX_USED_SPACE(I.ID)), 0) * B.PAGE_SIZE / 1024 / 1024
        FROM SYS.SYSOBJECTS I
        WHERE I.PID = T.ID AND I.SUBTYPE$ = 'INDEX'
    ) AS INDEX_MB
FROM SYS.SYSOBJECTS T
JOIN SYS.SYSOBJECTS S ON T.SCHID = S.ID
CROSS JOIN (SELECT PAGE_SIZE FROM V$BUFFERPOOL WHERE ROWNUM = 1) B
WHERE T.NAME = ?
    AND S.NAME = ?
    AND T.TYPE$ = 'SCHOBJ'
    AND T.SUBTYPE$ = 'UTAB'
"""


def gather_table_stats() -> str:
    """收集表最新统计信息。"""
    return """
CALL DBMS_STATS.GATHER_TABLE_STATS(?, ?, NULL, 100, TRUE);
"""


def get_table_basic_info() -> str:
    """从 DBA_TABLES 查询表统计信息。"""
    return """
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


def get_columns() -> str:
    """获取表的所有列及数据类型。"""
    return """
SELECT
    COLUMN_NAME,
    DATA_TYPE
FROM ALL_TAB_COLUMNS
WHERE OWNER = ?
  AND TABLE_NAME = ?
ORDER BY COLUMN_ID
"""


def analyze_column_stats(col_name: str, qualified_table: str) -> str:
    """逐列基础统计：总行数、空值、不重复值、最大最小值。

    Args:
        col_name: 列名；须已由调用方按达梦标识符白名单校验（见 bug 132101）。
        qualified_table: 带 schema 的表名（两段标识符均已校验）。
    """
    # bug 132101 ：片段嵌入 SQL；schema/table/column 必须由 DataMCPProvider 校验后再传入。
    return f"""
SELECT
    COUNT(*) AS TOTAL_ROWS,
    COUNT(CASE WHEN {col_name} IS NULL THEN 1 END) AS NULL_COUNT,
    COUNT(DISTINCT {col_name}) AS DISTINCT_COUNT,
    MAX({col_name}) AS MAX_VALUE,
    MIN({col_name}) AS MIN_VALUE
FROM {qualified_table}
"""


def analyze_column_top(col_name: str, qualified_table: str) -> str:
    """逐列 Top N 值及其出现次数。

    Args:
        col_name: 列名；须已由调用方按达梦标识符白名单校验（见 bug 132101）。
        qualified_table: 带 schema 的表名（两段标识符均已校验）。
    """
    # bug 132101 ：片段嵌入 SQL；schema/table/column 必须由 DataMCPProvider 校验后再传入。
    return f"""
SELECT
    {col_name} AS VALUE,
    COUNT(*) AS OCCUR_COUNT
FROM {qualified_table}
WHERE {col_name} IS NOT NULL
GROUP BY {col_name}
ORDER BY OCCUR_COUNT DESC
FETCH FIRST ? ROWS ONLY
"""
