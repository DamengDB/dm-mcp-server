"""MCP 统一上下文模块

提供 MCPContext 对象，用于聚合各类请求级上下文（认证、指标等），
并提供可扩展的上下文注册机制，避免在 BaseMCPProvider 中硬编码多个属性。
"""

import logging
import uuid
from contextlib import ExitStack, contextmanager
from typing import Any, Callable, ClassVar

from pydantic import BaseModel, Field

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.persistence.datasource_context import DatasourceContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext
from dm_mcp.infra.config.settings import Settings

logger = logging.getLogger(__name__)

# stdio 模式下无数据源服务时的固定临时 UUID，保证多次调用结果一致
_TEMP_DATASOURCE_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


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

    auth: AuthContext | None = Field(default=None, description="认证上下文")
    metrics: MetricsContext | None = Field(default=None, description="指标上下文")
    datasource: DatasourceContext | None = Field(
        default=None, description="数据源上下文（当前实际使用的数据源）"
    )
    extra: dict[str, Any] = Field(
        default_factory=dict, description="扩展上下文（按名称索引）"
    )

    # 类级别扩展上下文注册表：name -> getter()
    # _extra_getters: dict[str, Callable[[], Any]] = {}
    _extra_getters: ClassVar[dict[str, Callable[[], Any]]] = {}

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
        auth: AuthContext | None
        metrics: MetricsContext | None
        datasource: DatasourceContext | None

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

        extra: dict[str, Any] = {}
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
        cls, settings: Settings, datasource_service: Any | None = None
    ) -> "MCPContext":
        """为 stdio 模式构建请求上下文

        创建匿名认证上下文、指标上下文和数据源上下文。

        Args:
            settings: 服务器设置对象
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
        # 优先级：1. 持久化的默认数据源 2. "primary"
        ds_name = "primary"
        if datasource_service:
            try:
                # 优先从数据库读取持久化的默认数据源
                ds_name = await datasource_service.get_default_datasource()
            except Exception as e:
                logger.warning(f"获取持久化默认数据源失败: {e}")

        # 通过名称查找数据源 UUID
        datasource_id = _TEMP_DATASOURCE_UUID  # 固定临时 UUID（保证一致性）
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
        settings: Settings,
        datasource_service: Any | None = None,
        request_headers: dict[str, str] | None = None,
    ) -> "MCPContext":
        """为 HTTP 模式构建请求上下文

        根据认证用户和设置创建请求上下文。
        对于 Token 认证，支持通过 X-DMMCP-DataSource Header 动态指定数据源，
        未指定时回退到 Token 的默认数据源。

        Args:
            auth_user: 认证用户对象（可能为 None，表示匿名用户）
            settings: 服务器设置对象
            datasource_service: 数据源服务（可选，用于通过名称查找 UUID）
            request_headers: 请求头字典（可选，用于读取 X-DMMCP-DataSource）

        Returns:
            MCPContext: 构建好的 MCP 上下文对象
        """
        from dm_mcp.core.exceptions import AuthorizationError
        from dm_mcp.core.exceptions.auth_errors import TokenDatasourceNotFoundError

        if auth_user:
            auth = auth_user.auth_context
        else:
            auth = AuthContext(token=None)

        metrics = MetricsContext()
        datasource_id: uuid.UUID = _TEMP_DATASOURCE_UUID

        if auth.auth_type == "token" and auth_user:
            target_datasource_id: uuid.UUID | None = None
            datasource_name: str | None = None

            # 1. 优先从 Header 获取数据源名称（大小写敏感，与数据源 name 一致）
            if request_headers:
                datasource_name = request_headers.get("x-dmmcp-datasource")

            # 2. Header 未指定，回退到 token 的默认数据源
            if not datasource_name and auth_user.default_datasource_id:
                target_datasource_id = auth_user.default_datasource_id

            # 3. 如果通过 Header 指定了名称，解析为 UUID
            if datasource_name and not target_datasource_id:
                if datasource_service:
                    ds = await datasource_service.get_datasource(datasource_name)
                    if not ds:
                        raise TokenDatasourceNotFoundError(
                            f"数据源不存在: {datasource_name}"
                        )
                    if not ds.enabled:
                        raise TokenDatasourceNotFoundError(
                            f"数据源已禁用: {datasource_name}"
                        )
                    target_datasource_id = ds.id

            # 4. 校验 token 是否有权限访问该 UUID
            if target_datasource_id:
                if str(target_datasource_id) not in auth_user.datasource_ids:
                    raise AuthorizationError(
                        f"Token 无权访问数据源 '{datasource_name}'"
                    )
                datasource_id = target_datasource_id

        datasource = DatasourceContext(datasource_id=datasource_id)

        return cls(auth=auth, metrics=metrics, datasource=datasource)
