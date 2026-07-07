"""MCP 协议服务模块

MCPService 作为 MCP 协议的核心服务、查询侧、以及元数据 override 命令侧：
- 管理 Tools、Resources、Prompts 的路由和执行
- 维护轻量元数据视图缓存（dict-of-dict），mutation / 事件后整体失效
- 协议层（list_tools/list_resources/...）从合并视图直接构造载荷
- 元数据 override（描述/disabled）的写入也在本服务，mutation 后同步刷新合并视图

合并视图来源：
- Provider 原始定义（Provider.list_tools/list_resources/...）
- ``mcp_metadata_overrides``（描述/disabled，本服务自管）
- ``mcp_entity_group_assignments`` × ``mcp_cli_groups``（分组归属，由
  ``EntityGroupService`` / ``CliGroupService`` 通过事件通知本服务失效缓存）
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from functools import cached_property, lru_cache
from itertools import chain
from typing import Any, Callable

from mcp import Resource, Tool, types
from mcp.server import Server
from pydantic import AnyUrl
from sqlalchemy import delete, select

from dm_mcp.common import messages
from dm_mcp.infra.persistence import (
    CliGroupModel,
    EntityGroupAssignmentModel,
    MetadataOverrideModel,
    get_async_session,
)
from dm_mcp.core.events.subscription import EventSubscription
from dm_mcp.core.exceptions import (
    DmMCPError,
    MCPExecutionError,
    PromptNotFoundError,
    ResourceNotFoundError,
    ToolNotFoundError,
)
from dm_mcp.core.mcp import BaseMCPProvider
from dm_mcp.core.mcp.middleware import MCPMiddlewareStack
from dm_mcp.core.mcp.serialization import DataSerializer
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.domain.mcp.events import (
    MCPGroupChanged,
    MCPEntityAssigned,
    MCPProvidersStarted,
)
from dm_mcp.infra.config.settings import ServerConfig
from dm_mcp.common.utils import Timer

from dm_mcp.core.service import BaseService
from dm_mcp.domain.system.services.logging import LoggingService
from dm_mcp.domain.system.services.metrics import MetricsService

logger = logging.getLogger(__name__)


def _extract_cli_params(input_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """将 JSON Schema 形式的 input_schema 转为 CLI ParamSchema 列表。"""
    params: list[dict[str, Any]] = []
    if not input_schema or not isinstance(input_schema, dict):
        return params

    properties = input_schema.get("properties", {})
    required_set = set(input_schema.get("required", []))

    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue

        param_type = prop.get("type", "string")
        if param_type == "array" and "items" in prop:
            item_type = (
                prop["items"].get("type", "any")
                if isinstance(prop["items"], dict)
                else "any"
            )
            param_type = f"array[{item_type}]"

        params.append(
            {
                "name": name,
                "description": prop.get("description", ""),
                "param_type": param_type,
                "required": name in required_set,
                "default": prop.get("default"),
                "enum_values": prop.get("enum"),
            }
        )

    return params


def _is_error_json(text: str) -> bool:
    """判断文本是否为业务错误 JSON（含 error 和 message 键）。"""
    try:
        parsed = json.loads(text)
        return isinstance(parsed, dict) and "error" in parsed and "message" in parsed
    except (json.JSONDecodeError, TypeError):
        return False


class MCPService(BaseService):
    """MCP 协议核心服务（查询侧 + 协议层）"""

    def __init__(
        self,
        server_config: ServerConfig,
        metrics_service: MetricsService,
        logging_service: LoggingService,
        event_service: Any,
    ) -> None:
        from dm_mcp.domain.mcp.middleware.metrics import MetricsMCPMiddleware

        self.sdk_server = Server(server_config.name)
        self.providers: list[BaseMCPProvider] = []
        self.middleware_stack = MCPMiddlewareStack()
        self._event_service = event_service

        # ==== 轻量合并视图缓存 ====
        # 每个 dict 形如 {"name": "...", "short_description": "...",
        # "long_description": "...", "group": "a.b.c"|None, "disabled": bool,
        # "provider_name": "...", ...}
        self._merged_tools: dict[str, dict[str, Any]] | None = None
        self._merged_resources: dict[str, dict[str, Any]] | None = None
        self._merged_prompts: dict[str, dict[str, Any]] | None = None
        # CLI 树（懒构建，事件失效）
        self._cli_tree_cache: dict[str, Any] | None = None

        # 默认中间件
        self.add_mcp_middlewares(
            [
                MetricsMCPMiddleware(metrics_service),
            ]
        )

        self._setup_handlers()

    # ===================================================
    # Provider / Middleware 管理
    # ===================================================
    def add_mcp_middleware(self, middleware: Any) -> None:
        self.middleware_stack.add_middleware(middleware)

    def add_mcp_middlewares(self, middlewares: list[Any]) -> None:
        self.middleware_stack.add_middlewares(middlewares)

    def add_mcp_provider(self, provider: BaseMCPProvider) -> None:
        self.providers.append(provider)

    def add_mcp_providers(self, providers: list[BaseMCPProvider]) -> None:
        self.providers.extend(providers)

    def get_tool_definition(self, tool_name: str) -> Any:
        if tool_name in self._providers_tool_map:
            provider = self._providers_tool_map[tool_name]
            return provider.mcp.tools_map.get(tool_name)
        return None

    # ===================================================
    # Provider 原始定义缓存（cached_property）
    # ===================================================
    @cached_property
    def _tools(self) -> list[Tool]:
        provider_tools = [provider.list_tools() for provider in self.providers]
        return list(chain.from_iterable(t for t in provider_tools))

    @cached_property
    def _resources(self) -> list[Resource]:
        provider_resources = [provider.list_resources() for provider in self.providers]
        return list(chain.from_iterable(r for r in provider_resources))

    @cached_property
    def _resource_templates(self) -> list[types.ResourceTemplate]:
        provider_resource_templates = [
            provider.list_resource_templates() for provider in self.providers
        ]
        return list(chain.from_iterable(r for r in provider_resource_templates))

    @cached_property
    def _prompts(self) -> list[types.Prompt]:
        provider_prompts = [provider.list_prompts() for provider in self.providers]
        return list(chain.from_iterable(p for p in provider_prompts))

    @cached_property
    def _providers_tool_map(self) -> dict[str, BaseMCPProvider]:
        providers_map: dict[str, BaseMCPProvider] = {}
        for provider in self.providers:
            providers_map |= {tool.name: provider for tool in provider.list_tools()}
        return providers_map

    @cached_property
    def _providers_prompt_map(self) -> dict[str, BaseMCPProvider]:
        providers_map: dict[str, BaseMCPProvider] = {}
        for provider in self.providers:
            providers_map |= {
                prompt.name: provider for prompt in provider.list_prompts()
            }
        return providers_map

    @cached_property
    def _providers_resource_map(self) -> dict[str, BaseMCPProvider]:
        providers_map: dict[str, BaseMCPProvider] = {}
        for provider in self.providers:
            for resource in provider.list_resources():
                providers_map[str(resource.uri)] = provider

            for template in provider.list_resource_templates():
                providers_map[template.uriTemplate] = provider

        return providers_map

    @cached_property
    def _compiled_uri_patterns(self) -> list[tuple[Any, str]]:
        patterns = []
        templates = [uri for uri in self._providers_resource_map.keys() if "{" in uri]
        templates.sort(key=len, reverse=True)

        for template in templates:
            pattern_str = re.escape(template).replace(r"\{", "{").replace(r"\}", "}")
            pattern_str = re.sub(r"\{[^}]+\}", r"[^/]+", pattern_str)
            pattern_str = f"^{pattern_str}$"

            try:
                patterns.append((re.compile(pattern_str), template))
            except re.error as e:
                logger.error(f"编译资源模板正则表达式失败: {template}, 错误: {e}")

        return patterns

    # ===================================================
    # 缓存控制
    # ===================================================
    def clear_caches(self) -> None:
        """清除 Provider 原始定义缓存（动态注册后使用）。"""
        for attr in [
            "_tools",
            "_resources",
            "_resource_templates",
            "_prompts",
            "_providers_tool_map",
            "_providers_prompt_map",
            "_providers_resource_map",
            "_compiled_uri_patterns",
        ]:
            if hasattr(self, attr):
                try:
                    delattr(self, attr)
                except AttributeError:
                    pass
        self._invalidate_all()
        logger.info("已清除 MCPService 缓存")

    def _invalidate_all(self) -> None:
        """整体失效合并视图缓存（事件触发）。"""
        self._merged_tools = None
        self._merged_resources = None
        self._merged_prompts = None
        self._cli_tree_cache = None

    def _match_uri_template(self, uri: str, template: str) -> bool:
        """检查 URI 是否匹配模板"""
        pattern = re.escape(template)
        pattern = re.sub(r"\\{[^}]+\\}", r"[^/]+", pattern)
        pattern = f"^{pattern}$"
        return bool(re.match(pattern, uri))

    # ===================================================
    # 合并视图懒构建
    # ===================================================
    async def _load_merge_inputs(
        self,
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, dict[str, Any]],
        dict[str, str],
        dict[str, str],
        dict[str, str],
    ]:
        """一次性从 DB 拉所有合并所需数据。

        Returns:
            (tool_overrides, resource_overrides, prompt_overrides,
             group_path_by_key, group_id_by_key, path_to_id)
            - ``*_overrides``: ``{key: {short_description, long_description, disabled}}``
            - ``group_path_by_key``: ``{f"{object_type}:{key}": "a.b.c"}``
            - ``group_id_by_key``: ``{f"{object_type}:{key}": "short_id"}``
              （仅含已分配的实体）
            - ``path_to_id``: ``{"a.b.c": "short_id"}``
              供 fallback 解析 Provider 硬编码 group
        """
        async with get_async_session() as session:
            ovr_rows = (
                (await session.execute(select(MetadataOverrideModel))).scalars().all()
            )
            assign_rows = (
                (await session.execute(select(EntityGroupAssignmentModel)))
                .scalars()
                .all()
            )
            group_rows = (await session.execute(select(CliGroupModel))).scalars().all()

        tool_overrides: dict[str, dict[str, Any]] = {}
        resource_overrides: dict[str, dict[str, Any]] = {}
        prompt_overrides: dict[str, dict[str, Any]] = {}
        for o in ovr_rows:
            d = o.to_dict()
            if o.object_type == "tool":
                tool_overrides[o.key] = d
            elif o.object_type == "resource":
                resource_overrides[o.key] = d
            elif o.object_type == "prompt":
                prompt_overrides[o.key] = d

        # group_id -> path（基于邻接表 parent_id 链拼接）
        group_by_id = {g.id: g for g in group_rows}

        def _path_of(g: CliGroupModel) -> str:
            parts: list[str] = []
            cur: CliGroupModel | None = g
            seen: set = set()
            while cur is not None:
                if cur.id in seen:
                    break
                seen.add(cur.id)
                parts.append(cur.name)
                if cur.parent_id is None:
                    break
                cur = group_by_id.get(cur.parent_id)
            return ".".join(reversed(parts))

        id_to_path = {gid: _path_of(g) for gid, g in group_by_id.items()}
        path_to_id = {p: gid for gid, p in id_to_path.items()}

        group_path_by_key: dict[str, str] = {}
        group_id_by_key: dict[str, str] = {}
        for a in assign_rows:
            p = id_to_path.get(a.group_id)
            if p:
                group_path_by_key[f"{a.object_type}:{a.key}"] = p
                group_id_by_key[f"{a.object_type}:{a.key}"] = a.group_id

        return (
            tool_overrides,
            resource_overrides,
            prompt_overrides,
            group_path_by_key,
            group_id_by_key,
            path_to_id,
        )

    @staticmethod
    def _merge_one(
        original: dict[str, Any],
        override: dict[str, Any] | None,
        group_path: str | None,
        group_id: str | None,
    ) -> dict[str, Any]:
        """合并 Provider 原始字段 + override + 分配 group。

        Args:
            original: ``{name, short_description, long_description, group(default), provider_name, ...}``
            override: 可能为 None
            group_path: assignment 解析出的 path；为 None 表示沿用 original.group
            group_id: assignment 解析出的短 id；为 None 表示沿用 Provider 默认

        Returns:
            合并后的 dict（``group`` 字段为最终生效值）
        """
        merged = dict(original)
        if override:
            sd = override.get("short_description")
            ld = override.get("long_description")
            if sd is not None:
                merged["short_description"] = sd
            if ld is not None:
                merged["long_description"] = ld
            merged["disabled"] = bool(override.get("disabled", False))
        else:
            merged.setdefault("disabled", False)

        if group_path is not None:
            merged["group"] = group_path
        if group_id is not None:
            merged["group_id"] = group_id
        return merged

    async def _ensure_merged(self) -> None:
        """懒构建 merged_tools / merged_resources / merged_prompts。

        缺任意一个就重建全部（事件失效是整体失效）。
        """
        if (
            self._merged_tools is not None
            and self._merged_resources is not None
            and self._merged_prompts is not None
        ):
            return

        (
            tool_ov,
            resource_ov,
            prompt_ov,
            group_path_by_key,
            group_id_by_key,
            path_to_id,
        ) = await self._load_merge_inputs()

        merged_tools: dict[str, dict[str, Any]] = {}
        merged_resources: dict[str, dict[str, Any]] = {}
        merged_prompts: dict[str, dict[str, Any]] = {}

        def _resolve_group(
            object_type: str, key: str, original_group: str | None
        ) -> tuple[str | None, str | None]:
            """获取实体的 group_path 和 group_id。

            优先使用 assignment 表记录；若无 assignment 但 Provider
            硬编码了 group，则 fallback 到 cli_groups 查找对应 id。
            """
            gp = group_path_by_key.get(f"{object_type}:{key}")
            gid = group_id_by_key.get(f"{object_type}:{key}")
            if gp is not None:
                return gp, gid
            if original_group:
                return original_group, path_to_id.get(original_group)
            return None, None

        # Tools
        for provider in self.providers:
            pname = provider.__class__.__name__
            for tname, td in provider.mcp.tools_map.items():
                original = {
                    "name": tname,
                    "short_description": td.short_description or "",
                    "long_description": td.long_description
                    or td.short_description
                    or "",
                    "group": td.group,
                    "provider_name": pname,
                    "input_schema": td.input_schema,
                    "examples": getattr(td, "examples", []),
                }
                gp, gid = _resolve_group("tool", tname, td.group)
                merged_tools[tname] = self._merge_one(
                    original,
                    tool_ov.get(tname),
                    gp,
                    gid,
                )

        # Resources（静态 + 模板，key = name）
        for provider in self.providers:
            pname = provider.__class__.__name__
            for _uri, rd in provider.mcp._static_resources.items():
                original = {
                    "name": rd.name,
                    "uri": rd.uri,
                    "short_description": rd.short_description or "",
                    "long_description": rd.long_description
                    or rd.short_description
                    or "",
                    "group": rd.group,
                    "provider_name": pname,
                    "is_template": False,
                    "mime_type": rd.mime_type,
                }
                gp, gid = _resolve_group("resource", rd.name, rd.group)
                merged_resources[rd.name] = self._merge_one(
                    original,
                    resource_ov.get(rd.name),
                    gp,
                    gid,
                )
            for rd in provider.mcp._template_resources:
                original = {
                    "name": rd.name,
                    "uri": rd.uri,
                    "short_description": rd.short_description or "",
                    "long_description": rd.long_description
                    or rd.short_description
                    or "",
                    "group": rd.group,
                    "provider_name": pname,
                    "is_template": True,
                    "mime_type": rd.mime_type,
                }
                gp, gid = _resolve_group("resource", rd.name, rd.group)
                merged_resources[rd.name] = self._merge_one(
                    original,
                    resource_ov.get(rd.name),
                    gp,
                    gid,
                )

        # Prompts（来自 prompts_map，含 PromptDefinition）
        for provider in self.providers:
            pname = provider.__class__.__name__
            for prompt_name, pd in provider.mcp.prompts_map.items():
                original = {
                    "name": prompt_name,
                    "short_description": pd.short_description or "",
                    "long_description": pd.long_description
                    or pd.short_description
                    or "",
                    "group": pd.group,
                    "provider_name": pname,
                    "arguments": pd.arguments,
                }
                gp, gid = _resolve_group("prompt", prompt_name, pd.group)
                merged_prompts[prompt_name] = self._merge_one(
                    original,
                    prompt_ov.get(prompt_name),
                    gp,
                    gid,
                )

        self._merged_tools = merged_tools
        self._merged_resources = merged_resources
        self._merged_prompts = merged_prompts

    # ===================================================
    # fastmcp 注册支持
    # ===================================================
    async def register_tools_with_fastmcp(self, mcp: Any) -> None:
        logger.info("开始动态注册 MCP 工具")

        for tool in self._tools:

            @mcp.tool(name=tool.name, description=tool.description)
            async def wrapper(tool=tool, **kwargs: Any) -> str:
                return await self.call_tool(tool.name, kwargs)

        logger.info(f"成功注册 {len(self._tools)} 个工具")

    # ===================================================
    # MCP 协议回调函数
    # ===================================================
    async def list_tools(self) -> list[Tool]:
        """列出所有工具（应用 override，跳过 disabled）"""
        await self._ensure_merged()
        assert self._merged_tools is not None
        tools: list[Tool] = []
        for name, m in self._merged_tools.items():
            if m.get("disabled"):
                continue
            provider = self._providers_tool_map.get(name)
            if provider is None:
                continue
            td = provider.mcp.tools_map.get(name)
            if td is None:
                continue
            merged = td.apply_metadata_override(
                short_description=m.get("short_description"),
                long_description=m.get("long_description"),
                group=m.get("group"),
            )
            tools.append(merged.to_tool())
        return tools

    async def list_resources(self) -> list[Resource]:
        """列出所有静态资源（应用 override，跳过 disabled / 模板）"""
        await self._ensure_merged()
        assert self._merged_resources is not None
        resources: list[Resource] = []
        for name, m in self._merged_resources.items():
            if m.get("disabled") or m.get("is_template"):
                continue
            rd = self._find_resource_def(name)
            if rd is None:
                continue
            merged = rd.apply_metadata_override(
                short_description=m.get("short_description"),
                long_description=m.get("long_description"),
                group=m.get("group"),
            )
            resources.append(merged.to_resource())
        return resources

    async def list_resource_templates(self) -> list[types.ResourceTemplate]:
        """列出所有资源模板（应用 override，跳过 disabled / 静态）"""
        await self._ensure_merged()
        assert self._merged_resources is not None
        templates: list[types.ResourceTemplate] = []
        for name, m in self._merged_resources.items():
            if m.get("disabled") or not m.get("is_template"):
                continue
            rd = self._find_resource_def(name)
            if rd is None:
                continue
            merged = rd.apply_metadata_override(
                short_description=m.get("short_description"),
                long_description=m.get("long_description"),
                group=m.get("group"),
            )
            templates.append(merged.to_resource_template())
        return templates

    async def list_prompts(self) -> list[types.Prompt]:
        """列出所有提示（应用 override，跳过 disabled）"""
        await self._ensure_merged()
        assert self._merged_prompts is not None
        prompts: list[types.Prompt] = []
        for name, m in self._merged_prompts.items():
            if m.get("disabled"):
                continue
            provider = self._providers_prompt_map.get(name)
            pd = provider.mcp.prompts_map.get(name) if provider else None
            args = pd.arguments if pd else m.get("arguments")
            description = m.get("long_description") or m.get("short_description") or ""
            prompts.append(
                types.Prompt(
                    name=name,
                    description=description,
                    arguments=args,
                )
            )
        return prompts

    def _find_resource_def(self, name: str) -> Any:
        """通过 name 在所有 Provider 的 _static_resources / _template_resources 中查找。"""
        for provider in self.providers:
            for _uri, rd in provider.mcp._static_resources.items():
                if rd.name == name:
                    return rd
            for rd in provider.mcp._template_resources:
                if rd.name == name:
                    return rd
        return None

    @staticmethod
    def _format_exception_detail(e: Exception) -> str:
        """格式化异常详情，处理 TimeoutError 等特殊场景。"""
        if isinstance(e, TimeoutError):
            return (str(e) or "").strip() or "the execution of the statement timed out"
        return str(e)

    async def _timed_execute(
        self,
        name: str,
        action: Callable[..., Any],
        *args: Any,
        log_prefix: str,
        error_extra: dict[str, Any] | None = None,
        generic_error_code: str = "TOOL_EXECUTION_ERROR",
    ) -> str:
        """统一封装：计时、日志、异常捕获、序列化（不包 Envelope）。"""
        timer = Timer()
        try:
            result = await action(*args)
            elapsed = timer.elapsed_ms
            logger.info(f"{log_prefix}完成: {name}, 耗时: {elapsed}ms")
            if isinstance(result, str):
                return result
            return DataSerializer.serialize(result, indent=2)

        except MCPExecutionError as e:
            elapsed = timer.elapsed_ms
            log_extra = {"error_code": e.error_code, **(error_extra or {})}
            logger.warning(
                f"{log_prefix}业务错误: {name}, 错误码: {e.error_code}, 消息: {e.message}",
                extra=log_extra,
            )
            return DataSerializer.serialize(
                {"error": e.error_code, "message": e.message}, indent=2
            )

        except DmMCPError as e:
            elapsed = timer.elapsed_ms
            log_extra = {"error_code": e.error_code, **(error_extra or {})}
            logger.warning(
                f"{log_prefix}业务错误: {name}, 错误码: {e.error_code}, 消息: {e.message}",
                extra=log_extra,
            )
            return DataSerializer.serialize(
                {"error": e.error_code, "message": e.message}, indent=2
            )

        except Exception as e:
            elapsed = timer.elapsed_ms
            err_detail = self._format_exception_detail(e)
            logger.error(
                f"{log_prefix}系统错误: {name}, 错误: {err_detail}",
                exc_info=True,
                extra=error_extra,
            )
            return DataSerializer.serialize(
                {"error": generic_error_code, "message": err_detail},
                indent=2,
            )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """调用工具（统一的路由和执行中心）"""
        if name not in self._providers_tool_map:
            return DataSerializer.serialize(
                {
                    "error": "TOOL_NOT_FOUND",
                    "message": messages.MSG_TOOL_NOT_FOUND.format(name=name),
                },
                indent=2,
            )

        logger.info(f"执行工具调用: {name}, 参数: {arguments}")
        provider = self._providers_tool_map[name]

        return await self._timed_execute(
            name,
            provider.call_tool, name, arguments,
            log_prefix="工具调用",
            error_extra={"tool_name": name, "arguments": arguments},
            generic_error_code="TOOL_EXECUTION_ERROR",
        )

    async def get_prompt(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> types.GetPromptResult:
        if name not in self._providers_prompt_map:
            error_result = {
                "error": "PROMPT_NOT_FOUND",
                "message": messages.MSG_PROMPT_NOT_FOUND.format(name=name),
                "prompt_name": name,
                "arguments": arguments,
            }
            return types.GetPromptResult(
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=DataSerializer.serialize(error_result, indent=2),
                        ),
                    )
                ]
            )

        try:
            logger.info(f"获取提示: {name}, 参数: {arguments}")
            provider = self._providers_prompt_map[name]
            result = await provider.get_prompt(name, arguments)
            logger.debug(f"提示获取成功: {name}")
            return result
        except Exception as e:
            logger.error(f"获取提示失败: {name}, 错误: {e}", exc_info=True)
            error_result = {
                "error": "PROMPT_GET_ERROR",
                "message": messages.MSG_PROMPT_GET_FAILED.format(error=str(e)),
                "prompt_name": name,
                "arguments": arguments,
            }
            return types.GetPromptResult(
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=DataSerializer.serialize(error_result, indent=2),
                        ),
                    )
                ]
            )

    @lru_cache(maxsize=1000)
    def _resolve_resource_provider(self, uri_str: str) -> BaseMCPProvider | None:
        if uri_str in self._providers_resource_map:
            return self._providers_resource_map[uri_str]

        for pattern, template in self._compiled_uri_patterns:
            if pattern.match(uri_str):
                return self._providers_resource_map.get(template)

        return None

    async def read_resource(self, uri: AnyUrl) -> str:
        """读取资源（统一的路由和执行中心）"""
        uri_str = str(uri)
        provider = self._resolve_resource_provider(uri_str)

        if not provider:
            logger.warning(f"资源未找到: {uri_str}")
            return DataSerializer.serialize(
                {
                    "error": "RESOURCE_NOT_FOUND",
                    "message": messages.MSG_RESOURCE_NOT_FOUND.format(uri=uri_str),
                },
                indent=2,
            )

        logger.info(f"读取资源: {uri_str}")
        return await self._timed_execute(
            uri_str,
            provider.read_resource, uri,
            log_prefix="资源读取",
            error_extra={"uri": uri_str},
            generic_error_code="RESOURCE_READ_ERROR",
        )

    # ===================================================
    # 查询侧：管理后台高性能查询（读合并视图）
    # ===================================================
    @staticmethod
    def _entity_to_dict(m: dict[str, Any]) -> dict[str, Any]:
        """合并视图 -> 对外 dict（仅暴露稳定字段）。"""
        return {
            "name": m.get("name"),
            "short_description": m.get("short_description", ""),
            "long_description": m.get("long_description", ""),
            "group_id": m.get("group_id"),
            "group": m.get("group"),
            "disabled": bool(m.get("disabled", False)),
        }

    async def list_tools_with_metadata(self) -> list[dict[str, Any]]:
        await self._ensure_merged()
        assert self._merged_tools is not None
        return [self._entity_to_dict(m) for m in self._merged_tools.values()]

    async def get_tool_metadata(self, name: str) -> dict[str, Any]:
        await self._ensure_merged()
        assert self._merged_tools is not None
        m = self._merged_tools.get(name)
        if m is None:
            raise ToolNotFoundError(name)
        return self._entity_to_dict(m)

    async def list_resources_with_metadata(self) -> list[dict[str, Any]]:
        await self._ensure_merged()
        assert self._merged_resources is not None
        return [self._entity_to_dict(m) for m in self._merged_resources.values()]

    async def get_resource_metadata(self, name: str) -> dict[str, Any]:
        await self._ensure_merged()
        assert self._merged_resources is not None
        m = self._merged_resources.get(name)
        if m is None:
            raise ResourceNotFoundError(name)
        return self._entity_to_dict(m)

    async def list_prompts_with_metadata(self) -> list[dict[str, Any]]:
        await self._ensure_merged()
        assert self._merged_prompts is not None
        return [self._entity_to_dict(m) for m in self._merged_prompts.values()]

    async def get_prompt_metadata(self, name: str) -> dict[str, Any]:
        await self._ensure_merged()
        assert self._merged_prompts is not None
        m = self._merged_prompts.get(name)
        if m is None:
            raise PromptNotFoundError(name)
        return self._entity_to_dict(m)

    async def get_cli_metadata(self) -> dict[str, Any]:
        """生成 CLI 所需的树形命令元数据（懒构建）。"""
        if self._cli_tree_cache is not None:
            return self._cli_tree_cache
        await self._ensure_merged()
        self._cli_tree_cache = await self._build_cli_tree()
        return self._cli_tree_cache

    async def _build_cli_tree(self) -> dict[str, Any]:
        assert self._merged_tools is not None
        # 拉一次最新的 group 列表（cli 树需要展示所有分组，包括空分组）
        async with get_async_session() as session:
            group_rows = (await session.execute(select(CliGroupModel))).scalars().all()
        group_by_id = {g.id: g for g in group_rows}

        def _path_of(g: CliGroupModel) -> str:
            parts: list[str] = []
            cur: CliGroupModel | None = g
            seen: set = set()
            while cur is not None:
                if cur.id in seen:
                    break
                seen.add(cur.id)
                parts.append(cur.name)
                if cur.parent_id is None:
                    break
                cur = group_by_id.get(cur.parent_id)
            return ".".join(reversed(parts))

        all_paths = {gid: _path_of(g) for gid, g in group_by_id.items()}
        path_to_desc = {
            all_paths[gid]: g.long_description for gid, g in group_by_id.items()
        }

        root_commands: dict[str, Any] = {}

        def _ensure_group_path(tree: dict[str, Any], path: str):
            parts = path.split(".") if path else []
            current = tree
            last_group_node = None
            for part in parts:
                if part not in current:
                    current[part] = {
                        "Group": {
                            "name": part,
                            "description": "",
                            "subcommands": {},
                        }
                    }
                node = current[part]
                if "Group" not in node:
                    return current, None
                last_group_node = node["Group"]
                current = node["Group"]["subcommands"]
            return current, last_group_node

        # 1. 先插入所有分组（含空分组）
        for path, desc in path_to_desc.items():
            _, leaf_group = _ensure_group_path(root_commands, path)
            if leaf_group is not None:
                leaf_group["description"] = desc

        # 2. 插入工具
        for name, m in self._merged_tools.items():
            if m.get("disabled"):
                continue
            group = m.get("group") or ""
            tool_node = {
                "Tool": {
                    "name": name,
                    "description": m.get("short_description", ""),
                    "long_description": m.get("long_description", ""),
                    "mcp_method": name,
                    "category": group,
                    "params": _extract_cli_params(m.get("input_schema") or {}),
                    "examples": m.get("examples", []),
                }
            }
            if group:
                sub, _ = _ensure_group_path(root_commands, group)
                sub[name] = tool_node
            else:
                root_commands[name] = tool_node

        return {
            "version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "root_commands": root_commands,
        }

    async def get_cli_group_entities(
        self, path: str, types: list[str], recursive: bool
    ) -> dict[str, list[dict[str, Any]]]:
        """获取指定分组下的实体列表。"""
        await self._ensure_merged()
        assert self._merged_tools is not None
        assert self._merged_resources is not None
        assert self._merged_prompts is not None

        # 计算目标 path 集合
        target_paths: set[str] = set()
        if path:
            target_paths.add(path)
            if recursive:
                # 子孙：通过 cli_groups 表展开
                async with get_async_session() as session:
                    rows = (
                        (await session.execute(select(CliGroupModel))).scalars().all()
                    )
                group_by_id = {g.id: g for g in rows}

                def _path_of(g: CliGroupModel) -> str:
                    parts: list[str] = []
                    cur: CliGroupModel | None = g
                    seen: set = set()
                    while cur is not None:
                        if cur.id in seen:
                            break
                        seen.add(cur.id)
                        parts.append(cur.name)
                        if cur.parent_id is None:
                            break
                        cur = group_by_id.get(cur.parent_id)
                    return ".".join(reversed(parts))

                for gid, g in group_by_id.items():
                    p = _path_of(g)
                    if p == path or p.startswith(f"{path}."):
                        target_paths.add(p)
        else:
            # path="" 表示无分组实体（group is None）
            target_paths.add("")

        def _match(m: dict[str, Any]) -> bool:
            g = m.get("group") or ""
            return g in target_paths

        result: dict[str, list[dict[str, Any]]] = {}
        if "tool" in types:
            result["tools"] = [
                self._entity_to_dict(m)
                for m in self._merged_tools.values()
                if _match(m)
            ]
        if "resource" in types:
            result["resources"] = [
                self._entity_to_dict(m)
                for m in self._merged_resources.values()
                if _match(m)
            ]
        if "prompt" in types:
            result["prompts"] = [
                self._entity_to_dict(m)
                for m in self._merged_prompts.values()
                if _match(m)
            ]
        return result

    # ===================================================
    # 命令侧 — Metadata Override 管理
    # ===================================================
    @staticmethod
    def _override_default_dict(object_type: str, key: str) -> dict[str, Any]:
        return {
            "object_type": object_type,
            "key": key,
            "short_description": None,
            "long_description": None,
            "disabled": False,
        }

    @staticmethod
    def _is_empty_override(model: MetadataOverrideModel) -> bool:
        """override 行是否等效于空（无 description 且 disabled=False）。"""
        return (
            model.short_description is None
            and model.long_description is None
            and not model.disabled
        )

    @staticmethod
    def _override_to_dict(model: MetadataOverrideModel) -> dict[str, Any]:
        return {
            "object_type": model.object_type,
            "key": model.key,
            "short_description": model.short_description,
            "long_description": model.long_description,
            "disabled": model.disabled,
        }

    async def _upsert_override(
        self,
        object_type: str,
        key: str,
        short_description: str | None,
        long_description: str | None,
        disabled: bool | None,
    ) -> dict[str, Any]:
        update_vals: dict[str, Any] = {}
        if short_description is not None:
            update_vals["short_description"] = short_description
        if long_description is not None:
            update_vals["long_description"] = long_description
        if disabled is not None:
            update_vals["disabled"] = disabled

        async with get_async_session() as session:
            result = await session.execute(
                select(MetadataOverrideModel).where(
                    MetadataOverrideModel.object_type == object_type,
                    MetadataOverrideModel.key == key,
                )
            )
            model = result.scalar_one_or_none()

            # 空请求：不写入；若已存在空行则自动清理
            if not update_vals:
                if model is not None and self._is_empty_override(model):
                    await session.delete(model)
                    await session.flush()
                    self._invalidate_all()
                    return self._override_default_dict(object_type, key)
                return (
                    self._override_to_dict(model)
                    if model
                    else self._override_default_dict(object_type, key)
                )

            if model is None:
                update_vals.setdefault("disabled", False)
                model = MetadataOverrideModel(
                    object_type=object_type,
                    key=key,
                    **update_vals,
                )
                session.add(model)
            else:
                for k, v in update_vals.items():
                    setattr(model, k, v)
            await session.flush()

            # 写入后若变成全空，自动删除，避免留下无效行
            if self._is_empty_override(model):
                await session.delete(model)
                await session.flush()
                self._invalidate_all()
                return self._override_default_dict(object_type, key)

        self._invalidate_all()
        return self._override_to_dict(model)

    async def _delete_override(
        self, object_type: str, key: str, not_found_exc: type
    ) -> None:
        async with get_async_session() as session:
            result = await session.execute(
                select(MetadataOverrideModel).where(
                    MetadataOverrideModel.object_type == object_type,
                    MetadataOverrideModel.key == key,
                )
            )
            if result.scalar_one_or_none() is None:
                raise not_found_exc(key)
            await session.execute(
                delete(MetadataOverrideModel).where(
                    MetadataOverrideModel.object_type == object_type,
                    MetadataOverrideModel.key == key,
                )
            )

        self._invalidate_all()

    # 工具元数据
    async def upsert_tool_metadata_override(
        self,
        original_name: str,
        short_description: str | None = None,
        long_description: str | None = None,
        disabled: bool | None = None,
    ) -> dict[str, Any]:
        """插入或更新工具元数据覆盖（仅描述/disabled）。"""
        return await self._upsert_override(
            "tool", original_name, short_description, long_description, disabled
        )

    async def delete_tool_metadata_override(self, name: str) -> None:
        await self._delete_override("tool", name, ToolNotFoundError)

    # 资源元数据
    async def upsert_resource_metadata_override(
        self,
        original_name: str,
        short_description: str | None = None,
        long_description: str | None = None,
        disabled: bool | None = None,
    ) -> dict[str, Any]:
        return await self._upsert_override(
            "resource",
            original_name,
            short_description,
            long_description,
            disabled,
        )

    async def delete_resource_metadata_override(self, original_name: str) -> None:
        await self._delete_override("resource", original_name, ResourceNotFoundError)

    # 提示词元数据
    async def upsert_prompt_metadata_override(
        self,
        original_name: str,
        short_description: str | None = None,
        long_description: str | None = None,
        disabled: bool | None = None,
    ) -> dict[str, Any]:
        return await self._upsert_override(
            "prompt",
            original_name,
            short_description,
            long_description,
            disabled,
        )

    async def delete_prompt_metadata_override(self, original_name: str) -> None:
        await self._delete_override("prompt", original_name, PromptNotFoundError)

    # ===================================================
    # Provider 硬编码 group 固化
    # ===================================================
    async def _materialize_provider_assignments(
        self, old_path: str, group_id: str, new_path: str
    ) -> None:
        """move/rename 时将 Provider 硬编码 group 的实体固化为 assignment 行。

        Provider 硬编码 group（如 ``"db.mysql"``）的实体在
        ``mcp_entity_group_assignments`` 中没有行，合并视图通过
        ``path_to_id.get(original_group)`` fallback 解析。
        移动/重命名后旧 path 从 path_to_id 消失，fallback 失败。
        此方法将这些隐式归属固化为显式 assignment 行，使后续
        合并重建通过 assignment 路径正确解析。
        """
        prefix = old_path + "."

        # 收集 (object_type, key, provider_group) 三元组
        to_materialize: list[tuple[str, str, str]] = []
        for provider in self.providers:
            for tname, td in provider.mcp.tools_map.items():
                g = getattr(td, "group", None)
                if g and (g == old_path or g.startswith(prefix)):
                    to_materialize.append(("tool", tname, g))
            for _uri, rd in provider.mcp._static_resources.items():
                g = getattr(rd, "group", None)
                if g and (g == old_path or g.startswith(prefix)):
                    to_materialize.append(("resource", rd.name, g))
            for rd in provider.mcp._template_resources:
                g = getattr(rd, "group", None)
                if g and (g == old_path or g.startswith(prefix)):
                    to_materialize.append(("resource", rd.name, g))
            for prompt_name, pd in provider.mcp.prompts_map.items():
                g = getattr(pd, "group", None)
                if g and (g == old_path or g.startswith(prefix)):
                    to_materialize.append(("prompt", prompt_name, g))

        if not to_materialize:
            return

        # 从 DB 读全量数据：已有 assignment（跳过）+ 全量组（构建 path_to_id）
        async with get_async_session() as session:
            assign_rows = (
                (await session.execute(select(EntityGroupAssignmentModel)))
                .scalars()
                .all()
            )
            existing = {(a.object_type, a.key) for a in assign_rows}

            group_rows = (
                (await session.execute(select(CliGroupModel)))
                .scalars()
                .all()
            )

        # 构建新树的 path → id 映射（DB 已反映移动后的新结构）
        id_to_row = {g.id: g for g in group_rows}

        def _path_of(g: CliGroupModel) -> str:
            parts: list[str] = []
            cur: CliGroupModel | None = g
            seen: set[str] = set()
            while cur is not None and cur.id not in seen:
                seen.add(cur.id)
                parts.append(cur.name)
                if cur.parent_id is None:
                    break
                cur = id_to_row.get(cur.parent_id)
            return ".".join(reversed(parts))

        path_to_id = {_path_of(g): g.id for g in group_rows}

        # 对每个需要固化的实体，计算新 path 并 upsert assignment
        new_assignments: list[EntityGroupAssignmentModel] = []
        for obj_type, key, prov_group in to_materialize:
            if (obj_type, key) in existing:
                continue
            # prov_group 仍能通过 path_to_id 解析 → fallback 本身能工作，无需固化
            if prov_group in path_to_id:
                continue
            # 用 old_path → new_path 替换计算新 path
            suffix = prov_group[len(old_path) :]
            target_path = new_path + suffix
            target_gid = path_to_id.get(target_path)
            if target_gid is None:
                continue
            new_assignments.append(
                EntityGroupAssignmentModel(
                    object_type=obj_type,
                    key=key,
                    group_id=target_gid,
                )
            )

        if not new_assignments:
            return

        async with get_async_session() as session:
            session.add_all(new_assignments)
            await session.flush()

        logger.info(
            "已固化 %d 个 Provider 硬编码实体的分组归属（%s: %s → %s）",
            len(new_assignments),
            group_id,
            old_path,
            new_path,
        )

    # ===================================================
    # 事件订阅处理
    # ===================================================
    async def on_mcp_group_changed(self, event: MCPGroupChanged) -> None:
        """MCP 分组变更：失效合并视图（path 可能改变）。

        move/rename 时，Provider 硬编码 group 的实体会因旧 path 从
        path_to_id 中消失而失去分组。先将这些隐式归属固化为 assignment 行，
        再失效缓存，确保合并重建时能通过 assignment 解析到正确的组。
        """
        if event.operation in ("moved", "renamed") and event.old_path and event.group_id:
            await self._materialize_provider_assignments(
                old_path=event.old_path,
                group_id=event.group_id,
                new_path=event.new_path or "",
            )
        self._invalidate_all()

    async def on_mcp_entity_assigned(
        self, event: MCPEntityAssigned
    ) -> None:
        """实体↔分组归属变更：失效合并视图。"""
        self._invalidate_all()

    # ===================================================
    # 生命周期
    # ===================================================
    async def startup(self) -> None:
        """启动所有 Provider；完成后发布 ``MCPProvidersStarted`` 事件。"""
        for provider in self.providers:
            try:
                logger.info("正在启动 Provider: %s", provider.__class__.__name__)
                await provider.startup()
            except Exception as e:
                logger.error(
                    "Provider %s 启动失败: %s",
                    provider.__class__.__name__,
                    e,
                    exc_info=True,
                )

        paths = self._collect_provider_group_paths()
        await self._event_service.publish(
            MCPProvidersStarted(group_paths=sorted(paths))
        )

    def _collect_provider_group_paths(self) -> set[str]:
        """扫描所有 Provider 的 tools/resources/prompts，收集 group path 并展开中间段。"""
        paths: set[str] = set()
        for provider in self.providers:
            for tname, td in provider.mcp.tools_map.items():
                g = getattr(td, "group", None)
                if g:
                    parts = g.split(".")
                    for i in range(1, len(parts) + 1):
                        paths.add(".".join(parts[:i]))
            for _uri, rd in provider.mcp._static_resources.items():
                g = getattr(rd, "group", None)
                if g:
                    parts = g.split(".")
                    for i in range(1, len(parts) + 1):
                        paths.add(".".join(parts[:i]))
            for rd in provider.mcp._template_resources:
                g = getattr(rd, "group", None)
                if g:
                    parts = g.split(".")
                    for i in range(1, len(parts) + 1):
                        paths.add(".".join(parts[:i]))
            for pname, pd in provider.mcp.prompts_map.items():
                g = getattr(pd, "group", None)
                if g:
                    parts = g.split(".")
                    for i in range(1, len(parts) + 1):
                        paths.add(".".join(parts[:i]))
        return paths

    # ===================================================
    # 配置 MCP 协议的回调函数
    # ===================================================
    def _setup_handlers(self):
        @self.sdk_server.list_resources()
        async def handle_list_resources() -> list[Resource]:
            try:
                logger.info("处理资源列表请求")
                resources = await self.middleware_stack.on_list_resources(
                    self.list_resources
                )
                logger.info(f"返回 {len(resources)} 个资源")
                return resources
            except Exception as e:
                logger.error(f"处理资源列表请求失败: {e}", exc_info=True)
                return []

        @self.sdk_server.list_resource_templates()
        async def handle_list_resource_templates() -> list[types.ResourceTemplate]:
            try:
                logger.info("处理资源模板列表请求")
                resource_templates = (
                    await self.middleware_stack.on_list_resource_templates(
                        self.list_resource_templates
                    )
                )
                logger.debug(f"返回 {len(resource_templates)} 个资源模板")
                return resource_templates
            except Exception as e:
                logger.error(f"处理资源模板列表请求失败: {e}", exc_info=True)
                return []

        @self.sdk_server.read_resource()
        async def handle_read_resource(uri: AnyUrl) -> str:
            try:
                logger.info(f"处理资源读取请求: {uri}")
                content = await self.middleware_stack.on_read_resource(
                    self.read_resource, uri
                )
                logger.debug(f"资源读取成功: {uri}")
                if _is_error_json(content):
                    parsed = json.loads(content)
                    if parsed.get("error") == "RESOURCE_NOT_FOUND":
                        raise ResourceNotFoundError(str(uri))
                return content
            except ResourceNotFoundError:
                raise
            except Exception:
                logger.error(
                    f"处理资源读取请求失败: {uri}",
                    exc_info=True,
                )
                raise

        @self.sdk_server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            try:
                logger.info("处理工具列表请求")
                tools = await self.middleware_stack.on_list_tools(self.list_tools)
                logger.info(f"返回 {len(tools)} 个工具")
                return tools
            except Exception as e:
                logger.error(f"处理工具列表请求失败: {e}", exc_info=True)
                return []

        @self.sdk_server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> types.CallToolResult:
            try:
                logger.info(f"处理工具调用请求: {name}")
                result = await self.middleware_stack.on_call_tool(
                    self.call_tool, name, arguments
                )
                logger.debug(f"工具调用成功: {name}")
                is_error = _is_error_json(result)
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=result)],
                    is_error=is_error,
                )
            except Exception:
                logger.error(
                    f"处理工具调用请求失败: {name}",
                    exc_info=True,
                )
                raise

        @self.sdk_server.list_prompts()
        async def handle_list_prompts() -> list[types.Prompt]:
            try:
                logger.info("处理提示列表请求")
                prompts = await self.middleware_stack.on_list_prompts(self.list_prompts)
                logger.info(f"返回 {len(prompts)} 个提示")
                return prompts
            except Exception as e:
                logger.error(f"处理提示列表请求失败: {e}", exc_info=True)
                return []

        @self.sdk_server.get_prompt()
        async def handle_get_prompt(
            name: str, arguments: dict[str, str] | None
        ) -> types.GetPromptResult:
            try:
                logger.info(f"处理提示获取请求: {name}")
                result = await self.middleware_stack.on_get_prompt(
                    self.get_prompt, name, arguments
                )
                logger.debug(f"提示获取成功: {name}")
                # 检查 Service 层是否返回了错误包装（Prompt 未找到）
                if (
                    result.messages
                    and len(result.messages) == 1
                    and isinstance(result.messages[0].content, types.TextContent)
                    and _is_error_json(result.messages[0].content.text)
                ):
                    parsed = json.loads(result.messages[0].content.text)
                    if parsed.get("error") == "PROMPT_NOT_FOUND":
                        raise PromptNotFoundError(name)
                return result
            except PromptNotFoundError:
                raise
            except Exception:
                logger.error(
                    f"处理提示获取请求失败: {name}",
                    exc_info=True,
                )
                raise


class MCPServiceFactory(ServiceFactory):
    """MCP 服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="mcp_service",
            service_type=MCPService,
            description="MCP 协议服务",
            author="DM MCP Team",
            dependencies=[
                "metrics_service",
                "logging_service",
                "event_service",
            ],
            priority=50,
            event_subscriptions=[
                EventSubscription(
                    MCPGroupChanged,
                    "on_mcp_group_changed",
                    priority=50,
                ),
                EventSubscription(
                    MCPEntityAssigned,
                    "on_mcp_entity_assigned",
                    priority=50,
                ),
            ],
        )

    def create(self, settings, **deps) -> MCPService:
        return MCPService(
            settings.server,
            deps["metrics_service"],
            deps["logging_service"],
            deps["event_service"],
        )
