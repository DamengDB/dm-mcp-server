"""CLI 元数据导出控制器（/api/v1/cli-metadata）

供 dm-agent-cli 拉取，无需认证。
"""

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.api.base import BaseController
from dm_mcp.domain.mcp.services.mcp import MCPService
from dm_mcp.infra.web.error_codes import ErrorCode

logger = logging.getLogger(__name__)


class CLIExportController(BaseController):
    """CLI 元数据导出控制器"""

    def __init__(self, mcp_service: MCPService) -> None:
        self.mcp_service = mcp_service

    async def handle_cli_metadata(self, request: Request) -> JSONResponse:
        """返回 CLI 所需的树形命令元数据"""
        try:
            metadata = await self.mcp_service.get_cli_metadata()
            return self.success(
                data=metadata,
                message="获取 CLI 元数据成功",
            )
        except Exception as e:
            logger.error("生成 CLI 元数据失败: %s", e, exc_info=True)
            return self.error(
                error=str(e),
                code=ErrorCode.INTERNAL_ERROR,
                status_code=500,
            )
