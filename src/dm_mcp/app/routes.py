"""路由配置模块

定义所有HTTP路由，包括API路由、MCP路由、静态文件路由等。
"""

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from dm_mcp.api.auth.basic_auth import BasicAuthController
from dm_mcp.api.auth.config import AuthConfigController
from dm_mcp.api.auth.oauth import AuthController
from dm_mcp.api.datasource.datasource import DataSourceController
from dm_mcp.api.datasource.pool_config import PoolConfigController
from dm_mcp.api.mcp.cli_download import CLIDownloadController
from dm_mcp.api.mcp.cli_export import CLIExportController
from dm_mcp.api.mcp.groups import MCPGroupController
from dm_mcp.api.mcp.mcp import MCPController
from dm_mcp.api.mcp.prompts import PromptController
from dm_mcp.api.mcp.resources import ResourceController
from dm_mcp.api.mcp.tools import ToolController
from dm_mcp.api.db_metadata.db_metadata import DbMetadataController
from dm_mcp.api.db_metadata.db_config import DbMetadataConfigController
from dm_mcp.api.ssh.ssh_host import SSHHostController
from dm_mcp.api.system.config import ConfigController
from dm_mcp.api.system.health import HealthController
from dm_mcp.api.system.home import HomeController
from dm_mcp.api.system.metrics import MetricsController
from dm_mcp.api.token.token import TokenController

if TYPE_CHECKING:
    from dm_mcp.app.context import GlobalContext

logger = logging.getLogger(__name__)


