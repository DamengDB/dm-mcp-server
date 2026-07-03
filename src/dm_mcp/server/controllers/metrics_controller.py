"""指标控制器模块

提供指标导出API端点，用于Prometheus等监控系统拉取指标数据。
"""

from starlette.authentication import requires
from starlette.requests import Request
from starlette.responses import Response

from dm_mcp.services.metrics_service import MetricsService


class MetricsController(object):
    """指标控制器

    处理指标导出请求，将系统指标以Prometheus格式返回。
    """

    def __init__(self, metrics_service: MetricsService) -> None:
        """初始化指标控制器

        Args:
            metrics_service: 指标服务实例
        """
        self.metrics_service = metrics_service

    @requires("authenticated")
    async def handle_metrics_request(self, request: Request):
        """处理指标导出请求

        导出系统指标数据，通常以Prometheus格式返回。
        需要认证。

        Args:
            request: HTTP请求对象

        Returns:
            Response: 包含指标数据的响应，Content-Type为text/plain（Prometheus格式）
        """
        data, content_type = self.metrics_service.export()
        return Response(data, media_type=content_type)
