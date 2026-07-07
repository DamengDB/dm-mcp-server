"""核心异常模块

统一管理所有核心模块的异常，包括认证、数据库、Provider、服务、传输和验证等异常。
"""

from .auth_errors import (
    AuthenticationError,
    AuthorizationError,
    InvalidTokenError,
    IpNotAllowedError,
    OAuthError,
    TokenDatasourceNotFoundError,
    TokenExpiredError,
)
from .base_error import DmMCPError
from .event_errors import (
    EventServiceError,
    HandlerSyncError,
    PublishStrictError,
)
from .db_errors import (
    ConnectionPoolError,
    DatabaseError,
    DataSourceNotFoundError,
    QueryExecutionError,
)
from .provider_errors import (
    CliGroupConflictError,
    CliGroupMissingForToolsError,
    CliGroupNotFoundError,
    CliGroupPathInUseError,
    CommandTreeConflictError,
    MCPExecutionError,
    MCPProviderError,
    MCPProviderLoadError,
    MCPProviderNotFoundError,
    ToolNotFoundError,
    ToolMetadataConflictError,
    ResourceNotFoundError,
    PromptNotFoundError,
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
    "IpNotAllowedError",
    "TokenDatasourceNotFoundError",
    # Database
    "DatabaseError",
    "ConnectionPoolError",
    "DataSourceNotFoundError",
    "QueryExecutionError",
    # Provider
    "MCPProviderError",
    "MCPProviderLoadError",
    "MCPProviderNotFoundError",
    "MCPExecutionError",
    "CliGroupNotFoundError",
    "CliGroupPathInUseError",
    "CliGroupMissingForToolsError",
    "CliGroupConflictError",
    "CommandTreeConflictError",
    "ToolNotFoundError",
    "ToolMetadataConflictError",
    "ResourceNotFoundError",
    "PromptNotFoundError",
    # Service
    "ServiceError",
    "ServiceNotFoundError",
    "ServiceCircularDependencyError",
    # Events
    "EventServiceError",
    "HandlerSyncError",
    "PublishStrictError",
    # Transport
    "TransportError",
    "TransportConfigError",
    # Validation
    "ValidationError",
    "InvalidParameterError",
    "MissingParameterError",
]
