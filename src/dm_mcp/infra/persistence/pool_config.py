from typing import Literal

from pydantic import BaseModel


class DmPoolConfig(BaseModel):
    """
    连接池行为配置

    数据源配置已持久化到数据库（见 core/db/models.py DataSourceModel），
    此类仅控制"连接池行为配置"（路由策略、重试等），支持运行时热更新。
    """

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
