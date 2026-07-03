import asyncio

from dm_mcp.providers.test_pool import TestDbTool
from dm_mcp.services import AsyncPoolService
from dm_mcp.services.metrics_service import MetricsService
from dm_mcp.settings.settings import Settings


async def main():
    settings = Settings()

    ms = MetricsService(settings.metrics)
    manager = AsyncPoolService(settings.pool, settings.datasources, ms)

    await manager.startup()

    tool = TestDbTool(manager)

    result = await tool.test_query()

    await manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
