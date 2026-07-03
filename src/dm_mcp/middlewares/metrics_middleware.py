import logging

from dm_mcp.core.mcp.middleware import BaseMCPMiddleware, NextCallable
from dm_mcp.core.metrics.metrics_context import MetricsContext

logger = logging.getLogger(__name__)

from dm_mcp.services.metrics_service import MetricsService


class MetricsMCPMiddleware(BaseMCPMiddleware):

    def __init__(self, metrics_service: MetricsService) -> None:
        self.metrics_service = metrics_service

    async def on_call_tool(
        self, call_next: NextCallable, name: str, arguments: dict
    ) -> str:
        context = MetricsContext.get()

        try:
            res = await call_next(name, arguments)
            return res
        except Exception as e:
            raise e
        finally:
            self.metrics_service.record_from_context(context)
