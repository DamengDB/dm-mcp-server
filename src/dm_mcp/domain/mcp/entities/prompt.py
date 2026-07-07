"""MCP提示词定义模块

提供提示词定义的数据结构和从Python函数自动生成MCP提示词元数据的功能。
"""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, get_type_hints

from mcp.types import Prompt, PromptArgument

from dm_mcp.common.utils.docstring import resolve_function, split_description

logger = logging.getLogger(__name__)


@dataclass
class PromptDefinition:
    """提示词定义

    封装提示词的所有元数据信息，包括函数引用、名称、描述、参数列表等。
    支持参数化的对话模板，函数参数会自动转换为PromptArgument。
    """

    fn: Callable[..., Any]
    name: str
    short_description: str
    long_description: str
    arguments: list[PromptArgument] | None
    group: str | None = None

    def to_prompt(self) -> Prompt:
        """转换为MCP Prompt对象

        Returns:
            Prompt: MCP协议定义的Prompt对象
        """
        # 使用 long_description（如果没有则用 short_description）
        full_description = self.long_description or self.short_description
        return Prompt(
            name=self.name,
            description=full_description,
            arguments=self.arguments,
        )

    def apply_metadata_override(
        self,
        short_description: str | None = None,
        long_description: str | None = None,
        group: str | None = None,
    ) -> "PromptDefinition":
        """应用元数据覆盖，返回新的 PromptDefinition 实例

        Args:
            short_description: 覆盖的短描述
            long_description: 覆盖的长描述
            group: 覆盖的分组

        Returns:
            PromptDefinition: 应用元数据覆盖后的新实例
        """
        return PromptDefinition(
            fn=self.fn,
            name=self.name,
            short_description=short_description or self.short_description,
            long_description=long_description or self.long_description,
            arguments=self.arguments.copy() if self.arguments else None,
            group=group if group is not None else self.group,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式

        Returns:
            dict[str, Any]: 包含提示词元数据的字典
        """
        return {
            "name": self.name,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "arguments": [
                {
                    "name": arg.name,
                    "description": arg.description,
                    "required": arg.required,
                }
                for arg in self.arguments
            ] if self.arguments else None,
            "group": self.group,
        }

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        name: str | None = None,
        description: str | None = None,
    ) -> "PromptDefinition":
        """从函数创建Prompt定义

        函数参数会自动转换为PromptArgument。支持从类型注解和docstring中提取参数描述。

        Args:
            fn: 处理提示词的函数
            name: 提示词名称（可选，默认使用函数名）
            description: 提示词描述（可选，默认使用函数的docstring）

        Returns:
            PromptDefinition: 创建的提示词定义对象
        """
        # 获取函数信息
        fn = resolve_function(fn)

        fn_name = name or getattr(fn, "__name__", None) or fn.__class__.__name__
        raw_doc = description or inspect.getdoc(fn) or ""

        # 提取描述：首行作为 short，完整作为 long（类似 ToolDefinition）
        short_desc, long_desc = split_description(raw_doc)

        # 解析函数签名，生成 PromptArgument 列表
        sig = inspect.signature(fn)
        type_hints = get_type_hints(fn, include_extras=True)

        arguments: list[PromptArgument] = []
        for param_name, param in sig.parameters.items():
            # 检查是否必需
            required = param.default == inspect.Parameter.empty

            # 尝试从类型注解或 docstring 中提取描述
            param_description = None
            annotation = type_hints.get(param_name)
            if annotation and hasattr(annotation, "__metadata__"):
                # 支持 Annotated[str, "description"] 语法
                for metadata in annotation.__metadata__:
                    if isinstance(metadata, str):
                        param_description = metadata
                        break

            arguments.append(
                PromptArgument(
                    name=param_name,
                    description=param_description,
                    required=required,
                )
            )

        return cls(
            fn=fn,
            name=str(fn_name),
            short_description=short_desc,
            long_description=long_desc,
            arguments=arguments if arguments else None,
            group=None,
        )
