"""MCP 统一上下文模块

提供 MCPContext 对象，用于聚合各类请求级上下文（认证、指标等），
并提供可扩展的上下文注册机制，避免在 BaseMCPProvider 中硬编码多个属性。
"""

import logging
import uuid
from contextlib import ExitStack, contextmanager
from typing import Any, Callable, ClassVar, Dict, Optional, Tuple

from pydantic import BaseModel, Field

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.datasource.datasource_context import DatasourceContext
from dm_mcp.core.metrics.metrics_context import MetricsContext

logger = logging.getLogger(__name__)


class MCPContext(BaseModel):
    """MCP 统一上下文

    聚合当前请求的各类上下文信息：
    - 内置上下文：auth、metrics
    - 扩展上下文：通过 register_extra 注册的其他上下文（如 tenant、trace 等）

    使用方式：
        ctx = MCPContext.current()
        ctx.auth
        ctx.metrics
        ctx.get("tenant")
        ctx.extra.get("trace")
    """

    auth: Optional[AuthContext] = Field(default=None, description="认证上下文")
    metrics: Optional[MetricsContext] = Field(default=None, description="指标上下文")
    datasource: Optional[DatasourceContext] = Field(
        default=None, description="数据源上下文（当前实际使用的数据源）"
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict, description="扩展上下文（按名称索引）"
    )

    # 类级别扩展上下文注册表：name -> getter()
    # _extra_getters: Dict[str, Callable[[], Any]] = {}
    _extra_getters: ClassVar[Dict[str, Callable[[], Any]]] = {}

    @classmethod
    def register_extra(cls, name: str, getter: Callable[[], Any]) -> None:
        """注册额外的上下文访问器

        Args:
            name: 上下文名称，例如 "tenant" / "trace"
            getter: 无参函数，返回对应上下文对象（通常是 XxxContext.get）
        """
        cls._extra_getters[name] = getter

    @classmethod
    def current(cls) -> "MCPContext":
        """构建当前请求的 MCPContext

        从各个子 ContextVar 中拉取当前请求的上下文对象：
        - AuthContext / MetricsContext 如果未设置，不会抛异常，而是 None
        - 扩展上下文按已注册的 getter 拉取，单个失败会被忽略
        """
        auth: Optional[AuthContext]
        metrics: Optional[MetricsContext]
        datasource: Optional[DatasourceContext]

        try:
            auth = AuthContext.get()
        except ValueError:
            auth = None

        try:
            metrics = MetricsContext.get()
        except ValueError:
            metrics = None

        try:
            datasource = DatasourceContext.get()
        except ValueError:
            datasource = None

        extra: Dict[str, Any] = {}
        for name, getter in cls._extra_getters.items():
            try:
                extra[name] = getter()
            except Exception:
                # 某个扩展上下文未设置或获取失败时，忽略该项
                continue

        return cls(auth=auth, metrics=metrics, datasource=datasource, extra=extra)

    def get(self, name: str, default: Any = None) -> Any:
        """统一的上下文访问接口

        优先访问内置字段，其次访问 extra。

        Args:
            name: 上下文名称，例如 "auth" / "metrics" / "tenant"
            default: 未找到时返回的默认值
        """
        if name == "auth":
            return self.auth if self.auth is not None else default
        if name == "metrics":
            return self.metrics if self.metrics is not None else default
        if name == "datasource":
            return self.datasource if self.datasource is not None else default
        return self.extra.get(name, default)

    @classmethod
    @contextmanager
    def as_current(cls, ctx: "MCPContext"):
        """统一设置请求级上下文

        接收一个 MCPContext 实例，并将其中的 auth/metrics/datasource
        分别设置到对应的子上下文中。

        Args:
            ctx: MCPContext 实例，包含本次请求的完整上下文

        使用示例：
            ctx = MCPContext.build_for_stdio(settings)
            with MCPContext.as_current(ctx):
                await some_operation()
        """
        with ExitStack() as stack:
            if ctx.auth is not None:
                stack.enter_context(AuthContext.as_current(ctx.auth))
            if ctx.metrics is not None:
                stack.enter_context(MetricsContext.as_current(ctx.metrics))
            if ctx.datasource is not None:
                stack.enter_context(DatasourceContext.as_current(ctx.datasource))
            yield

    @classmethod
    async def build_for_stdio(
        cls, settings: Any, datasource_service: Optional[Any] = None
    ) -> "MCPContext":
        """为 stdio 模式构建请求上下文

        创建匿名认证上下文、指标上下文和数据源上下文。

        Args:
            settings: 服务器设置对象（需要包含 pool.default_source 属性）
            datasource_service: 数据源服务（可选，用于通过名称查找 UUID）

        Returns:
            MCPContext: 构建好的 MCP 上下文对象
        """
        auth = AuthContext(
            user_id="anonymous",
            auth_type="anonymous",
            token=None,
        )
        metrics = MetricsContext()

        # 解析默认数据源名称并查找 UUID
        # 优先级：1. 持久化的默认数据源 2. 配置中的默认数据源 3. "primary"
        ds_name = "primary"
        if datasource_service:
            try:
                # 优先从数据库读取持久化的默认数据源
                ds_name = await datasource_service.get_default_datasource()
            except Exception as e:
                logger.warning(f"获取持久化默认数据源失败，回退到配置: {e}")
                # 回退到配置中的默认值
                if hasattr(settings, "pool") and hasattr(
                    settings.pool, "default_source"
                ):
                    ds_name = settings.pool.default_source or "primary"
        elif hasattr(settings, "pool") and hasattr(settings.pool, "default_source"):
            ds_name = settings.pool.default_source or "primary"

        # 通过名称查找数据源 UUID
        datasource_id = uuid.uuid4()  # 默认生成一个 UUID（用于无数据源服务的情况）
        if datasource_service:
            ds = await datasource_service.get_datasource(ds_name)
            if ds:
                datasource_id = ds.id
            else:
                # 如果找不到数据源，使用默认 UUID（可能会在后续使用时失败）
                logger.warning(f"stdio 模式：未找到数据源 '{ds_name}'，使用临时 UUID")

        datasource = DatasourceContext(datasource_id=datasource_id)

        return cls(auth=auth, metrics=metrics, datasource=datasource)

    @classmethod
    async def build_for_http(
        cls,
        auth_user: Any,
        settings: Any,
        datasource_service: Optional[Any] = None,
    ) -> "MCPContext":
        """为 HTTP 模式构建请求上下文

        根据认证用户和设置创建请求上下文。

        Args:
            auth_user: 认证用户对象（可能为 None，表示匿名用户）
            settings: 服务器设置对象（需要包含 pool.default_source 属性）
            datasource_service: 数据源服务（可选，用于通过名称查找 UUID）

        Returns:
            MCPContext: 构建好的 MCP 上下文对象
        """
        if auth_user:
            auth = auth_user.auth_context
        else:
            auth = AuthContext(token=None)

        metrics = MetricsContext()

        # 解析数据源 UUID
        # 优先级：1. Token 认证绑定的数据源（从 MCPUser.datasource_id 获取） 2. 持久化的默认数据源 3. 配置的默认数据源 4. 生成临时 UUID
        datasource_id: uuid.UUID = uuid.uuid4()  # 默认生成一个 UUID

        if (
            auth.auth_type == "token"
            and auth_user
            and hasattr(auth_user, "datasource_id")
        ):
            # 一 Token 一数据源：从 MCPUser.datasource_id 获取 token 绑定的数据源 UUID
            if auth_user.datasource_id:
                datasource_id = auth_user.datasource_id
        elif datasource_service:
            # 优先级：1. 持久化的默认数据源 2. 配置中的默认数据源 3. "primary"
            ds_name: str = "primary"
            try:
                # 优先从数据库读取持久化的默认数据源
                ds_name = await datasource_service.get_default_datasource()
            except Exception as e:
                logger.warning(f"获取持久化默认数据源失败，回退到配置: {e}")
                # 回退到配置中的默认值
                if hasattr(settings, "pool") and hasattr(
                    settings.pool, "default_source"
                ):
                    ds_name = settings.pool.default_source or "primary"
            ds = await datasource_service.get_datasource(ds_name)
            if ds:
                datasource_id = ds.id

        datasource = DatasourceContext(datasource_id=datasource_id)

        return cls(auth=auth, metrics=metrics, datasource=datasource)
