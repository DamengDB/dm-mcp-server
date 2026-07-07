"""Inspection Mapper — 负责巡检类数据的格式化输出。"""

import re
from datetime import datetime
from typing import Any

from dm_mcp.core.mcp.format import to_table

# ============================================================
# 公共工具函数
# ============================================================


def compact_table(
    rows: list[dict], column_rename: dict[str, str] | None = None
) -> dict:
    """将 list[dict] 转为 columns+records 紧凑格式，支持列名映射。"""
    result = to_table(rows)
    if column_rename and result["columns"]:
        result["columns"] = [column_rename.get(c, c) for c in result["columns"]]
    return result


def clean_nulls(obj: Any) -> Any:
    """递归剔除 dict 中值为 None / 0 / '' 的字段。"""
    if isinstance(obj, dict):
        cleaned: dict[str, Any] = {}
        for k, v in obj.items():
            if v is None or v == "" or (isinstance(v, (int, float)) and v == 0):
                continue
            cleaned[k] = clean_nulls(v)
        return cleaned
    if isinstance(obj, list):
        return [clean_nulls(item) for item in obj]
    return obj


def compact_io_stats(fields: dict[str, Any]) -> dict[str, Any]:
    """IO 统计专用：保留 0，仅剔除 None / 空字符串。"""
    return {
        k: v
        for k, v in fields.items()
        if v is not None and not (isinstance(v, str) and v == "")
    }


_OPERATOR_STAT_ZERO_KEYS = (
    "memory_kb",
    "disk_kb",
    "rank",
    "time_us",
    "n_enter",
    "hash_used_cells",
    "hash_conflict",
    "dhash3_used_cells",
    "dhash3_conflict",
    "hash_same_value",
)


def _compact_operator_stats(fields: dict[str, Any]) -> dict[str, Any]:
    """算子运行时统计：保留数值类字段的 0。"""
    row = compact_io_stats(fields)
    for key in _OPERATOR_STAT_ZERO_KEYS:
        if key in fields and fields[key] is not None and key not in row:
            row[key] = fields[key]
    return row


_HASH_STAT_COLUMNS = (
    ("hash_used_cells", "HASH_USED_CELLS"),
    ("hash_conflict", "HASH_CONFLICT"),
    ("dhash3_used_cells", "DHASH3_USED_CELLS"),
    ("dhash3_conflict", "DHASH3_CONFLICT"),
    ("hash_same_value", "HASH_SAME_VALUE"),
)


def _merge_hash_statistics(op: dict[str, Any], row: dict[str, Any]) -> None:
    """从 ET / V$SQL_NODE_HISTORY 行合并哈希相关统计。"""
    for out_key, col in _HASH_STAT_COLUMNS:
        val = row.get(col)
        if val is not None:
            op[out_key] = val


