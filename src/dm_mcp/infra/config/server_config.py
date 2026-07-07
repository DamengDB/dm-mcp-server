import os
from typing import ClassVar, Literal

from pydantic import BaseModel, Field


class ServerConfig(BaseModel):
    # 不通过环境变量/CLI 配置（发布时只需同步此处版本号）
    name: ClassVar[str] = "dameng-mcp-server"
    version: ClassVar[str] = "0.2.0"

    host: str = "localhost"
    port: int = Field(default=18081, ge=1, le=65535)
    transport: Literal["stdio", "http"] = "stdio"
    static_path: str = os.path.join(os.getcwd(), "resources", "web")
    docs_path: str = os.path.join(os.getcwd(), "resources", "docs")
    cli_path: str = os.path.join(os.getcwd(), "resources", "cli", "latest")

    base_url: str = "/dm-mcp"
    frontend_url: str | None = ""

    workers: int = 1

    debug: bool = True
    audit_enabled: bool = True
