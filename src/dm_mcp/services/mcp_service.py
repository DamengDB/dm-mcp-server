"""MCP 协议服务模块

提供服务功能：
- MCP 协议的核心服务实现
- Tools、Resources、Prompts 的统一管理和路由
- MCP Provider 的注册和调度
- MCP Middleware 的支持
- fastmcp 兼容性支持
"""

import json
import logging
import re
import time
from datetime import datetime
from functools import cached_property, lru_cache
from itertools import chain
from typing import Any, Dict, List, Optional

from mcp import Resource, Tool, types
from mcp.server import Server
from pydantic import AnyUrl

from dm_mcp.core.exceptions import DmMCPError
from dm_mcp.core.mcp import BaseMCPProvider
from dm_mcp.core.mcp.middleware import BaseMCPMiddleware, MCPMiddlewareStack
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.middlewares.metrics_middleware import MetricsMCPMiddleware
from dm_mcp.middlewares.sql_guard_middleware import SqlGuardMCPMiddleware
from dm_mcp.settings.settings import ServerConfig
from dm_mcp.utils import json_dumps_with_datetime

from .base_service import BaseService
from .logging_service import LoggingService
from .metrics_service import MetricsService

logger = logging.getLogger(__name__)


class MCPService(BaseService):
    """MCP 协议服务

    管理 MCP（Model Context Protocol）协议的核心功能。

    主要功能：
    - Tools、Resources、Prompts 的统一管理和路由
    - MCP Provider 的注册和调度
    - MCP Middleware 的支持和调用链
    - fastmcp 兼容性支持
    - URI 模板匹配和资源路由
    """

    def __init__(
        self,
        server_config: ServerConfig,
        metrics_service: MetricsService,
        logging_service: LoggingService,
    ) -> None:
        self.sdk_server = Server(server_config.name)
        self.providers: List[BaseMCPProvider] = []
        self.middleaware_stack = MCPMiddlewareStack()

        # 默认中间件：
        # - MetricsMCPMiddleware: 采集工具调用指标
        # - SqlGuardMCPMiddleware: 对指定 SQL 工具做安全控制
        self.add_mcp_middlewares(
            [
                MetricsMCPMiddleware(metrics_service),
                SqlGuardMCPMiddleware(
                    protected_tools=[
                        "exec_readonly_query",
                    ]
                ),
            ]
        )

        self._setup_handlers()

    # ===================================================
    # 属性管理
    # ===================================================
    def add_mcp_middleware(self, middleware: BaseMCPMiddleware):
        """添加 MCP 中间件

        Args:
            middleware: MCP 中间件实例
        """
        self.middleaware_stack.add_middleware(middleware)

    def add_mcp_middlewares(self, middlewares: List[BaseMCPMiddleware]):
        """批量添加 MCP 中间件

        Args:
            middlewares: MCP 中间件实例列表
        """
        self.middleaware_stack.add_middlewares(middlewares)

    def add_mcp_provider(self, provider: BaseMCPProvider):
        """添加 MCP Provider

        Args:
            provider: MCP Provider 实例
        """
        self.providers.append(provider)

    def add_mcp_providers(self, providers: List[BaseMCPProvider]):
        """批量添加 MCP Provider

        Args:
            providers: MCP Provider 实例列表
        """
        self.providers.extend(providers)

    def get_tool_definition(self, tool_name: str):
        """获取工具定义

        Args:
            tool_name: 工具名称

        Returns:
            工具定义，如果不存在返回 None
        """
        if tool_name in self._providers_tool_map:
            provider = self._providers_tool_map[tool_name]
            return provider.mcp.tools_map.get(tool_name)
        return None

    # ===================================================
    # 缓存属性
    # ===================================================
    @cached_property
    def _tools(self) -> List[Tool]:
        provider_tools = [provider.list_tools() for provider in self.providers]
        return list(chain.from_iterable(t for t in provider_tools))

    @cached_property
    def _resources(self) -> List[Resource]:
        provider_resources = [provider.list_resources() for provider in self.providers]
        return list(chain.from_iterable(r for r in provider_resources))

    @cached_property
    def _resource_templates(self) -> List[types.ResourceTemplate]:
        provider_resource_templates = [
            provider.list_resource_templates() for provider in self.providers
        ]
        return list(chain.from_iterable(r for r in provider_resource_templates))

    @cached_property
    def _prompts(self) -> List[types.Prompt]:
        provider_prompts = [provider.list_prompts() for provider in self.providers]
        return list(chain.from_iterable(p for p in provider_prompts))

    @cached_property
    def _providers_tool_map(self) -> Dict[str, BaseMCPProvider]:
        providers_map: Dict[str, BaseMCPProvider] = {}
        for provider in self.providers:
            providers_map |= {tool.name: provider for tool in provider.list_tools()}
        return providers_map

    @cached_property
    def _providers_prompt_map(self) -> Dict[str, BaseMCPProvider]:
        providers_map: Dict[str, BaseMCPProvider] = {}
        for provider in self.providers:
            providers_map |= {
                prompt.name: provider for prompt in provider.list_prompts()
            }
        return providers_map

    @cached_property
    def _providers_resource_map(self) -> Dict[str, BaseMCPProvider]:
        """
        建立 URI 模板 -> Provider 的映射
        必须同时包含静态资源 (Resource) 和 动态模板 (ResourceTemplate)
        """
        providers_map: Dict[str, BaseMCPProvider] = {}
        for provider in self.providers:
            # 1. 映射静态资源
            for resource in provider.list_resources():
                providers_map[str(resource.uri)] = provider

            # 2. 映射资源模板
            for template in provider.list_resource_templates():
                providers_map[template.uriTemplate] = provider

        return providers_map

    @cached_property
    def _compiled_uri_patterns(self):
        """
        优化：预编译所有资源模板的正则表达式
        返回: List[(RegexPattern, original_template_uri)]
        按长度降序排列以处理优先级
        """
        patterns = []
        # 获取所有包含参数的模板 (静态资源已经在 map 中处理了)
        templates = [uri for uri in self._providers_resource_map.keys() if "{" in uri]

        # 简单优先级：长的模板优先匹配
        templates.sort(key=len, reverse=True)

        for template in templates:
            # 转换为正则:
            # 1. escape 转义特殊字符
            # 2. 将 \{...\} 替换为 [^/]+ (假设参数不包含斜杠)
            # 注意：先 replace 把转义后的 \{ 变回 { 以便识别
            pattern_str = re.escape(template).replace(r"\{", "{").replace(r"\}", "}")
            # 替换 {param} 为非贪婪匹配，或者简单的非斜杠匹配
            pattern_str = re.sub(r"\{[^}]+\}", r"[^/]+", pattern_str)
            # 全匹配
            pattern_str = f"^{pattern_str}$"

            try:
                patterns.append((re.compile(pattern_str), template))
            except re.error as e:
                logger.error(f"编译资源模板正则表达式失败: {template}, 错误: {e}")

        return patterns

    # ===================================================
    # 支持 fastmcp 注册
    # ===================================================
    async def register_tools_with_fastmcp(self, mcp):
        """支持 fastmcp 注册

        将所有注册的工具动态注册到 fastmcp 实例中。

        Args:
            mcp: fastmcp 实例
        """
        logger.info("开始动态注册 MCP 工具")

        for tool in self._tools:

            @mcp.tool(name=tool.name, description=tool.description)
            async def wrapper(**kwargs):
                return await self.call_tool(tool.name, kwargs)

        logger.info(f"成功注册 {len(self._tools)} 个工具")

    # ===================================================
    # MCP 协议的回调函数
    # ===================================================
    async def list_tools(self) -> List[Tool]:
        """列出所有工具

        Returns:
            工具列表
        """
        return self._tools

    async def list_resources(self) -> List[Resource]:
        """列出所有静态资源

        Returns:
            静态资源列表
        """
        return self._resources

    async def list_resource_templates(self) -> List[types.ResourceTemplate]:
        """列出所有资源模板

        Returns:
            资源模板列表
        """
        return self._resource_templates

    async def list_prompts(self) -> List[types.Prompt]:
        """列出所有提示

        Returns:
            提示列表
        """
        return self._prompts

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """调用工具（统一的路由和执行中心）

        Args:
            name: 工具名称
            arguments: 工具参数

        Returns:
            JSON 格式的执行结果字符串
        """
        if name not in self._providers_tool_map:
            error_result = {
                "error": "TOOL_NOT_FOUND",
                "message": f"Unknown tool: {name}",
                "tool_name": name,
                "timestamp": datetime.now().isoformat(),
            }
            return json_dumps_with_datetime(error_result, ensure_ascii=False, indent=2)

        try:
            logger.info(f"执行工具调用: {name}, 参数: {arguments}")

            provider = self._providers_tool_map[name]
            start_time = time.time()

            # 执行具体的 Handler
            result = await provider.call_tool(name, arguments)

            # 统一添加执行信息
            execution_time = time.time() - start_time
            if isinstance(result, dict):
                result["_execution_info"] = {
                    "tool_name": name,
                    "execution_time": round(execution_time, 3),
                    "timestamp": datetime.now().isoformat(),
                }

            logger.info(f"工具调用完成: {name}, 耗时: {execution_time:.3f}秒")
            return json_dumps_with_datetime(result, ensure_ascii=False, indent=2)

        except DmMCPError as e:
            # 业务异常
            logger.warning(
                f"工具调用业务错误: {name}, 错误码: {e.error_code}, 消息: {e.message}",
                extra={"error_code": e.error_code, "tool_name": name},
            )
            error_result = {
                "error": e.error_code,
                "message": e.message,
                "details": e.details,
                "tool_name": name,
                "arguments": arguments,
                "timestamp": datetime.now().isoformat(),
            }
            return json_dumps_with_datetime(error_result, ensure_ascii=False, indent=2)

        except Exception as e:
            # 系统异常
            logger.error(
                f"工具调用系统错误: {name}, 错误: {str(e)}",
                exc_info=True,
                extra={"tool_name": name, "arguments": arguments},
            )
            error_result = {
                "error": "TOOL_EXECUTION_ERROR",
                "message": f"Tool execution failed: {str(e)}",
                "tool_name": name,
                "arguments": arguments,
                "timestamp": datetime.now().isoformat(),
            }
            return json_dumps_with_datetime(error_result, ensure_ascii=False, indent=2)

    async def get_prompt(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> types.GetPromptResult:
        """获取提示内容

        Args:
            name: 提示名称
            arguments: 提示参数（可选）

        Returns:
            提示结果
        """
        if name not in self._providers_prompt_map:
            error_result = {
                "error": "PROMPT_NOT_FOUND",
                "message": f"Unknown prompt: {name}",
                "prompt_name": name,
                "arguments": arguments,
            }
            return types.GetPromptResult(
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=json_dumps_with_datetime(
                                error_result, ensure_ascii=False, indent=2
                            ),
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
                "message": f"Failed to get prompt: {str(e)}",
                "prompt_name": name,
                "arguments": arguments,
            }
            return types.GetPromptResult(
                messages=[
                    types.PromptMessage(
                        role="user",
                        content=types.TextContent(
                            type="text",
                            text=json_dumps_with_datetime(
                                error_result, ensure_ascii=False, indent=2
                            ),
                        ),
                    )
                ]
            )

    @lru_cache(maxsize=1000)
    def _resolve_resource_provider(self, uri_str: str) -> Optional[BaseMCPProvider]:
        """解析 URI 对应的 Provider（使用 LRU 缓存加速）

        Args:
            uri_str: 资源 URI 字符串

        Returns:
            对应的 Provider 实例，如果不存在返回 None
        """
        # 尝试精确匹配 (Static Resource)
        if uri_str in self._providers_resource_map:
            return self._providers_resource_map[uri_str]

        # 尝试正则匹配 (Template Resource)
        # 使用预编译的 patterns，避免每次重建正则
        for pattern, template in self._compiled_uri_patterns:
            if pattern.match(uri_str):
                return self._providers_resource_map.get(template)

        return None

    async def read_resource(self, uri: AnyUrl) -> str:
        """读取资源（统一的路由和执行中心）

        Args:
            uri: 资源 URI

        Returns:
            资源内容字符串（JSON 格式）
        """
        uri_str = str(uri)

        try:
            logger.info(f"读取资源: {uri_str}")

            # 使用带缓存的解析逻辑
            provider = self._resolve_resource_provider(uri_str)

            if provider:
                result = await provider.read_resource(uri)
                logger.debug(f"资源读取成功: {uri_str}")
                return result

            # 没有找到匹配的资源
            logger.warning(f"资源未找到: {uri_str}")
            error_result = {
                "error": "RESOURCE_NOT_FOUND",
                "message": f"Resource not found: {uri_str}",
                "uri": uri_str,
                "timestamp": datetime.now().isoformat(),
            }
            return json_dumps_with_datetime(error_result, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(
                f"资源读取系统错误: {uri_str}, 错误: {str(e)}",
                exc_info=True,
                extra={"uri": uri_str},
            )
            error_result = {
                "error": "RESOURCE_READ_ERROR",
                "message": f"Failed to read resource: {str(e)}",
                "uri": uri_str,
                "timestamp": datetime.now().isoformat(),
            }
            return json_dumps_with_datetime(error_result, ensure_ascii=False, indent=2)

    def _match_uri_template(self, uri: str, template: str) -> bool:
        """检查 URI 是否匹配模板

        Args:
            uri: 实际的 URI，例如 "users://123/profile"
            template: URI 模板，例如 "users://{user_id}/profile"

        Returns:
            True 如果匹配，False 否则
        """
        # 将模板转换为正则表达式
        # 转义特殊字符
        pattern = re.escape(template)
        # 将 \{param\} 或 \{param:type\} 替换为通配符
        pattern = re.sub(r"\\{[^}]+\\}", r"[^/]+", pattern)
        pattern = f"^{pattern}$"

        return bool(re.match(pattern, uri))

    # ===================================================
    # 配置 MCP 协议的回调函数
    # ===================================================
    def _setup_handlers(self):
        """配置 MCP 协议的回调函数

        将所有 MCP 协议的回调函数注册到 SDK Server 实例中。
        """

        @self.sdk_server.list_resources()
        async def handle_list_resources() -> List[Resource]:
            """Handle resource list request"""
            try:
                logger.info("处理资源列表请求")
                resources = await self.middleaware_stack.on_list_resources(
                    self.list_resources
                )
                logger.info(f"返回 {len(resources)} 个资源")

                return resources
            except Exception as e:
                logger.error(f"处理资源列表请求失败: {e}", exc_info=True)
                return []

        @self.sdk_server.list_resource_templates()
        async def handle_list_resource_templates() -> List[types.ResourceTemplate]:
            """Handle resource template list request"""
            try:
                logger.info("处理资源模板列表请求")
                resource_templates = (
                    await self.middleaware_stack.on_list_resource_templates(
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
            """Handle resource read request"""
            try:
                logger.info(f"处理资源读取请求: {uri}")
                content = await self.middleaware_stack.on_read_resource(
                    self.read_resource, uri
                )
                logger.debug(f"资源读取成功: {uri}")
                return content
            except Exception as e:
                logger.error(f"处理资源读取请求失败: {uri}, 错误: {e}", exc_info=True)
                return json_dumps_with_datetime(
                    {"error": f"Failed to read resource: {str(e)}", "uri": uri},
                    ensure_ascii=False,
                    indent=2,
                )

        @self.sdk_server.list_tools()
        async def handle_list_tools() -> List[Tool]:
            try:
                logger.info("处理工具列表请求")
                tools = await self.middleaware_stack.on_list_tools(self.list_tools)
                logger.info(f"返回 {len(tools)} 个工具")
                return tools
            except Exception as e:
                logger.error(f"处理工具列表请求失败: {e}", exc_info=True)
                return []

        @self.sdk_server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> List[types.TextContent]:
            try:
                logger.info(f"处理工具调用请求: {name}")
                result = await self.middleaware_stack.on_call_tool(
                    self.call_tool, name, arguments
                )
                logger.debug(f"工具调用成功: {name}")
                return [types.TextContent(type="text", text=result)]
            except Exception as e:
                logger.error(f"处理工具调用请求失败: {name}, 错误: {e}", exc_info=True)
                error_result = json_dumps_with_datetime(
                    {
                        "error": f"Tool call failed: {str(e)}",
                        "tool_name": name,
                        "arguments": arguments,
                    },
                    ensure_ascii=False,
                    indent=2,
                )

                return [types.TextContent(type="text", text=error_result)]

        @self.sdk_server.list_prompts()
        async def handle_list_prompts() -> List[types.Prompt]:
            """Handle prompt list request"""
            try:
                logger.info("处理提示列表请求")
                prompts = await self.middleaware_stack.on_list_prompts(
                    self.list_prompts
                )
                logger.info(f"返回 {len(prompts)} 个提示")
                return prompts
            except Exception as e:
                logger.error(f"处理提示列表请求失败: {e}", exc_info=True)
                return []

        @self.sdk_server.get_prompt()
        async def handle_get_prompt(
            name: str, arguments: dict[str, str] | None  # 1. 允许接收 None
        ) -> types.GetPromptResult:
            """Handle prompt get request"""
            try:
                logger.info(f"处理提示获取请求: {name}")
                result = await self.middleaware_stack.on_get_prompt(
                    self.get_prompt, name, arguments
                )
                logger.debug(f"提示获取成功: {name}")
                return result
            except Exception as e:
                logger.error(f"处理提示获取请求失败: {name}, 错误: {e}", exc_info=True)
                error_result = json_dumps_with_datetime(
                    {
                        "error": f"Failed to get prompt: {str(e)}",
                        "prompt_name": name,
                        "arguments": arguments,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                return types.GetPromptResult(
                    messages=[
                        types.PromptMessage(
                            role="user",
                            content=types.TextContent(type="text", text=error_result),
                        )
                    ]
                )


class MCPServiceFactory(ServiceFactory):
    """MCP 服务工厂

    负责创建和配置 MCPService 实例。
    """

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="mcp_service",
            service_type=MCPService,
            description="MCP 协议服务",
            author="DM MCP Team",
            dependencies=[
                "metrics_service",
                "logging_service",
            ],  # 依赖 metrics_service
            priority=50,
        )

    def create(self, settings, **deps) -> MCPService:
        return MCPService(
            settings.server,
            deps["metrics_service"],
            deps["logging_service"],
        )
