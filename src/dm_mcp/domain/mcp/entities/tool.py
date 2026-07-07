"""MCP工具定义模块

提供工具定义的数据结构和从Python函数自动生成MCP工具元数据的功能。
"""

import inspect
import logging
import typing
from dataclasses import dataclass, field
from typing import Any, Callable, Type, get_type_hints

from mcp import Tool
from pydantic import TypeAdapter, create_model, Field, BaseModel
from pydantic.fields import FieldInfo
from docstring_parser import parse as parse_docstring

from dm_mcp.common import messages
from dm_mcp.common.utils.docstring import resolve_function, split_description

logger = logging.getLogger(__name__)


def _extract_field_info(annotation: Any) -> tuple[Any, FieldInfo | None]:
    """从 Annotated 类型中提取实际类型和 FieldInfo。

    Args:
        annotation: 类型注解，可能是 Annotated[T, FieldInfo, ...] 或普通类型

    Returns:
        (实际类型, FieldInfo 或 None)
    """
    origin = typing.get_origin(annotation)
    if origin is not typing.Annotated:
        return annotation, None

    args = typing.get_args(annotation)
    for meta in args[1:]:
        if isinstance(meta, FieldInfo):
            return args[0], meta

    return args[0], None


@dataclass
class ToolDefinition:
    """MCP工具定义

    封装工具的所有元数据信息，包括函数引用、名称、双粒度描述、输入输出Schema等。
    """

    fn: Callable[..., Any]
    name: str
    short_description: str  # 短描述，首行
    long_description: str   # 长描述，完整内容
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    requires_token_auth: bool = False
    input_model: Type[BaseModel] | None = field(default=None, repr=False)  # 动态 Pydantic 输入模型
    examples: list[str] = field(default_factory=list)  # 工具级别的 CLI 调用示例
    # 仅 CLI 侧使用的逻辑分组（如 db.mysql）；不出现在 MCP list_tools 的 Tool 载荷中
    group: str | None = None

    def to_tool(self) -> Tool:
        """转换为MCP Tool对象

        Returns:
            Tool: MCP协议定义的Tool对象
        """
        # 为了兼容原生 MCP 协议，使用长描述（如果没有则用短描述）
        full_description = self.long_description or self.short_description
        return Tool(
            name=self.name,
            description=full_description,
            inputSchema=self.input_schema,
            outputSchema=self.output_schema,
        )

    def apply_metadata_override(
        self,
        short_description: str | None = None,
        long_description: str | None = None,
        group: str | None = None,
    ) -> "ToolDefinition":
        """应用元数据覆盖，返回新的 ToolDefinition 实例

        Args:
            short_description: 覆盖的短描述
            long_description: 覆盖的长描述
            group: 覆盖的分组

        Returns:
            ToolDefinition: 应用元数据覆盖后的新实例
        """
        return ToolDefinition(
            fn=self.fn,
            name=self.name,
            short_description=short_description or self.short_description,
            long_description=long_description or self.long_description,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            requires_token_auth=self.requires_token_auth,
            input_model=self.input_model,
            examples=self.examples.copy(),
            group=group if group is not None else self.group,
        )

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式

        Returns:
            dict[str, Any]: 包含工具元数据的字典
        """
        return {
            "name": self.name,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "requires_token_auth": self.requires_token_auth,
            "examples": self.examples,
            "group": self.group,
        }

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
        fn = resolve_function(fn)

        fn_name = getattr(fn, "__name__", None) or fn.__class__.__name__
        raw_doc = inspect.getdoc(fn) or ""

        # 2. 结构化解析 Docstring
        parsed_doc = parse_docstring(raw_doc)

        # 提取描述：首行作为 short，完整作为 long
        short_desc, long_desc = split_description(raw_doc)

        # 构建 参数名 -> 参数描述 的字典
        param_descriptions = {
            param.arg_name: param.description 
            for param in parsed_doc.params 
            if param.description
        }

        # 3. 签名验证与解析
        sig = inspect.signature(fn)
        type_hints = get_type_hints(fn, include_extras=True)

        if validate:
            for param in sig.parameters.values():
                if param.kind in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ):
                    raise ValueError(
                        messages.MSG_FN_ARGS_KWARGS_NOT_SUPPORTED.format(fn_name=fn_name)
                    )

            for arg in exclude_args:
                if arg not in sig.parameters:
                    raise ValueError(
                        messages.MSG_FN_EXCLUDED_ARG_NOT_FOUND.format(fn_name=fn_name, arg=arg)
                    )

        # 4. 构建输入 Schema (Input Schema)
        input_fields: dict[str, Any] = {}

        for param_name, param in sig.parameters.items():
            if param_name in exclude_args:
                continue

            # 获取类型注解，默认为 Any
            annotation = type_hints.get(param_name, Any)

            # 提取 Annotated 类型中的 FieldInfo
            _, field_info = _extract_field_info(annotation)

            # 获取参数描述：Annotated FieldInfo.description 优先级 > docstring
            param_desc = ""
            if field_info is not None and field_info.description:
                param_desc = field_info.description
            else:
                param_desc = param_descriptions.get(param_name, "")

            # 处理与 BaseModel 属性/方法冲突的字段名（如 schema、copy 等）
            field_name = param_name
            needs_alias = hasattr(BaseModel, param_name)
            if needs_alias:
                field_name = f"field_{param_name}"

            # 构建显式 Field 参数：只覆盖 Annotated 中不存在的属性
            field_kwargs: dict[str, Any] = {}
            if param_desc and (field_info is None or not field_info.description):
                field_kwargs["description"] = param_desc
            if needs_alias and (field_info is None or not field_info.alias):
                field_kwargs["alias"] = param_name

            # 处理默认值
            if param.default == inspect.Parameter.empty:
                field_val = Field(..., **field_kwargs) if field_kwargs else ...
            else:
                field_kwargs["default"] = param.default
                field_val = Field(**field_kwargs)

            input_fields[field_name] = (annotation, field_val)

        # 动态创建 Pydantic 模型
        DynamicInputModel = create_model(
            f"{fn_name}_Input",
            __config__={"populate_by_name": True},
            **input_fields,
        )  # type: ignore

        # 生成并清理 Schema
        input_schema = DynamicInputModel.model_json_schema()
        if "title" in input_schema:
            del input_schema["title"]

        # 5. 构建输出 Schema (Output Schema)
        output_schema = None
        return_annotation = type_hints.get("return", sig.return_annotation)

        if return_annotation not in (inspect.Signature.empty, None, type(None)):
            try:
                # 检查返回值是否是 Pydantic Model、字典或列表
                # 列表（如 list[Model]）本身就是合法的 JSON Schema 对象，不需要包装
                is_complex_object = False
                try:
                    origin = typing.get_origin(return_annotation)
                    if (
                        (
                            isinstance(return_annotation, type)
                            and issubclass(return_annotation, dict)
                        )
                        or (origin is dict)
                        or (origin is list)
                        or (hasattr(return_annotation, "model_json_schema"))
                    ):
                        is_complex_object = True
                except Exception:
                    pass

                # 生成基础 Schema
                adapter = TypeAdapter(return_annotation)
                base_output_schema = adapter.json_schema()

                # 核心逻辑：如果返回值不是对象，包装成对象
                if wrap_non_object_output_schema and not is_complex_object:
                    WrappedOutput = create_model(
                        f"{fn_name}_Output", result=(return_annotation, ...)
                    )
                    output_schema = WrappedOutput.model_json_schema()
                else:
                    output_schema = base_output_schema

                if output_schema and "title" in output_schema:
                    del output_schema["title"]

            except Exception:
                output_schema = None

        return cls(
            fn=fn,
            name=str(fn_name),
            short_description=short_desc,
            long_description=long_desc,
            input_schema=input_schema,
            output_schema=output_schema,
            input_model=DynamicInputModel,
            group=None,
        )