class SPAStaticFiles(StaticFiles):
    """SPA 静态文件处理器

    支持前端路由的 fallback 行为：当请求的文件不存在时，
    返回 index.html，由前端路由接管。
    """

    def __init__(self, directory: str, index_file: str = "index.html", **kwargs):
        super().__init__(directory=directory, **kwargs)
        self.index_path = os.path.join(directory, index_file)

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return FileResponse(self.index_path)
            raise


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
        list[Route | Mount]: 路由列表
    """
    settings = context.settings

    # ============================================================
    # 控制器
    # ============================================================
    home_controller = HomeController(settings)
    health_controller = HealthController(settings)
    config_controller = ConfigController(settings, context.basic_auth_service, context.auth_config_service)
    auth_controller = AuthController(settings, context.oauth_service, context.auth_config_service)
    basic_auth_controller = BasicAuthController(context.basic_auth_service)
    auth_config_controller = AuthConfigController(
        context.auth_config_service, context.oauth_service
    )
    metrics_controller = MetricsController(context.metrics_service)
    mcp_controller = MCPController(
        session_manager, settings, context.datasource_service
    )
    datasource_controller = DataSourceController(
        context.datasource_service, context.pool_service
    )
    pool_config_controller = PoolConfigController(context.datasource_service)
    ssh_host_controller = SSHHostController(context.ssh_host_service)
    token_controller = TokenController(
        context.token_service, context.datasource_service, context.ssh_host_service
    )
    mcp_group_controller = MCPGroupController(
        context.mcp_group_service,
        context.mcp_service,
    )
    tool_controller = ToolController(
        context.mcp_group_service,
        context.mcp_service,
    )
    resource_controller = ResourceController(
        context.mcp_group_service,
        context.mcp_service,
    )
    prompt_controller = PromptController(
        context.mcp_group_service,
        context.mcp_service,
    )
    cli_export_controller = CLIExportController(context.mcp_service)
    cli_download_controller = CLIDownloadController(settings)
    db_metadata_controller = DbMetadataController(
        context.db_metadata_service,
    )
    db_metadata_config_controller = DbMetadataConfigController(
        context.db_config_service,
        context.datasource_service,
    )

    # ============================================================
    # 静态文件
    # ============================================================
    project_root = os.getcwd()
    default_static_dir = os.path.join(project_root, "resources", "web")

    # web 前端静态目录（可选：不存在或缺少 index.html 时跳过挂载）
    default_static_dir = os.path.join(project_root, "resources", "web")
    static_dir = getattr(settings.server, "static_path", default_static_dir)
    static_dir = Path(static_dir)
    web_available = static_dir.is_dir() and (static_dir / "index.html").is_file()
    if not web_available:
        if static_dir.is_dir():
            logger.warning(
                'Web 静态目录缺少 index.html，将跳过 web 路由挂载: "%s"',
                static_dir,
            )
        else:
            logger.warning(
                'Web 静态目录不存在，将跳过 web 路由挂载: "%s"',
                static_dir,
            )

    # cli 二进制目录（路由始终注册；目录缺失时由控制器在请求阶段返回 404）
    default_cli_dir = os.path.join(project_root, "resources", "cli", "latest")
    cli_dir = Path(getattr(settings.server, "cli_path", default_cli_dir))
    if not cli_dir.is_dir():
        logger.warning(
            'CLI 静态目录不存在，cli-download 请求将返回不可用: "%s"',
            cli_dir,
        )
    default_docs_dir = os.path.join(project_root, "resources", "docs")
    docs_dir = getattr(settings.server, "docs_path", default_docs_dir)
    docs_dir = Path(docs_dir)
    docs_available = docs_dir.is_dir()
    if not docs_available:
        logger.warning(
            '文档静态目录不存在，将跳过 docs 路由挂载: "%s"',
            docs_dir,
        )

    # ============================================================
    # API 路由
    # ============================================================
    api_routes = [
        # health check
        Route("/health", health_controller.handle_health_check, methods=["GET"]),
        # config endpoint
        Route("/config", config_controller.handle_config, methods=["GET"]),
        # =================================================
        # auth config endpoints
        # =================================================
        Route("/auth-config", auth_config_controller.handle_get, methods=["GET"]),
        Route("/auth-config", auth_config_controller.handle_put, methods=["PUT"]),
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
        # oauth providers (admin only)
        # =================================================
        Route(
            "/oauth/providers",
            auth_config_controller.handle_list_providers,
            methods=["GET"],
            name="oauth_providers_list",
        ),
        Route(
            "/oauth/providers/{slot}",
            auth_config_controller.handle_get_provider,
            methods=["GET"],
            name="oauth_provider_get",
        ),
        Route(
            "/oauth/providers/{slot}",
            auth_config_controller.handle_put_provider,
            methods=["PUT"],
            name="oauth_provider_put",
        ),
        Route(
            "/oauth/providers/{slot}/enable",
            auth_config_controller.handle_enable_provider,
            methods=["POST"],
            name="oauth_provider_enable",
        ),
        Route(
            "/oauth/providers/{slot}/disable",
            auth_config_controller.handle_disable_provider,
            methods=["POST"],
            name="oauth_provider_disable",
        ),
        Route(
            "/oauth/providers/{slot}/test",
            auth_config_controller.handle_test_provider,
            methods=["POST"],
            name="oauth_provider_test",
        ),
        # =================================================
        # pool config endpoints (admin only)
        # =================================================
        Route(
            "/pool-config",
            pool_config_controller.handle_get,
            methods=["GET"],
            name="pool_config_get",
        ),
        Route(
            "/pool-config",
            pool_config_controller.handle_put,
            methods=["PUT"],
            name="pool_config_put",
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
        # 数据库元数据查询（模式 / 表 / 视图 / 列）
        # =================================================
        Route(
            "/datasources/{name}/metadata/schemas",
            db_metadata_controller.handle_list_schemas,
            methods=["GET"],
            name="db_metadata_schemas",
        ),
        Route(
            "/datasources/{name}/metadata/tables",
            db_metadata_controller.handle_list_tables,
            methods=["GET"],
            name="db_metadata_tables",
        ),
        Route(
            "/datasources/{name}/metadata/views",
            db_metadata_controller.handle_list_views,
            methods=["GET"],
            name="db_metadata_views",
        ),
        Route(
            "/datasources/{name}/metadata/columns",
            db_metadata_controller.handle_list_columns,
            methods=["GET"],
            name="db_metadata_columns",
        ),
        # =================================================
        # 数据库元数据配置（DataSource 级）
        # =================================================
        Route(
            "/datasources/{name}/metadata/configs",
            db_metadata_config_controller.handle_list,
            methods=["GET"],
            name="db_metadata_configs_list",
        ),
        Route(
            "/datasources/{name}/metadata/configs",
            db_metadata_config_controller.handle_upsert,
            methods=["PUT"],
            name="db_metadata_configs_upsert",
        ),
        Route(
            "/datasources/{name}/metadata/configs",
            db_metadata_config_controller.handle_delete,
            methods=["DELETE"],
            name="db_metadata_configs_delete",
        ),
        Route(
            "/datasources/{name}/metadata/configs/batch",
            db_metadata_config_controller.handle_batch_upsert,
            methods=["POST"],
            name="db_metadata_configs_batch",
        ),
        # =================================================
        # MCP 分组（id 化 REST）
        # =================================================
        Route(
            "/mcp-groups",
            mcp_group_controller.handle_list,
            methods=["GET"],
            name="mcp_groups_list",
        ),
        Route(
            "/mcp-groups",
            mcp_group_controller.handle_create,
            methods=["POST"],
            name="mcp_groups_create",
        ),
        Route(
            "/mcp-groups/tree",
            mcp_group_controller.handle_tree,
            methods=["GET"],
            name="mcp_groups_tree",
        ),
        Route(
            "/mcp-groups/{id}",
            mcp_group_controller.handle_get,
            methods=["GET"],
            name="mcp_groups_get",
        ),
        Route(
            "/mcp-groups/{id}",
            mcp_group_controller.handle_update,
            methods=["PUT"],
            name="mcp_groups_update",
        ),
        Route(
            "/mcp-groups/{id}",
            mcp_group_controller.handle_delete,
            methods=["DELETE"],
            name="mcp_groups_delete",
        ),
        Route(
            "/mcp-groups/{id}/rename",
            mcp_group_controller.handle_rename,
            methods=["POST"],
            name="mcp_groups_rename",
        ),
        Route(
            "/mcp-groups/{id}/move",
            mcp_group_controller.handle_move,
            methods=["POST"],
            name="mcp_groups_move",
        ),
        Route(
            "/mcp-groups/{id}/entities",
            mcp_group_controller.handle_list_entities,
            methods=["GET"],
            name="mcp_groups_entities",
        ),
        # =================================================
        # 工具元数据管理
        # =================================================
        Route(
            "/tools",
            tool_controller.handle_list,
            methods=["GET"],
            name="tools_list",
        ),
        Route(
            "/tools/{name}",
            tool_controller.handle_get,
            methods=["GET"],
            name="tools_get",
        ),
        Route(
            "/tools/{name}/override",
            tool_controller.handle_update_override,
            methods=["PUT"],
            name="tools_update_override",
        ),
        Route(
            "/tools/{name}/override",
            tool_controller.handle_reset_override,
            methods=["DELETE"],
            name="tools_reset_override",
        ),
        Route(
            "/tools/{name}/group",
            tool_controller.handle_assign_group,
            methods=["PUT"],
            name="tools_assign_group",
        ),
        Route(
            "/tools/batch-assign-group",
            tool_controller.handle_batch_assign_group,
            methods=["POST"],
            name="tools_batch_assign_group",
        ),
        # =================================================
        # 资源元数据管理
        # =================================================
        Route(
            "/resources",
            resource_controller.handle_list,
            methods=["GET"],
            name="resources_list",
        ),
        Route(
            "/resources/{name}",
            resource_controller.handle_get,
            methods=["GET"],
            name="resources_get",
        ),
        Route(
            "/resources/{name}/override",
            resource_controller.handle_update_override,
            methods=["PUT"],
            name="resources_update_override",
        ),
        Route(
            "/resources/{name}/override",
            resource_controller.handle_reset_override,
            methods=["DELETE"],
            name="resources_reset_override",
        ),
        Route(
            "/resources/{name}/group",
            resource_controller.handle_assign_group,
            methods=["PUT"],
            name="resources_assign_group",
        ),
        Route(
            "/resources/batch-assign-group",
            resource_controller.handle_batch_assign_group,
            methods=["POST"],
            name="resources_batch_assign_group",
        ),
        # =================================================
        # 提示词元数据管理
        # =================================================
        Route(
            "/prompts",
            prompt_controller.handle_list,
            methods=["GET"],
            name="prompts_list",
        ),
        Route(
            "/prompts/{name}",
            prompt_controller.handle_get,
            methods=["GET"],
            name="prompts_get",
        ),
        Route(
            "/prompts/{name}/override",
            prompt_controller.handle_update_override,
            methods=["PUT"],
            name="prompts_update_override",
        ),
        Route(
            "/prompts/{name}/override",
            prompt_controller.handle_reset_override,
            methods=["DELETE"],
            name="prompts_reset_override",
        ),
        Route(
            "/prompts/{name}/group",
            prompt_controller.handle_assign_group,
            methods=["PUT"],
            name="prompts_assign_group",
        ),
        Route(
            "/prompts/batch-assign-group",
            prompt_controller.handle_batch_assign_group,
            methods=["POST"],
            name="prompts_batch_assign_group",
        ),
        # =================================================
        # CLI 元数据导出（供 dm-agent-cli 拉取，无需认证）
        # =================================================
        Route(
            "/cli-metadata",
            cli_export_controller.handle_cli_metadata,
            methods=["GET"],
            name="cli_tools_metadata",
        ),
        # =================================================
        # CLI 元数据导出（供 dm-agent-cli 拉取，无需认证）
        # =================================================
        Route(
            "/cli-metadata",
            cli_export_controller.handle_cli_metadata,
            methods=["GET"],
            name="cli_tools_metadata",
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
            "/tokens/{token_id}",
            token_controller.handle_get,
            methods=["GET"],
            name="tokens_get",
        ),
        Route(
            "/tokens/{token_id}",
            token_controller.handle_update,
            methods=["PUT"],
            name="tokens_update",
        ),
        Route(
            "/tokens/{token_id}",
            token_controller.handle_delete,
            methods=["DELETE"],
            name="tokens_delete",
        ),
        # =================================================
        # ssh host endpoints
        # =================================================
        Route(
            "/ssh-hosts",
            ssh_host_controller.handle_list,
            methods=["GET"],
            name="ssh_hosts_list",
        ),
        Route(
            "/ssh-hosts",
            ssh_host_controller.handle_create,
            methods=["POST"],
            name="ssh_hosts_create",
        ),
        Route(
            "/ssh-hosts/{host_id}",
            ssh_host_controller.handle_get,
            methods=["GET"],
            name="ssh_hosts_get",
        ),
        Route(
            "/ssh-hosts/{host_id}",
            ssh_host_controller.handle_update,
            methods=["PATCH"],
            name="ssh_hosts_update",
        ),
        Route(
            "/ssh-hosts/{host_id}",
            ssh_host_controller.handle_delete,
            methods=["DELETE"],
            name="ssh_hosts_delete",
        ),
    ]

    # ============================================================
    # 总路由
    # ============================================================
    base_url = settings.server.base_url
    routes: list[Route | Mount] = [
        Mount(f"{base_url}/mcp", app=mcp_controller.handle_request, name="mcp"),
    ]
    if docs_available:
        routes.extend(
            [
                # docs 不带斜杠时重定向到带斜杠（Mount 正则要求末尾 /）
                Route(
                    f"{base_url}/docs",
                    lambda request: RedirectResponse(url=f"{base_url}/docs/"),
                    methods=["GET"],
                    name="docs_redirect",
                ),
                Mount(
                    f"{base_url}/docs/",
                    app=StaticFiles(directory=docs_dir, html=True),
                    name="docs",
                ),
            ]
        )
    routes.extend(
        [
            Mount(f"{base_url}/api/v1", routes=api_routes, name="api"),
            # CLI 二进制下载（直接挂在 base_url 下，非 API 路由）
            Route(
                f"{base_url}/cli-download/{{program}}/{{platform}}",
                cli_download_controller.handle_download,
                methods=["GET"],
                name="cli_download",
            ),
        ]
    )
    if web_available:
        # SPA 前端路由（文件存在则直接返回，否则 fallback 到 index.html）
        routes.append(
            Mount(
                f"{base_url}/",
                app=SPAStaticFiles(directory=static_dir),
                name="web",
            )
        )

    return routes


__all__ = [
    "get_routes",
]