def iso_time(value: Any) -> str | None:
    """将时间值转为 ISO 8601 字符串。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        # 已经是字符串则直接返回
        return value
    return str(value)


def compute_delta(
    prev_rows: list[dict],
    curr_rows: list[dict],
    key_cols: list[str],
    delta_cols: list[str] | dict[str, str],
    drop_nonpos: bool = False,
) -> list[dict]:
    """通用 Delta 计算。

    Args:
        prev_rows: 第一次采样结果。
        curr_rows: 第二次采样结果。
        key_cols: 用于关联两次采样的键列。
        delta_cols: 需要求差的列。
            - list[str]: 在 curr 行上添加 `delta_{col}` 列。
            - dict[str, str]: 按 {源列名: 输出列名} 映射添加。
        drop_nonpos: 为 True 时丢弃所有 delta 值均小于等于 0 的行。

    Returns:
        在 curr_rows 基础上添加了 delta 列的结果列表。
    """
    if not curr_rows:
        return []

    prev_map: dict[tuple, dict] = {}
    for row in prev_rows:
        key = tuple(row.get(c) for c in key_cols)
        prev_map[key] = row

    col_map: dict[str, str]
    if isinstance(delta_cols, dict):
        col_map = delta_cols
    else:
        col_map = {c: f"delta_{c}" for c in delta_cols}

    result: list[dict] = []
    for row in curr_rows:
        key = tuple(row.get(c) for c in key_cols)
        prev_row = prev_map.get(key)
        new_row = dict(row)
        has_positive = False
        for src_col, dst_col in col_map.items():
            curr_val = row.get(src_col)
            prev_val = prev_row.get(src_col) if prev_row else 0
            if curr_val is None:
                curr_val = 0
            if prev_val is None:
                prev_val = 0
            try:
                delta = float(curr_val) - float(prev_val)
            except (TypeError, ValueError):
                delta = 0
            if delta > 0:
                has_positive = True
            new_row[dst_col] = delta
        if drop_nonpos and not has_positive:
            continue
        result.append(new_row)
    return result


_CLASSID_MAP = {
    1: "字典",
    2: "SQL",
    3: "事务",
    4: "检查点",
    5: "RLOG",
    6: "UNDO",
    7: "IO",
    8: "B树",
    9: "网络",
    10: "文件",
    11: "内存",
    12: "CPU",
    13: "OS",
    14: "缓冲区",
    15: "限流控制",
    16: "DMDPC",
    20: "其它",
}


def map_delta_result(
    rows: list[dict],
    delta_seconds: int,
    mode: str,
    result_key: str,
    prev_rows: list[dict] | None = None,
    key_cols: list[str] | None = None,
    delta_cols: list[str] | dict[str, str] | None = None,
    drop_nonpos: bool = False,
    sort_key: str | None = None,
) -> dict[str, Any]:
    """通用 delta 结果包装：可选 compute_delta + compact_table + mode/delta_seconds 元信息。"""
    if mode == "delta" and prev_rows is not None and key_cols and delta_cols:
        rows = compute_delta(
            prev_rows,
            rows,
            key_cols=key_cols,
            delta_cols=delta_cols,
            drop_nonpos=drop_nonpos,
        )
        if sort_key:
            rows.sort(key=lambda x: -x.get(sort_key, 0))
    result = compact_table(rows)
    result["mode"] = mode
    if mode == "delta":
        result["delta_seconds"] = delta_seconds
    return {result_key: result}


def map_buffer_pool_stats(rows: list[dict]) -> dict[str, Any]:
    """格式化缓冲池统计输出（#09）。"""
    return {"pools": compact_table(rows)}


def map_object_lock_context(object_id: int, rows: list[dict]) -> dict[str, Any]:
    """格式化对象锁上下文输出（#07）。"""
    return {"object_id": object_id, "locks": compact_table(rows)}


# ============================================================
# explain_plan
# ============================================================


