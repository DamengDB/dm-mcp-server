"""健康检查控制器模块

提供健康检查API端点，用于监控服务状态。
"""

from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.api.base import BaseController
from dm_mcp.infra.config import Settings


class HealthController(BaseController):
    """健康检查控制器

    提供健康检查功能，返回服务状态信息。
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @requires("authenticated")
    async def handle_health_check(self, request: Request) -> JSONResponse:
        """处理健康检查请求"""
        return self.success(
            data={
                "status": "healthy",
                "service": self.settings.server.name,
            }
        )
