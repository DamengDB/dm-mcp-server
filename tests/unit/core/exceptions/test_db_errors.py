"""数据库相关异常测试"""

import pytest
from dm_mcp.core.exceptions import (
    DmMCPError,
    DatabaseError,
    ConnectionPoolError,
    DataSourceNotFoundError,
    QueryExecutionError,
)


class TestDatabaseError:
    """DatabaseError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = DatabaseError("DB error")
        assert error.message == "DB error"
        assert error.error_code == "DATABASE_ERROR"
        assert error.status_code == 500

    def test_with_source(self):
        """测试带 source 参数"""
        error = DatabaseError("Connection failed", source="primary")
        assert error.details["source"] == "primary"

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(DatabaseError, DmMCPError)


class TestConnectionPoolError:
    """ConnectionPoolError 异常测试类"""

    def test_default_values(self):
        """测试默认值"""
        error = ConnectionPoolError("Pool exhausted")
        assert error.message == "Pool exhausted"
        assert error.error_code == "DB_POOL_ERROR"
        assert error.status_code == 500

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(ConnectionPoolError, DatabaseError)


class TestDataSourceNotFoundError:
    """DataSourceNotFoundError 异常测试类"""

    def test_with_source_name(self):
        """测试带数据源名称"""
        error = DataSourceNotFoundError("primary")
        assert "primary" in error.message
        assert error.error_code == "DB_SOURCE_NOT_FOUND"
        assert error.status_code == 404
        assert error.details["source"] == "primary"

    def test_status_code_404(self):
        """测试状态码为 404"""
        error = DataSourceNotFoundError("test")
        assert error.status_code == 404

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(DataSourceNotFoundError, DatabaseError)


class TestQueryExecutionError:
    """QueryExecutionError 异常测试类"""

    def test_without_sql(self):
        """测试不带 SQL 参数"""
        error = QueryExecutionError("Query failed")
        assert error.message == "Query failed"
        assert error.error_code == "DB_QUERY_ERROR"

    def test_with_sql_short(self):
        """测试带短 SQL"""
        sql = "SELECT * FROM users"
        error = QueryExecutionError("Query failed", sql=sql)
        assert error.details["sql"] == sql

    def test_with_sql_long_truncated(self):
        """测试长 SQL 被截断"""
        sql = "SELECT * FROM users WHERE name = 'a' AND email = 'b' AND address = 'c' AND phone = 'd' AND age = 'e' AND more = 'f'"
        error = QueryExecutionError("Query failed", sql=sql)
        # 验证 SQL 被截断为 100 字符
        assert len(error.details["sql"]) == 103  # 100 + "..."
        assert error.details["sql"].endswith("...")

    def test_sql_103_chars(self):
        """测试恰好 100 字符的 SQL 不截断"""
        sql = "a" * 100
        error = QueryExecutionError("Query failed", sql=sql)
        assert error.details["sql"] == sql

    def test_inheritance(self):
        """测试继承关系"""
        assert issubclass(QueryExecutionError, DatabaseError)
