"""健康检查控制器模块

提供健康检查API端点，用于监控服务状态。
"""

from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.settings import Settings


class HealthController(object):
    """健康检查控制器

    提供健康检查功能，返回服务状态信息。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化健康检查控制器

        Args:
            settings: 服务器设置
        """
        self.settings = settings

    @requires("authenticated")
    async def handle_health_check(self, request: Request) -> JSONResponse:
        """处理健康检查请求

        返回服务健康状态和服务名称。需要认证。

        Args:
            request: HTTP请求对象

        Returns:
            JSONResponse: 包含健康状态信息的JSON响应
        """
        return JSONResponse(
            {
                "status": "healthy",
                "service": self.settings.server.name,
            }
        )
