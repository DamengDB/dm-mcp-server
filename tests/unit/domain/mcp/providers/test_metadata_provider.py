"""Metadata MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from dm_mcp.domain.mcp.providers.metadata import MetadataMCPProvider, ObjectType
from dm_mcp.domain.datasource.services.datasource import DataSourceService
from dm_mcp.domain.datasource.services.pool import AsyncPoolService
from dm_mcp.domain.db_metadata.services.db_metadata import (
    ColumnItem,
    DbMetadataService,
    SchemaItem,
    TableItem,
    ViewItem,
)
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.infra.persistence.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.metrics.metrics_context import MetricsContext


def _mock_datasource_setup(mock_datasource_service):
    mock_datasource = MagicMock()
    mock_datasource.name = "test_db"
    mock_datasource_service.get_datasource_by_id = AsyncMock(
        return_value=mock_datasource
    )
    return mock_datasource


class TestMetadataMCPProvider:
    """MetadataMCPProvider测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        """创建Mock DataSourceService"""
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        """创建Mock AsyncPoolService"""
        service = MagicMock(spec=AsyncPoolService)
        service.execute_query = AsyncMock()
        return service

    @pytest.fixture
    def mock_db_metadata_service(self):
        """创建Mock DbMetadataService"""
        service = MagicMock(spec=DbMetadataService)
        service.list_schemas = AsyncMock(return_value=[])
        service.list_tables = AsyncMock(return_value=[])
        service.list_views = AsyncMock(return_value=[])
        service.list_columns = AsyncMock(return_value=[])
        return service

    @pytest.fixture
    def provider(self, mock_datasource_service, mock_db_metadata_service):
        """创建MetadataMCPProvider实例"""
        return MetadataMCPProvider(
            mock_datasource_service,
            db_metadata_service=mock_db_metadata_service,
        )

    @pytest.fixture
    def mock_mcp_context(self):
        """创建Mock MCPContext并设置为当前上下文"""
        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )
        return ctx, datasource_id

    def test_init(self, provider, mock_datasource_service, mock_pool_service):
        """测试初始化"""
        assert provider.datasource_service is mock_datasource_service
        assert hasattr(provider, "mcp")

    def test_resource_templates_registered(self, provider):
        """测试资源模板已注册"""
        templates = provider.mcp.list_resource_templates()
        template_uris = [t.uriTemplate for t in templates]

        assert "dm://table/{schema}/{table}" in template_uris
        assert "dm://schema/{schema}" in template_uris
        assert "dm://view/{schema}/{view}" in template_uris
        assert "dm://database/{db}" in template_uris

    def test_tools_registered(self, provider):
        """测试工具已注册"""
        tools = provider.mcp.list_tools()
        tool_names = [t.name for t in tools]

        assert "get_db_schemas_list" in tool_names
        assert "get_db_objects_list" in tool_names
        assert "get_table_describe" in tool_names
        assert "get_view_describe" in tool_names
        assert "get_view_definition" in tool_names
        assert "get_table_columns_list" in tool_names
        assert "get_table_indexes_list" in tool_names
        assert "get_table_constraints_list" in tool_names

    @pytest.mark.asyncio
    async def test_tool_get_db_schemas_list(
        self, provider, mock_mcp_context, mock_datasource_service, mock_db_metadata_service
    ):
        """测试获取schema列表"""
        ctx, datasource_id = mock_mcp_context
        _mock_datasource_setup(mock_datasource_service)
        mock_db_metadata_service.list_schemas = AsyncMock(
            return_value=[
                SchemaItem(name="SYSDBA", comment="主模式"),
                SchemaItem(name="TEST", comment="测试模式"),
            ]
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_db_schemas_list", {})

        assert result == {"SYSDBA": "主模式", "TEST": "测试模式"}

    @pytest.mark.asyncio
    async def test_tool_get_db_objects_list_tables(
        self, provider, mock_mcp_context, mock_datasource_service, mock_db_metadata_service
    ):
        """测试获取对象列表 - 仅表"""
        ctx, datasource_id = mock_mcp_context
        _mock_datasource_setup(mock_datasource_service)
        mock_db_metadata_service.list_tables = AsyncMock(
            return_value=[TableItem(name="USERS", comment="用户表")]
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": "TEST", "object_type": "TABLE"}
            )

        assert result == {"USERS": "用户表"}

    @pytest.mark.asyncio
    async def test_tool_get_db_objects_list_views(
        self, provider, mock_mcp_context, mock_datasource_service, mock_db_metadata_service
    ):
        """测试获取对象列表 - 仅视图"""
        ctx, datasource_id = mock_mcp_context
        _mock_datasource_setup(mock_datasource_service)
        mock_db_metadata_service.list_views = AsyncMock(
            return_value=[ViewItem(name="V_USERS", comment="用户视图")]
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": "TEST", "object_type": "VIEW"}
            )

        assert result == {"V_USERS": "用户视图"}

    @pytest.mark.asyncio
    async def test_tool_get_db_objects_list_all(
        self, mock_mcp_context, mock_db_metadata_service
    ):
        """测试获取对象列表 - 所有类型"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource_service = MagicMock(spec=DataSourceService)
        _mock_datasource_setup(mock_datasource_service)
        mock_db_metadata_service.list_tables = AsyncMock(
            return_value=[TableItem(name="USERS", comment="用户表")]
        )
        mock_db_metadata_service.list_views = AsyncMock(
            return_value=[ViewItem(name="V_USERS", comment="用户视图")]
        )

        provider = MetadataMCPProvider(
            mock_datasource_service,
            db_metadata_service=mock_db_metadata_service,
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": "TEST", "object_type": None}
            )

        assert result == {
            "TABLE": {"USERS": "用户表"},
            "VIEW": {"V_USERS": "用户视图"},
        }

    @pytest.mark.asyncio
    async def test_tool_get_table_describe(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取表结构"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_datasource_service.execute_query = AsyncMock(
            side_effect=[
                {
                    "result": [
                        {
                            "SCHEMA_NAME": "TEST",
                            "TABLE_NAME": "USERS",
                            "COLUMN_ID": 1,
                            "COLUMN_NAME": "ID",
                            "DATA_TYPE": "INTEGER",
                            "NULLABLE": "N",
                            "COLUMN_COMMENT": "主键",
                        }
                    ]
                },
                # DBA_CONSTRAINTS
                {
                    "result": [
                        {
                            "SCHEMA_NAME": "TEST",
                            "TABLE_NAME": "USERS",
                            "CONSTRAINT_NAME": "PK_USERS",
                            "CONSTRAINT_TYPE": "P",
                            "COLUMN_NAME": "ID",
                        }
                    ]
                },
                # ALL_TAB_COLUMNS (NOT NULL)
                {"result": []},
                {"result": [{"SCHEMA_NAME": "TEST", "TABLE_NAME": "USERS"}]},
            ]
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_describe", {"schema": "TEST", "table": "USERS"}
            )

        assert result["table"] == "USERS"
        assert "columns" in result
        assert "constraints" in result
        assert result["constraints"][0]["name"] == "PK_USERS"
        assert result["constraints"][0]["type"] == "PRIMARY_KEY"

    @pytest.mark.asyncio
    async def test_tool_get_table_describe_empty_table(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取不存在的表结构"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_datasource_service.execute_query = AsyncMock(return_value={"result": []})

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_describe", {"schema": "TEST", "table": "NONEXISTENT"}
            )

        assert result["table"] == "NONEXISTENT"
        assert result["columns"] == {"columns": [], "records": []}
        assert result["constraints"] == []

    @pytest.mark.asyncio
    async def test_tool_get_table_describe_no_table_param(
        self, provider, mock_mcp_context
    ):
        """测试缺少table参数"""
        ctx, datasource_id = mock_mcp_context

        with MCPContext.as_current(ctx):
            with pytest.raises(ValueError, match="table 不能为空"):
                await provider.mcp.call_tool(
                    "get_table_describe", {"schema": "TEST", "table": ""}
                )

    @pytest.mark.asyncio
    async def test_tool_get_view_describe(self, mock_mcp_context):
        """测试获取视图结构"""
        from dm_mcp.domain.mcp.providers.metadata import MetadataMCPProvider
        from dm_mcp.domain.datasource.services.datasource import DataSourceService
        from dm_mcp.domain.datasource.services.pool import AsyncPoolService

        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service = MagicMock(spec=AsyncPoolService)

        # 使用函数来返回不同的值
        call_count = [0]

        def execute_query_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"result": [{"schema_name": "TEST", "view_name": "V_USERS"}]}
            elif call_count[0] == 2:
                return {
                    "result": [
                        {"column_id": 1, "column_name": "ID", "data_type": "INTEGER"}
                    ]
                }
            return {"result": []}

        mock_datasource_service.execute_query = AsyncMock(
            side_effect=execute_query_side_effect
        )

        provider = MetadataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_view_describe", {"schema": "TEST", "view": "V_USERS"}
            )

        assert result["view"] == "V_USERS"
        assert "columns" in result

    @pytest.mark.asyncio
    async def test_tool_get_view_definition(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取视图定义"""
        from dm_mcp.domain.mcp.providers.metadata import MetadataMCPProvider

        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        # 需要返回两个结果：view info 和 definition
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=[
                {"result": [{"SCHEMA_NAME": "TEST", "VIEW_NAME": "V_USERS"}]},
                {"result": [{"TEXT": "SELECT * FROM USERS"}]},
            ]
        )

        provider = MetadataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_view_definition", {"schema": "TEST", "view": "V_USERS"}
            )

        assert result["view"] == "V_USERS"
        assert "definition" in result

    @pytest.mark.asyncio
    async def test_tool_get_table_columns_list(
        self, provider, mock_mcp_context, mock_datasource_service, mock_db_metadata_service
    ):
        """测试获取表列注释列表"""
        ctx, datasource_id = mock_mcp_context
        _mock_datasource_setup(mock_datasource_service)
        mock_db_metadata_service.list_columns = AsyncMock(
            return_value=[
                ColumnItem(name="ID", comment="主键ID"),
                ColumnItem(name="NAME", comment="用户名"),
            ]
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_columns_list", {"schema": "TEST", "table": "USERS"}
            )

        assert result == {"ID": "主键ID", "NAME": "用户名"}

    @pytest.mark.asyncio
    async def test_tool_get_table_indexes_list(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取表索引列表"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_datasource_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "SCHEMA_NAME": "TEST",
                        "TABLE_NAME": "USERS",
                        "INDEX_NAME": "IDX_USERS_NAME",
                        "UNIQUENESS": "NONUNIQUE",
                        "INDEX_TYPE": "NORMAL",
                        "COLUMN_POSITION": 1,
                        "COLUMN_NAME": "NAME",
                        "SORT_ORDER": "ASC",
                    }
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_indexes_list", {"schema": "TEST", "table": "USERS"}
            )

        assert len(result) == 1
        assert result[0]["name"] == "IDX_USERS_NAME"
        assert result[0]["columns"][0]["name"] == "NAME"

    @pytest.mark.asyncio
    async def test_tool_get_table_constraints_list(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取表约束列表"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_datasource_service.execute_query = AsyncMock(
            side_effect=[
                # DBA_CONSTRAINTS
                {
                    "result": [
                        {
                            "SCHEMA_NAME": "TEST",
                            "TABLE_NAME": "USERS",
                            "CONSTRAINT_NAME": "PK_USERS",
                            "CONSTRAINT_TYPE": "P",
                            "COLUMN_NAME": "ID",
                        }
                    ]
                },
                # ALL_TAB_COLUMNS (NOT NULL)
                {"result": [{"COLUMN_NAME": "ID", "NULLABLE": "N"}]},
            ]
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_constraints_list", {"schema": "TEST", "table": "USERS"}
            )

        # 应有 PK + NOT_NULL 两个约束
        assert len(result) == 2
        # PK
        pk = [c for c in result if c["type"] == "PRIMARY_KEY"][0]
        assert pk["name"] == "PK_USERS"
        assert pk["columns"] == ["ID"]
        # NOT NULL
        nn = [c for c in result if c["type"] == "NOT_NULL"][0]
        assert nn["columns"] == ["ID"]

    def test_resource_read_table(self, provider):
        """测试读取表资源"""
        resource_templates = provider.mcp.list_resource_templates()
        assert len(resource_templates) > 0

    def test_list_tools(self, provider):
        """测试列出所有工具"""
        tools = provider.list_tools()
        assert len(tools) == 8


