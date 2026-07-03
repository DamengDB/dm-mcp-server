"""指标监控服务模块

提供服务功能：
- Prometheus 指标的收集和管理
- 从 MetricsContext 自动记录指标
- 支持 Counter、Gauge、Histogram 指标类型
- 指标导出（Prometheus 格式）
- HTTP 服务器支持（stdio 模式）
"""

import dataclasses
import os
import time
from typing import Any, Dict

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    start_http_server,
)
from prometheus_client.parser import text_string_to_metric_families

from dm_mcp.core.metrics.metrics_context import MetricsContext
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.settings.metrics_config import MetricsConfig

from .base_service import BaseService


class MetricsService(BaseService):
    """指标监控服务

    管理 Prometheus 指标的收集、记录和导出。

    主要功能：
    - Prometheus 指标的收集和管理
    - 从 MetricsContext 自动记录指标
    - 支持 Counter、Gauge、Histogram 指标类型
    - 指标导出（Prometheus 格式）
    - HTTP 服务器支持（stdio 模式）
    """

    def __init__(self, metrics_config: MetricsConfig):
        self.registry = CollectorRegistry()
        self.metrics_config = metrics_config
        self._metrics_cache: Dict[str, Any] = {}

    async def startup(self) -> None:
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = self.metrics_config.multiproc_dir

    async def shutdown(self) -> None:
        pass

    def get_current_values(self, filter_prefix: str = "mcp") -> Dict[str, Any]:
        """读取当前所有指标的数值

        读取当前所有指标的数值，返回给 LLM 使用的字典。

        Args:
            filter_prefix: 只返回以此前缀开头的业务指标（避免返回 python_gc_ 等噪音），默认 "mcp"

        Returns:
            指标名称到数值的字典
        """
        # 1. 获取原始文本数据 (这是获取当前值的最通用方法)
        # 虽然有点绕，但直接遍历 registry.collect() 的结构比较复杂
        raw_data = generate_latest(self.registry).decode("utf-8")

        result = {}

        # 2. 解析 MetricFamily
        for family in text_string_to_metric_families(raw_data):
            if not family.name.startswith(filter_prefix):
                continue

            # 3. 提取样本值
            for sample in family.samples:
                # sample 结构: Sample(name, labels, value, timestamp, exemplar)

                # 如果有 label，把 label 拼接到名字里，方便 LLM 理解
                # 例如: mcp_request_count{status="error"}
                if sample.labels:
                    label_str = ",".join(
                        [f'{k}="{v}"' for k, v in sample.labels.items()]
                    )
                    key = f"{sample.name}{{{label_str}}}"
                else:
                    key = sample.name

                result[key] = sample.value

        return result

    def record_from_context(self, context: MetricsContext):
        """从当前上下文自动记录所有指标

        Args:
            context: 指标上下文（可选，如果不提供则从全局获取）
        """
        ctx = MetricsContext.get()

        # 1. 准备 Labels (从 metadata 提取)
        # 这里你可以做一个 filter，或者全部放入
        extra_labels = {k: str(v) for k, v in ctx.metadata.items()}

        # 2. 遍历所有用户提交的指标快照
        for snapshot in ctx.collect():
            # record_dataclass 是通用的，它通过反射读取 dataclass 字段
            # 所以它支持 DemoMetrics，也支持用户定义的 OrderMetrics
            self.record_dataclass(snapshot, extra_labels=extra_labels)

    def record_dataclass(
        self, instance: Any, prefix: str = "mcp", extra_labels: Dict[str, str] = {}
    ):
        """从 dataclass 实例记录指标

        自动识别 dataclass 中的指标字段和标签字段，并记录到 Prometheus。

        Args:
            instance: dataclass 实例
            prefix: 指标名称前缀，默认 "mcp"
            extra_labels: 额外的标签字典
        """
        cls = type(instance)
        cls_name = cls.__name__

        # 1. 分离 Label 字段和 Metric 字段
        metric_fields = []
        label_fields = {}

        for f in dataclasses.fields(instance):
            val = getattr(instance, f.name)
            # 指标字段：必须显式标注 metric=True（避免字符串字段因为带 help 被误判为 metric）
            if f.metadata.get("metric") is True:
                metric_fields.append(f)
            # label 字段：显式标注 label=True
            elif f.metadata.get("label") is True:
                # label 统一转 str，避免 bool/int 等类型被漏掉
                label_fields[f.name] = "" if val is None else str(val)
            # 兼容旧逻辑：如果用户没有标注 label，但字段值是 str，则仍作为 label
            elif isinstance(val, str):
                label_fields[f.name] = val

        # 合并标签：Dataclass 自身标签 > Context 传入标签
        final_labels = {**extra_labels, **label_fields}
        label_names = list(final_labels.keys())
        label_values = list(final_labels.values())

        # 2. 遍历指标字段
        for f in metric_fields:
            # 获取当前值 (这是这一次任务产生的数值，比如 "本任务处理了5行")
            metric_value = getattr(instance, f.name)

            if metric_value is None or metric_value == 0:
                continue

            metric_name = f"{prefix}_{f.name}"
            cache_key = f"{cls_name}.{f.name}"

            # 获取 metadata 中的类型，默认为 gauge
            metric_type = f.metadata.get("type", "gauge")
            help_text = f.metadata.get("help", "No description")

            # --- Lazy Registration ---
            if cache_key not in self._metrics_cache:
                if metric_type == "counter":
                    # 【关键点 1】创建真正的 Counter 对象
                    m_obj = Counter(
                        metric_name, help_text, label_names, registry=self.registry
                    )
                elif metric_type == "histogram":
                    # Histogram 默认 buckets 可通过 buckets=[...] 参数调整，这里使用默认值
                    m_obj = Histogram(
                        metric_name, help_text, label_names, registry=self.registry
                    )
                else:
                    # Gauge 对象
                    m_obj = Gauge(
                        metric_name, help_text, label_names, registry=self.registry
                    )

                self._metrics_cache[cache_key] = m_obj

            # --- Update Value ---
            m_obj = self._metrics_cache[cache_key]

            # 获取带 label 的指标实例
            item = m_obj.labels(*label_values) if label_names else m_obj

            # 【关键点 2】根据类型决定行为
            if metric_type == "counter":
                # Counter: 累加增量 (Delta)
                item.inc(metric_value)
            elif metric_type == "histogram":
                # Histogram: 观测样本 (Observation)
                # 例如：记录一次 API 耗时 0.5s
                item.observe(metric_value)
            else:
                # Gauge: 设置快照 (Snapshot)
                item.set(metric_value)

    def export(self):
        """导出指标数据（Prometheus 格式）

        Returns:
            (data, content_type) 元组，data 是指标数据，content_type 是内容类型
        """
        data = generate_latest(self.registry)
        return data, CONTENT_TYPE_LATEST

    def export_metrics_snapshot(self, filter_prefix: str = "") -> Dict[str, Any]:
        """导出指标快照（数值型，便于 MCP/LLM 使用）。"""
        return {
            "success": True,
            "metrics": self.get_current_values(filter_prefix=filter_prefix),
            "timestamp": time.time(),
        }

    def start_http_server(self):
        """启动 HTTP 服务器（用于 stdio 模式）

        在指定的端口上启动 Prometheus HTTP 服务器，用于导出指标。
        """
        start_http_server(self.metrics_config.http_port, registry=self.registry)


class MetricsServiceFactory(ServiceFactory):
    """指标监控服务工厂

    负责创建和配置 MetricsService 实例。
    """

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="metrics_service",
            service_type=MetricsService,
            description="指标监控服务",
            author="DM MCP Team",
            dependencies=[],
            priority=20,
        )

    def create(self, settings, **deps) -> MetricsService:
        return MetricsService(settings.metrics)
