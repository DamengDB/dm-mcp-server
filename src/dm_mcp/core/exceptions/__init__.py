"""核心异常模块

统一管理所有核心模块的异常，包括认证、数据库、Provider、服务、传输和验证等异常。
"""

from .auth_errors import (
    AuthenticationError,
    AuthorizationError,
    InvalidTokenError,
    OAuthError,
    TokenExpiredError,
)
from .base_error import DmMCPError
from .db_errors import (
    ConnectionPoolError,
    DatabaseError,
    DataSourceNotFoundError,
    QueryExecutionError,
)
from .provider_errors import (
    MCPProviderDependencyError,
    MCPProviderError,
    MCPProviderLoadError,
    MCPProviderNotFoundError,
)
from .service_errors import (
    ServiceCircularDependencyError,
    ServiceError,
    ServiceNotFoundError,
)
from .transport_errors import TransportConfigError, TransportError
from .validation_errors import (
    InvalidParameterError,
    MissingParameterError,
    ValidationError,
)

__all__ = [
    # Base
    "DmMCPError",
    # Auth
    "AuthenticationError",
    "AuthorizationError",
    "TokenExpiredError",
    "InvalidTokenError",
    "OAuthError",
    # Database
    "DatabaseError",
    "ConnectionPoolError",
    "DataSourceNotFoundError",
    "QueryExecutionError",
    # Provider
    "MCPProviderError",
    "MCPProviderLoadError",
    "MCPProviderNotFoundError",
    "MCPProviderDependencyError",
    # Service
    "ServiceError",
    "ServiceNotFoundError",
    "ServiceCircularDependencyError",
    # Transport
    "TransportError",
    "TransportConfigError",
    # Validation
    "ValidationError",
    "InvalidParameterError",
    "MissingParameterError",
]
