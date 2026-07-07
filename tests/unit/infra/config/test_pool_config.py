"""DmPoolConfig 连接池配置测试"""

import pytest
from dm_mcp.infra.persistence.pool_config import DmPoolConfig


class TestDmPoolConfig:
    """DmPoolConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = DmPoolConfig()
        assert config.read_write_split is True
        assert config.load_balancing_strategy == "least_connections"
        assert config.default_source == "primary"
        assert config.max_retries == 1
        assert config.retry_backoff_ms == 100

    def test_custom_values(self):
        """测试自定义值"""
        config = DmPoolConfig(
            read_write_split=False,
            load_balancing_strategy="round_robin",
            default_source="replica1",
            max_retries=3,
            retry_backoff_ms=500,
        )
        assert config.read_write_split is False
        assert config.load_balancing_strategy == "round_robin"
        assert config.default_source == "replica1"
        assert config.max_retries == 3
        assert config.retry_backoff_ms == 500


class TestDmPoolConfigLoadBalancing:
    """负载均衡策略测试"""

    def test_round_robin(self):
        """测试轮询策略"""
        config = DmPoolConfig(load_balancing_strategy="round_robin")
        assert config.load_balancing_strategy == "round_robin"

    def test_least_connections(self):
        """测试最少连接策略"""
        config = DmPoolConfig(load_balancing_strategy="least_connections")
        assert config.load_balancing_strategy == "least_connections"

    def test_weighted_round_robin(self):
        """测试加权轮询策略"""
        config = DmPoolConfig(load_balancing_strategy="weighted_round_robin")
        assert config.load_balancing_strategy == "weighted_round_robin"

    def test_invalid_strategy(self):
        """测试无效策略"""
        with pytest.raises(Exception):
            DmPoolConfig(load_balancing_strategy="invalid")


class TestDmPoolConfigValidation:
    """验证测试"""

    def test_retry_backoff_range(self):
        """测试重试间隔范围"""
        config = DmPoolConfig(retry_backoff_ms=0)
        assert config.retry_backoff_ms == 0

        config = DmPoolConfig(retry_backoff_ms=10000)
        assert config.retry_backoff_ms == 10000
