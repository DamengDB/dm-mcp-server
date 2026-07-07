"""DbMetadataService SQL 函数"""

# ============================================================
# Schemas
# ============================================================


def list_schemas() -> str:
    """查询所有 schema 列表。"""
    return """
SELECT NAME AS SCHEMA_NAME
FROM SYS.SYSOBJECTS
WHERE TYPE$ = 'SCH'
ORDER BY NAME
"""


# ============================================================
# Tables
# ============================================================


def list_tables() -> str:
    """查询指定 schema 下的表列表（含动态性能表）。

    Returns:
        SQL 字符串；调用方须传入 (schema, schema) 两个参数。
    """
    return """
SELECT TABLE_NAME, "COMMENT" FROM (
    SELECT OBJ.NAME AS TABLE_NAME,
           TC.COMMENT$ AS "COMMENT"
    FROM SYS.SYSOBJECTS OBJ
    JOIN SYS.SYSOBJECTS SCH ON OBJ.SCHID = SCH.ID
    LEFT JOIN SYS.SYSTABLECOMMENTS TC
        ON SCH.NAME = TC.SCHNAME
       AND OBJ.NAME = TC.TVNAME
    WHERE SCH.NAME = ?
      AND OBJ.SUBTYPE$ IN ('UTAB', 'STAB', 'VIEW')
    UNION
    SELECT NAME AS TABLE_NAME,
           NULL AS "COMMENT"
    FROM V$DYNAMIC_TABLES
    WHERE SCHNAME = ?
) T
ORDER BY TABLE_NAME
"""


# ============================================================
# Views
# ============================================================


def list_views(schema: str) -> tuple[str, tuple]:
    """查询指定 schema 下的视图列表。

    Args:
        schema: Schema 名称；当为 'SYS' 时放宽 subtype 条件。

    Returns:
        (sql_string, params) 元组。
    """
    if schema == "SYS":
        subtype_condition = "OBJ.SUBTYPE$ IN ('VIEW', 'SYNOM')"
        type_condition = "1=1"
    else:
        subtype_condition = "OBJ.SUBTYPE$ = 'VIEW'"
        type_condition = "OBJ.TYPE$ = 'SCHOBJ'"

    sql = f"""
SELECT OBJ.NAME AS VIEW_NAME,
       TC.COMMENT$ AS "COMMENT"
FROM SYS.SYSOBJECTS OBJ
JOIN SYS.SYSOBJECTS SCH ON OBJ.SCHID = SCH.ID
LEFT JOIN SYS.SYSTABLECOMMENTS TC
    ON SCH.NAME = TC.SCHNAME
   AND OBJ.NAME = TC.TVNAME
WHERE SCH.NAME = ?
  AND {subtype_condition}
  AND {type_condition}
ORDER BY OBJ.NAME
"""
    return sql, (schema,)


# ============================================================
# Columns
# ============================================================


def list_columns() -> str:
    """查询指定表下的列列表。

    Returns:
        SQL 字符串；调用方须传入 (schema, table) 两个参数。
    """
    return """
SELECT COL.NAME AS COLUMN_NAME,
       CC.COMMENT$ AS "COMMENT"
FROM SYS.SYSCOLUMNS COL
JOIN SYS.SYSOBJECTS OBJ ON COL.ID = OBJ.ID
JOIN SYS.SYSOBJECTS SCH ON OBJ.SCHID = SCH.ID
LEFT JOIN SYS.SYSCOLUMNCOMMENTS CC
    ON SCH.NAME = CC.SCHNAME
   AND OBJ.NAME = CC.TVNAME
   AND COL.NAME = CC.COLNAME
WHERE SCH.NAME = ?
  AND OBJ.NAME = ?
ORDER BY COL.COLID
"""
