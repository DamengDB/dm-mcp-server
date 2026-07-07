from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="日志级别"
    )
    log_dir: Path = Field(default=Path("logs"), description="日志文件存储目录")

    # 开关配置
    enable_console: bool = Field(default=True, description="是否启用控制台输出")
    enable_file: bool = Field(default=True, description="是否启用文件日志")
    enable_audit: bool = Field(default=True, description="是否启用审计日志")

    # Loguru 特定配置
    rotation: str = Field(
        default="10 MB", description="日志切割大小 (例如: '10 MB', '500 MB', '12:00')"
    )
    retention: str = Field(
        default="30 days", description="日志保留时间 (例如: '1 week', '30 days')"
    )
    compression: Literal[
        "zip", "gz", "bz2", "xz", "lzma", "tar", "tar.gz", "tar.bz2", "tar.xz"
    ] | None = Field(default="zip", description="压缩格式。设为 null/None 则不压缩。")

    # 可选的高级配置
    audit_file: Path | None = Field(
        default=None, description="自定义审计日志路径，留空则自动在 log_dir 下生成"
    )

    # --- 校验器 ---
    @classmethod
    @field_validator("audit_file", mode="before")
    def empty_audit_file_to_none(cls, v):
        """环境变量里常写 LOGGING__AUDIT_FILE= 表示「留空」，需视为未设置。

        若把空串交给 Path，会变成 Path('.')，在 Docker 工作目录 /app 下会把审计日志
        写到「当前目录」/app，触发 IsADirectoryError。
        """
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @classmethod
    @field_validator("level", mode="before")
    def upper_case_level(cls, v: str):
        return v.upper() if isinstance(v, str) else v

    @classmethod
    @field_validator("log_dir", mode="after")
    def create_dir_if_missing(cls, v: Path):
        """可选：在加载配置时自动创建目录（或者仅仅确保它是有效路径）"""
        # 注意：在这里创建目录有副作用，但在某些简单应用中很方便
        # 如果你不希望在 Config 初始化时有副作用，可以删掉这行
        if not v.exists():
            try:
                v.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass  # 忽略权限错误，留给 logger 初始化时报错
        return v
