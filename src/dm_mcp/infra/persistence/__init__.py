"""数据库模块包

提供数据库模型和会话管理功能，包括Token模型、Admin用户模型、数据源模型等。
"""

from .models import (
    AdminUserModel,
    AppSettingsModel,
    CliGroupModel,
    DBObjectConfigModel,
    DataSourceModel,
    DBSystemObjectDefaultModel,
    EntityGroupAssignmentModel,
    GenericSqlDefinitionModel,
    MetadataOverrideModel,
    OAuthProviderModel,
    SSHHostModel,
    TokenModel,
)
from .datasource_context import DatasourceContext
from .pool_config import DmPoolConfig
from .query import OwnedQuery
from .schema_check import SchemaIncompatibleError
from .session import (
    AsyncSession,
    bootstrap_schema,
    close_db,
    create_tables,
    ensure_schema_compatible,
    get_async_session,
    get_schema_location_hint,
    init_db,
)

__all__ = [
    "DatasourceContext",
    "DmPoolConfig",
    "OwnedQuery",
    "TokenModel",
    "DBObjectConfigModel",
    "DBSystemObjectDefaultModel",
    "AdminUserModel",
    "DataSourceModel",
    "CliGroupModel",
    "EntityGroupAssignmentModel",
    "AppSettingsModel",
    "MetadataOverrideModel",
    "GenericSqlDefinitionModel",
    "OAuthProviderModel",
    "SSHHostModel",
    "SchemaIncompatibleError",
    "get_async_session",
    "init_db",
    "create_tables",
    "bootstrap_schema",
    "ensure_schema_compatible",
    "get_schema_location_hint",
    "close_db",
    "AsyncSession",
]
