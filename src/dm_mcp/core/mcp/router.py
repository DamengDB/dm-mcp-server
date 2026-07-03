"""MCP路由器模块

提供MCP路由器实现，用于注册和管理工具、资源、提示词，并处理MCP协议的调用。
"""

import functools
import logging
from typing import Any, Callable, Dict, List

from mcp import Resource, Tool
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptMessage,
    Resource,
    ResourceTemplate,
    TextContent,
)
from pydantic.networks import AnyUrl

from dm_mcp.utils.encoding import json_dumps_with_datetime

from .prompt import PromptDefinition
from .resource import ResourceDefinition
from .tool import ToolDefinition

logger = logging.getLogger(__name__)


class MCPRouter(object):
    """MCP路由器

    负责注册和管理MCP工具、资源、提示词，提供装饰器接口方便注册，
    并实现MCP协议的标准方法（list_tools、call_tool、list_resources等）。
    """

    def __init__(self):
        # Tools
        self.tools: List[Tool] = []
        self.tools_map: Dict[str, ToolDefinition] = {}

        # Resources
        self._static_resources: Dict[str, ResourceDefinition] = {}
        self._template_resources: List[ResourceDefinition] = []

        # Prompts
        self.prompts: List[Prompt] = []
        self.prompts_map: Dict[str, Callable] = {}

    # ==========================
    # 装饰器
    # ==========================
    def tool(
        self,
        name: str | None = None,
        description: str | None = None,
        exclude_args: list[str] | None = None,
        requires_token_auth: bool = False,
    ):
        """
        工具装饰器

        Args:
            name: 工具名称（可选，默认使用函数名）
            description: 工具描述（可选，默认使用函数 docstring）
            exclude_args: 要从输入 schema 中排除的参数列表
            requires_token_auth: 是否需要对 Token 认证（默认 False）

        使用示例：
            @router.tool(name="db.query", requires_token_auth=True)
            async def db_query(...):
                ...
        """

        def decorator(func):
            tool_def = ToolDefinition.from_function(
                func,
                exclude_args=exclude_args,
            )
            tool_def.name = name or tool_def.name
            tool_def.description = description or tool_def.description
            tool_def.requires_token_auth = requires_token_auth

            if requires_token_auth:
                logger.debug(f"Tool '{tool_def.name}' requires token authentication")

            self.tools.append(tool_def.to_tool())
            self.tools_map[tool_def.name] = tool_def

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def resource(
        self,
        uri: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
    ):
        """
        资源装饰器，支持 URI 模板（使用 parse 库语法）

        示例：
            @router.resource("users://{user_id}/profile")
            async def get_user_profile(user_id: str) -> str:
                return f"Profile for user {user_id}"

            # 支持类型转换
            @router.resource("posts://{post_id:d}/comments")
            async def get_post_comments(post_id: int) -> str:
                return f"Comments for post {post_id}"

            # name 支持与 uri 相同的模板参数，共用 template_params
            @router.resource("users://{user_id}/profile", name="user-{user_id}-profile")
            async def get_user_profile(user_id: str) -> str:
                return f"Profile for user {user_id}"

        参数：
            uri: URI 模板，支持 parse 库的格式语法
                 如 {param}, {param:d}, {param:f} 等
            name: 资源名称，支持与 uri 相同的模板参数语法，共用 template_params。
                  未指定时默认使用 uri
            description: 资源描述（可选）
            mime_type: MIME 类型（默认 text/plain）
        """

        def decorator(func):
            resource_def = ResourceDefinition.from_function(
                func,
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
            )

            # 根据是否为模板分类存储
            if resource_def.is_template:
                self._template_resources.append(resource_def)
                # 简单优先级策略：按 URI 长度降序排列，保证更具体的路径优先匹配
                # 例如 users/detail/{id} 会排在 users/{id} 前面
                self._template_resources.sort(key=lambda r: len(r.uri), reverse=True)
            else:
                self._static_resources[uri] = resource_def

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    def prompt(
        self,
        name: str | None = None,
        description: str | None = None,
    ):
        """
        Prompt 装饰器，用于定义对话模板

        示例：
            @router.prompt("greeting")
            async def greeting_prompt(user_name: str) -> str:
                '''生成问候语'''
                return f"Hello, {user_name}! How can I help you today?"

        参数：
            name: Prompt 名称（可选，默认使用函数名）
            description: Prompt 描述（可选，默认使用函数 docstring）
        """

        def decorator(func):
            prompt_def = PromptDefinition.from_function(
                func,
                name=name,
                description=description,
            )

            # 添加到列表（用于 list_prompts）
            self.prompts.append(prompt_def.to_prompt())

            # 添加到映射表（用于 get_prompt）- 和 tool 一样
            self.prompts_map[prompt_def.name] = prompt_def.fn

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    # ==========================
    # 辅助方法
    # ==========================
    @functools.cached_property
    def _resources(self) -> List[Resource]:
        """列出所有静态资源"""
        return [r.to_resource() for r in self._static_resources.values()]

    @functools.cached_property
    def _resource_templates(self) -> List[ResourceTemplate]:
        """列出所有资源模板"""
        return [r.to_resource_template() for r in self._template_resources]

    # ==========================
    # mcp 接口
    # ==========================
    def list_resources(self) -> List[Resource]:
        """列出所有资源"""
        return self._resources

    def list_resource_templates(self) -> List[ResourceTemplate]:
        """列出所有资源模板"""
        return self._resource_templates

    async def read_resource(self, uri: str | AnyUrl) -> str:
        """
        读取资源
        优化：先查静态表，再遍历动态模板列表
        """
        uri_str = str(uri)

        # 查找静态资源
        if uri_str in self._static_resources:
            try:
                resource_def = self._static_resources[uri_str]
                # 静态资源无参数
                result = await resource_def.fn()
                if isinstance(result, str):
                    return result
                return json_dumps_with_datetime(result, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"读取静态资源失败: {uri_str}, 错误: {e}", exc_info=True)
                raise ValueError(f"Failed to read resource {uri_str}: {str(e)}")

        # 遍历动态模板 (已按长度排序)
        for resource_def in self._template_resources:
            params = resource_def.match_uri(uri_str)
            if params is not None:
                try:
                    result = await resource_def.fn(**params)
                    if isinstance(result, str):
                        return result
                    return json_dumps_with_datetime(
                        result, ensure_ascii=False, indent=2
                    )
                except Exception as e:
                    logger.error(
                        f"读取模板资源失败: {uri_str}, 错误: {e}", exc_info=True
                    )
                    raise ValueError(f"Failed to read resource {uri_str}: {str(e)}")

        # 没有找到匹配的资源
        raise ValueError(f"Resource not found: {uri_str}")

    def list_tools(self) -> List[Tool]:
        return self.tools

    async def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if name not in self.tools_map:
            raise ValueError(f"Unknown tool: {name}")

        tool_def = self.tools_map[name]
        result = await tool_def.fn(**args)
        return result

    def list_prompts(self) -> List[Prompt]:
        """列出所有 Prompts"""
        return self.prompts

    async def get_prompt(
        self, name: str, arguments: Dict[str, str] | None = None
    ) -> GetPromptResult:
        """
        获取 Prompt 结果 - 和 call_tool 类似的简化实现

        参数：
            name: Prompt 名称
            arguments: Prompt 参数（字典形式）

        返回：
            GetPromptResult 对象，包含 messages
        """
        if name not in self.prompts_map:
            raise ValueError(f"Unknown prompt: {name}")

        handler = self.prompts_map[name]

        try:
            # 调用 prompt 处理函数
            result = await handler(**(arguments or {}))

            # 如果返回的是 GetPromptResult，直接返回
            if isinstance(result, GetPromptResult):
                return result

            # 如果返回的是字符串，包装成 GetPromptResult
            if isinstance(result, str):
                return GetPromptResult(
                    description=None,
                    messages=[
                        PromptMessage(
                            role="user",
                            content=TextContent(type="text", text=result),
                        )
                    ],
                )

            # 如果返回的是消息列表
            if isinstance(result, list):
                return GetPromptResult(description=None, messages=result)

            # 其他情况，尝试 JSON 序列化
            text = json_dumps_with_datetime(result, ensure_ascii=False, indent=2)
            return GetPromptResult(
                description=None,
                messages=[
                    PromptMessage(
                        role="user", content=TextContent(type="text", text=text)
                    )
                ],
            )

        except Exception as e:
            logger.error(f"获取提示失败: {name}, 错误: {e}", exc_info=True)
            raise ValueError(f"Failed to get prompt {name}: {str(e)}")
