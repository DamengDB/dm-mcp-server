"""MetricsConfig 指标配置测试"""

import pytest
from dm_mcp.infra.config.metrics_config import MetricsConfig


class TestMetricsConfig:
    """MetricsConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = MetricsConfig()
        assert config.enabled is False
        assert config.multiproc_dir == "metrics"
        assert config.http_port == 3001
        assert config.http_path == "/metrics"

    def test_custom_values(self):
        """测试自定义值"""
        config = MetricsConfig(
            enabled=True,
            multiproc_dir="/var/run/prometheus",
            http_port=9090,
            http_path="/custom/metrics",
        )
        assert config.enabled is True
        assert config.multiproc_dir == "/var/run/prometheus"
        assert config.http_port == 9090
        assert config.http_path == "/custom/metrics"

    def test_path_validation(self):
        """测试路径格式"""
        config = MetricsConfig(http_path="/metrics")
        assert config.http_path == "/metrics"

        config = MetricsConfig(http_path="/custom/metrics")
        assert config.http_path == "/custom/metrics"
