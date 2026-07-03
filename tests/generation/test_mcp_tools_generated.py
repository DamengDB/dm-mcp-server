"""
基于 MCP tools/list schema 自动生成的工具集成测试。

前置条件：
    1. 已在真实环境中运行 scripts/dump_mcp_schemas.py，
       生成 tests/mcp_schemas/tools_list.json 等文件。
    2. 通过环境变量提供 MCP 服务信息：
        - MCP_BASE_URL: MCP 服务基础地址
        - MCP_SESSION_ID: 已建立好的会话 ID
        - MCP_AUTH_TOKEN: 可选的认证 Token
    3. 提供数据库/环境 facts（用于生成真实入参）：
        - tests/mcp_facts.json

测试目标：
    - 遍历 tools_list.json 中的所有工具；
    - 根据 tests/mcp_facts.json 为每个工具生成“可真实执行”的入参；
    - 通过 MCP JSON-RPC 接口对每个工具调用一次；
    - 将「请求 + 响应」落地到 tests/artifacts/mcp_tools/{tool_name}.json。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 可选依赖
    load_dotenv = None


SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_schemas")
ARTIFACT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "artifacts", "mcp_tools"
)
FACTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_facts.json")


def _load_env_from_project_root(env_filename: str = ".env.mcp-client") -> None:
    """
    从项目根目录加载专门用于「调用 MCP 服务」的 env 文件。

    不会去加载默认的 .env（该文件用于启动服务）。
    """
    if load_dotenv is None:
        return

    base_dir = Path(__file__).resolve().parents[2]
    env_path = base_dir / env_filename
    if env_path.exists():
        load_dotenv(env_path)


def _ensure_artifacts_dir() -> None:
    os.makedirs(ARTIFACT_DIR, exist_ok=True)


def _load_facts() -> Dict[str, Any]:
    """
    加载用于生成真实入参的 facts 配置。

    说明：只包含“可公开的数据库对象信息/查询样例”，不要在此文件存放 token 等敏感信息。
    """
    if not os.path.exists(FACTS_PATH):
        pytest.skip("mcp_facts.json 不存在，请先提供 tests/mcp_facts.json")

    with open(FACTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        pytest.skip("mcp_facts.json 格式不正确（应为 JSON object）")
    return data


def _load_tools_from_schema() -> List[Dict[str, Any]]:
    """
    从 dump_mcp_schemas.py 生成的 tools_list.json 加载工具定义。
    """
    path = os.path.join(SCHEMA_DIR, "tools_list.json")
    if not os.path.exists(path):
        pytest.skip("tools_list.json 不存在，请先运行 scripts/dump_mcp_schemas.py")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    resp = data.get("response", {})

    # 兼容：response 可能是完整 JSON-RPC，也可能直接是 result
    if isinstance(resp, dict) and "result" in resp:
        tools = resp["result"].get("tools", [])
    elif isinstance(resp, dict):
        tools = resp.get("tools", [])
    else:
        tools = []

    if not isinstance(tools, list):
        pytest.skip("tools_list.json 中的 tools 字段格式不正确")

    return tools


def _build_client() -> tuple[httpx.AsyncClient, str]:
    """
    构建 HTTP 客户端和 MCP sessionId。
    """
    # 优先从项目根目录的 .env 加载配置
    _load_env_from_project_root()

    base_url = os.getenv("MCP_BASE_URL", "http://localhost:8000")
    session_id = os.getenv("MCP_SESSION_ID", "test_session")
    token = os.getenv("MCP_AUTH_TOKEN", "")

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # 按服务约定使用 "Token <key>" 形式
    if token:
        headers["Authorization"] = f"Token {token}"

    client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=60.0)
    return client, session_id


def _facts_get(facts: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = facts
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _facts_defaults(facts: Dict[str, Any]) -> Tuple[str, str, str]:
    schema = _facts_get(facts, ["defaults", "schema"])
    table = _facts_get(facts, ["defaults", "table"])
    view = _facts_get(facts, ["defaults", "view"])
    if not all(isinstance(x, str) and x for x in (schema, table, view)):
        pytest.skip("mcp_facts.json 缺少 defaults.schema/defaults.table/defaults.view")
    return schema, table, view


def _normalize_sql(sql: str) -> str:
    s = sql.strip().rstrip(";").strip()
    return s


def _build_tool_args(
    tool_name: str, input_schema: Dict[str, Any], facts: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    为每个工具生成“可真实执行”的入参。
    返回 (arguments, skip_reason)。skip_reason 非空则该工具跳过。
    """
    schema, table, view = _facts_defaults(facts)
    has_dpc = bool(_facts_get(facts, ["capabilities", "has_dpc"], False))
    audit_enabled = bool(_facts_get(facts, ["capabilities", "audit_enabled"], False))

    sample_sql = _facts_get(facts, ["sql", "sample_select"])
    if not isinstance(sample_sql, str) or not sample_sql.strip():
        pytest.skip("mcp_facts.json 缺少 sql.sample_select")
    sample_sql = _normalize_sql(sample_sql)

    # --- DPC 工具：无 DPC 环境统一跳过 ---
    if tool_name.startswith("get_dpc_") and not has_dpc:
        return None, "当前环境 capabilities.has_dpc=false，跳过 DPC 工具"

    # --- 审计工具 ---
    if tool_name == "get_audit_recent_logs":
        if not audit_enabled:
            return None, "当前环境 capabilities.audit_enabled=false，跳过审计工具"
        days = int(_facts_get(facts, ["audit", "days"], 30))
        limit = int(_facts_get(facts, ["audit", "limit"], 200))
        return {"days": days, "limit": limit}, None

    # --- 慢 SQL ---
    if tool_name == "get_sql_slow_queries_top":
        days = int(_facts_get(facts, ["slow_sql", "days"], 30))
        top_n = int(_facts_get(facts, ["slow_sql", "top_n"], 20))
        return {"days": days, "top_n": top_n}, None

    # --- 元数据/结构类：schema/table/view ---
    if tool_name == "get_db_schemas_list":
        return {}, None

    if tool_name == "get_db_objects_list":
        return {"schema": schema, "object_type": None, "include_comments": False}, None

    if tool_name in {
        "get_table_describe",
        "get_table_comment",
        "get_table_column_comments",
        "get_table_indexes_list",
        "get_table_constraints_list",
    }:
        return {"schema": schema, "table": table, "table_comment": None}, None

    if tool_name in {"get_view_describe", "get_view_definition"}:
        return {"schema": schema, "view": view, "view_comment": None}, None

    if tool_name in {"get_table_data_size", "get_table_basic_info", "analyze_columns"}:
        # 这三类工具使用 schema_name/table_name 参数
        args: Dict[str, Any] = {"schema_name": schema, "table_name": table}
        if tool_name == "analyze_columns":
            args["top_n"] = int(_facts_get(facts, ["analyze_columns", "top_n"], 10))
        return args, None

    # --- SQL 执行/分析 ---
    if tool_name == "analyze_sql_risk":
        return {"sql": sample_sql, "mode": "readonly"}, None

    if tool_name == "exec_readonly_query":
        return {"sql": sample_sql, "schema": schema, "max_rows": 200}, None

    if tool_name == "exec_query":
        # 默认用 SELECT，避免误写入；如需写入测试可在 facts 里扩展 write_sql 再打开策略
        return {
            "sql": sample_sql,
            "params": None,
            "max_rows": 200,
            "timeout": None,
        }, None

    if tool_name == "get_sql_explain_plan":
        return {"sql": sample_sql, "schema": schema}, None

    if tool_name == "get_sql_profile":
        # 优先 sql_id，其次 sql_text。没提供 sql_id 时使用 sample_sql 做模糊匹配
        sql_id = _facts_get(facts, ["sql_profile", "sql_id"])
        sql_text = _facts_get(facts, ["sql_profile", "sql_text"])
        if isinstance(sql_id, str) and sql_id.strip():
            return {"sql_id": sql_id.strip(), "sql_text": None, "schema": schema}, None
        if isinstance(sql_text, str) and sql_text.strip():
            return {
                "sql_id": None,
                "sql_text": _normalize_sql(sql_text),
                "schema": schema,
            }, None
        return {"sql_id": None, "sql_text": sample_sql, "schema": schema}, None

    # --- 连接/指标类：无入参 ---
    if tool_name in {
        "pool_status",
        "test_connection",
        "get_connection_metrics",
        "export_metrics",
        "get_memory_stats",
        "get_metrics",
        "get_pool_status",
        "get_worker_status",
        "get_dpc_sp_instances",
        "get_dpc_instances",
        "get_dpc_raft_list",
        "get_dpc_instance_raft_topology",
        "get_dpc_esession_detail",
        "get_dpc_esession_summary",
    }:
        # DPC 相关已经在前面统一 skip
        # test_connection 有 timeout，可选不传
        if tool_name == "test_connection":
            return {"timeout": 5.0}, None
        return {}, None

    # --- 兜底：如果 schema 没字段就传空，否则跳过 ---
    properties = (input_schema or {}).get("properties", {}) or {}
    if not properties:
        return {}, None
    return None, "缺少该工具的入参生成策略（请在 _build_tool_args 增加映射）"


