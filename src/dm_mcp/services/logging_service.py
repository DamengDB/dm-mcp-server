"""日志服务模块

提供服务功能：
- Loguru 日志系统的配置和管理
- 文件日志切割和保留策略
- 审计日志独立管理
- 标准库 logging 拦截和重定向
- Uvicorn 日志配置
"""

import logging
import sys
from pathlib import Path
from typing import Any, Dict

from loguru import logger

from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.services import BaseService
from dm_mcp.settings.logging_config import LoggingConfig

# --- 日志格式 ---
FMT_STD = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "| <level>{level: <8}</level> | "
    "<cyan>{extra[name]}</cyan>:"
    "<cyan>{function}</cyan>:"
    "<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

FMT_AUDIT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
    "| AUDIT    | "
    "<cyan>{extra[name]}</cyan>:"
    "<cyan>{function}</cyan>:"
    "<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)


class InterceptHandler(logging.Handler):
    """拦截标准库 logging 并重定向到 loguru（辅助类）

    将 Python 标准库 logging 的日志记录重定向到 Loguru 日志系统，
    实现统一的日志管理。
    """

    def emit(self, record):
        """处理日志记录并转发到 Loguru

        Args:
            record: 标准库 logging 的 LogRecord 对象
        """
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # 获取调用栈，确保文件名显示正确
        frame = logging.currentframe()
        depth = 2
        while frame is not None and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        # 1. 获取 logger 名称 (例如 "uvicorn.error" 或 "multiprocessing")
        logger_name = record.name

        # 2. 如果是 root logger (name="root")，通常显示为模块名可能更有意义，
        # 但为了保持格式统一，我们直接使用 record.name

        # 3. 统一绑定 name
        logger.opt(depth=depth, exception=record.exc_info).bind(name=logger_name).log(
            level, record.getMessage()
        )


class LoggingService(BaseService):
    """日志服务

    管理 Loguru 日志系统的配置和运行。

    主要功能：
    - Loguru 日志系统配置
    - 文件日志切割和保留策略
    - 审计日志独立管理
    - 标准库 logging 拦截和重定向
    - Uvicorn 日志配置
    """

    def __init__(self, config: LoggingConfig):
        # 我们需要 logging 的具体配置
        self.config = config
        self._initialized = False

    # --- 过滤器 (静态方法，因为 loguru 需要无状态的 callable) ---
    @staticmethod
    def _is_audit(record):
        """判断是否为审计日志

        Args:
            record: Loguru 日志记录

        Returns:
            True 如果是审计日志，False 否则
        """
        return record["extra"].get("is_audit", False)

    @staticmethod
    def _is_app_log(record):
        """判断是否为应用日志

        Args:
            record: Loguru 日志记录

        Returns:
            True 如果是应用日志（非审计日志），False 否则
        """
        return not LoggingService._is_audit(record)

    @staticmethod
    def _patcher(record):
        """确保 name 存在于 extra 中

        Loguru 的 patcher，用于为所有日志记录添加 name 字段。

        Args:
            record: Loguru 日志记录
        """
        if "name" not in record["extra"]:
            record["extra"]["name"] = record["name"]

    # --- 生命周期 ---

    def setup_logging(self):
        """初始化日志系统

        配置 Loguru 日志系统，包括控制台、文件和审计日志的输出。
        注意：此方法可以重复调用，但只会初始化一次。
        """
        if self._initialized:
            return

        log_path = Path(self.config.log_dir)

        # 1. 准备目录
        if self.config.enable_file or self.config.enable_audit:
            log_path.mkdir(parents=True, exist_ok=True)

        audit_path = log_path / "dm_mcp_server_audit.log"
        if self.config.audit_file:
            audit_path = Path(self.config.audit_file)

        # 2. 重置 Loguru
        logger.remove()
        logger.configure(patcher=self._patcher)

        common_cfg = {
            "rotation": self.config.rotation,
            "retention": self.config.retention,
            "compression": self.config.compression,
            "encoding": "utf-8",
            "enqueue": True,
        }

        # 3. 配置 Sinks
        # Console
        # 注意：
        # - 在 MCP stdio 模式下，stdout 必须只用于 JSON-RPC 协议数据
        # - 如果把日志打到 stdout，会导致客户端解析 JSON 失败
        # 因此，这里统一使用 stderr 作为控制台日志输出
        if self.config.enable_console:
            logger.add(
                sys.stderr,
                level=self.config.level,
                format=FMT_STD,
                filter=self._is_app_log,
            )

        # File (All)
        if self.config.enable_file:
            logger.add(
                log_path / "dm_mcp_server_all.log",
                level=self.config.level,
                format=FMT_STD,
                filter=self._is_app_log,
                **common_cfg,
            )
            # File (Error)
            logger.add(
                log_path / "dm_mcp_server_error.log",
                level="ERROR",
                format=FMT_STD,
                filter=self._is_app_log,
                **common_cfg,
            )

        # Audit
        if self.config.enable_audit:
            logger.add(
                audit_path,
                level="INFO",
                format=FMT_AUDIT,
                filter=self._is_audit,
                **common_cfg,
            )

        # 4. 拦截标准库
        logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

        self._initialized = True

        # 使用自身获取 logger 打印一条初始化信息
        self.get_logger("system").info(
            f"日志系统已初始化 - 级别: {self.config.level}, 目录: {log_path}"
        )

    def close_logging(self):
        """关闭日志系统，确保所有日志刷入磁盘

        等待所有待写入的日志完成，确保数据不丢失。
        """
        logger.complete()

    async def startup(self) -> None:
        self.setup_logging()

    async def shutdown(self) -> None:
        """关闭日志系统，确保所有日志刷入磁盘"""
        self.close_logging()

    # --- 对外接口 ---

    def get_logger(self, name: str = "app"):
        """获取一个绑定了模块名的 logger

        Args:
            name: 模块名，默认为 "app"

        Returns:
            绑定了模块名的 Loguru logger
        """
        return logger.bind(name=name)

    def get_audit_logger(self):
        """获取审计专用 logger

        Returns:
            审计日志专用的 Loguru logger
        """
        return logger.bind(name="audit", is_audit=True)

    def get_uvicorn_config(self) -> Dict[str, Any]:
        """获取传给 Uvicorn 的 log_config 字典

        Returns:
            Uvicorn 日志配置字典
        """
        log_dir_str = str(self.config.log_dir)

        return {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "uvicorn.logging.DefaultFormatter",
                    "fmt": "%(levelprefix)s %(message)s",
                    "use_colors": None,
                },
            },
            "handlers": {
                "intercept": {
                    "()": InterceptHandler,  # 直接引用类
                },
            },
            "loggers": {
                "uvicorn": {
                    "handlers": ["intercept"],
                    "level": self.config.level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["intercept"],
                    "level": self.config.level,
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["intercept"],
                    "level": self.config.level,
                    "propagate": False,
                },
            },
        }


class LoggingServiceFactory(ServiceFactory):
    """日志服务工厂

    负责创建和配置 LoggingService 实例。
    """

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="logging_service",
            service_type=LoggingService,
            description="日志服务",
            author="DM MCP Team",
            dependencies=[],
            priority=10,  # 最先初始化
        )

    def create(self, settings, **deps) -> LoggingService:
        return LoggingService(settings.logging)
