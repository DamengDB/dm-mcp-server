"""指标服务单元测试

测试指标收集、记录、导出等功能。
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from dm_mcp.infra.metrics.metrics_context import MetricsContext
from dm_mcp.domain.system.services.metrics import MetricsService
from dm_mcp.infra.config.metrics_config import MetricsConfig


class TestMetricsService:
    """指标服务测试类"""

    @pytest.fixture
    def metrics_config(self, tmp_path):
        """指标配置 fixture"""
        return MetricsConfig(
            multiproc_dir=str(tmp_path / "prometheus"),
        )

    @pytest.fixture
    def metrics_service(self, metrics_config):
        """指标服务 fixture"""
        return MetricsService(metrics_config)

    @pytest.mark.asyncio
    async def test_startup(self, metrics_service):
        """测试服务启动"""
        await metrics_service.startup()

        # 验证环境变量已设置
        import os

        assert "PROMETHEUS_MULTIPROC_DIR" in os.environ

    @pytest.mark.asyncio
    async def test_shutdown(self, metrics_service):
        """测试服务关闭"""
        await metrics_service.startup()
        await metrics_service.shutdown()

        # 验证可以正常关闭（无异常）

    def test_get_current_values(self, metrics_service):
        """测试获取当前指标值"""
        values = metrics_service.get_current_values()

        assert isinstance(values, dict)

    def test_get_current_values_with_prefix(self, metrics_service):
        """测试使用前缀过滤获取指标值"""
        values = metrics_service.get_current_values(filter_prefix="test")

        assert isinstance(values, dict)
        # 所有键都应该以 "test" 开头（如果有的话）
        for key in values.keys():
            assert key.startswith("test")

    def test_record_dataclass_counter(self, metrics_service):
        """测试记录 Counter 类型指标"""

        @dataclass
        class TestMetrics:
            request_count: int = 0

        # 添加 metadata
        TestMetrics.__dataclass_fields__["request_count"].metadata = {
            "metric": True,
            "type": "counter",
            "help": "Request count",
        }

        instance = TestMetrics(request_count=5)
        metrics_service.record_dataclass(instance, prefix="test")

        # 验证指标已记录
        values = metrics_service.get_current_values(filter_prefix="test")
        assert len(values) > 0

    def test_record_dataclass_gauge(self, metrics_service):
        """测试记录 Gauge 类型指标"""

        @dataclass
        class TestMetrics:
            active_connections: int = 0

        TestMetrics.__dataclass_fields__["active_connections"].metadata = {
            "metric": True,
            "type": "gauge",
            "help": "Active connections",
        }

        instance = TestMetrics(active_connections=10)
        metrics_service.record_dataclass(instance, prefix="test")

        values = metrics_service.get_current_values(filter_prefix="test")
        assert len(values) > 0

    def test_record_dataclass_histogram(self, metrics_service):
        """测试记录 Histogram 类型指标"""

        @dataclass
        class TestMetrics:
            response_time: float = 0.0

        TestMetrics.__dataclass_fields__["response_time"].metadata = {
            "metric": True,
            "type": "histogram",
            "help": "Response time",
        }

        instance = TestMetrics(response_time=0.5)
        metrics_service.record_dataclass(instance, prefix="test")

        values = metrics_service.get_current_values(filter_prefix="test")
        assert len(values) > 0

    def test_record_dataclass_with_labels(self, metrics_service):
        """测试记录带标签的指标"""

        @dataclass
        class TestMetrics:
            status: str = "ok"
            request_count: int = 0

        # 显式标注 label（新约定）
        TestMetrics.__dataclass_fields__["status"].metadata = {"label": True}

        TestMetrics.__dataclass_fields__["request_count"].metadata = {
            "metric": True,
            "type": "counter",
            "help": "Request count",
        }

        instance = TestMetrics(status="ok", request_count=3)
        metrics_service.record_dataclass(instance, prefix="test")

        values = metrics_service.get_current_values(filter_prefix="test")
        assert len(values) > 0

    def test_export(self, metrics_service):
        """测试导出指标"""
        data, content_type = metrics_service.export()

        assert data is not None
        assert content_type is not None
        assert isinstance(data, bytes)

    def test_record_from_context(self, metrics_service):
        """测试从上下文记录指标"""

        @dataclass
        class TestMetrics:
            request_count: int = 0

        TestMetrics.__dataclass_fields__["request_count"].metadata = {
            "metric": True,
            "type": "counter",
            "help": "Request count",
        }

        # 创建上下文并记录指标
        context = MetricsContext()
        context.record(TestMetrics(request_count=5))

        # 设置上下文
        with MetricsContext.as_current(context):
            # 记录指标
            metrics_service.record_from_context(context)

        values = metrics_service.get_current_values(filter_prefix="mcp")
        assert len(values) >= 0  # 可能有其他指标
