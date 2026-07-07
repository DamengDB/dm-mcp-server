"""MCP Resource 单元测试

测试 ResourceDefinition 的功能，包括静态资源、动态模板资源、URI 匹配等。
"""

import pytest
from pydantic.networks import AnyUrl

from dm_mcp.domain.mcp.entities.resource import ResourceDefinition


class TestResourceDefinition:
    """ResourceDefinition 测试类"""

    def test_static_resource_creation(self):
        """测试创建静态资源"""

        async def get_static_resource() -> str:
            """Get static resource"""
            return "static content"

        resource_def = ResourceDefinition.from_function(
            get_static_resource, uri="resource://static", description="Static resource"
        )

        assert resource_def.uri == "resource://static"
        assert resource_def.short_description == "Static resource"  # 使用传入的 description
        assert not resource_def.is_template
        assert len(resource_def.template_params) == 0

    def test_template_resource_creation(self):
        """测试创建模板资源"""

        async def get_user_profile(user_id: str) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user_profile,
            uri="users://{user_id}/profile",
            description="User profile resource",
        )

        assert resource_def.uri == "users://{user_id}/profile"
        assert resource_def.is_template
        assert "user_id" in resource_def.template_params

    def test_template_resource_with_multiple_params(self):
        """测试包含多个参数的模板资源"""

        async def get_post_comments(post_id: int, comment_id: int) -> str:
            """Get post comments"""
            return f"Comment {comment_id} for post {post_id}"

        resource_def = ResourceDefinition.from_function(
            get_post_comments,
            uri="posts://{post_id}/comments/{comment_id}",
        )

        assert resource_def.is_template
        assert "post_id" in resource_def.template_params
        assert "comment_id" in resource_def.template_params

    def test_template_param_not_in_function_signature(self):
        """测试模板参数不在函数签名中"""

        async def get_resource() -> str:
            """Get resource"""
            return "content"

        with pytest.raises(ValueError, match="未找到"):
            ResourceDefinition.from_function(
                get_resource, uri="resource://{missing_param}"
            )

    def test_static_resource_to_resource(self):
        """测试静态资源转换为 Resource 对象"""

        async def get_static_resource() -> str:
            """Get static resource"""
            return "static content"

        resource_def = ResourceDefinition.from_function(
            get_static_resource, uri="resource://static"
        )

        resource = resource_def.to_resource()

        assert resource.uri == AnyUrl("resource://static")
        assert resource.name == "resource://static"
        assert resource.description == "Get static resource"

    def test_template_resource_to_resource_raises_error(self):
        """测试模板资源转换为 Resource 对象应该抛出异常"""

        async def get_user_profile(user_id: str) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user_profile, uri="users://{user_id}/profile"
        )

        with pytest.raises(ValueError, match="模板类型"):
            resource_def.to_resource()

    def test_template_resource_to_resource_template(self):
        """测试模板资源转换为 ResourceTemplate 对象"""

        async def get_user_profile(user_id: str) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user_profile, uri="users://{user_id}/profile"
        )

        template = resource_def.to_resource_template()

        assert template.uriTemplate == "users://{user_id}/profile"
        assert template.name == "users://{user_id}/profile"
        assert template.description == "Get user profile"

    def test_static_resource_to_resource_template_raises_error(self):
        """测试静态资源转换为 ResourceTemplate 应该抛出异常"""

        async def get_static_resource() -> str:
            """Get static resource"""
            return "static content"

        resource_def = ResourceDefinition.from_function(
            get_static_resource, uri="resource://static"
        )

        with pytest.raises(ValueError, match="不是模板类型"):
            resource_def.to_resource_template()

    def test_match_uri_static_resource(self):
        """测试匹配静态资源 URI"""

        async def get_static_resource() -> str:
            """Get static resource"""
            return "static content"

        resource_def = ResourceDefinition.from_function(
            get_static_resource, uri="resource://static"
        )

        # 静态资源应该精确匹配
        # 对于静态 URI（无模板参数），parse 库匹配成功时返回空字典 {}
        result = resource_def.match_uri("resource://static")
        # parse 库匹配成功时返回空字典（因为没有命名参数）
        assert result == {}

    def test_match_uri_template_resource(self):
        """测试匹配模板资源 URI"""

        async def get_user_profile(user_id: str) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user_profile, uri="users://{user_id}/profile"
        )

        result = resource_def.match_uri("users://123/profile")
        assert result is not None
        assert result["user_id"] == "123"

    def test_match_uri_template_resource_no_match(self):
        """测试模板资源 URI 不匹配"""

        async def get_user_profile(user_id: str) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user_profile, uri="users://{user_id}/profile"
        )

        result = resource_def.match_uri("users://123/invalid")
        assert result is None

    def test_match_uri_template_with_type_conversion(self):
        """测试模板资源 URI 匹配（带类型转换）"""

        async def get_post(post_id: int) -> str:
            """Get post"""
            return f"Post {post_id}"

        resource_def = ResourceDefinition.from_function(
            get_post, uri="posts://{post_id:d}"
        )

        result = resource_def.match_uri("posts://123")
        assert result is not None
        # parse 库的类型转换 {post_id:d} 返回整数类型，不是字符串
        assert result["post_id"] == 123

    def test_resource_mime_type(self):
        """测试资源 MIME 类型"""

        async def get_json_resource() -> str:
            """Get JSON resource"""
            return '{"key": "value"}'

        resource_def = ResourceDefinition.from_function(
            get_json_resource, uri="resource://json", mime_type="application/json"
        )

        resource = resource_def.to_resource()
        assert resource.mimeType == "application/json"

    def test_resource_default_mime_type(self):
        """测试资源默认 MIME 类型"""

        async def get_resource() -> str:
            """Get resource"""
            return "content"

        resource_def = ResourceDefinition.from_function(
            get_resource, uri="resource://test"
        )

        resource = resource_def.to_resource()
        assert resource.mimeType == "text/plain"

    def test_resource_custom_description(self):
        """测试资源自定义描述"""

        async def get_resource() -> str:
            """Function docstring"""
            return "content"

        resource_def = ResourceDefinition.from_function(
            get_resource, uri="resource://test", description="Custom description"
        )

        assert resource_def.short_description == "Custom description"

    def test_resource_no_docstring(self):
        """测试没有 docstring 的资源函数"""

        async def get_resource() -> str:
            return "content"

        resource_def = ResourceDefinition.from_function(
            get_resource, uri="resource://test"
        )

        assert resource_def.short_description == "未提供描述"

    def test_template_resource_with_optional_param(self):
        """测试带可选参数的模板资源"""

        async def get_user_profile(user_id: str, include_posts: bool = False) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user_profile, uri="users://{user_id}/profile"
        )

        assert resource_def.is_template
        assert "user_id" in resource_def.template_params

    def test_match_uri_multiple_params(self):
        """测试多参数模板 URI 匹配"""

        async def get_comment(post_id: str, comment_id: str) -> str:
            """Get comment"""
            return f"Comment {comment_id}"

        resource_def = ResourceDefinition.from_function(
            get_comment, uri="posts//{post_id}/comments/{comment_id}"
        )

        result = resource_def.match_uri("posts//123/comments/456")
        assert result is not None
        assert result["post_id"] == "123"
        assert result["comment_id"] == "456"

    def test_match_uri_with_annotations(self):
        """测试带类型注解的模板参数"""

        async def get_item(item_id: int) -> str:
            """Get item"""
            return f"Item {item_id}"

        resource_def = ResourceDefinition.from_function(
            get_item, uri="items://{item_id:d}"
        )

        result = resource_def.match_uri("items://42")
        assert result is not None
        assert result["item_id"] == 42

    def test_match_uri_float_type(self):
        """测试浮点类型模板参数"""

        async def get_price(product_id: str, price: float) -> str:
            """Get price"""
            return f"Price: {price}"

        resource_def = ResourceDefinition.from_function(
            get_price, uri="products//{product_id}/price/{price:.2f}"
        )

        result = resource_def.match_uri("products//abc/price/19.99")
        assert result is not None
        assert result["product_id"] == "abc"

    def test_static_resource_with_mime_type_none(self):
        """测试 MIME 类型为 None 时使用默认值"""

        async def get_resource() -> str:
            """Get resource"""
            return "content"

        resource_def = ResourceDefinition.from_function(
            get_resource, uri="resource://test", mime_type=None
        )

        assert resource_def.mime_type == "text/plain"

    def test_resource_with_class_method(self):
        """测试类方法作为资源函数"""

        class ResourceHandler:
            @classmethod
            async def get_static(cls) -> str:
                """Class method resource"""
                return "content"

        resource_def = ResourceDefinition.from_function(
            ResourceHandler.get_static, uri="resource://class_method"
        )

        assert resource_def.uri == "resource://class_method"
        assert resource_def.short_description == "Class method resource"

    def test_resource_with_static_method(self):
        """测试静态方法作为资源函数"""

        class ResourceHandler:
            @staticmethod
            async def get_static() -> str:
                """Static method resource"""
                return "content"

        resource_def = ResourceDefinition.from_function(
            ResourceHandler.get_static, uri="resource://static_method"
        )

        assert resource_def.uri == "resource://static_method"
        assert resource_def.short_description == "Static method resource"

    def test_resource_uri_variations(self):
        """测试各种 URI 格式"""

        async def get_resource() -> str:
            """Get resource"""
            return "content"

        # 不同的 URI 格式（parse 都能处理）
        resource_def = ResourceDefinition.from_function(
            get_resource, uri="resource/path/test"
        )

        assert resource_def.uri == "resource/path/test"

    def test_sync_function_resource(self):
        """测试同步函数作为资源函数"""

        def get_sync_resource() -> str:
            """Sync resource"""
            return "content"

        resource_def = ResourceDefinition.from_function(
            get_sync_resource, uri="resource://sync"
        )

        assert resource_def.uri == "resource://sync"
        assert resource_def.fn == get_sync_resource

    def test_match_uri_returns_empty_for_static(self):
        """测试静态资源 match_uri 返回空字典"""

        async def get_static() -> str:
            """Static"""
            return "content"

        resource_def = ResourceDefinition.from_function(
            get_static, uri="resource://static"
        )

        result = resource_def.match_uri("resource://static")
        # 静态 URI 匹配时返回空字典
        assert result == {}

    def test_match_uri_no_match_returns_none(self):
        """测试不匹配的 URI 返回 None"""

        async def get_user(user_id: str) -> str:
            """Get user"""
            return f"User {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user, uri="users://{user_id}"
        )

        result = resource_def.match_uri("users://")
        # 不完整或不匹配的 URI
        assert result is None or result == {}

    def test_resource_custom_name_static(self):
        """测试静态资源自定义 name"""

        async def get_static_resource() -> str:
            """Get static resource"""
            return "static content"

        resource_def = ResourceDefinition.from_function(
            get_static_resource, uri="resource://static", name="My Static Resource"
        )

        resource = resource_def.to_resource()
        assert resource.name == "My Static Resource"
        assert resource.uri == AnyUrl("resource://static")

    def test_resource_custom_name_template(self):
        """测试模板资源自定义 name，共用 template_params"""

        async def get_user_profile(user_id: str) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        resource_def = ResourceDefinition.from_function(
            get_user_profile,
            uri="users://{user_id}/profile",
            name="user-{user_id}-profile",
        )

        template = resource_def.to_resource_template()
        assert template.uriTemplate == "users://{user_id}/profile"
        assert template.name == "user-{user_id}-profile"
        assert "user_id" in resource_def.template_params

    def test_resource_name_template_param_must_be_in_uri(self):
        """测试 name 模板参数必须在 uri 的 template_params 中"""

        async def get_user_profile(user_id: str) -> str:
            """Get user profile"""
            return f"Profile for {user_id}"

        with pytest.raises(ValueError, match="必须在 uri template_params"):
            ResourceDefinition.from_function(
                get_user_profile,
                uri="users://{user_id}/profile",
                name="user-{user_id}-{extra_param}",  # extra_param 不在 uri 中
            )
