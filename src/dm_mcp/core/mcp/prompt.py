"""MCP提示词定义模块

提供提示词定义的数据结构和从Python函数自动生成MCP提示词元数据的功能。
"""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, List, get_type_hints

from mcp.types import Prompt, PromptArgument

logger = logging.getLogger(__name__)


@dataclass
class PromptDefinition:
    """提示词定义

    封装提示词的所有元数据信息，包括函数引用、名称、描述、参数列表等。
    支持参数化的对话模板，函数参数会自动转换为PromptArgument。
    """

    fn: Callable[..., Any]
    name: str
    description: str | None
    arguments: List[PromptArgument] | None

    def to_prompt(self) -> Prompt:
        """转换为MCP Prompt对象

        Returns:
            Prompt: MCP协议定义的Prompt对象
        """
        return Prompt(
            name=self.name,
            description=self.description,
            arguments=self.arguments,
        )

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
        if not inspect.isroutine(fn) and hasattr(fn, "__call__"):
            fn = fn.__call__
        if isinstance(fn, staticmethod):
            fn = fn.__func__

        fn_name = name or getattr(fn, "__name__", None) or fn.__class__.__name__
        fn_doc = description or inspect.getdoc(fn) or ""

        # 解析函数签名，生成 PromptArgument 列表
        sig = inspect.signature(fn)
        type_hints = get_type_hints(fn, include_extras=True)

        arguments: List[PromptArgument] = []
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
            description=fn_doc,
            arguments=arguments if arguments else None,
        )
