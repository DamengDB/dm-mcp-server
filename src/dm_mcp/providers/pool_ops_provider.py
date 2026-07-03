import stat
from typing import Any, Dict, Optional

from dm_mcp.providers.base_datasource_provider import BaseDataSourceMCPProvider
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.services.datasource_service import DataSourceService


class PoolOpsMCPProvider(BaseDataSourceMCPProvider):
    """连接池运维类工具 Provider：状态查看、连通性探测等。"""

    def __init__(
        self, datasource_service: DataSourceService, pool_service: AsyncPoolService
    ) -> None:
        super().__init__(datasource_service)
        self._pool_service = pool_service

        self._register_routes()

    # ============================================================
    # 业务逻辑方法（封装@self.mcp.tool下的逻辑）
    # ============================================================

    async def _get_pool_status(self) -> Dict[str, Any]:
        """获取连接池状态"""
        # 注意：方法名请与 AsyncPoolService 实际实现对齐
        # 如果你的 AsyncPoolService 是 status()/get_status()/get_pool_status()，在这里改一下即可。
        if hasattr(self._pool_service, "get_pool_status"):
            return await self._pool_service.get_pool_status()  # type: ignore[attr-defined]
        if hasattr(self._pool_service, "pool_status"):
            return await self._pool_service.pool_status()  # type: ignore[attr-defined]
        if hasattr(self._pool_service, "status"):
            return await self._pool_service.status()  # type: ignore[attr-defined]
        raise AttributeError(
            "AsyncPoolService 缺少 pool 状态查询方法（get_pool_status/pool_status/status）"
        )

    async def _test_connection(
        self,
        timeout: Optional[float] = 5.0,
    ) -> Dict[str, Any]:
        """测试数据源连通性"""
        try:
            source = await self._get_current_datasource_name()
            r = await self._pool_service.execute_query(
                sql="SELECT 1",
                source=source,
                params=None,
                max_rows=1,
                timeout=timeout,
            )
            return {"ok": True, "result": r}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _get_connection_metrics(self) -> Dict[str, Any]:
        """获取连接池监控指标"""
        source = await self._get_current_datasource_name()

        try:
            # 连接状态指标
            connection_status_sql = """
            SELECT
                COUNT(*) AS TOTAL_CONNECTIONS,
                COUNT(CASE WHEN STATE = 'ACTIVE' THEN 1 END) AS ACTIVE_CONNECTIONS,
                COUNT(CASE WHEN STATE = 'IDLE' THEN 1 END) AS IDLE_CONNECTIONS,
                COUNT(CASE WHEN STATE NOT IN ('ACTIVE', 'IDLE') THEN 1 END) AS OTHER_CONNECTIONS
            FROM V$SESSIONS
            """
            status_result = await self._pool_service.execute_query(
                sql=connection_status_sql, source=source, max_rows=1
            )
            status_metrics = (
                status_result.get("result", [{}])[0]
                if status_result.get("result")
                else {}
            )

            # 计算连接使用率
            total_connections = status_metrics.get("TOTAL_CONNECTIONS", 0)
            active_connections = status_metrics.get("ACTIVE_CONNECTIONS", 0)
            connection_usage_rate = (
                (active_connections / total_connections * 100)
                if total_connections > 0
                else 0
            )

            # 连接健康指标 - 检查最近的连接错误和超时
            health_sql = """
            SELECT
                COUNT(CASE WHEN STATE = 'ACTIVE' THEN 1 END) AS HEALTHY_CONNECTIONS,
                COUNT(CASE WHEN STATE NOT IN ('ACTIVE', 'IDLE') THEN 1 END) AS UNHEALTHY_CONNECTIONS,
                COUNT(CASE WHEN STATE = 'TIMEOUT' THEN 1 END) AS CONNECTION_TIMEOUT_COUNT,
                COUNT(CASE WHEN STATE = 'ERROR' THEN 1 END) AS CONNECTION_ERROR_COUNT
            FROM V$SESSIONS
            WHERE CREATE_TIME >= (SYSDATE - INTERVAL '1' HOUR)
            """
            health_result = await self._pool_service.execute_query(
                sql=health_sql, source=source, max_rows=1
            )
            health_metrics = (
                health_result.get("result", [{}])[0]
                if health_result.get("result")
                else {}
            )

            # 合并所有指标
            metrics = {
                "total_connections": status_metrics.get("TOTAL_CONNECTIONS", 0),
                "active_connections": status_metrics.get("ACTIVE_CONNECTIONS", 0),
                "idle_connections": status_metrics.get("IDLE_CONNECTIONS", 0),
                "connection_usage_rate": round(connection_usage_rate, 2),
                "healthy_connections": health_metrics.get("HEALTHY_CONNECTIONS", 0),
                "unhealthy_connections": health_metrics.get("UNHEALTHY_CONNECTIONS", 0),
                "connection_timeout_count": health_metrics.get(
                    "CONNECTION_TIMEOUT_COUNT", 0
                ),
                "connection_error_count": health_metrics.get(
                    "CONNECTION_ERROR_COUNT", 0
                ),
            }

            return {
                "success": True,
                "connection_metrics": metrics,
                "timestamp": "SYSDATE",
            }

        except Exception as e:
            return {"success": False, "error": f"获取连接池监控指标失败: {str(e)}"}

    # ============================================================
    # MCP Tool 注册
    # ============================================================

    def _register_routes(self) -> None:
        """
        注册连接池运维相关的 MCP Tools。

        该方法仅负责把内部业务方法通过 `@self.mcp.tool` 暴露出去，
        不在此处编写 SQL 或复杂逻辑，便于后续维护与扩展。
        """

        @self.mcp.tool(requires_token_auth=True)
        async def pool_status():
            """
            返回各数据源连接池状态（总连接数、活跃数、空闲数、队列长度）。
            适用场景：排查连接池满、连接泄漏、性能瓶颈。

            Returns:
                Dict[str, Any]: 含 total_connections, active_connections, idle_connections, queue_size 等。
            """
            return await self._get_pool_status()

        @self.mcp.tool(requires_token_auth=True)
        async def test_connection(
            timeout: Optional[float] = 5.0,
        ):
            """
            对当前数据源执行 SELECT 1 探测连通性。
            适用场景：验证数据库是否可连、响应是否正常；排查连接失败问题。

            Args:
                timeout: 探测超时秒数，默认 5。

            Returns:
                Dict[str, Any]: 含 ok（是否连通）, result（成功时）, error（失败时错误信息）。
            """
            return await self._test_connection(timeout)

        @self.mcp.tool(requires_token_auth=True)
        async def get_connection_metrics():
            """
            返回连接池监控指标（连接数、使用率、超时/错误次数等）。
            适用场景：监控大盘、连接池健康度评估、排障。

            Returns:
                Dict[str, Any]: 含 success, connection_metrics（total/active/idle/usage_rate/
                    healthy/unhealthy/timeout_count/error_count）, timestamp, error。
            """
            return await self._get_connection_metrics()
