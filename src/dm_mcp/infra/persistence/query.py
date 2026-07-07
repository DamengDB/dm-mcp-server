"""统一查询构建器模块

提供自动注入 owner_id 可见性过滤的查询构建工具，
消除 Service 层分散的权限检查逻辑。
"""

from sqlalchemy import select
from sqlalchemy.sql import Select

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions.auth_errors import AuthorizationError


class OwnedQuery:
    """自动注入 owner_id 可见性过滤的查询构建器

    适用于所有带有 ``owner_id`` 字段的模型（DataSourceModel、SSHHostModel 等）。

    权限规则（统一适用于所有用户，包括 admin）：
    1. ``owner_id is None`` → 公共记录，所有人可见
    2. ``owner_id == user_id`` → 所有者可见
    3. 其他情况 → 拒绝访问
    """

    @staticmethod
    def _current_user() -> str | None:
        try:
            ctx = AuthContext.get()
            return ctx.user_id
        except ValueError:
            return None

    @classmethod
    def filter(cls, stmt: Select, model_cls) -> Select:
        """为查询注入 owner_id 过滤条件

        对于 list / 批量查询场景，直接在 SQL 层面过滤，
        避免查出无权记录后再手动丢弃。

        Args:
            stmt: 原始 SQLAlchemy Select 语句
            model_cls: 带有 ``owner_id`` 属性的模型类

        Returns:
            Select: 注入过滤条件后的查询语句
        """
        user_id = cls._current_user()
        return stmt.where(
            (model_cls.owner_id == user_id) | (model_cls.owner_id.is_(None))
        )

    @classmethod
    def check_access(cls, model) -> None:
        """检查当前用户是否有权访问单条记录

        用于 get_by_id / get_by_name 等单条查询场景，
        在查出记录后做二次校验，可区分"不存在"和"无权限"。

        Args:
            model: 带有 ``owner_id`` 属性的模型实例

        Raises:
            AuthorizationError: 无权访问时抛出
        """
        user_id = cls._current_user()
        if model.owner_id is None:
            return
        if model.owner_id == user_id:
            return

        name = getattr(model, "name", None) or getattr(model, "id", "unknown")
        raise AuthorizationError(
            f"无权访问: {name}",
            error_code="ACCESS_DENIED",
        )
