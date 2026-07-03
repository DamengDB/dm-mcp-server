from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class MetricsConfig(BaseModel):

    # Switch & Provider
    enabled: bool = False

    multiproc_dir: str = Field(
        default="metrics",
    )
    http_port: int = 3001
    http_path: str = "/metrics"
