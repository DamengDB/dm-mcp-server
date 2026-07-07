"""CLI 分组路径规则与条目结构（权威元数据在数据库，由 MCPGroupService 管理）。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from dm_mcp.common import messages


@dataclass
class CliGroupEntry:
    """供 CLI / API 使用的分组描述（首行短、全文长）。"""

    path: str
    short_description: str
    long_description: str

    @staticmethod
    def from_description(path: str, description: str) -> CliGroupEntry:
        text = description.strip()
        lines = text.split("\n")
        short_desc = lines[0].strip() if lines else ""
        return CliGroupEntry(
            path=path,
            short_description=short_desc,
            long_description=text,
        )

    def update_from_description(self, description: str) -> CliGroupEntry:
        text = description.strip()
        lines = text.split("\n")
        self.short_description = lines[0].strip() if lines else ""
        self.long_description = text
        return self


class CliGroupRegistry:
    """分组 path 语法与保留字校验（不写进程内注册表；数据见 MCPGroupService / DB）。"""

    _PATH_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^[a-z0-9_]+(\.[a-z0-9_]+)*$"
    )
    _RESERVED: ClassVar[frozenset[str]] = frozenset(
        {"help", "version", "config", "set", "get"}
    )

    @staticmethod
    def validate_path(path: str | None) -> None:
        if path is None:
            return
        if not CliGroupRegistry._PATH_PATTERN.match(path):
            raise ValueError(
                messages.MSG_GROUP_PATH_INVALID.format(path=path)
            )
        for part in path.split("."):
            if part in CliGroupRegistry._RESERVED:
                raise ValueError(
                    messages.MSG_GROUP_PATH_SEGMENT_RESERVED.format(path=path, segment=part)
                )