class TestMetadataMCPProviderEdgeCases:
    """MetadataMCPProvider边界情况测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        service.execute_query = AsyncMock()
        return service

    @pytest.mark.asyncio
    async def test_normalize_schema(self, mock_datasource_service, mock_pool_service):
        """测试schema规范化"""
        provider = MetadataMCPProvider(mock_datasource_service)

        assert provider._normalize_schema(None) is None
        assert provider._normalize_schema("") is None
        assert provider._normalize_schema("  ") is None
        assert provider._normalize_schema("TEST") == "TEST"
        assert provider._normalize_schema("  TEST  ") == "TEST"

    def test_ensure_dict_rows_with_dicts(self):
        """测试 ensure_dict_rows 保留字典行"""
        from dm_mcp.domain.mcp.mappers import metadata_mapper as mp

        rows = [{"col1": "val1"}, {"col2": "val2"}]
        result = mp.ensure_dict_rows(rows, ["col1", "col2"])
        assert result == rows

    def test_ensure_dict_rows_with_lists(self):
        """测试 ensure_dict_rows 转换列表行"""
        from dm_mcp.domain.mcp.mappers import metadata_mapper as mp

        rows = [["val1", "val2"], ["val3", "val4"]]
        columns = ["col1", "col2"]
        result = mp.ensure_dict_rows(rows, columns)

        assert result[0]["col1"] == "val1"
        assert result[0]["col2"] == "val2"
        assert result[1]["col1"] == "val3"

    def test_ensure_dict_rows_empty(self):
        """测试 ensure_dict_rows 处理空列表"""
        from dm_mcp.domain.mcp.mappers import metadata_mapper as mp

        assert mp.ensure_dict_rows([], ["col1"]) == []
        assert mp.ensure_dict_rows(None, ["col1"]) is None

    @pytest.mark.asyncio
    async def test_exec_with_list_result(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试_exec返回列表结果"""
        provider = MetadataMCPProvider(mock_datasource_service)

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )
        mock_datasource_service.execute_query = AsyncMock(
            return_value={"result": [{"id": 1}]}
        )

        with MCPContext.as_current(ctx):
            result = await provider._exec(sql="SELECT 1")

        assert isinstance(result, list)

    @pytest.fixture
    def mock_db_metadata_service(self):
        service = MagicMock(spec=DbMetadataService)
        service.list_schemas = AsyncMock(return_value=[])
        service.list_tables = AsyncMock(return_value=[])
        service.list_views = AsyncMock(return_value=[])
        service.list_columns = AsyncMock(return_value=[])
        return service

    @pytest.mark.asyncio
    async def test_get_db_objects_list_no_schema(
        self, mock_datasource_service, mock_db_metadata_service
    ):
        """测试获取对象列表不传schema"""
        provider = MetadataMCPProvider(
            mock_datasource_service,
            db_metadata_service=mock_db_metadata_service,
        )

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        _mock_datasource_setup(mock_datasource_service)
        mock_db_metadata_service.list_tables = AsyncMock(return_value=[])

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": None, "object_type": "TABLE"}
            )

        assert result == {}


