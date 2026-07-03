"""日志服务单元测试

测试日志配置、初始化等功能。
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from dm_mcp.services.logging_service import LoggingService
from dm_mcp.settings.logging_config import LoggingConfig


class TestLoggingService:
    """日志服务测试类"""

    @pytest.fixture
    def logging_config(self, tmp_path):
        """日志配置 fixture"""
        return LoggingConfig(
            level="DEBUG",
            log_dir=tmp_path / "logs",
            enable_console=True,
            enable_file=True,
            enable_audit=True,
        )

    @pytest.fixture
    def logging_service(self, logging_config):
        """日志服务 fixture"""
        return LoggingService(logging_config)

    def test_logging_service_initialization(self, logging_service):
        """测试日志服务初始化"""
        assert logging_service is not None
        assert logging_service.config is not None
        assert not logging_service._initialized

    @pytest.mark.asyncio
    async def test_startup(self, logging_service):
        """测试服务启动"""
        await logging_service.startup()

        assert logging_service._initialized

    @pytest.mark.asyncio
    async def test_shutdown(self, logging_service):
        """测试服务关闭"""
        await logging_service.startup()
        await logging_service.shutdown()

        # 验证可以正常关闭（无异常）

    def test_setup_logging_creates_directory(self, logging_service, tmp_path):
        """测试设置日志时创建目录"""
        logging_service.setup_logging()

        log_dir = tmp_path / "logs"
        assert log_dir.exists()

    def test_setup_logging_idempotent(self, logging_service):
        """测试设置日志是幂等的"""
        logging_service.setup_logging()
        first_init = logging_service._initialized

        logging_service.setup_logging()
        second_init = logging_service._initialized

        assert first_init == second_init == True

    def test_get_logger(self, logging_service):
        """测试获取 logger"""
        logger = logging_service.get_logger("test_module")

        assert logger is not None

    def test_get_audit_logger(self, logging_service):
        """测试获取审计 logger"""
        audit_logger = logging_service.get_audit_logger()

        assert audit_logger is not None

    def test_get_uvicorn_config(self, logging_service):
        """测试获取 Uvicorn 配置"""
        config = logging_service.get_uvicorn_config()

        assert config is not None
        assert "version" in config
        assert "loggers" in config
        assert "uvicorn" in config["loggers"]

    def test_close_logging(self, logging_service):
        """测试关闭日志系统"""
        logging_service.setup_logging()
        logging_service.close_logging()

        # 验证可以正常关闭（无异常）
