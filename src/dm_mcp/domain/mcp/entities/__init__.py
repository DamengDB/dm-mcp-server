"""MCP 实体层

数据库原始查询结果到 MCP 层输出结构的映射实体。
"""

from .column_entity import ColumnEntity
from .index_entity import IndexEntity
from .metadata import ConstraintEntity
from .schema_entity import SchemaEntity
from .table_describe_entity import TableDescribeEntity
from .table_entity import TableEntity

__all__ = [
    "ConstraintEntity",
    "SchemaEntity",
    "TableEntity",
    "ColumnEntity",
    "IndexEntity",
    "TableDescribeEntity",
]
