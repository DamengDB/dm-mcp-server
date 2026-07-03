import os
from typing import ClassVar, Literal, Optional

from pydantic import BaseModel, Field, SecretStr


class ServerConfig(BaseModel):
    # 不通过环境变量/CLI 配置（发布时只需同步此处版本号）
    name: ClassVar[str] = "dameng-mcp-server"
    version: ClassVar[str] = "0.1.0"

    host: str = "localhost"
    port: int = Field(default=18081, ge=1, le=65535)
    transport: Literal["stdio", "http"] = "stdio"
    static_path: str = os.path.join(os.getcwd(), "resources", "static")

    base_url: str = "/dm-mcp"
    frontend_url: Optional[str] = ""

    workers: int = 1

    session_secret: SecretStr = SecretStr(
        "qYtOxg/?&QD(+]2+5RHGhwg6Oi423l=FrX4@'OzHqRXC(2e$N-g1gUcxpTcY+KF"
    )

    debug: bool = True
    audit_enabled: bool = True
