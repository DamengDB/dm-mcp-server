import json
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Type, TypeVar

from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import (
    BaseSettings,
    CliSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from .database_config import DatabaseConfig
from .logging_config import LoggingConfig
from .metrics_config import MetricsConfig
from .server_config import ServerConfig


class Settings(BaseSettings):

    app_secret: SecretStr = SecretStr("")

    server: ServerConfig = Field(default=ServerConfig())
    database: DatabaseConfig = Field(default=DatabaseConfig())
    metrics: MetricsConfig = Field(default=MetricsConfig())
    logging: LoggingConfig = Field(default=LoggingConfig())

    @field_validator("app_secret")
    @classmethod
    def _validate_app_secret(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value():
            raise ValueError("APP_SECRET 是必填项")
        return v

    # 配置 Pydantic
    model_config = SettingsConfigDict(
        env_file=[".env", ".env.local", ".env.prod"],
        env_file_encoding="utf-8",
        extra="ignore",
        env_nested_delimiter="__",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,  # 1. 构造函数传入的值 (优先级最高)
            CliSettingsSource(settings_cls, cli_parse_args=True),  # 2. 命令行参数
            env_settings,  # 3. 环境变量
            dotenv_settings,  # 4. .env 文件
            file_secret_settings,  # 5. Docker secrets 等
        )

    def to_env(
        self, prefix: str = "", upper: bool = True, separator: str = "__"
    ) -> dict[str, str]:
        """
        导出为扁平的环境变量字典，自动解密 SecretStr
        """
        env_vars = {}

        def _json_encoder(obj):
            if isinstance(obj, SecretStr):
                # 遇到 SecretStr，解密并返回字符串
                return obj.get_secret_value()
            if isinstance(obj, uuid.UUID):
                # 遇到 UUID，转换为字符串
                return str(obj)
            if isinstance(obj, set):
                # 遇到 set，转成 list
                return list(obj)
            if isinstance(obj, BaseModel):
                # 支持 Pydantic 模型（ DataSourceModel / DmPoolConfig）
                return obj.model_dump()
            if is_dataclass(obj):
                # 支持 dataclass
                return asdict(obj)
            if hasattr(obj, "get_secret_value"):
                # SecretStr 支持（保留已有行为）
                return obj.get_secret_value()
            if isinstance(obj, Path):
                # 支持 Path / WindowsPath / PosixPath
                return str(obj)

            # 其他不认识的类型，抛出异常
            raise TypeError(f"类型 {type(obj)} 不可序列化")

        def _recurse(model: BaseModel, current_prefix: str):
            # 使用 type(model) 避免 Pylance 警告
            for field_name in type(model).model_fields.keys():
                value = getattr(model, field_name)

                # 生成键名: server.port -> SERVER__PORT
                key = (
                    f"{current_prefix}{separator}{field_name}"
                    if current_prefix
                    else field_name
                )
                if upper:
                    key = key.upper()

                # ------- 递归子模型 -------
                if isinstance(value, BaseModel):
                    _recurse(value, key)
                    continue
                # 简单类型直接转字符串（不做 JSON）
                elif isinstance(value, (str, int, float, bool)) or value is None:
                    env_vars[key] = "" if value is None else str(value)
                    continue
                elif isinstance(value, SecretStr):
                    env_vars[key] = value.get_secret_value()
                # elif isinstance(value, (list, dict, tuple, set)):
                #     if isinstance(value, set):
                #         value = list(value)
                #     env_vars[key] = json.dumps(value, default=_json_encoder)
                # elif value is not None:
                #     env_vars[key] = str(value)
                else:  # 复杂类型 Pydantic、dataclass、list / tuple / dict / set、SecretStr
                    # 统一使用 JSON 序列化
                    env_vars[key] = json.dumps(value, default=_json_encoder)

        _recurse(self, prefix)

        return env_vars


T_Settings = TypeVar("T_Settings", bound=Settings)
