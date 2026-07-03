"""MCP工具定义模块

提供工具定义的数据结构和从Python函数自动生成MCP工具元数据的功能。
"""

import inspect
import logging
import typing
from dataclasses import dataclass
from typing import Any, Callable, Dict, get_type_hints

from mcp import Tool
from pydantic import TypeAdapter, create_model

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """MCP工具定义

    封装工具的所有元数据信息，包括函数引用、名称、描述、输入输出Schema等。
    """

    fn: Callable[..., Any]
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    requires_token_auth: bool = False

    def to_tool(self) -> Tool:
        """转换为MCP Tool对象

        Returns:
            Tool: MCP协议定义的Tool对象
        """
        return Tool(
            name=self.name,
            description=self.description,
            inputSchema=self.input_schema,
            outputSchema=self.output_schema,
        )

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        exclude_args: list[str] | None = None,
        validate: bool = True,
        wrap_non_object_output_schema: bool = True,
    ) -> "ToolDefinition":
        """
        解析函数并生成符合 MCP/JSON Schema 标准的元数据。
        """
        exclude_args = list(set(exclude_args or []))

        # 1. 基础信息提取
        # 处理类实例或 staticmethod
        if not inspect.isroutine(fn) and hasattr(fn, "__call__"):
            fn = fn.__call__
        if isinstance(fn, staticmethod):
            fn = fn.__func__

        fn_name = getattr(fn, "__name__", None) or fn.__class__.__name__
        fn_doc = inspect.getdoc(fn)

        # 2. 签名验证与解析
        sig = inspect.signature(fn)
        type_hints = get_type_hints(fn, include_extras=True)

        if validate:
            for param in sig.parameters.values():
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    raise ValueError(
                        f"Function {fn_name}: *args and **kwargs are not supported."
                    )

            for arg in exclude_args:
                if arg not in sig.parameters:
                    raise ValueError(
                        f"Function {fn_name}: Excluded arg '{arg}' not found in signature."
                    )

        # 3. 构建输入 Schema (Input Schema)
        # 我们通过动态创建一个 Pydantic Model 来生成 Schema，这样最健壮
        input_fields: Dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name in exclude_args:
                continue

            # 获取类型注解，默认为 Any
            annotation = type_hints.get(param_name, Any)

            # 处理默认值
            if param.default == inspect.Parameter.empty:
                # 必填参数
                default = ...
            else:
                default = param.default

            input_fields[param_name] = (annotation, default)

        # 动态创建 Pydantic 模型
        DynamicInputModel = create_model(f"{fn_name}_Input", **input_fields)  # type: ignore

        # 生成并清理 Schema
        input_schema = DynamicInputModel.model_json_schema()
        # 移除 title 和 definitions (简化处理，可选)
        if "title" in input_schema:
            del input_schema["title"]

        # 4. 构建输出 Schema (Output Schema)
        output_schema = None
        return_annotation = type_hints.get("return", sig.return_annotation)

        if return_annotation not in (inspect.Signature.empty, None, type(None)):
            try:
                # 检查返回值是否是 Pydantic Model 或 字典
                is_complex_object = False
                try:
                    # 简单判断：如果是 dict 或 pydantic model，则视为对象
                    origin = typing.get_origin(return_annotation)
                    if (
                        (
                            isinstance(return_annotation, type)
                            and issubclass(return_annotation, dict)
                        )
                        or (origin is dict)
                        or (hasattr(return_annotation, "model_json_schema"))
                    ):
                        is_complex_object = True
                except Exception:
                    pass

                # 生成基础 Schema
                adapter = TypeAdapter(return_annotation)
                base_output_schema = adapter.json_schema()

                # 核心逻辑：如果返回值不是对象（例如返回 int 或 str），为了符合某些 Tool Schema 标准，
                # 我们通常需要将其包装成一个对象，例如 {"value": int}
                if wrap_non_object_output_schema and not is_complex_object:
                    # 动态创建一个包装模型
                    WrappedOutput = create_model(
                        f"{fn_name}_Output", result=(return_annotation, ...)
                    )
                    output_schema = WrappedOutput.model_json_schema()
                else:
                    output_schema = base_output_schema

                if output_schema and "title" in output_schema:
                    del output_schema["title"]

            except Exception:
                # 如果无法序列化返回值（比如是 Image 对象等），则忽略 Output Schema
                output_schema = None

        return cls(
            fn=fn,
            name=str(fn_name),
            description=fn_doc or "",
            input_schema=input_schema,
            output_schema=output_schema,
        )
