"""指标定义模块

提供指标数据类的定义，用于收集和记录系统指标。
"""

from dataclasses import dataclass, field


def metric_field(help_text: str, type: str = "gauge"):
    """创建指标字段

    Args:
        help_text: 指标帮助文本
        type: 指标类型，可选值："gauge" | "counter" | "histogram"

    Returns:
        field: 数据类字段对象
    """
    # 注意：指标字段必须是数值；label 字段不要使用该函数
    return field(default=0, metadata={"metric": True, "help": help_text, "type": type})


@dataclass
class DemoMetrics:
    """演示指标

    用于演示的指标数据类。
    """

    counter: int = metric_field("This is a counter metric", "counter")


# ============================================================
# Pool Metrics 暂放这里：后续可按需抽离
# ============================================================
@dataclass
class PoolQueryMetrics:
    """连接池执行指标

    用于记录连接池执行相关的指标，包括标签和数值。
    Prometheus指标前缀：db_pool
    """

    # labels（只用于 Prometheus label，必须可转成 str；不要带 help，否则会被误判为 metric 字段）
    source: str = field(default="primary", metadata={"label": True})
    is_read_only: bool = field(default=False, metadata={"label": True})
    lb_strategy: str = field(default="round_robin", metadata={"label": True})
    sql_type: str = field(default="query", metadata={"label": True})
    status: str = field(default="ok", metadata={"label": True})

    # values（必须是数值）
    total: int = metric_field("执行总次数", "counter")
    error: int = metric_field("失败次数", "counter")
    retries: int = metric_field("重试次数", "counter")
    duration_ms: float = metric_field("耗时(ms)", "histogram")
    active_connections: int = metric_field("活跃连接数", "gauge")
