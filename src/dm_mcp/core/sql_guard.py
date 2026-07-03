"""SQL 风控核心逻辑（纯工具模块）。

原先位于 services/sql_guard_service.py，这里下沉为 core 层工具：
- 不再作为 Service 暴露
- 由 MCP 中间件和 Provider 内部按需直接调用
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


class RiskLevel(str, enum.Enum):
    """SQL 风险等级枚举"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCK = "BLOCK"


WRITE_KEYWORDS: List[str] = [
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "TRUNCATE",
    "ALTER",
    "DROP",
    "CREATE",
    "CALL",
]

TX_KEYWORDS: List[str] = [
    "COMMIT",
    "ROLLBACK",
]

LOCK_PATTERNS: List[str] = [
    "FOR UPDATE",
    "LOCK TABLE",
]

SYSTEM_FUNCTION_ALLOWLIST: List[str] = [
    "ABS",
    "SUBSTR",
    "INSTR",
    "LENGTH",
    "LPAD",
    "RPAD",
    "TRIM",
    "LTRIM",
    "RTRIM",
    "REPLACE",
    "REVERSE",
    "UPPER",
    "LOWER",
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "ROUND",
    "CAST",
    "CEIL",
    "FLOOR",
    "ABS",
    "SIGN",
    "SQRT",
    "POW",
    "EXP",
    "LOG",
    "SIN",
    "COS",
    "TAN",
    "ASIN",
    "ACOS",
    "ATAN",
    "GROUP",
    "ORDER",
    "BY",
    "LIMIT",
    "OFFSET",
]

SYSTEM_SCHEMA_ALLOWLIST: List[str] = [
    "SYS",
    "SYSDBA",
]


@dataclass
class SqlRiskReport:
    """SQL 风险分析报告"""

    normalized_sql: str
    statement_type: str
    is_select: bool
    has_for_update: bool
    has_lock_table: bool
    write_tokens: List[str]
    tx_tokens: List[str]
    calls: List[str]
    unknown_calls: List[str]
    risky_calls: List[str]
    risk_level: RiskLevel
    reason: str
    details: Dict[str, Any]


class RoutineIntrospector:
    """例程内省器（可选，用于进一步分析函数/过程的安全性）"""

    def __init__(self, exec_sql_func: Optional[Any] = None) -> None:
        self._exec_sql_func = exec_sql_func

    # 这里保留最小实现以满足当前 SqlGuard 用例；详细行为仍由测试约束

    def classify_routine(self, name: str) -> str:
        """根据例程定义内容大致判断 SAFE / RISKY / UNKNOWN"""
        text = self._fetch_routine_text(name)
        if not text:
            return "UNKNOWN"

        upper = text.upper()
        if any(k in upper for k in WRITE_KEYWORDS):
            return "RISKY"
        return "SAFE"

    def _fetch_routine_text(self, name: str) -> Optional[str]:
        if not self._exec_sql_func or not name or not name.strip():
            return None
        try:
            return str(self._exec_sql_func(name))
        except Exception:
            return None