def merge_runtime_statistics(
    sql_stat: dict[str, Any] | None,
    sql_history: dict[str, Any] | None = None,
    sql_stat_history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将运行时统计行（或三视图合并结果）映射为 Statistics 字段。"""
    row = sql_stat or {}
    if not row and (sql_history or sql_stat_history):
        stat_hist = sql_stat_history or {}
        hist = sql_history or {}

        def _pick(*keys: str) -> Any:
            for key in keys:
                if key in stat_hist and stat_hist[key] is not None:
                    return stat_hist[key]
                if key in hist and hist[key] is not None:
                    return hist[key]
            return None

        row = {
            "DATA_PAGES_CHANGED": _pick("DATA_PAGES_CHANGED"),
            "UNDO_PAGES_CHANGED": _pick("UNDO_PAGES_CHANGED"),
            "LOGICAL_READS": _pick("LOGICAL_READS"),
            "PHYSICAL_READS": _pick("PHYSICAL_READS"),
            "REDO_SIZE": _pick("REDO_SIZE"),
            "BYTES_SENT_TO_CLIENT": _pick("BYTES_SENT_TO_CLIENT"),
            "BYTES_RECEIVED_FROM_CLIENT": _pick("BYTES_RECEIVED_FROM_CLIENT"),
            "ROUNDTRIPS_TO_FROM_CLIENT": _pick("ROUNDTRIPS_TO_FROM_CLIENT"),
            "ROWS_PROCESSED": _pick("ROWS_PROCESSED"),
            "IO_WAIT_TIME_MS": _pick("IO_WAIT_TIME_MS"),
            "EXEC_TIME_MS": _pick("EXEC_TIME_MS"),
            "TAB_SCAN_COUNT": _pick("TAB_SCAN_COUNT"),
            "EXEC_CPU_MS": _pick("EXEC_CPU_MS"),
        }

    return compact_io_stats(
        {
            "data_pages_changed": row.get("DATA_PAGES_CHANGED"),
            "undo_pages_changed": row.get("UNDO_PAGES_CHANGED"),
            "logical_reads": row.get("LOGICAL_READS"),
            "physical_reads": row.get("PHYSICAL_READS"),
            "redo_size": row.get("REDO_SIZE"),
            "bytes_sent_to_client": row.get("BYTES_SENT_TO_CLIENT"),
            "bytes_received_from_client": row.get("BYTES_RECEIVED_FROM_CLIENT"),
            "roundtrips_to_from_client": row.get("ROUNDTRIPS_TO_FROM_CLIENT"),
            "rows_processed": row.get("ROWS_PROCESSED"),
            "io_wait_time_ms": row.get("IO_WAIT_TIME_MS"),
            "exec_time_ms": row.get("EXEC_TIME_MS"),
            "tab_scan_count": row.get("TAB_SCAN_COUNT"),
            "exec_cpu_ms": row.get("EXEC_CPU_MS"),
        }
    )


def _format_statistics_block(statistics: dict[str, Any]) -> str:
    """格式化为 disql AUTOTRACE 风格的 Statistics 文本块。"""
    if not statistics:
        return ""

    label_map = [
        ("data_pages_changed", "data pages changed"),
        ("undo_pages_changed", "undo pages changed"),
        ("logical_reads", "logical reads"),
        ("physical_reads", "physical reads"),
        ("redo_size", "redo size"),
        ("bytes_sent_to_client", "bytes sent to client"),
        ("bytes_received_from_client", "bytes received from client"),
        ("roundtrips_to_from_client", "roundtrips to/from client"),
        ("rows_processed", "rows processed"),
        ("io_wait_time_ms", "io wait time(ms)"),
        ("exec_time_ms", "exec time(ms)"),
    ]
    lines = ["Statistics"]
    for key, label in label_map:
        if key in statistics:
            lines.append(f"    {statistics[key]}\t{label}")
    return "\n".join(lines)


_EXPLAIN_LINE_RE = re.compile(r"^(\s*\d+\s+)(.*)$")


def _append_operator_extras(rest: str, extras: list[str]) -> str:
    if not extras:
        return rest
    missing = [
        item
        for item in extras
        if f"{item.split('(')[0]}(" not in rest.upper()
    ]
    if not missing:
        return rest
    bracket_end = rest.find("]")
    if bracket_end < 0:
        return f"{rest}; {', '.join(missing)}"
    insert_at = bracket_end + 1
    tail = rest[insert_at:]
    if tail.startswith(";"):
        tail = tail[1:].lstrip()
        sep = ", " if tail else ""
        return f"{rest[:insert_at]}; {', '.join(missing)}{sep}{tail}"
    return f"{rest[:insert_at]}; {', '.join(missing)}{tail}"


def enrich_explain_text(
    explain_text: str | None,
    node_rows: list[dict[str, Any]] | None,
) -> str:
    """用 V$SQL_NODE_HISTORY 为计划行补充 MEM_USED / DISK_USED 等运行时信息。"""
    if not explain_text or not node_rows:
        return (explain_text or "").strip()

    nodes: dict[int, dict[str, Any]] = {}
    for row in node_rows:
        seq = row.get("SEQ_NO")
        if seq is not None:
            nodes[int(seq)] = row

    enriched: list[str] = []
    for line in explain_text.splitlines():
        match = _EXPLAIN_LINE_RE.match(line)
        if not match:
            enriched.append(line)
            continue
        prefix, rest = match.groups()
        if "#" not in rest:
            enriched.append(line)
            continue
        line_no = int(prefix.strip())
        node = nodes.get(line_no)
        if node:
            extras: list[str] = []
            mem = node.get("MEM_USED")
            if mem is not None and int(mem) > 0:
                extras.append(f"MEM_USED({int(mem)}KB)")
            disk = node.get("DISK_USED")
            if disk is not None and int(disk) > 0:
                extras.append(f"DISK_USED({int(disk)}KB)")
            rest = _append_operator_extras(rest, extras)
        enriched.append(f"{prefix}{rest}")

    return "\n".join(enriched).strip()


def _et_row_seq(row: dict[str, Any]) -> int | None:
    for key in ("SEQ", "seq", "SEQ_NO"):
        val = row.get(key)
        if val is not None:
            return int(val)
    return None


def _et_row_get(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def build_operators_summary(
    node_rows: list[dict[str, Any]] | None,
    et_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """按 SEQ 合并 V$SQL_NODE_HISTORY 与 ET()，突出算子级内存/磁盘/耗时。"""
    by_seq: dict[int, dict[str, Any]] = {}

    for row in node_rows or []:
        seq = row.get("SEQ_NO")
        if seq is None:
            continue
        s = int(seq)
        op_row: dict[str, Any] = {
            "seq": s,
            "operator": None,
            "type_code": row.get("TYPE$"),
            "mem_used_kb": row.get("MEM_USED"),
            "disk_used_kb": row.get("DISK_USED"),
            "time_used_us": row.get("TIME_USED"),
            "n_enter": row.get("N_ENTER"),
            "time_us": None,
            "time_percent": None,
            "et_rank": None,
        }
        _merge_hash_statistics(op_row, row)
        by_seq[s] = op_row

    for row in et_rows or []:
        seq = _et_row_seq(row)
        if seq is None:
            continue
        op = by_seq.setdefault(
            seq,
            {
                "seq": seq,
                "operator": None,
                "type_code": None,
                "mem_used_kb": None,
                "disk_used_kb": None,
                "time_used_us": None,
                "n_enter": None,
                "time_us": None,
                "time_percent": None,
                "et_rank": None,
            },
        )
        op["operator"] = _et_row_get(row, "OP", "op") or op.get("operator")
        op["time_us"] = _et_row_get(row, "TIME(US)", "TIME_US", "time_us")
        op["time_percent"] = _et_row_get(row, "PERCENT", "percent")
        op["et_rank"] = _et_row_get(row, "RANK", "rank")
        op["n_enter"] = _et_row_get(row, "N_ENTER", "n_enter") or op.get("n_enter")
        mem_kb = _et_row_get(row, "MEM_USED(KB)", "MEM_USED_KB", "mem_used_kb")
        disk_kb = _et_row_get(row, "DISK_USED(KB)", "DISK_USED_KB", "disk_used_kb")
        if mem_kb is not None:
            op["mem_used_kb"] = mem_kb
        if disk_kb is not None:
            op["disk_used_kb"] = disk_kb
        _merge_hash_statistics(op, row)

    return [by_seq[k] for k in sorted(by_seq)]


def _statement_io_statistics(
    merged: dict[str, Any] | None,
) -> dict[str, Any]:
    """语句级逻辑读/物理读（V$SQL_STAT / V$SQL_HISTORY）；0 亦保留。"""
    stats = merged or {}
    return compact_io_stats(
        {
            "logical_reads": stats.get("logical_reads"),
            "physical_reads": stats.get("physical_reads"),
        }
    )


def _operator_has_io_statistics(op: dict[str, Any]) -> bool:
    """算子是否存在非零内存或磁盘用量。"""
    mem = op.get("mem_used_kb")
    disk = op.get("disk_used_kb")
    return (mem is not None and mem != 0) or (disk is not None and disk != 0)


def _operator_has_runtime_statistics(op: dict[str, Any]) -> bool:
    """算子是否有可输出的运行时统计（ET 耗时或 node/ET 内存磁盘）。"""
    if op.get("time_us") is not None or op.get("time_used_us") is not None:
        return True
    return _operator_has_io_statistics(op)


_PLAN_OPERATOR_RE = re.compile(r"#\s*([A-Z][A-Z0-9]+(?:\s+[A-Z]+)*)", re.IGNORECASE)
_INI_PARAM_EXCLUDE = frozenset({"NLS_SORT_TYPE"})


def _param_ini_groups(name: str) -> set[str]:
    """V$PARAMETER 名称对应的算子参数组。"""
    upper = name.upper()
    if upper in _INI_PARAM_EXCLUDE:
        return set()
    groups: set[str] = set()
    if upper.startswith("HAGR_") or upper == "USE_HAGR_FLAG":
        groups.add("hash_aggregate")
    if upper.startswith("HJ_"):
        groups.add("hash_join")
    if upper.startswith("SORT_") or upper.startswith("TSORT_"):
        groups.add("sort")
    return groups


def _operator_ini_group(operator: str) -> str | None:
    """计划/ET 算子名映射到 sort / hash_join / hash_aggregate。"""
    token = operator.strip().split()[0].upper()
    full = operator.upper()
    if token.startswith("SORT"):
        return "sort"
    if token.startswith("HI") or token.startswith("HJ"):
        return "hash_join"
    if "HASH" in full and "JOIN" in full:
        return "hash_join"
    if token.startswith("HAGR"):
        return "hash_aggregate"
    return None


def extract_plan_operators(origin_plan: str | None) -> list[str]:
    """从 origin_plan 文本提取算子名（保持出现顺序、去重）。"""
    if not origin_plan:
        return []
    seen: list[str] = []
    for match in _PLAN_OPERATOR_RE.finditer(origin_plan):
        op = match.group(1).strip()
        if op and op not in seen:
            seen.append(op)
    return seen


def group_ini_params_by_operator(
    origin_plan: str | None,
    parameter_rows: list[dict[str, Any]] | None,
    *,
    node_rows: list[dict[str, Any]] | None = None,
    et_rows: list[dict] | None = None,
) -> dict[str, dict[str, Any]]:
    """按执行计划中的算子聚合 V$PARAMETER，每组仅保留参数名 -> value。"""
    by_group: dict[str, dict[str, Any]] = {
        "sort": {},
        "hash_join": {},
        "hash_aggregate": {},
    }
    for row in parameter_rows or []:
        name = row.get("NAME") or row.get("PARA_NAME")
        value = row.get("VALUE")
        if not name or value is None:
            continue
        for group in _param_ini_groups(str(name)):
            by_group[group][str(name)] = value

    operators = extract_plan_operators(origin_plan)
    for op in build_operators_summary(node_rows, et_rows):
        name = op.get("operator")
        if name and name not in operators:
            operators.append(str(name))

    grouped: dict[str, dict[str, Any]] = {}
    for op in operators:
        group = _operator_ini_group(op)
        if not group:
            continue
        params = by_group.get(group)
        if not params:
            continue
        grouped[op] = dict(sorted(params.items()))
    return grouped


def build_operator_statistics(
    origin_plan: str | None,
    node_rows: list[dict[str, Any]] | None,
    et_rows: list[dict] | None,
    parameter_rows: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """按 seq 合并 ET、V$SQL_NODE_HISTORY 与相关 INI（V$PARAMETER）。"""
    ini_by_operator = group_ini_params_by_operator(
        origin_plan,
        parameter_rows,
        node_rows=node_rows,
        et_rows=et_rows,
    )
    operators: dict[str, dict[str, Any]] = {}
    for op in build_operators_summary(node_rows, et_rows):
        if not _operator_has_runtime_statistics(op):
            continue
        seq = op.get("seq")
        if seq is None:
            continue

        time_us = op.get("time_us")
        if time_us is None:
            time_us = op.get("time_used_us")

        row = _compact_operator_stats(
            {
                "operator": op.get("operator"),
                "time_us": time_us,
                "time_percent": op.get("time_percent"),
                "rank": op.get("et_rank"),
                "memory_kb": op.get("mem_used_kb"),
                "disk_kb": op.get("disk_used_kb"),
                "n_enter": op.get("n_enter"),
                "hash_used_cells": op.get("hash_used_cells"),
                "hash_conflict": op.get("hash_conflict"),
                "dhash3_used_cells": op.get("dhash3_used_cells"),
                "dhash3_conflict": op.get("dhash3_conflict"),
                "hash_same_value": op.get("hash_same_value"),
            }
        )
        op_name = op.get("operator")
        if op_name and op_name in ini_by_operator:
            row["ini"] = ini_by_operator[str(op_name)]

        operators[str(int(seq))] = row
    return operators


def explain_plan(
    *,
    explain_text: str | None = None,
    statistics: dict[str, Any] | None = None,
    exec_id: int | None = None,
    et_rows: list[dict] | None = None,
    node_rows: list[dict[str, Any]] | None = None,
    session_parameter_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """返回执行计划原文与语句/算子级 IO 统计，供 Agent 自行解读。"""
    origin_plan = (explain_text or "").strip() or None
    operator_stats = build_operator_statistics(
        origin_plan,
        node_rows,
        et_rows,
        session_parameter_rows,
    )
    stats: dict[str, Any] = {
        "statement": _statement_io_statistics(statistics),
        "operators": operator_stats,
    }
    return {
        "exec_id": exec_id,
        "origin_plan": origin_plan,
        "statistics": stats,
    }


def map_session_wait_events(
    prev_rows: list[dict] | None,
    curr_rows: list[dict],
    delta_seconds: int,
) -> tuple[dict, str]:
    """格式化会话等待事件，支持 delta / cumulative 两种模式。

    Returns:
        (compact_table_result, mode)
    """
    if delta_seconds > 0 and prev_rows is not None:
        rows = compute_delta(
            prev_rows,
            curr_rows,
            key_cols=["EVENT"],
            delta_cols={
                "TOTAL_WAITS": "delta_waits",
                "TIME_WAITED_SEC": "delta_time_ms",
            },
        )
        for r in rows:
            r["delta_time_ms"] = r.get("delta_time_ms", 0) * 1000
        mode = "delta"
    else:
        rows = curr_rows
        mode = "cumulative"
    return compact_table(rows), mode


def map_session_context(
    session_row: dict | None,
    wait_events: dict,
    wait_history: dict,
    delta_seconds: int,
    mode: str,
) -> dict[str, Any]:
    """组装工具 5 的分层嵌套结构。"""
    if not session_row:
        return {}

    # 会话基本信息
    session = {
        "sess_id": session_row.get("session_id") or session_row.get("SESS_ID"),
        "state": session_row.get("state") or session_row.get("STATE"),
        "user_name": session_row.get("user_name") or session_row.get("USER_NAME"),
        "clnt_ip": session_row.get("client_ip") or session_row.get("CLNT_IP"),
        "create_time": iso_time(
            session_row.get("create_time") or session_row.get("CREATE_TIME")
        ),
        "auto_commit": session_row.get("auto_commit") or session_row.get("AUTO_CMT"),
    }

    # 事务信息
    transaction = {
        "trx_id": session_row.get("trx_id") or session_row.get("TRX_ID"),
        "status": session_row.get("trx_status") or session_row.get("STATUS"),
        "lock_cnt": session_row.get("lock_count") or session_row.get("LOCK_CNT"),
        "n_undo_pages": session_row.get("n_undo_pages") or session_row.get("N_PAGES"),
    }

    # 当前 SQL
    current_sql = {
        "sql_id": session_row.get("sql_id") or session_row.get("SQL_ID"),
        "sql_text": session_row.get("sql_text") or session_row.get("SQL_TXT"),
        "exec_time_ms": session_row.get("exec_time_ms") or session_row.get("EXEC_TIME"),
    }

    # 线程信息
    thread = {
        "thread_id": session_row.get("thread_id") or session_row.get("ID"),
        "cpu_id": session_row.get("cpu_id") or session_row.get("PROCESSOR_ID"),
        "wait_status": session_row.get("wait_status") or session_row.get("WAIT_STATUS"),
        "wait_ms": session_row.get("THREAD_WAIT_TIME_MS"),
    }

    return clean_nulls(
        {
            "session": session,
            "transaction": transaction,
            "current_sql": current_sql,
            "thread": thread,
            "wait_events": {
                "mode": mode,
                "delta_seconds": delta_seconds if mode == "delta" else None,
                "events": wait_events,
                "recent_history": wait_history,
            },
        }
    )


def map_transaction_context(
    trx_row: dict | None,
    holding: list[dict],
    waiting: list[dict],
    chain_rows: list[dict],
) -> dict[str, Any]:
    """组装工具 6 的分层嵌套结构。"""
    empty = compact_table([])
    if not trx_row:
        return {
            "transaction": {},
            "session": {},
            "locks": {"holding": empty, "waiting": empty},
            "wait_chain": {"blocked_by": empty, "blocking": empty},
        }

    transaction = {
        "trx_id": trx_row.get("trx_id") or trx_row.get("ID"),
        "status": trx_row.get("trx_status") or trx_row.get("STATUS"),
        "read_only": trx_row.get("read_only") or trx_row.get("READ_ONLY"),
        "lock_cnt": trx_row.get("lock_count") or trx_row.get("LOCK_CNT"),
        "n_undo_pages": trx_row.get("n_undo_pages") or trx_row.get("N_PAGES"),
    }

    session = {
        "sess_id": trx_row.get("session_id") or trx_row.get("SESS_ID"),
        "user_name": trx_row.get("user_name") or trx_row.get("USER_NAME"),
        "current_sql": trx_row.get("CURRENT_SQL"),
    }

    blocked_by = [
        r
        for r in chain_rows
        if (r.get("chain_role") or r.get("CHAIN_ROLE")) == "BLOCKED_BY"
    ]
    blocking = [
        r
        for r in chain_rows
        if (r.get("chain_role") or r.get("CHAIN_ROLE")) == "BLOCKING"
    ]

    return clean_nulls(
        {
            "transaction": transaction,
            "session": session,
            "locks": {
                "holding": compact_table(holding),
                "waiting": compact_table(waiting),
            },
            "wait_chain": {
                "blocked_by": compact_table(blocked_by),
                "blocking": compact_table(blocking),
            },
        }
    )


def format_sql_stat_row(row: dict, mode: str) -> dict[str, Any] | None:
    """格式化单条 SQL 统计记录（#08 使用）"""
    source = row.get("SOURCE")
    if not source:
        return None

    result: dict[str, Any] = {
        "source": source,
        "start_time": iso_time(row.get("start_time") or row.get("START_TIME")),
    }
    end_time = row.get("end_time") or row.get("END_TIME")
    if end_time:
        result["end_time"] = iso_time(end_time)

    # execution
    execution: dict[str, Any] = {}
    if mode == "delta" and source == "current":
        execution["parse_elapsd_ms"] = row.get("delta_parse_elapsd_ms")
        execution["exec_cpu_ms"] = row.get("delta_exec_cpu_ms")
        execution["parse_cnt"] = row.get("delta_parse_count")
        execution["hard_parse_cnt"] = row.get("delta_hard_parse_count")
        execution["parse_time_ms"] = row.get("delta_parse_time_ms")
        execution["hard_parse_time_ms"] = row.get("delta_hard_parse_time_ms")
    else:
        execution["parse_elapsd_ms"] = row.get("PARSE_ELAPSD_MS")
        execution["exec_cpu_ms"] = row.get("EXEC_CPU_MS")
        execution["parse_cnt"] = row.get("PARSE_COUNT")
        execution["hard_parse_cnt"] = row.get("HARD_PARSE_COUNT")
        execution["parse_time_ms"] = row.get("PARSE_TIME_MS")
        execution["hard_parse_time_ms"] = row.get("HARD_PARSE_TIME_MS")
    if any(v is not None for v in execution.values()):
        result["execution"] = execution

    # io
    io_data: dict[str, Any] = {}
    if mode == "delta" and source == "current":
        io_data["logical_reads"] = row.get("DELTA_LOGICAL_READS")
        io_data["physical_reads"] = row.get("DELTA_PHYSICAL_READS")
        io_data["physical_writes"] = row.get("DELTA_PHYSICAL_WRITES")
        io_data["tab_scan_cnt"] = row.get("DELTA_TAB_SCAN_COUNT")
    else:
        io_data["logical_reads"] = row.get("LOGICAL_READS")
        io_data["physical_reads"] = row.get("PHYSICAL_READS")
        io_data["physical_writes"] = row.get("PHYSICAL_WRITES")
        io_data["tab_scan_cnt"] = row.get("TAB_SCAN_COUNT")
    if any(v is not None for v in io_data.values()):
        result["io"] = io_data

    # memory
    mem = row.get("MAX_MEM_USED_KB")
    if mem is not None:
        result["memory"] = {"max_mem_used_kb": mem}

    # network
    net: dict[str, Any] = {}
    if mode == "delta" and source == "current":
        net["bytes_recv"] = row.get("DELTA_NET_BYTES_RECV")
        net["bytes_send"] = row.get("DELTA_NET_BYTES_SEND")
    else:
        net["bytes_recv"] = row.get("NET_BYTES_RECV")
        net["bytes_send"] = row.get("NET_BYTES_SEND")
    if any(v is not None for v in net.values()):
        result["network"] = net

    return clean_nulls(result)


def map_sql_execution_stats(
    rows: list[dict],
    prev_rows: list[dict] | None,
    delta_seconds: int,
    sql_id: Any,
) -> dict[str, Any]:
    """格式化 SQL 执行统计输出，支持 delta / cumulative 两种模式。

    当 delta_seconds > 0 且 prev_rows 存在时，仅对 source='current' 的行
    做 delta 计算，history 行保持不变。
    """
    if delta_seconds > 0 and prev_rows is not None:
        prev_current = [r for r in prev_rows if r.get("SOURCE") == "current"]
        current_rows = [r for r in rows if r.get("SOURCE") == "current"]
        history_rows = [r for r in rows if r.get("SOURCE") == "history"]
        if prev_current and current_rows:
            current_rows = compute_delta(
                prev_current,
                current_rows,
                key_cols=["SOURCE"],
                delta_cols={
                    "PARSE_ELAPSD_MS": "delta_parse_elapsd_ms",
                    "EXEC_CPU_MS": "delta_exec_cpu_ms",
                    "PARSE_COUNT": "delta_parse_count",
                    "HARD_PARSE_COUNT": "delta_hard_parse_count",
                    "PARSE_TIME_MS": "delta_parse_time_ms",
                    "HARD_PARSE_TIME_MS": "delta_hard_parse_time_ms",
                    "LOGICAL_READS": "delta_logical_reads",
                    "PHYSICAL_READS": "delta_physical_reads",
                    "PHYSICAL_WRITES": "delta_physical_writes",
                    "IO_WAIT_TIME_MS": "delta_io_wait_time_ms",
                    "TAB_SCAN_COUNT": "delta_tab_scan_count",
                    "NET_BYTES_RECV": "delta_net_bytes_recv",
                    "NET_BYTES_SEND": "delta_net_bytes_send",
                },
            )
        rows = current_rows + history_rows
        mode = "delta"
    else:
        mode = "cumulative"

    sql_text = ""
    if rows:
        sql_text = rows[0].get("sql_text") or rows[0].get("SQL_TXT") or ""

    stats = [stat for r in rows if (stat := format_sql_stat_row(r, mode))]

    return clean_nulls(
        {
            "sql_id": sql_id,
            "sql_text": sql_text,
            "mode": mode,
            "stats": stats,
        }
    )


def map_sysstat_delta(
    rows: list[dict],
    prev_rows: list[dict] | None,
    delta_seconds: int,
) -> dict[str, Any]:
    """格式化系统统计增量输出。"""
    if prev_rows:
        rows = compute_delta(
            prev_rows,
            rows,
            key_cols=["CLASS_ID", "STAT_NAME"],
            delta_cols={"STAT_VALUE": "delta"},
            drop_nonpos=True,
        )
        for r in rows:
            r["rate_per_sec"] = round(r["delta"] / delta_seconds, 2)
            r["class_name"] = _CLASSID_MAP.get(r.get("CLASS_ID"), "其它")
        rows.sort(key=lambda x: -x.get("delta", 0))

    return {
        "delta_seconds": delta_seconds,
        "categories": compact_table(rows),
    }
