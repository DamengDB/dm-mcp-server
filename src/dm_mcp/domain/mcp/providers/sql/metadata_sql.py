"""MetadataMCPProvider SQL 函数"""

# ============================================================
# Schema
# ============================================================


def list_schemas() -> str:
    """查询所有 schema 列表。"""
    return """
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


def get_schema_info() -> str:
    """查询单个 schema 信息。"""
    return """
SELECT
  SCH_OBJ.NAME    AS SCHEMA_NAME,
  USER_OBJ.NAME   AS OWNER,
  SCH_OBJ.CRTDATE AS CREATED_TIME
FROM SYS.SYSOBJECTS SCH_OBJ
JOIN SYS.SYSOBJECTS USER_OBJ
  ON SCH_OBJ.PID = USER_OBJ.ID
WHERE SCH_OBJ.TYPE$ = 'SCH' AND SCH_OBJ.NAME = ?
"""


# ============================================================
# Tables
# ============================================================


def _table_comment_select() -> str:
    return ", TC.COMMENT$ AS TABLE_COMMENT"


def _table_comment_join() -> str:
    return """
LEFT JOIN SYS.SYSTABLECOMMENTS TC
  ON TC.SCHNAME = S.NAME
 AND TC.TVNAME = T.NAME
 AND TC.TABLE_TYPE = 'TABLE'
"""


def list_tables(include_comments: bool, schema: str | None = None) -> tuple[str, list[str] | None]:
    """返回表列表 SQL 及参数。

    Args:
        include_comments: 是否包含注释字段。
        schema: 指定 schema 则返回该 schema 下的表，None 返回全库。

    Returns:
        (sql_string, params) 元组；params 为 None 表示无参数。
    """
    comment_sel = _table_comment_select() if include_comments else ""
    comment_join = _table_comment_join() if include_comments else ""

    sql = f"""
SELECT
  S.NAME       AS SCHEMA_NAME,
  T.NAME       AS OBJECT_NAME,
  'TABLE'      AS OBJECT_TYPE
  {comment_sel}
FROM SYS.SYSOBJECTS T
JOIN SYS.SYSOBJECTS S ON T.SCHID = S.ID
{comment_join}
WHERE T.TYPE$ = 'SCHOBJ' AND T.SUBTYPE$ IN ('UTAB', 'STAB')
"""
    if schema:
        sql += "  AND S.NAME = ?\nORDER BY T.NAME;\n"
        params: list[str] | None = [schema]
    else:
        sql += "ORDER BY S.NAME, T.NAME;\n"
        params = None

    return sql, params


def get_table_info() -> str:
    """查询表基本信息（含注释）。"""
    return """
SELECT
  S.NAME AS SCHEMA_NAME,
  T.NAME AS TABLE_NAME,
  TC.COMMENT$ AS TABLE_COMMENT
FROM SYS.SYSOBJECTS T
JOIN SYS.SYSOBJECTS S ON T.SCHID = S.ID
LEFT JOIN SYS.SYSTABLECOMMENTS TC
  ON S.NAME = TC.SCHNAME
 AND T.NAME = TC.TVNAME
 AND TC.TABLE_TYPE = 'TABLE'
WHERE S.NAME = ? AND T.NAME = ?
  AND T.TYPE$ = 'SCHOBJ' AND T.SUBTYPE$ IN ('UTAB', 'STAB')
"""


def get_table_columns() -> str:
    """查询表列结构（含注释）。"""
    return """
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
FROM DBA_TAB_COLUMNS c
LEFT JOIN DBA_COL_COMMENTS cc
  ON cc.OWNER = c.OWNER
 AND cc.TABLE_NAME = c.TABLE_NAME
 AND cc.COLUMN_NAME = c.COLUMN_NAME
WHERE c.OWNER = ? AND c.TABLE_NAME = ?
ORDER BY c.COLUMN_ID;
"""


# ============================================================
# Views
# ============================================================


def _view_comment_select() -> str:
    return ", TC.COMMENT$ AS VIEW_COMMENT"


def _view_comment_join() -> str:
    return """
LEFT JOIN SYS.SYSTABLECOMMENTS TC
  ON TC.SCHNAME = S.NAME
 AND TC.TVNAME = T.NAME
 AND TC.TABLE_TYPE = 'VIEW'
"""


def list_views(include_comments: bool, schema: str | None = None) -> tuple[str, list[str] | None]:
    """返回视图列表 SQL 及参数。

    Args:
        include_comments: 是否包含注释字段。
        schema: 指定 schema 则返回该 schema 下的视图，None 返回全库。

    Returns:
        (sql_string, params) 元组；params 为 None 表示无参数。
    """
    comment_sel = _view_comment_select() if include_comments else ""
    comment_join = _view_comment_join() if include_comments else ""

    sql = f"""
SELECT
  S.NAME       AS SCHEMA_NAME,
  T.NAME       AS OBJECT_NAME,
  'VIEW'       AS OBJECT_TYPE
  {comment_sel}