def _facts_digest(facts: Dict[str, Any]) -> Dict[str, Any]:
    """
    artifact 中记录一份可复现的（脱敏）摘要，避免把敏感信息写入文件。
    """
    schema = _facts_get(facts, ["defaults", "schema"])
    table = _facts_get(facts, ["defaults", "table"])
    view = _facts_get(facts, ["defaults", "view"])
    return {
        "capabilities": {
            "has_dpc": bool(_facts_get(facts, ["capabilities", "has_dpc"], False)),
            "audit_enabled": bool(
                _facts_get(facts, ["capabilities", "audit_enabled"], False)
            ),
        },
        "defaults": {"schema": schema, "table": table, "view": view},
        "slow_sql": {
            "days": int(_facts_get(facts, ["slow_sql", "days"], 30)),
            "top_n": int(_facts_get(facts, ["slow_sql", "top_n"], 20)),
        },
        "audit": {
            "days": int(_facts_get(facts, ["audit", "days"], 30)),
            "limit": int(_facts_get(facts, ["audit", "limit"], 200)),
        },
        "sql": {"sample_select": "<provided>"},
    }


TOOLS = _load_tools_from_schema()
FACTS = _load_facts()


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.mcp
@pytest.mark.parametrize("tool_def", TOOLS, ids=lambda t: t.get("name", "unknown_tool"))
async def test_mcp_tool_call_generated(tool_def: Dict[str, Any]) -> None:
    """
    基于 tools_list.json 自动生成的工具调用测试。

    每个工具调用一次，将请求和响应记录到 tests/artifacts/mcp_tools 目录。
    """
    _ensure_artifacts_dir()
    client, session_id = _build_client()

    try:
        name = tool_def.get("name")
        if not isinstance(name, str) or not name:
            pytest.skip("tool 定义中缺少有效的 name 字段")

        input_schema = tool_def.get("inputSchema") or {}
        if not isinstance(input_schema, dict):
            input_schema = {}

        arguments, skip_reason = _build_tool_args(name, input_schema, FACTS)
        if skip_reason:
            pytest.skip(skip_reason)
        if arguments is None:
            pytest.skip("未能生成该工具的入参")

        request_payload: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 100,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
            },
        }

        path = f"/mcp/messages?sessionId={session_id}"
        resp = await client.post(path, json=request_payload)

        try:
            response_data: Any = resp.json()
        except Exception:
            response_data = resp.text

        record: Dict[str, Any] = {
            "tool": name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "facts_digest": _facts_digest(FACTS),
            "request": request_payload,
            "status_code": resp.status_code,
            "response": response_data,
        }

        # 每个工具一个文件，name 中的特殊字符做简单替换
        safe_name = name.replace("/", "_").replace(":", "_")
        filename = f"{safe_name}.json"
        filepath = os.path.join(ARTIFACT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        # 是否强制 200 由你来决定；
        # 这里为了“探测”为主，先允许常见错误码，方便先收集完整样本。
        assert resp.status_code in (200, 400, 403, 404, 500)

    finally:
        await client.aclose()
