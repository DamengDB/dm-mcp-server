"""MCP Tool 单元测试

测试 ToolDefinition 的功能，包括从函数生成工具定义、Schema 生成等。
"""

import pytest
from typing import Dict, Any
from pydantic import BaseModel

from dm_mcp.domain.mcp.entities.tool import ToolDefinition


class TestToolDefinition:
    """ToolDefinition 测试类"""

    def test_tool_definition_creation(self):
        """测试工具定义创建"""

        def test_function(x: int, y: str = "default") -> str:
            """Test function"""
            return f"{x}:{y}"

        tool_def = ToolDefinition.from_function(test_function)

        assert tool_def.name == "test_function"
        assert tool_def.short_description == "Test function"
        assert tool_def.long_description == "Test function"
        assert tool_def.fn == test_function
        assert tool_def.input_schema is not None
        assert "properties" in tool_def.input_schema

    def test_tool_definition_to_tool(self):
        """测试转换为 MCP Tool 对象"""

        def test_function(x: int) -> str:
            """Test function"""
            return str(x)

        tool_def = ToolDefinition.from_function(test_function)
        tool = tool_def.to_tool()

        assert tool.name == "test_function"
        assert tool.description == "Test function"
        assert tool.inputSchema is not None

    def test_tool_with_required_and_optional_params(self):
        """测试包含必需和可选参数的工具"""

        def test_function(required: int, optional: str = "default") -> str:
            """Test function with optional param"""
            return f"{required}:{optional}"

        tool_def = ToolDefinition.from_function(test_function)

        assert "required" in tool_def.input_schema["properties"]
        assert "optional" in tool_def.input_schema["properties"]
        assert "required" in tool_def.input_schema.get("required", [])

    def test_tool_exclude_args(self):
        """测试排除参数"""

        def test_function(x: int, y: str, z: bool = True) -> str:
            """Test function"""
            return f"{x}:{y}:{z}"

        tool_def = ToolDefinition.from_function(test_function, exclude_args=["y"])

        assert "x" in tool_def.input_schema["properties"]
        assert "y" not in tool_def.input_schema["properties"]
        assert "z" in tool_def.input_schema["properties"]

    def test_tool_exclude_args_not_found(self):
        """测试排除不存在的参数"""

        def test_function(x: int) -> str:
            """Test function"""
            return str(x)

        with pytest.raises(ValueError, match="在签名中未找到"):
            ToolDefinition.from_function(test_function, exclude_args=["nonexistent"])

    def test_tool_with_var_args_not_allowed(self):
        """测试不支持 *args"""

        def test_function(*args):
            """Test function with *args"""
            return str(args)

        with pytest.raises(
            ValueError, match="不支持 \\*args 和 \\*\\*kwargs"
        ):
            ToolDefinition.from_function(test_function)

    def test_tool_with_var_kwargs_not_allowed(self):
        """测试不支持 **kwargs"""

        def test_function(**kwargs):
            """Test function with **kwargs"""
            return str(kwargs)

        with pytest.raises(
            ValueError, match="不支持 \\*args 和 \\*\\*kwargs"
        ):
            ToolDefinition.from_function(test_function)

    def test_tool_output_schema_with_dict(self):
        """测试返回字典类型的输出 Schema"""

        def test_function(x: int) -> Dict[str, Any]:
            """Test function returning dict"""
            return {"result": x}

        tool_def = ToolDefinition.from_function(test_function)

        assert tool_def.output_schema is not None
        assert (
            "properties" in tool_def.output_schema or "type" in tool_def.output_schema
        )

    def test_tool_output_schema_with_pydantic_model(self):
        """测试返回 Pydantic 模型的输出 Schema"""

        class ResultModel(BaseModel):
            value: int
            message: str

        def test_function(x: int) -> ResultModel:
            """Test function returning Pydantic model"""
            return ResultModel(value=x, message="ok")

        tool_def = ToolDefinition.from_function(test_function)

        assert tool_def.output_schema is not None

    def test_tool_output_schema_with_primitive_type(self):
        """测试返回基本类型的输出 Schema（会被包装）"""

        def test_function(x: int) -> int:
            """Test function returning int"""
            return x

        tool_def = ToolDefinition.from_function(test_function)

        # 基本类型会被包装成对象
        assert tool_def.output_schema is not None

    def test_tool_output_schema_wrap_disabled(self):
        """测试禁用输出 Schema 包装"""

        def test_function(x: int) -> int:
            """Test function returning int"""
            return x

        tool_def = ToolDefinition.from_function(
            test_function, wrap_non_object_output_schema=False
        )

        assert tool_def.output_schema is not None

    def test_tool_no_docstring(self):
        """测试没有 docstring 的函数"""

        def test_function(x: int) -> str:
            return str(x)

        tool_def = ToolDefinition.from_function(test_function)

        assert tool_def.short_description == "未提供描述"
        assert tool_def.long_description == ""

    def test_tool_staticmethod(self):
        """测试静态方法"""

        class TestClass:
            @staticmethod
            def test_function(x: int) -> str:
                """Test static method"""
                return str(x)

        tool_def = ToolDefinition.from_function(TestClass.test_function)

        assert tool_def.name == "test_function"
        assert tool_def.short_description == "Test static method"
        assert tool_def.long_description == "Test static method"

    def test_tool_class_method(self):
        """测试类方法"""

        class TestClass:
            @classmethod
            def test_function(cls, x: int) -> str:
                """Test class method"""
                return str(x)

        tool_def = ToolDefinition.from_function(TestClass.test_function)

        assert tool_def.name == "test_function"
        assert tool_def.short_description == "Test class method"
        assert tool_def.long_description == "Test class method"

    def test_tool_instance_method(self):
        """测试实例方法"""

        class TestClass:
            def test_function(self, x: int) -> str:
                """Test instance method"""
                return str(x)

        tool_def = ToolDefinition.from_function(TestClass.test_function)

        assert tool_def.name == "test_function"
        assert tool_def.short_description == "Test instance method"
        assert tool_def.long_description == "Test instance method"
        # 实例方法应该正确解析参数，不包含 self
        assert "x" in tool_def.input_schema["properties"]

    def test_tool_async_function(self):
        """测试异步函数"""

        async def test_async_function(x: int, y: str = "default") -> str:
            """Test async function"""
            return f"{x}:{y}"

        tool_def = ToolDefinition.from_function(test_async_function)

        assert tool_def.name == "test_async_function"
        assert tool_def.short_description == "Test async function"
        assert tool_def.long_description == "Test async function"
        assert tool_def.input_schema is not None

    def test_tool_with_complex_type_hints(self):
        """测试复杂类型注解"""
        from typing import List, Optional

        def test_function(
            items: List[str], optional_int: Optional[int] = None
        ) -> List[int]:
            """Function with complex types"""
            return items

        tool_def = ToolDefinition.from_function(test_function)

        assert "items" in tool_def.input_schema["properties"]
        assert "optional_int" in tool_def.input_schema["properties"]

    def test_tool_with_annotated_description(self):
        """测试带 Annotated 描述的参数"""
        from typing import Annotated

        def test_function(
            x: Annotated[str, "The input value"],
            y: Annotated[int, "The multiplier"] = 10,
        ) -> str:
            """Test function"""
            return x * y

        tool_def = ToolDefinition.from_function(test_function)

        # 应该能正确解析
        assert "x" in tool_def.input_schema["properties"]

    def test_tool_name_override(self):
        """测试自定义名称（通过包装）"""

        def original_function(x: int) -> str:
            """Original function"""
            return str(x)

        # 直接修改属性模拟重命名
        tool_def = ToolDefinition.from_function(original_function)
        tool_def.name = "custom_name"

        assert tool_def.name == "custom_name"
        assert tool_def.to_tool().name == "custom_name"

    def test_tool_input_schema_structure(self):
        """测试输入 Schema 结构完整性"""

        def test_function(name: str, age: int, city: str = "Beijing") -> str:
            """Test function"""
            return f"{name}, {age}, {city}"

        tool_def = ToolDefinition.from_function(test_function)

        schema = tool_def.input_schema
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_tool_required_params_detection(self):
        """测试必需参数检测"""

        def test_function(required: str, optional: int = 0) -> str:
            """Test function"""
            return required

        tool_def = ToolDefinition.from_function(test_function)

        required_list = tool_def.input_schema.get("required", [])
        assert "required" in required_list
        assert "optional" not in required_list

    def test_tool_no_type_annotation(self):
        """测试无类型注解的参数"""

        def test_function(x, y=10):  # type: ignore[no-untyped-def]
            """Test function without type hints"""
            return x

        tool_def = ToolDefinition.from_function(test_function)

        assert "x" in tool_def.input_schema["properties"]
        assert "y" in tool_def.input_schema["properties"]

    def test_tool_mixed_types(self):
        """测试混合类型注解"""
        from typing import Union, Any

        def test_function(x: Union[int, str], y: Any) -> str:
            """Test function"""
            return str(x)

        tool_def = ToolDefinition.from_function(test_function)

        assert "x" in tool_def.input_schema["properties"]
        assert "y" in tool_def.input_schema["properties"]

    def test_tool_callable_object(self):
        """测试可调用对象"""

        class CallableObject:
            def __call__(self, x: int) -> str:
                """Callable object"""
                return str(x)

        obj = CallableObject()
        tool_def = ToolDefinition.from_function(obj)

        # 可调用对象的名称会是 __call__
        assert tool_def.name == "__call__"
        assert tool_def.short_description == "Callable object"
        assert tool_def.long_description == "Callable object"

    def test_tool_validation_disabled(self):
        """测试禁用验证时可以包含 *args/**kwargs"""

        def test_function(*args, **kwargs):
            """Test function with var args"""
            return str(args)

        # 当 validate=False 时应该不验证
        tool_def = ToolDefinition.from_function(test_function, validate=False)

        assert tool_def.name == "test_function"
        assert "args" in tool_def.input_schema["properties"]

    def test_tool_output_schema_with_list(self):
        """测试返回列表类型的输出 Schema"""
        from typing import List

        def test_function(x: int) -> List[str]:
            """Test function returning list"""
            return ["a", "b"]

        tool_def = ToolDefinition.from_function(test_function)

        assert tool_def.output_schema is not None

    def test_tool_output_schema_with_tuple(self):
        """测试返回元组类型的输出 Schema"""
        from typing import Tuple

        def test_function(x: int) -> Tuple[int, str]:
            """Test function returning tuple"""
            return (x, "test")

        tool_def = ToolDefinition.from_function(test_function)

        assert tool_def.output_schema is not None
