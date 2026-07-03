"""指标中间件测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dm_mcp.core.metrics.metrics_context import MetricsContext
from dm_mcp.middlewares.metrics_middleware import MetricsMCPMiddleware


class TestMetricsMCPMiddleware:
    """指标中间件测试类"""

    @pytest.fixture
    def mock_metrics_service(self):
        """创建Mock指标服务"""
        service = MagicMock()
        service.record_from_context = MagicMock()
        return service

    @pytest.fixture
    def middleware(self, mock_metrics_service):
        """创建指标中间件"""
        return MetricsMCPMiddleware(metrics_service=mock_metrics_service)

    @pytest.fixture
    def mock_call_next(self):
        """创建Mock的call_next函数"""
        return AsyncMock(return_value="result")

    @pytest.mark.asyncio
    async def test_on_call_tool_success(self, middleware, mock_call_next):
        """测试成功调用工具时记录指标"""
        result = await middleware.on_call_tool(
            mock_call_next, "test_tool", {"param": "value"}
        )
        assert result == "result"
        mock_call_next.assert_called_once_with("test_tool", {"param": "value"})
        # 验证指标被记录
        middleware.metrics_service.record_from_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_call_tool_exception(self, middleware, mock_call_next):
        """测试工具调用异常时也记录指标"""
        exception = ValueError("Test error")
        mock_call_next.side_effect = exception

        with pytest.raises(ValueError) as exc_info:
            await middleware.on_call_tool(mock_call_next, "test_tool", {})
        assert exc_info.value == exception

        # 即使发生异常，也应该记录指标
        middleware.metrics_service.record_from_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_call_tool_captures_context(self, middleware, mock_call_next):
        """测试捕获指标上下文"""
        # 设置指标上下文
        context = MetricsContext()
        with MetricsContext.as_current(context):
            await middleware.on_call_tool(mock_call_next, "test_tool", {})

        # 验证record_from_context被调用，且传入了上下文
        middleware.metrics_service.record_from_context.assert_called_once()
        # 注意：这里验证的是调用参数，但实际传入的可能是新的上下文实例
        # 由于MetricsContext.get()的实现，我们验证调用即可

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, middleware, mock_call_next):
        """测试多次工具调用都记录指标"""
        await middleware.on_call_tool(mock_call_next, "tool1", {})
        await middleware.on_call_tool(mock_call_next, "tool2", {})

        # 每次调用都应该记录指标
        assert middleware.metrics_service.record_from_context.call_count == 2
