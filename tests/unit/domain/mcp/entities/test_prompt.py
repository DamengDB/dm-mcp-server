"""MCP Prompt 单元测试

测试 PromptDefinition 的功能，包括从函数生成提示词定义、参数提取等。
"""

import pytest
from typing import Annotated

from dm_mcp.domain.mcp.entities.prompt import PromptDefinition


class TestPromptDefinition:
    """PromptDefinition 测试类"""

    def test_prompt_definition_creation(self):
        """测试提示词定义创建"""

        async def greeting_prompt(user_name: str) -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(greeting_prompt)

        assert prompt_def.name == "greeting_prompt"
        assert prompt_def.short_description == "Generate greeting"
        assert prompt_def.fn == greeting_prompt
        assert prompt_def.arguments is not None
        assert len(prompt_def.arguments) == 1

    def test_prompt_definition_to_prompt(self):
        """测试转换为 MCP Prompt 对象"""

        async def greeting_prompt(user_name: str) -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(greeting_prompt)
        prompt = prompt_def.to_prompt()

        assert prompt.name == "greeting_prompt"
        assert prompt.description == "Generate greeting"
        assert prompt.arguments is not None
        assert len(prompt.arguments) == 1
        assert prompt.arguments[0].name == "user_name"
        assert prompt.arguments[0].required is True

    def test_prompt_with_required_and_optional_params(self):
        """测试包含必需和可选参数的提示词"""

        async def greeting_prompt(user_name: str, language: str = "en") -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(greeting_prompt)

        assert len(prompt_def.arguments) == 2
        # 找到必需参数
        required_arg = next(a for a in prompt_def.arguments if a.name == "user_name")
        optional_arg = next(a for a in prompt_def.arguments if a.name == "language")

        assert required_arg.required is True
        assert optional_arg.required is False

    def test_prompt_custom_name(self):
        """测试自定义提示词名称"""

        async def greeting_prompt(user_name: str) -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(
            greeting_prompt, name="custom_greeting"
        )

        assert prompt_def.name == "custom_greeting"

    def test_prompt_custom_description(self):
        """测试自定义提示词描述"""

        async def greeting_prompt(user_name: str) -> str:
            """Function docstring"""
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(
            greeting_prompt, description="Custom description"
        )

        assert prompt_def.short_description == "Custom description"

    def test_prompt_no_docstring(self):
        """测试没有 docstring 的函数"""

        async def greeting_prompt(user_name: str) -> str:
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(greeting_prompt)

        assert prompt_def.short_description == "未提供描述"

    def test_prompt_no_arguments(self):
        """测试没有参数的提示词"""

        async def simple_prompt() -> str:
            """Simple prompt"""
            return "Hello!"

        prompt_def = PromptDefinition.from_function(simple_prompt)

        assert prompt_def.arguments is None or len(prompt_def.arguments) == 0

    def test_prompt_staticmethod(self):
        """测试静态方法"""

        class TestClass:
            @staticmethod
            async def greeting_prompt(user_name: str) -> str:
                """Generate greeting"""
                return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(TestClass.greeting_prompt)

        assert prompt_def.name == "greeting_prompt"
        assert prompt_def.short_description == "Generate greeting"

    def test_prompt_class_method(self):
        """测试类方法"""

        class TestClass:
            @classmethod
            async def greeting_prompt(cls, user_name: str) -> str:
                """Generate greeting"""
                return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(TestClass.greeting_prompt)

        assert prompt_def.name == "greeting_prompt"
        assert prompt_def.short_description == "Generate greeting"

    def test_prompt_with_annotated_type(self):
        """测试带 Annotated 类型的参数（提取描述）"""

        async def greeting_prompt(
            user_name: Annotated[str, "The name of the user"],
        ) -> str:
            """Generate greeting"""
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(greeting_prompt)

        assert len(prompt_def.arguments) == 1
        arg = prompt_def.arguments[0]
        assert arg.name == "user_name"
        assert arg.description == "The name of the user"

    def test_prompt_multiple_arguments(self):
        """测试多个参数的提示词"""

        async def complex_prompt(
            user_name: str, language: str = "en", formal: bool = False
        ) -> str:
            """Complex greeting prompt"""
            return f"Hello, {user_name}!"

        prompt_def = PromptDefinition.from_function(complex_prompt)

        assert len(prompt_def.arguments) == 3
        names = [arg.name for arg in prompt_def.arguments]
        assert "user_name" in names
        assert "language" in names
        assert "formal" in names

    def test_prompt_with_complex_types(self):
        """测试复杂类型参数"""
        from typing import List

        async def list_prompt(items: List[str]) -> str:
            """List prompt"""
            return ",".join(items)

        prompt_def = PromptDefinition.from_function(list_prompt)

        assert len(prompt_def.arguments) == 1
        assert prompt_def.arguments[0].name == "items"

    def test_prompt_with_optional_type(self):
        """测试 Optional 类型参数"""
        from typing import Optional

        async def optional_prompt(user_name: Optional[str] = None) -> str:
            """Optional prompt"""
            return f"Hello, {user_name or 'Guest'}!"

        prompt_def = PromptDefinition.from_function(optional_prompt)

        assert len(prompt_def.arguments) == 1
        # Optional 且有默认值应该是可选的
        assert prompt_def.arguments[0].required is False

    def test_prompt_var_args(self):
        """测试 *args 参数会被转换"""

        async def varargs_prompt(*args: str) -> str:
            """Varargs prompt"""
            return ",".join(args)

        prompt_def = PromptDefinition.from_function(varargs_prompt)
        # *args 被转换为必需参数 "args"
        assert len(prompt_def.arguments) >= 1
        arg_names = [a.name for a in prompt_def.arguments]
        assert "args" in arg_names

    def test_prompt_kwargs(self):
        """测试 **kwargs 参数会被转换"""

        async def kwargs_prompt(**kwargs: str) -> str:
            """Kwargs prompt"""
            return str(kwargs)

        prompt_def = PromptDefinition.from_function(kwargs_prompt)
        # **kwargs 被转换为必需参数 "kwargs"
        assert len(prompt_def.arguments) >= 1
        arg_names = [a.name for a in prompt_def.arguments]
        assert "kwargs" in arg_names

    def test_prompt_all_optional_params(self):
        """测试全部为可选参数"""

        async def all_optional(user: str = "default", count: int = 10) -> str:
            """All optional"""
            return user

        prompt_def = PromptDefinition.from_function(all_optional)

        for arg in prompt_def.arguments:
            assert arg.required is False

    def test_prompt_with_nested_annotated(self):
        """测试嵌套 Annotated 类型"""
        from typing import Annotated

        async def annotated_prompt(
            x: Annotated[Annotated[int, "inner"], "outer"],
        ) -> str:
            """Annotated prompt"""
            return str(x)

        prompt_def = PromptDefinition.from_function(annotated_prompt)

        assert len(prompt_def.arguments) == 1

    def test_prompt_sync_function(self):
        """测试同步函数"""

        def sync_prompt(name: str) -> str:
            """Sync prompt"""
            return f"Hello, {name}!"

        prompt_def = PromptDefinition.from_function(sync_prompt)

        assert prompt_def.name == "sync_prompt"
        assert prompt_def.fn == sync_prompt

    def test_prompt_instance_method(self):
        """测试实例方法"""

        class PromptClass:
            async def greeting_prompt(self, name: str) -> str:
                """Instance method prompt"""
                return f"Hello, {name}!"

        obj = PromptClass()
        prompt_def = PromptDefinition.from_function(obj.greeting_prompt)

        assert prompt_def.name == "greeting_prompt"
        assert prompt_def.short_description == "Instance method prompt"

    def test_prompt_argument_order(self):
        """测试参数顺序保持"""

        async def ordered_prompt(z: str, a: str, m: str) -> str:
            """Ordered prompt"""
            return f"{z}{a}{m}"

        prompt_def = PromptDefinition.from_function(ordered_prompt)

        names = [arg.name for arg in prompt_def.arguments]
        assert names == ["z", "a", "m"]

    def test_prompt_with_return_annotation(self):
        """测试带返回类型注解"""

        async def typed_prompt(name: str) -> str:
            """Typed prompt"""
            return f"Hello, {name}!"

        prompt_def = PromptDefinition.from_function(typed_prompt)

        # 返回类型不影响 PromptDefinition
        assert prompt_def.fn is not None
