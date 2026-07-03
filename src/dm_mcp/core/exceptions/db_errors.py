"""数据库相关异常模块

提供数据库操作相关的异常类定义，包括连接池、数据源、查询执行等异常。
"""

from .base_error import DmMCPError


class DatabaseError(DmMCPError):
    """数据库基础异常

    所有数据库相关异常的基类，HTTP状态码为500。
    """

    def __init__(self, message: str, source: str | None = None, **kwargs):
        """初始化数据库异常

        Args:
            message: 错误消息
            source: 数据源名称（可选）
            **kwargs: 其他参数传递给基类
        """
        error_code = kwargs.pop("error_code", "DATABASE_ERROR")
        status_code = kwargs.pop("status_code", 500)
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )
        if source:
            self.details["source"] = source


class ConnectionPoolError(DatabaseError):
    """连接池错误异常

    当数据库连接池操作失败时抛出，继承自DatabaseError。
    """

    def __init__(self, message: str, **kwargs):
        """初始化连接池异常

        Args:
            message: 错误消息
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=message, error_code="DB_POOL_ERROR", status_code=500, **kwargs
        )


class DataSourceNotFoundError(DatabaseError):
    """数据源不存在异常

    当指定的数据源不存在时抛出，继承自DatabaseError，HTTP状态码为404。
    """

    def __init__(self, source_name: str, **kwargs):
        """初始化数据源不存在异常

        Args:
            source_name: 数据源名称
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=f"Data source '{source_name}' not found",
            source=source_name,
            error_code="DB_SOURCE_NOT_FOUND",
            status_code=404,
            **kwargs,
        )


class QueryExecutionError(DatabaseError):
    """查询执行错误异常

    当SQL查询执行失败时抛出，继承自DatabaseError。
    为避免泄露敏感信息，只记录SQL的前100个字符。
    """

    def __init__(self, message: str, sql: str | None = None, **kwargs):
        """初始化查询执行异常

        Args:
            message: 错误消息
            sql: SQL语句（可选，为避免泄露敏感信息只记录前100个字符）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=message, error_code="DB_QUERY_ERROR", status_code=500, **kwargs
        )
        if sql:
            # 避免泄露敏感信息，只记录前100个字符
            self.details["sql"] = sql[:100] + "..." if len(sql) > 100 else sql
