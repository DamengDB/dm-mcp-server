"""用户模型模块

提供基于Starlette的MCP用户模型实现。
"""

import uuid
from typing import Optional

from starlette.authentication import BaseUser

from .auth_context import AuthContext


class MCPUser(BaseUser):
    """MCP用户模型

    基于Starlette BaseUser实现的MCP用户模型，封装认证上下文。
    对于 Token 认证，可以携带 token 绑定的数据源信息。
    """

    def __init__(
        self, auth_context: AuthContext, datasource_id: Optional[uuid.UUID] = None
    ) -> None:
        """初始化MCP用户

        Args:
            auth_context: 认证上下文对象
            datasource_id: Token 绑定的数据源 UUID（仅 Token 认证时使用）
        """
        self.auth_context = auth_context
        self.datasource_id = datasource_id

    @property
    def is_authenticated(self) -> bool:
        """检查用户是否已认证

        Returns:
            bool: 始终返回True，因为创建MCPUser即表示已认证
        """
        return True

    # @property
    # def display_name(self) -> str:
    #     return self.username
