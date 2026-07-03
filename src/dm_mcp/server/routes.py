"""路由配置模块

定义所有HTTP路由，包括API路由、MCP路由、静态文件路由等。
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dm_mcp.server.controllers import (
    AuthController,
    BasicAuthController,
    ConfigController,
    DataSourceController,
    HealthController,
    HomeController,
    MCPController,
    MetricsController,
    TokenController,
)

if TYPE_CHECKING:
    from dm_mcp.server.global_context import GlobalContext


def get_routes(context: "GlobalContext", session_manager: StreamableHTTPSessionManager):
    """获取所有路由配置

    创建并配置所有HTTP路由，包括：
    - API路由（健康检查、配置、认证、数据源、Token等）
    - MCP路由（流式HTTP会话管理）
    - 静态文件路由
    - 主页路由

    Args:
        context: 全局上下文对象
        session_manager: MCP流式HTTP会话管理器

    Returns:
        List[Route | Mount]: 路由列表
    """
    settings = context.settings

    # ============================================================
    # 控制器
    # ============================================================
    home_controller = HomeController(settings)
    health_controller = HealthController(settings)
    config_controller = ConfigController(settings, context.basic_auth_service)
    auth_controller = AuthController(settings, context.oauth_service)
    basic_auth_controller = BasicAuthController(context.basic_auth_service)
    metrics_controller = MetricsController(context.metrics_service)
    mcp_controller = MCPController(
        session_manager, settings, context.datasource_service
    )
    datasource_controller = DataSourceController(
        context.datasource_service, context.pool_service
    )
    token_controller = TokenController(
        context.token_service, context.datasource_service
    )

    # ============================================================
    # 静态文件
    # ============================================================
    project_root = os.getcwd()
    default_static_dir = os.path.join(project_root, "resources", "static")

    # 优先从配置读取，在 settings.server.static_path 指定
    static_dir = getattr(settings.server, "static_path", default_static_dir)
    static_dir = Path(static_dir)
    if not static_dir.exists():
        os.makedirs(static_dir, exist_ok=True)

    # ============================================================
    # API 路由
    # ============================================================
    api_routes = [
        # health check
        Route("/health", health_controller.handle_health_check, methods=["GET"]),
        # config endpoint
        Route("/config", config_controller.handle_config, methods=["GET"]),
        # pool test endpoint
        # Route(
        #     "/pool/test",
        #     pool_controller.handle_pool_test,
        #     methods=["GET"],
        #     name="pool_test",
        # ),
        # =================================================
        # oauth endpoints
        # =================================================
        Route(
            "/auth/{provider}/login",
            auth_controller.handle_oauth_login,
            methods=["GET"],
            name="oauth_login",
        ),
        Route(
            "/auth/{provider}/callback",
            auth_controller.handle_oauth_callback,
            name="oauth_callback",
        ),
        Route(
            "/auth/providers",
            auth_controller.handle_oauth_providers,
            methods=["GET"],
            name="oauth_providers",
        ),
        # =================================================
        # basic auth endpoints
        # =================================================
        Route(
            "/auth/admin/login",
            basic_auth_controller.handle_login,
            methods=["POST"],
            name="basic_auth_login",
        ),
        Route(
            "/auth/admin/init-password",
            basic_auth_controller.handle_init_password,
            methods=["POST"],
            name="basic_auth_init_password",
        ),
        Route(
            "/auth/admin/change-password",
            basic_auth_controller.handle_change_password,
            methods=["POST"],
            name="basic_auth_change_password",
        ),
        Route(
            settings.metrics.http_path,
            metrics_controller.handle_metrics_request,
            methods=["GET"],
            name="metrics",
        ),
        # =================================================
        # datasource endpoints
        # =================================================
        Route(
            "/datasources",
            datasource_controller.handle_list,
            methods=["GET"],
            name="datasources_list",
        ),
        Route(
            "/datasources",
            datasource_controller.handle_create,
            methods=["POST"],
            name="datasources_create",
        ),
        Route(
            "/datasources/status",
            datasource_controller.handle_status,
            methods=["GET"],
            name="datasources_status",
        ),
        Route(
            "/datasources/default",
            datasource_controller.handle_get_default,
            methods=["GET"],
            name="datasources_get_default",
        ),
        Route(
            "/datasources/default",
            datasource_controller.handle_set_default,
            methods=["PUT"],
            name="datasources_set_default",
        ),
        Route(
            "/datasources/reload",
            datasource_controller.handle_reload_all,
            methods=["POST"],
            name="datasources_reload_all",
        ),
        Route(
            "/datasources/test",
            datasource_controller.handle_test_new,
            methods=["POST"],
            name="datasources_test_new",
        ),
        Route(
            "/datasources/{name}",
            datasource_controller.handle_get,
            methods=["GET"],
            name="datasources_get",
        ),
        Route(
            "/datasources/{name}",
            datasource_controller.handle_update,
            methods=["PUT"],
            name="datasources_update",
        ),
        Route(
            "/datasources/{name}",
            datasource_controller.handle_delete,
            methods=["DELETE"],
            name="datasources_delete",
        ),
        Route(
            "/datasources/{name}/enable",
            datasource_controller.handle_enable,
            methods=["POST"],
            name="datasources_enable",
        ),
        Route(
            "/datasources/{name}/disable",
            datasource_controller.handle_disable,
            methods=["POST"],
            name="datasources_disable",
        ),
        Route(
            "/datasources/{name}/test",
            datasource_controller.handle_test_existing,
            methods=["POST"],
            name="datasources_test_existing",
        ),
        Route(
            "/datasources/{name}/reload",
            datasource_controller.handle_reload_one,
            methods=["POST"],
            name="datasources_reload_one",
        ),
        # =================================================
        # token endpoints
        # =================================================
        Route(
            "/tokens",
            token_controller.handle_list,
            methods=["GET"],
            name="tokens_list",
        ),
        Route(
            "/tokens",
            token_controller.handle_create,
            methods=["POST"],
            name="tokens_create",
        ),
        Route(
            "/tokens/{token}",
            token_controller.handle_get,
            methods=["GET"],
            name="tokens_get",
        ),
        Route(
            "/tokens/{token}",
            token_controller.handle_update,
            methods=["PUT"],
            name="tokens_update",
        ),
        Route(
            "/tokens/{token}",
            token_controller.handle_delete,
            methods=["DELETE"],
            name="tokens_delete",
        ),
    ]

    # ============================================================
    # 总路由
    # ============================================================
    base_url = settings.server.base_url
    routes = [
        Mount(f"{base_url}/mcp", app=mcp_controller.handle_request, name="mcp"),
        Mount(
            f"{base_url}/static", app=StaticFiles(directory=static_dir), name="static"
        ),
        Mount(f"{base_url}/api/v1", routes=api_routes, name="api"),
        Route(
            f"{base_url}/{{path:path}}",
            home_controller.handle_home_page,
            methods=["GET"],
            name="home",
        ),
    ]

    return routes


__all__ = [
    "get_routes",
]
