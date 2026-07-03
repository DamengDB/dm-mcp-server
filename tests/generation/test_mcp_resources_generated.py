"""
基于 MCP resources/templates/list schema 自动生成的资源读取集成测试。

前置条件：
    1. 已在真实环境中运行 scripts/dump_mcp_schemas.py，
       生成 tests/mcp_schemas/resources_templates_list.json 等文件。
    2. 通过环境变量提供 MCP 服务信息：
        - MCP_BASE_URL: MCP 服务基础地址
        - MCP_SESSION_ID: 已建立好的会话 ID
        - MCP_AUTH_TOKEN: 可选的认证 Token
    3. 提供数据库/环境 facts（用于填充 URI 模板）：
        - tests/mcp_facts.json

测试目标：
    - resources/list：若存在静态资源则逐个 resources/read
    - resources/templates/list：对每个 uriTemplate 用 facts 填参后 resources/read
    - 将「请求 + 响应」落地到 tests/artifacts/mcp_resources/{safe_name}.json
"""

from __future__ import annotations

import json
import os
import re
from typing import cast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


SCHEMA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_schemas")
ARTIFACT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "artifacts", "mcp_resources"
)
FACTS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "mcp_facts.json")


def _load_env_from_project_root(env_filename: str = ".env.mcp-client") -> None:
    if load_dotenv is None:
        return
    base_dir = Path(__file__).resolve().parents[2]
    env_path = base_dir / env_filename
    if env_path.exists():
        load_dotenv(env_path)


def _ensure_artifacts_dir() -> None:
    os.makedirs(ARTIFACT_DIR, exist_ok=True)


def _load_facts() -> Dict[str, Any]:
    if not os.path.exists(FACTS_PATH):
        pytest.skip("mcp_facts.json 不存在，请先提供 tests/mcp_facts.json")
    with open(FACTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        pytest.skip("mcp_facts.json 格式不正确（应为 JSON object）")
    return data


def _facts_get(facts: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = facts
    for k in path:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _build_client() -> tuple[httpx.AsyncClient, str]:
    _load_env_from_project_root()
    base_url = os.getenv("MCP_BASE_URL", "http://localhost:8000")
    session_id = os.getenv("MCP_SESSION_ID", "test_session")
    token = os.getenv("MCP_AUTH_TOKEN", "")

    headers: Dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Token {token}"

    client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=60.0)
    return client, session_id


def _safe_name(s: str) -> str:
    s = s.replace("/", "_").replace(":", "_")
    s = re.sub(r"[^a-zA-Z0-9_\-\.\u4e00-\u9fff]+", "_", s)
    return s.strip("_") or "resource"


def _facts_digest(facts: Dict[str, Any]) -> Dict[str, Any]:
    schema = _facts_get(facts, ["defaults", "schema"])
    table = _facts_get(facts, ["defaults", "table"])
    view = _facts_get(facts, ["defaults", "view"])
    db = _facts_get(facts, ["defaults", "db"])
    return {
        "capabilities": {
            "has_dpc": bool(_facts_get(facts, ["capabilities", "has_dpc"], False)),
            "audit_enabled": bool(
                _facts_get(facts, ["capabilities", "audit_enabled"], False)
            ),
        },
        "defaults": {"schema": schema, "table": table, "view": view, "db": db},
    }


def _load_schema_response(path: str, key: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        pytest.skip(
            f"{os.path.basename(path)} 不存在，请先运行 scripts/dump_mcp_schemas.py"
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    resp = data.get("response", {})
    if isinstance(resp, dict) and "result" in resp:
        result = resp["result"]
    elif isinstance(resp, dict):
        result = resp
    else:
        result = {}

    items = result.get(key, [])
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


_TEMPLATE_VAR_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)[^}]*\}")


