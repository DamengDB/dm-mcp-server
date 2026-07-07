"""MCP Provider 辅助工具单元测试

测试 to_table 和 McpResponseBuilder。
"""

import pytest

from dm_mcp.core.mcp.format import (
    McpResponseBuilder,
    to_table,
)


class TestToTable:
    """to_table 辅助函数测试"""

    def test_empty_list(self):
        """空列表返回空表格"""
        result = to_table([])
        assert result == {"columns": [], "records": []}

    def test_single_row(self):
        """单行转换"""
        result = to_table([{"a": 1, "b": 2}])
        assert result["columns"] == ["a", "b"]
        assert result["records"] == [[1, 2]]

    def test_multiple_rows(self):
        """多行转换"""
        result = to_table([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        assert result["columns"] == ["a", "b"]
        assert result["records"] == [[1, 2], [3, 4]]

    def test_missing_keys(self):
        """缺失键用 None 填充"""
        result = to_table([{"a": 1, "b": 2}, {"a": 3}])
        assert result["records"] == [[1, 2], [3, None]]


class TestMcpResponseBuilder:
    """McpResponseBuilder 测试"""

    def test_table(self):
        """表格类型构建"""
        result = McpResponseBuilder.table([{"a": 1}], summary={"count": 1})
        assert result["_mcp_response_type"] == "table"
        assert result["summary"] == {"count": 1}
        assert "columns" in result["value"]

    def test_data(self):
        """数据类型构建"""
        result = McpResponseBuilder.data({"key": "value"}, summary={"total": 1})
        assert result["_mcp_response_type"] == "data"
        assert result["value"] == {"key": "value"}
        assert result["summary"] == {"total": 1}

    def test_error(self):
        """错误类型构建"""
        result = McpResponseBuilder.error("ERR_CODE", "error message")
        assert result["_mcp_response_type"] == "error"
        assert result["code"] == "ERR_CODE"
        assert result["message"] == "error message"
