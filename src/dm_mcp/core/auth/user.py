"""用户模型模块

提供基于Starlette的MCP用户模型实现。
"""

import uuid

from starlette.authentication import BaseUser

from .auth_context import AuthContext


class MCPUser(BaseUser):
    """MCP用户模型

    基于Starlette BaseUser实现的MCP用户模型，封装认证上下文。
    对于 Token 认证，携带 token 允许访问的数据源 UUID 列表。
    """

    def __init__(
        self,
        auth_context: AuthContext,
        datasource_ids: list[str] | None = None,
        default_datasource_id: str | None = None,
    ) -> None:
        """初始化MCP用户

        Args:
            auth_context: 认证上下文对象
            datasource_ids: Token 允许访问的数据源 UUID 列表（仅 Token 认证时使用）
            default_datasource_id: Token 的默认数据源 UUID（仅 Token 认证时使用）
        """
        self.auth_context = auth_context
        self._datasource_ids = datasource_ids or []
        self._default_datasource_id = default_datasource_id

    @property
    def is_authenticated(self) -> bool:
        """检查用户是否已认证

        Returns:
            bool: 始终返回True，因为创建MCPUser即表示已认证
        """
        return True

    @property
    def datasource_ids(self) -> list[str]:
        """Token 允许访问的数据源 UUID 列表"""
        return self._datasource_ids

    @property
    def default_datasource_id(self) -> str | None:
        """Token 的默认数据源 UUID"""
        return self._default_datasource_id

    # @property
    # def display_name(self) -> str:
    #     return self.username