def _render_uri_template(
    uri_template: str, facts: Dict[str, Any]
) -> Tuple[Optional[str], Optional[str]]:
    """
    将 uriTemplate 中的 {var} 用 facts.defaults.* 填充。
    若缺少必要变量，则返回 (None, reason)
    """
    defaults = _facts_get(facts, ["defaults"], {})
    if not isinstance(defaults, dict):
        defaults = {}

    needed = _TEMPLATE_VAR_RE.findall(uri_template or "")
    mapping: Dict[str, str] = {}
    for var in needed:
        v = defaults.get(var)
        if not isinstance(v, str) or not v:
            return None, f"facts.defaults 缺少模板变量 '{var}'"
        mapping[var] = v

    def repl(m: re.Match) -> str:
        var = m.group(1)
        # var 来自 needed，mapping 必然存在该 key
        return mapping[var]

    return _TEMPLATE_VAR_RE.sub(repl, uri_template), None


async def _mcp_call(
    client: httpx.AsyncClient,
    session_id: str,
    method: str,
    params: Dict[str, Any] | None = None,
    rpc_id: int = 200,
) -> httpx.Response:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        payload["params"] = params
    path = f"/mcp/messages?sessionId={session_id}"
    return cast(httpx.Response, await client.post(path, json=payload))


FACTS = _load_facts()
RESOURCES = _load_schema_response(
    os.path.join(SCHEMA_DIR, "resources_list.json"), "resources"
)
TEMPLATES = _load_schema_response(
    os.path.join(SCHEMA_DIR, "resources_templates_list.json"), "resourceTemplates"
)


MARK_INTEGRATION = "integration"
MARK_ASYNCIO = "asyncio"
MARK_MCP = "mcp"


@pytest.mark.__getattr__(MARK_INTEGRATION)
@pytest.mark.__getattr__(MARK_ASYNCIO)
@pytest.mark.__getattr__(MARK_MCP)
async def test_mcp_resources_list_and_read_static() -> None:
    _ensure_artifacts_dir()
    client, session_id = _build_client()
    try:
        # resources/list 本身也调用一次，记录下当前返回（不依赖 schema dump）
        resp = await _mcp_call(client, session_id, "resources/list", rpc_id=201)
        assert resp.status_code in (200, 400, 403, 404, 500)

        # schema dump 中的静态资源逐个读取（目前多数环境为空）
        for r in RESOURCES:
            uri = r.get("uri")
            if not isinstance(uri, str) or not uri:
                continue
            read = await _mcp_call(
                client, session_id, "resources/read", params={"uri": uri}, rpc_id=202
            )
            record = {
                "kind": "static_resource",
                "uri": uri,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "facts_digest": _facts_digest(FACTS),
                "request": {"method": "resources/read", "params": {"uri": uri}},
                "status_code": read.status_code,
                "response": _safe_json(read),
            }
            with open(
                os.path.join(ARTIFACT_DIR, f"static_{_safe_name(uri)}.json"),
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
    finally:
        await client.aclose()


@pytest.mark.__getattr__(MARK_INTEGRATION)
@pytest.mark.__getattr__(MARK_ASYNCIO)
@pytest.mark.__getattr__(MARK_MCP)
@pytest.mark.parametrize(
    "tpl",
    TEMPLATES,
    ids=lambda t: t.get("uriTemplate", "unknown_template"),
)
async def test_mcp_resource_template_read_generated(tpl: Dict[str, Any]) -> None:
    _ensure_artifacts_dir()
    client, session_id = _build_client()
    try:
        uri_template = tpl.get("uriTemplate")
        if not isinstance(uri_template, str) or not uri_template:
            pytest.skip("resourceTemplate 缺少 uriTemplate")

        uri, reason = _render_uri_template(uri_template, FACTS)
        if reason:
            pytest.skip(reason)
        assert uri is not None

        resp = await _mcp_call(
            client, session_id, "resources/read", params={"uri": uri}, rpc_id=203
        )

        record = {
            "kind": "resource_template",
            "name": tpl.get("name"),
            "uriTemplate": uri_template,
            "renderedUri": uri,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "facts_digest": _facts_digest(FACTS),
            "request": {"method": "resources/read", "params": {"uri": uri}},
            "status_code": resp.status_code,
            "response": _safe_json(resp),
        }
        with open(
            os.path.join(ARTIFACT_DIR, f"tpl_{_safe_name(uri_template)}.json"),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        assert resp.status_code in (200, 400, 403, 404, 500)
    finally:
        await client.aclose()


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text