FROM SYS.SYSOBJECTS T
JOIN SYS.SYSOBJECTS S ON T.SCHID = S.ID
{comment_join}
WHERE T.TYPE$ = 'SCHOBJ' AND T.SUBTYPE$ = 'VIEW'
"""
    if schema:
        sql += "  AND S.NAME = ?\nORDER BY T.NAME;\n"
        params: list[str] | None = [schema]
    else:
        sql += "ORDER BY S.NAME, T.NAME;\n"
        params = None

    return sql, params


def get_view_info() -> str:
    """查询视图基本信息（含注释）。"""
    return """
SELECT
  S.NAME AS SCHEMA_NAME,
  T.NAME AS VIEW_NAME,
  'VIEW' AS OBJECT_TYPE,
  TC.COMMENT$ AS VIEW_COMMENT
FROM SYS.SYSOBJECTS T
JOIN SYS.SYSOBJECTS S ON T.SCHID = S.ID
LEFT JOIN SYS.SYSTABLECOMMENTS TC
  ON S.NAME = TC.SCHNAME
 AND T.NAME = TC.TVNAME
 AND TC.TABLE_TYPE = 'VIEW'
WHERE S.NAME = ? AND T.NAME = ?
  AND T.TYPE$ = 'SCHOBJ' AND T.SUBTYPE$ = 'VIEW'
"""


def get_view_definition() -> str:
    """查询视图定义（DDL 文本）。

    优先从 DBA_VIEWS 按 OWNER + VIEW_NAME 获取，兼容部分环境 DBA_VIEWS 取不到时
    保留 SYS.SYSTEXTS 兜底查询（按 schema 过滤避免同名视图跨 schema 取错）。
    """
    return """
SELECT TEXT AS DEFINITION
FROM DBA_VIEWS
WHERE OWNER = ? AND VIEW_NAME = ?
"""


def get_view_columns() -> str:
    """查询视图列结构。"""
    return """
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


# ============================================================
# Indexes & Constraints
# ============================================================


def get_table_indexes() -> str:
    """查询表索引列表（返回多行，由 Mapper 按 INDEX_NAME 聚合）。"""
    return """
SELECT
  i.TABLE_OWNER  AS SCHEMA_NAME,
  i.TABLE_NAME   AS TABLE_NAME,
  i.INDEX_NAME   AS INDEX_NAME,
  i.UNIQUENESS   AS UNIQUENESS,
  i.INDEX_TYPE   AS INDEX_TYPE,
  c.COLUMN_POSITION AS COLUMN_POSITION,
  c.COLUMN_NAME  AS COLUMN_NAME,
  c.DESCEND      AS SORT_ORDER
FROM DBA_INDEXES i
JOIN DBA_IND_COLUMNS c
  ON i.OWNER = c.INDEX_OWNER
 AND i.INDEX_NAME = c.INDEX_NAME
WHERE i.TABLE_OWNER = ? AND i.TABLE_NAME = ?
ORDER BY i.INDEX_NAME, c.COLUMN_POSITION;
"""


def get_table_constraints() -> str:
    """查询表约束（PK/FK/UK/CHECK）。"""
    return """
SELECT
  c.OWNER            AS SCHEMA_NAME,
  c.TABLE_NAME       AS TABLE_NAME,
  c.CONSTRAINT_NAME  AS CONSTRAINT_NAME,
  c.CONSTRAINT_TYPE  AS CONSTRAINT_TYPE,
  c.STATUS           AS STATUS,
  cc.COLUMN_NAME     AS COLUMN_NAME,
  cc.POSITION        AS COLUMN_POSITION,
  c.R_OWNER          AS REF_OWNER,
  c.R_CONSTRAINT_NAME AS REF_CONSTRAINT_NAME,
  rc.TABLE_NAME      AS REF_TABLE_NAME,
  rcc.COLUMN_NAME    AS REF_COLUMN_NAME
FROM DBA_CONSTRAINTS c
LEFT JOIN DBA_CONS_COLUMNS cc
  ON c.OWNER = cc.OWNER
 AND c.CONSTRAINT_NAME = cc.CONSTRAINT_NAME
LEFT JOIN DBA_CONSTRAINTS rc
  ON rc.OWNER = c.R_OWNER
 AND rc.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME
LEFT JOIN DBA_CONS_COLUMNS rcc
  ON rcc.OWNER = c.R_OWNER
 AND rcc.CONSTRAINT_NAME = c.R_CONSTRAINT_NAME
 AND rcc.POSITION = cc.POSITION
WHERE c.OWNER = ? AND c.TABLE_NAME = ?
ORDER BY c.CONSTRAINT_NAME, cc.POSITION;
"""


def get_not_null_constraints() -> str:
    """补充 NOT NULL 约束查询。"""
    return """
SELECT COLUMN_NAME, NULLABLE
FROM ALL_TAB_COLUMNS
WHERE OWNER = ? AND TABLE_NAME = ? AND NULLABLE = 'N';
"""
