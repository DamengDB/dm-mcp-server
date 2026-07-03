import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TokenConfig(BaseModel):
    """Token 配置模型"""

    token: str = Field(..., description="Token 值（Base64 编码）")
    user_id: str = Field(..., description="用户 ID")
    datasource_id: uuid.UUID = Field(
        ..., description="绑定的数据源 UUID（强制一 Token 一数据源）"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="创建时间"
    )
    expires_at: datetime = Field(..., description="过期时间")
    last_used_at: Optional[datetime] = Field(None, description="最后使用时间")
    description: Optional[str] = Field(None, description="描述信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    ip_whitelist: Optional[List[str]] = Field(
        None, description="IP 白名单列表（支持单个 IP 或 CIDR）"
    )
    ip_blacklist: Optional[List[str]] = Field(
        None, description="IP 黑名单列表（支持单个 IP 或 CIDR）"
    )


class TokenAuthConfig(BaseModel):
    """Token 认证配置"""

    enabled: bool = Field(default=False, description="是否启用 Token 验证")
    cleanup_interval: int = Field(
        default=3600, description="清理过期 token 的间隔（秒）", ge=60
    )
    auto_cleanup: bool = Field(default=True, description="是否自动清理过期 token")
    default_expires_in: int = Field(
        default=604800, description="默认有效期（秒），7天", ge=60
    )
