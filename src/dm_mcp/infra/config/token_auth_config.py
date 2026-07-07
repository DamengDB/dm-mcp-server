import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class TokenConfig(BaseModel):
    """Token 配置模型"""

    token: str = Field(..., description="Token 值（Base64 编码，仅创建时返回 / Bearer 认证用）")
    token_id: str = Field(..., description="管理用短码（12 字符 base62），URL 中使用")
    user_id: str = Field(..., description="用户 ID")
    datasource_ids: list[str] = Field(
        default_factory=list, description="可访问的数据源 UUID 列表"
    )
    default_datasource_id: str | None = Field(
        None, description="默认数据源 UUID"
    )
    ssh_host_ids: list[str] = Field(
        default_factory=list, description="可访问的 SSH 主机 UUID 列表"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="创建时间"
    )
    expires_at: datetime = Field(..., description="过期时间")
    last_used_at: datetime | None = Field(None, description="最后使用时间")
    name: str = Field(..., min_length=1, description="Token 名称（必填，非空）")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
    ip_whitelist: list[str] | None = Field(
        None, description="IP 白名单列表（支持单个 IP 或 CIDR）"
    )
    ip_blacklist: list[str] | None = Field(
        None, description="IP 黑名单列表（支持单个 IP 或 CIDR）"
    )