class TestMetadataMCPProviderResources:
    """MetadataMCPProvider资源测试类"""

    @pytest.fixture
    def mock_datasource_service(self):
        service = MagicMock(spec=DataSourceService)
        return service

    @pytest.fixture
    def mock_pool_service(self):
        service = MagicMock(spec=AsyncPoolService)
        service.execute_query = AsyncMock()
        return service

    @pytest.fixture
    def provider(self, mock_datasource_service, mock_db_metadata_service):
        return MetadataMCPProvider(
            mock_datasource_service,
            db_metadata_service=mock_db_metadata_service,
        )

    @pytest.fixture
    def mock_db_metadata_service(self):
        service = MagicMock(spec=DbMetadataService)
        service.list_schemas = AsyncMock(return_value=[])
        service.list_tables = AsyncMock(return_value=[])
        service.list_views = AsyncMock(return_value=[])
        service.list_columns = AsyncMock(return_value=[])
        return service

    @pytest.mark.asyncio
    async def test_resource_dm_table(self):
        """测试dm://table资源"""
        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource_service = MagicMock(spec=DataSourceService)
        _mock_datasource_setup(mock_datasource_service)
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=[
                {"result": [{"SCHEMA_NAME": "TEST", "TABLE_NAME": "USERS"}]},
                {
                    "result": [
                        {
                            "SCHEMA_NAME": "TEST",
                            "TABLE_NAME": "USERS",
                            "COLUMN_ID": 1,
                            "COLUMN_NAME": "ID",
                            "DATA_TYPE": "INTEGER",
                            "COLUMN_COMMENT": "主键",
                        }
                    ]
                },
                {"result": []},
            ]
        )

        provider = MetadataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            # read_resource returns a string that includes the JSON result
            result = await provider.mcp.read_resource("dm://table/TEST/USERS")

        # Result should contain schema and table info
        assert "schema" in result or "TEST" in result

    @pytest.mark.asyncio
    async def test_resource_dm_schema(self, provider):
        """测试dm://schema资源"""
        provider = (
            MetadataMCPProvider(self.mock_datasource_service, self.mock_pool_service)
            if hasattr(self, "mock_datasource_service")
            else provider
        )

        datasource_id = uuid4()
        ctx = MCPContext(
            auth=AuthContext(user_id="test_user", auth_type="token"),
            metrics=MetricsContext(),
            datasource=DatasourceContext(datasource_id=datasource_id),
        )

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        pool_service = MagicMock(spec=AsyncPoolService)
        mock_datasource_service.execute_query = AsyncMock(
            side_effect=[
                {
                    "result": [
                        {
                            "SCHEMA_NAME": "TEST",
                            "OBJECT_NAME": "USERS",
                            "OBJECT_TYPE": "TABLE",
                        }
                    ]
                },
                {"result": []},
                {"result": [{"SCHEMA_NAME": "TEST", "OWNER": "SYSDBA"}]},
            ]
        )

        provider = MetadataMCPProvider(mock_datasource_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.read_resource("dm://schema/TEST")

        assert "schema" in result

    def test_list_resource_templates(self, provider):
        """测试列出资源模板"""
        templates = provider.list_resource_templates()
        assert len(templates) >= 4

        template_uris = [t.uriTemplate for t in templates]
        assert "dm://table/{schema}/{table}" in template_uris
        assert "dm://schema/{schema}" in template_uris
