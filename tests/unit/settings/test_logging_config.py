"""LoggingConfig 日志配置测试"""

import pytest
from pathlib import Path
from dm_mcp.settings.logging_config import LoggingConfig


class TestLoggingConfig:
    """LoggingConfig 测试类"""

    def test_default_values(self):
        """测试默认值"""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.log_dir == Path("logs")
        assert config.enable_console is True
        assert config.enable_file is True
        assert config.enable_audit is True
        assert config.rotation == "10 MB"
        assert config.retention == "30 days"
        assert config.compression == "zip"

    def test_custom_values(self):
        """测试自定义值"""
        config = LoggingConfig(
            level="DEBUG",
            log_dir=Path("/var/log/myapp"),
            enable_console=False,
            enable_file=False,
            enable_audit=False,
            rotation="100 MB",
            retention="7 days",
            compression="gz",
        )
        assert config.level == "DEBUG"
        assert config.log_dir == Path("/var/log/myapp")
        assert config.enable_console is False
        assert config.enable_file is False
        assert config.enable_audit is False
        assert config.rotation == "100 MB"
        assert config.retention == "7 days"
        assert config.compression == "gz"

    def test_valid_log_levels(self):
        """测试有效的日志级别"""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            config = LoggingConfig(level=level)
            assert config.level == level

    def test_audit_file_optional(self):
        """测试审计日志路径可选"""
        config = LoggingConfig()
        assert config.audit_file is None

        config = LoggingConfig(audit_file=Path("/var/log/audit.log"))
        assert config.audit_file == Path("/var/log/audit.log")

    def test_compression_options(self):
        """测试压缩选项"""
        # 无压缩
        config = LoggingConfig(compression=None)
        assert config.compression is None

        # 各压缩格式
        for compression in [
            "zip",
            "gz",
            "bz2",
            "xz",
            "lzma",
            "tar",
            "tar.gz",
            "tar.bz2",
            "tar.xz",
        ]:
            config = LoggingConfig(compression=compression)
            assert config.compression == compression


class TestLoggingConfigValidation:
    """LoggingConfig 验证测试"""

    def test_invalid_log_level(self):
        """测试无效的日志级别"""
        with pytest.raises(Exception):
            LoggingConfig(level="INVALID")

    def test_invalid_compression(self):
        """测试无效的压缩格式"""
        with pytest.raises(Exception):
            LoggingConfig(compression="invalid")
