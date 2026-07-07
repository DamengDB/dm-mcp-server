"""Metrics 指标模块测试模块"""

import pytest
from dm_mcp.infra.metrics.metrics import DemoMetrics, PoolQueryMetrics, metric_field
from dm_mcp.infra.metrics import MetricsContext


class TestMetricField:
    """metric_field 辅助函数测试类"""

    def test_metric_field_default(self):
        """测试默认 metric_field"""
        field = metric_field("test help")
        metadata = field.metadata
        assert metadata["metric"] is True
        assert metadata["help"] == "test help"
        assert metadata["type"] == "gauge"
        assert field.default == 0

    def test_metric_field_counter(self):
        """测试 counter 类型"""
        field = metric_field("counter help", "counter")
        assert field.metadata["type"] == "counter"

    def test_metric_field_histogram(self):
        """测试 histogram 类型"""
        field = metric_field("histogram help", "histogram")
        assert field.metadata["type"] == "histogram"


class TestDemoMetrics:
    """DemoMetrics 测试类"""

    def test_create_demo_metrics(self):
        """测试创建演示指标"""
        metrics = DemoMetrics()
        assert metrics.counter == 0

    def test_demo_metrics_with_values(self):
        """测试带值的演示指标"""
        metrics = DemoMetrics(counter=42)
        assert metrics.counter == 42

    def test_demo_metrics_increment(self):
        """测试指标递增"""
        metrics = DemoMetrics()
        metrics.counter += 1
        assert metrics.counter == 1


class TestPoolQueryMetrics:
    """PoolQueryMetrics 测试类"""

    def test_create_pool_metrics_defaults(self):
        """测试创建默认连接池指标"""
        metrics = PoolQueryMetrics()
        assert metrics.source == "primary"
        assert metrics.is_read_only is False
        assert metrics.lb_strategy == "round_robin"
        assert metrics.sql_type == "query"
        assert metrics.status == "ok"
        assert metrics.total == 0
        assert metrics.error == 0
        assert metrics.retries == 0
        assert metrics.duration_ms == 0
        assert metrics.active_connections == 0

    def test_create_pool_metrics_custom(self):
        """测试创建自定义连接池指标"""
        metrics = PoolQueryMetrics(
            source="replica1",
            is_read_only=True,
            lb_strategy="least_connections",
            sql_type="update",
            status="error",
            total=100,
            error=5,
            retries=3,
            duration_ms=150.5,
            active_connections=10,
        )
        assert metrics.source == "replica1"
        assert metrics.is_read_only is True
        assert metrics.lb_strategy == "least_connections"
        assert metrics.sql_type == "update"
        assert metrics.status == "error"
        assert metrics.total == 100
        assert metrics.error == 5
        assert metrics.retries == 3
        assert metrics.duration_ms == 150.5
        assert metrics.active_connections == 10


class TestMetricsContext:
    """MetricsContext 测试类"""

    def test_create_metrics_context(self):
        """测试创建指标上下文"""
        ctx = MetricsContext()
        assert ctx.metadata == {}
        assert ctx.collect() == []

    def test_metrics_context_with_metadata(self):
        """测试带元数据的指标上下文"""
        ctx = MetricsContext(metadata={"user_id": "test_user"})
        assert ctx.metadata["user_id"] == "test_user"

    def test_record_metric(self):
        """测试记录指标"""
        ctx = MetricsContext()
        metrics = DemoMetrics(counter=10)
        ctx.record(metrics)
        collected = ctx.collect()
        assert len(collected) == 1
        assert collected[0].counter == 10

    def test_record_multiple_metrics(self):
        """测试记录多个指标"""
        ctx = MetricsContext()
        ctx.record(DemoMetrics(counter=1))
        ctx.record(PoolQueryMetrics(total=100))
        assert len(ctx.collect()) == 2

    def test_collect_empty(self):
        """测试收集空指标"""
        ctx = MetricsContext()
        assert ctx.collect() == []

    def test_get_without_context(self):
        """测试无上下文时返回新实例"""
        import dm_mcp.infra.metrics.metrics_context as mc_module

        orig_default = mc_module._metrics_context_var.get()
        try:
            mc_module._metrics_context_var.set(None)
            ctx = MetricsContext.get()
            assert isinstance(ctx, MetricsContext)
        finally:
            mc_module._metrics_context_var.set(orig_default)

    def test_get_with_context(self):
        """测试有上下文时返回正确对象"""
        ctx = MetricsContext(metadata={"test": "value"})
        import dm_mcp.infra.metrics.metrics_context as mc_module

        orig_default = mc_module._metrics_context_var.get()
        try:
            token = mc_module._metrics_context_var.set(ctx)
            try:
                result = MetricsContext.get()
                assert result.metadata["test"] == "value"
            finally:
                mc_module._metrics_context_var.reset(token)
        finally:
            mc_module._metrics_context_var.set(orig_default)

    def test_as_current_context_manager(self):
        """测试上下文管理器"""
        ctx = MetricsContext(metadata={"key": "value"})
        import dm_mcp.infra.metrics.metrics_context as mc_module

        orig_default = mc_module._metrics_context_var.get()
        try:
            with MetricsContext.as_current(ctx):
                result = MetricsContext.get()
                assert result.metadata["key"] == "value"
        finally:
            mc_module._metrics_context_var.set(orig_default)

    def test_as_current_restores_previous(self):
        """测试上下文管理器退出后恢复之前状态"""
        ctx1 = MetricsContext(metadata={"source": "ctx1"})
        import dm_mcp.infra.metrics.metrics_context as mc_module

        orig_default = mc_module._metrics_context_var.get()
        try:
            token = mc_module._metrics_context_var.set(ctx1)
            try:
                ctx2 = MetricsContext(metadata={"source": "ctx2"})
                with MetricsContext.as_current(ctx2):
                    assert MetricsContext.get().metadata["source"] == "ctx2"
                # 退出后应该恢复 ctx1
                assert MetricsContext.get().metadata["source"] == "ctx1"
            finally:
                mc_module._metrics_context_var.reset(token)
        finally:
            mc_module._metrics_context_var.set(orig_default)
