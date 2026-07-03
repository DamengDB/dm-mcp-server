from typing import Literal

from pydantic import BaseModel


class DmPoolConfig(BaseModel):
    """
    连接池总配置

    支持方式：
    数据源配置已独立为 `DataSourcesConfig`（见 settings/datasource_config.py），
    便于控制“连接池行为配置”和“数据源列表配置”的职责边界。
    """

    enabled: bool = True

    # 读写分离开关：true 时 SELECT 默认走 replica
    read_write_split: bool = True

    # 负载均衡策略：rr / least / weighted
    load_balancing_strategy: Literal[
        "round_robin", "least_connections", "weighted_round_robin"
    ] = "least_connections"

    # 执行器行为
    default_source: str = "primary"
    max_retries: int = 1
    retry_backoff_ms: int = 100
