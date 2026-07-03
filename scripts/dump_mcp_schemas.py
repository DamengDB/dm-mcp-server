import json
import os
from datetime import datetime, timezone
from pathlib import Path

import anyio
import httpx

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 可选依赖
    load_dotenv = None


def _load_env_from_project_root(env_filename: str = ".env.mcp-client") -> None:
    """
    从项目根目录加载专门用于「调用 MCP 服务」的 env 文件。

    注意：不会自动读取项目根的默认 .env，避免干扰服务自身启动配置。

    建议文件名：
        - .env.mcp-client
    示例内容：
        MCP_BASE_URL=https://your-env
        MCP_SESSION_ID=xxxx
        MCP_AUTH_TOKEN=optional
    """
    if load_dotenv is None:
        return

    base_dir = Path(__file__).resolve().parents[1]
    env_path = base_dir / env_filename
    if env_path.exists():
        load_dotenv(env_path)


def _ensure_output_dir() -> str:
    """
    确保输出目录存在，默认放在 tests/mcp_schemas 目录下。
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))
    output_dir = os.path.join(base_dir, "tests", "mcp_schemas")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _get_env(name: str, required: bool = True, default: str | None = None) -> str:
    """
    读取环境变量的简单封装。
    """
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"环境变量 {name} 未设置")
    return value  # type: ignore[return-value]


def _build_client() -> tuple[httpx.AsyncClient, str]:
    """
    构建 HTTP 客户端和 sessionId。

    约定环境变量：
        - MCP_BASE_URL: MCP 服务的基础地址，例如 https://example.com
        - MCP_AUTH_TOKEN: 可选，若存在则作为 Token 发送

    说明：
        - 当前脚本对 MCP_SESSION_ID 没有强制依赖，如未设置则使用固定占位值
          "test_session" 作为查询参数，方便复用现有测试环境配置。
    """
    base_url = _get_env("MCP_BASE_URL")
    # sessionId 非必填，未提供时使用占位值
    session_id = os.getenv("MCP_SESSION_ID", "test_session")
    token = os.getenv("MCP_AUTH_TOKEN", "")

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # 按服务约定使用 "Token <key>" 形式
    if token:
        headers["Authorization"] = f"Token {token}"

    client = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0)
    return client, session_id


async def _post_mcp(
    client: httpx.AsyncClient, session_id: str, payload: dict
) -> httpx.Response:
    """
    向 MCP /mcp/messages 端点发送 JSON-RPC 请求。
    """
    path = f"/mcp/messages?sessionId={session_id}"
    return await client.post(path, json=payload)


async def dump_mcp_schemas() -> None:
    """
    调用 MCP 协议的 list 接口，将 schema 原样保存到本地文件。

    输出文件：
        - tests/mcp_schemas/tools_list.json
        - tests/mcp_schemas/resources_list.json
        - tests/mcp_schemas/prompts_list.json
    """
    # 优先从项目根目录的 .env 加载配置
    _load_env_from_project_root()

    output_dir = _ensure_output_dir()
    client, session_id = _build_client()
    now = datetime.now(timezone.utc).isoformat()

    try:
        # 1) tools/list
        tools_req = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        tools_resp = await _post_mcp(client, session_id, tools_req)

        tools_data = {
            "timestamp": now,
            "request": tools_req,
            "status_code": tools_resp.status_code,
            "response": _safe_json(tools_resp),
        }
        tools_path = os.path.join(output_dir, "tools_list.json")
        _write_json(tools_path, tools_data)

        # 2) resources/list
        resources_req = {"jsonrpc": "2.0", "id": 2, "method": "resources/list"}
        resources_resp = await _post_mcp(client, session_id, resources_req)

        resources_data = {
            "timestamp": now,
            "request": resources_req,
            "status_code": resources_resp.status_code,
            "response": _safe_json(resources_resp),
        }
        resources_path = os.path.join(output_dir, "resources_list.json")
        _write_json(resources_path, resources_data)

        # 3) resources/templates/list
        templates_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/templates/list",
        }
        templates_resp = await _post_mcp(client, session_id, templates_req)

        templates_data = {
            "timestamp": now,
            "request": templates_req,
            "status_code": templates_resp.status_code,
            "response": _safe_json(templates_resp),
        }
        templates_path = os.path.join(output_dir, "resources_templates_list.json")
        _write_json(templates_path, templates_data)

        # 4) prompts/list
        prompts_req = {"jsonrpc": "2.0", "id": 4, "method": "prompts/list"}
        prompts_resp = await _post_mcp(client, session_id, prompts_req)

        prompts_data = {
            "timestamp": now,
            "request": prompts_req,
            "status_code": prompts_resp.status_code,
            "response": _safe_json(prompts_resp),
        }
        prompts_path = os.path.join(output_dir, "prompts_list.json")
        _write_json(prompts_path, prompts_data)

    finally:
        await client.aclose()


def _safe_json(resp: httpx.Response) -> dict | str:
    """
    尝试以 JSON 解析响应，若失败则返回原始文本。
    """
    try:
        return resp.json()
    except Exception:
        return resp.text


def _write_json(path: str, data: dict) -> None:
    """
    将数据写入 JSON 文件，使用 UTF-8 和 pretty 格式。
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    anyio.run(dump_mcp_schemas)
