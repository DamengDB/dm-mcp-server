"""MCP路由器模块

提供MCP路由器实现，用于注册和管理工具、资源、提示词，并处理MCP协议的调用。
"""

import functools
import logging
from typing import Any, Callable

from mcp import Resource, Tool
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptMessage,
    Resource,
    ResourceTemplate,
    TextContent,
)
from pydantic import ValidationError
from pydantic.networks import AnyUrl

from dm_mcp.common import messages
from dm_mcp.core.exceptions import (
    PromptNotFoundError,
    ResourceNotFoundError,
    ToolNotFoundError,
)
from dm_mcp.core.mcp.serialization import DataSerializer

from dm_mcp.domain.mcp.groups import CliGroupRegistry
from dm_mcp.domain.mcp.entities.prompt import PromptDefinition
from dm_mcp.domain.mcp.entities.resource import ResourceDefinition
from dm_mcp.domain.mcp.entities.tool import ToolDefinition

logger = logging.getLogger(__name__)


class MCPRouter(object):
    """MCP路由器

    负责注册和管理MCP工具、资源、提示词，提供装饰器接口方便注册，
    并实现MCP协议的标准方法（list_tools、call_tool、list_resources等）。
    """

    def __init__(self):
        # Tools
        self.tools: list[Tool] = []
        self.tools_map: dict[str, ToolDefinition] = {}

        # Resources
        self._static_resources: dict[str, ResourceDefinition] = {}
        self._template_resources: list[ResourceDefinition] = []
        self._template_resources_dirty: bool = True  # 标记是否需要重新排序

        # Prompts
        self.prompts: list[Prompt] = []
        self.prompts_map: dict[str, PromptDefinition] = {}

    # ==========================
    # 装饰器
    # ==========================
    def tool(
        self,
        name: str | None = None,
            group: str | None = None,  # 仅 CLI 元数据；MCP 协议不依赖此字段
        description: str | None = None,
        exclude_args: list[str] | None = None,
        requires_token_auth: bool = False,
        examples: list[str] | None = None,
    ):
        """
        工具装饰器

        Args:
            name: 工具名称（可选，默认使用函数名）
            group: 分组路径（可选，例如 "db" 或 "db.mysql"）
            description: 工具描述（可选，默认使用函数 docstring）
            exclude_args: 要从输入 schema 中排除的参数列表
            requires_token_auth: 是否需要对 Token 认证（默认 False）
            examples: 工具示例列表（可选）

        使用示例：
            @router.tool(group="db", name="query", requires_token_auth=True)
            async def db_query(...):
                ...
        """

        def decorator(func):
            # 1. 确定最终的工具名称（保持原有默认功能）
            resolved_name = name or getattr(func, "__name__", None) or func.__class__.__name__
            
            # 2. 分组路径仅用于开发期校验与 CLI 元数据（见 groups 模块）
            CliGroupRegistry.validate_path(group)

            # 3. 生成工具定义
            tool_def = ToolDefinition.from_function(
                func,
                exclude_args=exclude_args,
            )
            # name 使用短名，group 单独存储（工具、资源、提示词不会重名）
            tool_def.name = resolved_name
            tool_def.group = group

            # 4. 显式传入的 description 优先级高于 docstring 自动提取
            if description:
                lines = description.strip().split('\n')
                tool_def.short_description = lines[0].strip()
                tool_def.long_description = description.strip()
            
            tool_def.requires_token_auth = requires_token_auth
            if examples:
                tool_def.examples = examples

            if requires_token_auth:
                logger.debug(f"Tool '{resolved_name}' requires token authentication")

            self.tools.append(tool_def.to_tool())
            self.tools_map[resolved_name] = tool_def

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
        group: str | None = None,  # 仅 CLI 元数据；MCP 协议不依赖此字段
        mime_type: str | None = None,
    ):
        """
        资源装饰器，支持 URI 模板（使用 parse 库语法）

        示例：
            @router.resource("users://{user_id}/profile", group="db")
            async def get_user_profile(user_id: str) -> str:
                return f"Profile for user {user_id}"

            # 支持类型转换
            @router.resource("posts://{post_id:d}/comments", group="db")
            async def get_post_comments(post_id: int) -> str:
                return f"Comments for post {post_id}"

            # name 支持与 uri 相同的模板参数，共用 template_params
            @router.resource("users://{user_id}/profile", name="user-{user_id}-profile", group="db")
            async def get_user_profile(user_id: str) -> str:
                return f"Profile for user {user_id}"

        参数：
            uri: URI 模板，支持 parse 库的格式语法
                 如 {param}, {param:d}, {param:f} 等
            name: 资源名称，支持与 uri 相同的模板参数语法，共用 template_params。
                  未指定时默认使用 uri
            description: 资源描述（可选）
            group: 分组路径（可选，例如 "db" 或 "db.mysql"）
            mime_type: MIME 类型（默认 text/plain）
        """

        def decorator(func):
            # 分组路径仅用于开发期校验与 CLI 元数据（见 groups 模块）
            CliGroupRegistry.validate_path(group)
            
            resource_def = ResourceDefinition.from_function(
                func,
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
            )
            resource_def.group = group

            # 根据是否为模板分类存储
            if resource_def.is_template:
                self._template_resources.append(resource_def)
                self._template_resources_dirty = True  # 标记需要重新排序
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
        group: str | None = None,  # 仅 CLI 元数据；MCP 协议不依赖此字段
    ):
        """
        Prompt 装饰器，用于定义对话模板

        示例：
            @router.prompt("greeting", group="chat")
            async def greeting_prompt(user_name: str) -> str:
                '''生成问候语'''
                return f"Hello, {user_name}! How can I help you today?"

        参数：
            name: Prompt 名称（可选，默认使用函数名）
            description: Prompt 描述（可选，默认使用函数 docstring）
            group: 分组路径（可选，例如 "chat" 或 "chat.greeting"）
        """

        def decorator(func):
            # 分组路径仅用于开发期校验与 CLI 元数据（见 groups 模块）
            CliGroupRegistry.validate_path(group)
            
            prompt_def = PromptDefinition.from_function(
                func,
                name=name,
                description=description,
            )
            prompt_def.group = group

            # 添加到列表（用于 list_prompts）
            self.prompts.append(prompt_def.to_prompt())

            # 存储 PromptDefinition（用于 get_prompt，保留完整元数据）
            self.prompts_map[prompt_def.name] = prompt_def

            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

        return decorator

    # ==========================
    # 辅助方法
    # ==========================
    @functools.cached_property
    def _resources(self) -> list[Resource]:
        """列出所有静态资源"""
        return [r.to_resource() for r in self._static_resources.values()]

    def _ensure_templates_sorted(self) -> None:
        """确保模板资源列表已按 URI 长度降序排列（惰性排序）"""
        if self._template_resources_dirty:
            self._template_resources.sort(key=lambda r: len(r.uri), reverse=True)
            self._template_resources_dirty = False

    @property
    def _resource_templates(self) -> list[ResourceTemplate]:
        """列出所有资源模板"""
        self._ensure_templates_sorted()
        return [r.to_resource_template() for r in self._template_resources]

    # ==========================
    # mcp 接口
    # ==========================
    def list_resources(self) -> list[Resource]:
        """列出所有资源"""
        return self._resources

    def list_resource_templates(self) -> list[ResourceTemplate]:
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
                return DataSerializer.serialize(result, indent=2)
            except Exception as e:
                logger.error(f"读取静态资源失败: {uri_str}, 错误: {e}", exc_info=True)
                raise ResourceNotFoundError(
                    messages.MSG_RESOURCE_READ_FAILED.format(uri=uri_str, error=str(e))
                ) from e

        # 遍历动态模板 (惰性排序确保按长度降序)
        self._ensure_templates_sorted()
        for resource_def in self._template_resources:
            params = resource_def.match_uri(uri_str)
            if params is not None:
                try:
                    result = await resource_def.fn(**params)
                    if isinstance(result, str):
                        return result
                    return DataSerializer.serialize(result, indent=2)
                except Exception as e:
                    logger.error(
                        f"读取模板资源失败: {uri_str}, 错误: {e}", exc_info=True
                    )
                    raise ResourceNotFoundError(
                        messages.MSG_RESOURCE_READ_FAILED.format(uri=uri_str, error=str(e))
                    ) from e

        # 没有找到匹配的资源
        raise ResourceNotFoundError(messages.MSG_RESOURCE_NOT_FOUND.format(uri=uri_str))

    def list_tools(self) -> list[Tool]:
        return self.tools

    async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """
        调用指定的工具（增加强类型前置拦截）
        """
        if name not in self.tools_map:
            raise ToolNotFoundError(messages.MSG_TOOL_NOT_FOUND.format(name=name))

        tool_def = self.tools_map[name]
        
        # 1. 强类型验证与隐式转换拦截 (Runtime Validation)
        try:
            if tool_def.input_model:
                # Pydantic v2: 实例化模型并执行严格校验
                validated_model = tool_def.input_model.model_validate(args)

                # 校验通过后，将其转回安全的字典（使用 alias 以还原原始参数名）
                safe_args = validated_model.model_dump(by_alias=True)
            else:
                safe_args = args
        except ValidationError:
            # 验证失败，暂时先抛给上层处理
            raise

        # 2. 安全执行底层业务逻辑
        result = await tool_def.fn(**safe_args)
        return result

    def list_prompts(self) -> list[Prompt]:
        """列出所有 Prompts"""
        return self.prompts

    async def get_prompt(
        self, name: str, arguments: dict[str, str] | None = None
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
            raise PromptNotFoundError(messages.MSG_PROMPT_NOT_FOUND.format(name=name))

        prompt_def = self.prompts_map[name]

        try:
            # 调用 prompt 处理函数
            result = await prompt_def.fn(**(arguments or {}))

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
            text = DataSerializer.serialize(result, indent=2)
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
            raise PromptNotFoundError(
                messages.MSG_PROMPT_GET_FAILED.format(error=str(e))
            ) from e