class SqlGuard:
    """SQL 安全防护器"""

    def __init__(self, *, routine_introspector: Optional[RoutineIntrospector] = None):
        self._ri = routine_introspector

    def analyze(self, sql_text: str, *, mode: str = "readonly") -> SqlRiskReport:
        normalized, meta = self._normalize(sql_text)

        token_hits = self._scan_tokens(normalized)
        statement_type_guess = self._guess_statement_type(normalized)
        ast = self._parse_ast_safe(normalized)
        stmt_type = ast.get("statement_type") if ast else statement_type_guess
        is_select = stmt_type.upper() == "SELECT"

        has_for_update = (
            ast.get("has_for_update", False)
            if ast
            else self._regex_for_update(normalized)
        )
        has_lock_table = (
            ast.get("has_lock_table", False)
            if ast
            else self._regex_lock_table(normalized)
        )

        calls = (
            ast.get("routine_calls", [])
            if ast
            else self._heuristic_extract_calls(normalized)
        )
        calls = self._canonicalize_calls(calls)

        unknown_calls: List[str] = []
        risky_calls: List[str] = []
        for c in calls:
            if self._is_system_safe_call(c):
                continue
            if not self._ri:
                unknown_calls.append(c)
                continue
            verdict = self._ri.classify_routine(c)
            if verdict == "RISKY":
                risky_calls.append(c)
            elif verdict == "UNKNOWN":
                unknown_calls.append(c)

        write_tokens = token_hits.get("write", [])
        tx_tokens = token_hits.get("tx", [])

        risk_level, reason = self._decide(
            mode=mode,
            is_select=is_select,
            stmt_type=stmt_type,
            has_for_update=has_for_update,
            has_lock_table=has_lock_table,
            write_tokens=write_tokens,
            tx_tokens=tx_tokens,
            risky_calls=risky_calls,
            unknown_calls=unknown_calls,
        )

        return SqlRiskReport(
            normalized_sql=normalized,
            statement_type=stmt_type,
            is_select=is_select,
            has_for_update=has_for_update,
            has_lock_table=has_lock_table,
            write_tokens=write_tokens,
            tx_tokens=tx_tokens,
            calls=calls,
            unknown_calls=unknown_calls,
            risky_calls=risky_calls,
            risk_level=risk_level,
            reason=reason,
            details={"meta": meta, "token_hits": token_hits},
        )

    def _normalize(self, sql: str) -> Tuple[str, Dict[str, Any]]:
        meta: Dict[str, Any] = {"original_length": len(sql), "has_comments": False}

        # 去掉行注释 --
        lines: List[str] = []
        for line in sql.split("\n"):
            if "--" in line:
                comment_pos = line.find("--")
                before_comment = line[:comment_pos]
                if before_comment.count("'") % 2 == 0:
                    lines.append(before_comment)
                    meta["has_comments"] = True
                else:
                    lines.append(line)
            else:
                lines.append(line)
        sql = "\n".join(lines)

        # 去掉多行注释 /* */
        def remove_block_comments(text: str) -> str:
            pattern = r"/\*.*?\*/"
            result = re.sub(pattern, "", text, flags=re.DOTALL)
            if result != text:
                meta["has_comments"] = True
            return result

        sql = remove_block_comments(sql)

        # 保护字符串字面量
        str_placeholders: List[str] = []
        str_pattern = r"'([^']|'')*'"

        def replace_str(match: re.Match[str]) -> str:
            placeholder = f"__STR_{len(str_placeholders)}__"
            str_placeholders.append(match.group(0))
            return placeholder

        normalized = re.sub(str_pattern, replace_str, sql)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        meta["str_placeholders_count"] = len(str_placeholders)
        return normalized, meta

    def _scan_tokens(self, normalized: str) -> Dict[str, List[str]]:
        result: Dict[str, List[str]] = {"write": [], "tx": [], "lock": []}
        upper_sql = normalized.upper()

        for keyword in WRITE_KEYWORDS:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, upper_sql):
                result["write"].append(keyword)

        for keyword in TX_KEYWORDS:
            pattern = r"\b" + re.escape(keyword) + r"\b"
            if re.search(pattern, upper_sql):
                result["tx"].append(keyword)

        for pattern_str in LOCK_PATTERNS:
            if pattern_str.upper() in upper_sql:
                result["lock"].append(pattern_str)

        return result

    def _parse_ast_safe(self, normalized: str) -> Optional[Dict[str, Any]]:
        try:
            stmt_type = self._guess_statement_type(normalized)
            has_for_update = self._regex_for_update(normalized)
            has_lock_table = self._regex_lock_table(normalized)
            routine_calls = self._heuristic_extract_calls(normalized)
            return {
                "statement_type": stmt_type,
                "has_for_update": has_for_update,
                "has_lock_table": has_lock_table,
                "routine_calls": routine_calls,
            }
        except Exception as exc:  # noqa: BLE001
            logger.debug("AST解析失败: %s", exc)
            return None

    def _guess_statement_type(self, normalized: str) -> str:
        upper = normalized.upper().strip().lstrip("(").strip()
        first_word = upper.split(None, 1)[0] if upper else ""

        statement_types: Iterable[str] = [
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "MERGE",
            "TRUNCATE",
            "ALTER",
            "DROP",
            "CREATE",
            "GRANT",
            "REVOKE",
            "COMMIT",
            "ROLLBACK",
            "CALL",
            "EXEC",
            "EXECUTE",
            "WITH",
            "EXPLAIN",
        ]

        for stmt_type in statement_types:
            if first_word.startswith(stmt_type):
                return stmt_type
        return "UNKNOWN"

    def _regex_for_update(self, normalized: str) -> bool:
        return bool(re.search(r"\bFOR\s+UPDATE\b", normalized, re.IGNORECASE))

    def _regex_lock_table(self, normalized: str) -> bool:
        return bool(re.search(r"\bLOCK\s+TABLE\b", normalized, re.IGNORECASE))

    def _heuristic_extract_calls(self, normalized: str) -> List[str]:
        calls: List[str] = []
        pattern = r"\b([A-Z_][A-Z0-9_]*\.)?([A-Z_][A-Z0-9_]*)\s*\("
        for match in re.finditer(pattern, normalized, re.IGNORECASE):
            schema = match.group(1)
            func_name = match.group(2)
            if func_name.upper() in SYSTEM_FUNCTION_ALLOWLIST:
                continue
            if schema:
                schema_name = schema.rstrip(".").upper()
                if schema_name in SYSTEM_SCHEMA_ALLOWLIST:
                    continue
            full_name = (
                f"{schema.rstrip('.')}.{func_name}" if schema else func_name  # type: ignore[union-attr]
            )
            calls.append(full_name)
        return list(set(calls))

    def _canonicalize_calls(self, calls: List[str]) -> List[str]:
        canonicalized: List[str] = []
        for call in calls:
            normalized_call = re.sub(r"\s+", "", call.upper())
            canonicalized.append(normalized_call)
        return list(set(canonicalized))

    def _is_system_safe_call(self, call_name: str) -> bool:
        upper_call = call_name.upper()
        if "." in upper_call:
            schema, func = upper_call.split(".", 1)
            if schema in SYSTEM_SCHEMA_ALLOWLIST:
                return True
            if func in SYSTEM_FUNCTION_ALLOWLIST:
                return True
        else:
            if upper_call in SYSTEM_FUNCTION_ALLOWLIST:
                return True
        return False

    def _decide(
        self,
        mode: str,
        is_select: bool,
        stmt_type: str,
        has_for_update: bool,
        has_lock_table: bool,
        write_tokens: List[str],
        tx_tokens: List[str],
        risky_calls: List[str],
        unknown_calls: List[str],
    ) -> Tuple[RiskLevel, str]:
        reasons: List[str] = []

        if mode == "readonly":
            if not is_select:
                reasons.append(f"非SELECT语句: {stmt_type}")
                return RiskLevel.BLOCK, "; ".join(reasons)
            if write_tokens:
                reasons.append(f"包含写操作关键字: {', '.join(write_tokens)}")
                return RiskLevel.BLOCK, "; ".join(reasons)
            if tx_tokens:
                reasons.append(f"包含事务控制关键字: {', '.join(tx_tokens)}")
                return RiskLevel.BLOCK, "; ".join(reasons)
            if has_lock_table:
                reasons.append("包含LOCK TABLE操作")
                return RiskLevel.BLOCK, "; ".join(reasons)
            if has_for_update:
                reasons.append("包含FOR UPDATE锁定操作")
                return RiskLevel.BLOCK, "; ".join(reasons)
            if risky_calls:
                reasons.append(f"调用可能执行写操作的例程: {', '.join(risky_calls)}")
                return RiskLevel.BLOCK, "; ".join(reasons)
            if unknown_calls:
                reasons.append(
                    f"调用未在白名单中的例程（可能不安全）: {', '.join(unknown_calls)}"
                )
                return RiskLevel.BLOCK, "; ".join(reasons)
            return RiskLevel.LOW, "安全的只读查询"

        # normal 模式：只分级，不必然拦截
        if not is_select:
            reasons.append(f"非SELECT语句: {stmt_type}")
            return RiskLevel.HIGH, "; ".join(reasons) if reasons else "普通查询"
        if write_tokens or tx_tokens or has_lock_table:
            reasons.append("包含写操作或锁定操作")
            return RiskLevel.HIGH, "; ".join(reasons) if reasons else "普通查询"
        if has_for_update:
            reasons.append("包含FOR UPDATE锁定操作")
            return RiskLevel.MEDIUM, "; ".join(reasons) if reasons else "普通查询"
        if risky_calls:
            reasons.append(f"调用可能执行写操作的例程: {', '.join(risky_calls)}")
            return RiskLevel.HIGH, "; ".join(reasons) if reasons else "普通查询"
        if unknown_calls:
            reasons.append(f"调用未在白名单中的例程: {', '.join(unknown_calls)}")
            return RiskLevel.MEDIUM, "; ".join(reasons) if reasons else "普通查询"
        return RiskLevel.LOW, "安全的查询"


__all__ = [
    "RiskLevel",
    "SqlRiskReport",
    "SqlGuard",
    "RoutineIntrospector",
    "WRITE_KEYWORDS",
    "TX_KEYWORDS",
    "LOCK_PATTERNS",
    "SYSTEM_FUNCTION_ALLOWLIST",
    "SYSTEM_SCHEMA_ALLOWLIST",
]
