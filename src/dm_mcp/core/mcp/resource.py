"""MCP资源定义模块

提供资源定义的数据结构和从Python函数自动生成MCP资源元数据的功能。
支持静态资源和动态URI模板资源。
"""

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from mcp import Resource
from mcp.types import Resource, ResourceTemplate
from pydantic.networks import AnyUrl

logger = logging.getLogger(__name__)


@dataclass
class ResourceDefinition:
    """资源定义

    封装资源的所有元数据信息，包括函数引用、URI、描述、MIME类型等。
    支持URI模板语法，可以从URI中提取参数并传递给处理函数。
    name 支持与 uri 相同的模板参数语法，共用 template_params。
    """

    fn: Callable[..., Any]
    uri: str
    name: str
    description: str
    mime_type: str | None

    # 从 URI 模板中提取的参数名列表（name 模板共用）
    template_params: List[str]

    # 预编译的 parse 模板，用于高效匹配
    _parser: Any = None

    def __post_init__(self):
        """初始化时预编译parse模板"""
        if self._parser is None:
            from parse import compile as parse_compile

            self._parser = parse_compile(self.uri)

    @property
    def is_template(self) -> bool:
        """判断是否为动态模板（含有参数）

        Returns:
            bool: 如果URI包含模板参数则返回True
        """
        return len(self.template_params) > 0

    def to_resource(self) -> Resource:
        """转换为静态Resource对象

        Returns:
            Resource: MCP协议定义的静态Resource对象

        Raises:
            ValueError: 如果资源是模板类型则抛出异常
        """
        if self.is_template:
            raise ValueError(
                f"Resource {self.uri} is a template, cannot convert to static Resource."
            )

        return Resource(
            uri=AnyUrl(self.uri),  # 静态 URI 不含 {}，AnyUrl 不会报错
            name=self.name,
            description=self.description,
            mimeType=self.mime_type,
        )

    def to_resource_template(self) -> ResourceTemplate:
        """转换为ResourceTemplate对象

        Returns:
            ResourceTemplate: MCP协议定义的ResourceTemplate对象，用于list_resource_templates

        Raises:
            ValueError: 如果资源不是模板类型则抛出异常
        """
        if not self.is_template:
            raise ValueError(
                f"Resource {self.uri} is not a template, cannot convert to ResourceTemplate."
            )

        return ResourceTemplate(
            uriTemplate=self.uri,  # 这里是字符串类型，允许包含 {}
            name=self.name,
            description=self.description,
            mimeType=self.mime_type,
        )

    def match_uri(self, uri: str) -> Dict[str, str] | None:
        """检查URI是否匹配模板，如果匹配则返回提取的参数

        Args:
            uri: 要匹配的URI字符串

        Returns:
            Dict[str, str] | None: 如果匹配则返回参数字典，否则返回None

        示例:
            模板: "users://profile/{user_id}"
            URI:  "users://profile/123"
            返回: {"user_id": "123"}
        """
        result = self._parser.parse(uri)
        if result:
            return result.named
        return None

    @classmethod
    def from_function(
        cls,
        fn: Callable[..., Any],
        uri: str,
        name: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
    ) -> "ResourceDefinition":
        """从函数创建资源定义

        使用parse库的内部机制提取模板中的参数名，并验证函数签名。
        name 支持与 uri 相同的模板参数语法，共用 template_params。

        Args:
            fn: 处理资源的函数
            uri: 资源URI，支持模板语法（如 "users://{user_id}/profile"）
            name: 资源名称，支持模板语法（如 "user-{user_id}-profile"），
                  与 uri 共用 template_params，默认使用 uri
            description: 资源描述（可选，默认使用函数的docstring）
            mime_type: MIME类型（可选，默认为"text/plain"）

        Returns:
            ResourceDefinition: 创建的资源定义对象

        Raises:
            ValueError: 如果模板参数不在函数签名中则抛出异常
        """
        import re

        # 使用 parse 库编译模板，然后从编译结果中提取参数名
        from parse import compile as parse_compile

        parser = parse_compile(uri)
        template_params = (
            list(parser._named_fields) if hasattr(parser, "_named_fields") else []
        )

        # 如果 parse 库版本不支持 _named_fields，使用正则作为后备方案
        if not template_params:
            template_params = re.findall(r"\{(\w+)(?::[^}]+)?\}", uri)

        # name 默认使用 uri
        resolved_name = name if name is not None else uri

        # 若 name 包含模板参数，验证其参数必须在 template_params 中
        if "{" in resolved_name:
            name_params = re.findall(r"\{(\w+)(?::[^}]+)?\}", resolved_name)
            for param in name_params:
                if param not in template_params:
                    raise ValueError(
                        f"Resource {uri}: Name template parameter '{param}' "
                        f"must be in uri template_params {template_params}"
                    )

        # 获取函数信息
        if not inspect.isroutine(fn) and hasattr(fn, "__call__"):
            fn = fn.__call__
        if isinstance(fn, staticmethod):
            fn = fn.__func__

        fn_name = getattr(fn, "__name__", None) or fn.__class__.__name__
        fn_doc = description or inspect.getdoc(fn) or ""

        # 验证函数参数
        sig = inspect.signature(fn)
        func_params = list(sig.parameters.keys())

        # 检查模板参数是否都在函数参数中
        for param in template_params:
            if param not in func_params:
                raise ValueError(
                    f"Resource {uri}: Template parameter '{param}' "
                    f"not found in function signature of {fn_name}"
                )

        resource_def = cls(
            fn=fn,
            uri=uri,
            name=resolved_name,
            description=fn_doc,
            mime_type=mime_type or "text/plain",
            template_params=template_params,
        )

        # 预编译 parser
        resource_def._parser = parser

        return resource_def
