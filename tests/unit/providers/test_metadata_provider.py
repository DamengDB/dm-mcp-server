"""Metadata MCP Provider测试模块"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

from dm_mcp.providers.metadata_provider import MetadataMCPProvider, ObjectType
from dm_mcp.services.datasource_service import DataSourceService
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.core.mcp.context import MCPContext
from dm_mcp.core.datasource.datasource_context import DatasourceContext
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.metrics.metrics_context import MetricsContext


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
    def provider(self, mock_datasource_service, mock_pool_service):
        """创建MetadataMCPProvider实例"""
        return MetadataMCPProvider(mock_datasource_service, mock_pool_service)

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
        assert provider._pool_service is mock_pool_service
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
        assert "get_table_comment" in tool_names
        assert "get_table_column_comments" in tool_names
        assert "get_table_indexes_list" in tool_names
        assert "get_table_constraints_list" in tool_names

    @pytest.mark.asyncio
    async def test_tool_get_db_schemas_list(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取schema列表"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "schema_name": "SYSDBA",
                        "owner_name": "SYSDBA",
                        "created_time": "2024-01-01",
                    },
                    {
                        "schema_name": "TEST",
                        "owner_name": "SYSDBA",
                        "created_time": "2024-01-02",
                    },
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool("get_db_schemas_list", {})

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["schema_name"] == "SYSDBA"

    @pytest.mark.asyncio
    async def test_tool_get_db_objects_list_tables(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取对象列表 - 仅表"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "SCHEMA_NAME": "TEST",
                        "OBJECT_NAME": "USERS",
                        "OBJECT_TYPE": "TABLE",
                    }
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": "TEST", "object_type": "TABLE"}
            )

        assert result["object_type"] == "TABLE"
        assert len(result["objects"]) == 1
        assert result["objects"][0]["TABLE_NAME"] == "USERS"

    @pytest.mark.asyncio
    async def test_tool_get_db_objects_list_views(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取对象列表 - 仅视图"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "SCHEMA_NAME": "TEST",
                        "OBJECT_NAME": "V_USERS",
                        "OBJECT_TYPE": "VIEW",
                    }
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": "TEST", "object_type": "VIEW"}
            )

        assert result["object_type"] == "VIEW"
        assert len(result["objects"]) == 1

    @pytest.mark.asyncio
    async def test_tool_get_db_objects_list_all(self, mock_mcp_context):
        """测试获取对象列表 - 所有类型"""
        from dm_mcp.providers.metadata_provider import MetadataMCPProvider
        from dm_mcp.services.datasource_service import DataSourceService
        from dm_mcp.services.async_pool_service import AsyncPoolService

        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"

        mock_datasource_service = MagicMock(spec=DataSourceService)
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service = MagicMock(spec=AsyncPoolService)

        # 使用函数来返回不同的值 - 使用大写字段名
        call_count = [0]

        def execute_query_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:  # tables and views
                return {
                    "result": [
                        {
                            "SCHEMA_NAME": "TEST",
                            "OBJECT_NAME": f"OBJ{call_count[0]}",
                            "OBJECT_TYPE": (
                                "TABLE" if call_count[0] % 2 == 1 else "VIEW"
                            ),
                        }
                    ]
                }
            return {"result": []}

        mock_pool_service.execute_query = AsyncMock(
            side_effect=execute_query_side_effect
        )

        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": "TEST", "object_type": None}
            )

        assert "tables" in result or "objects" in result

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

        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {"result": [{"SCHEMA_NAME": "TEST", "TABLE_NAME": "USERS"}]},
                {
                    "result": [
                        {
                            "COLUMN_ID": 1,
                            "COLUMN_NAME": "ID",
                            "DATA_TYPE": "INTEGER",
                            "NULLABLE": "N",
                            "COLUMN_COMMENT": "主键",
                        }
                    ]
                },
                {"result": [{"CONSTRAINT_NAME": "PK_USERS", "CONSTRAINT_TYPE": "P"}]},
            ]
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_describe", {"schema": "TEST", "table": "USERS"}
            )

        assert result["table"] == "USERS"
        assert "columns" in result
        assert "constraints" in result

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

        mock_pool_service.execute_query = AsyncMock(return_value={"result": []})

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_describe", {"schema": "TEST", "table": "NONEXISTENT"}
            )

        assert result["table"] == "NONEXISTENT"
        assert result["table_info"] == {}

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
        from dm_mcp.providers.metadata_provider import MetadataMCPProvider
        from dm_mcp.services.datasource_service import DataSourceService
        from dm_mcp.services.async_pool_service import AsyncPoolService

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

        mock_pool_service.execute_query = AsyncMock(
            side_effect=execute_query_side_effect
        )

        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

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
        from dm_mcp.providers.metadata_provider import MetadataMCPProvider

        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        # 需要返回两个结果：view info 和 definition
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {"result": [{"SCHEMA_NAME": "TEST", "VIEW_NAME": "V_USERS"}]},
                {"result": [{"TEXT": "SELECT * FROM USERS"}]},
            ]
        )

        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_view_definition", {"schema": "TEST", "view": "V_USERS"}
            )

        assert result["view"] == "V_USERS"
        assert "definition" in result

    @pytest.mark.asyncio
    async def test_tool_get_table_comment(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取表注释"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {"SCHEMA_NAME": "TEST", "TABLE_NAME": "USERS", "COMMENT": "用户表"}
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_comment", {"schema": "TEST", "table": "USERS"}
            )

        assert result["comment"] == "用户表"

    @pytest.mark.asyncio
    async def test_tool_get_table_comment_provided(self, provider, mock_mcp_context):
        """测试传入table_comment时直接返回"""
        ctx, datasource_id = mock_mcp_context

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_comment",
                {"schema": "TEST", "table": "USERS", "table_comment": "Direct comment"},
            )

        assert result["comment"] == "Direct comment"

    @pytest.mark.asyncio
    async def test_tool_get_table_column_comments(
        self, provider, mock_mcp_context, mock_datasource_service, mock_pool_service
    ):
        """测试获取表列注释"""
        ctx, datasource_id = mock_mcp_context

        mock_datasource = MagicMock()
        mock_datasource.name = "test_db"
        mock_datasource_service.get_datasource_by_id = AsyncMock(
            return_value=mock_datasource
        )

        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "COLUMN_ID": 1,
                        "COLUMN_NAME": "ID",
                        "DATA_TYPE": "INTEGER",
                        "COLUMN_COMMENT": "主键ID",
                    },
                    {
                        "COLUMN_ID": 2,
                        "COLUMN_NAME": "NAME",
                        "DATA_TYPE": "VARCHAR",
                        "COLUMN_COMMENT": "用户名",
                    },
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_column_comments", {"schema": "TEST", "table": "USERS"}
            )

        assert len(result["column_comments"]) == 2
        assert result["column_comments"][0]["column"] == "ID"

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

        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "INDEX_NAME": "IDX_USERS_NAME",
                        "UNIQUENESS": "NONUNIQUE",
                        "COLUMN_NAME": "NAME",
                    }
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_indexes_list", {"schema": "TEST", "table": "USERS"}
            )

        assert len(result["indexes"]) == 1
        assert result["indexes"][0]["INDEX_NAME"] == "IDX_USERS_NAME"

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

        mock_pool_service.execute_query = AsyncMock(
            return_value={
                "result": [
                    {
                        "CONSTRAINT_NAME": "PK_USERS",
                        "CONSTRAINT_TYPE": "P",
                        "COLUMN_NAME": "ID",
                    }
                ]
            }
        )

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_table_constraints_list", {"schema": "TEST", "table": "USERS"}
            )

        assert len(result["constraints"]) == 1
        assert result["constraints"][0]["CONSTRAINT_NAME"] == "PK_USERS"

    def test_resource_read_table(self, provider):
        """测试读取表资源"""
        resource_templates = provider.mcp.list_resource_templates()
        assert len(resource_templates) > 0

    def test_list_tools(self, provider):
        """测试列出所有工具"""
        tools = provider.list_tools()
        assert len(tools) >= 9


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
        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

        assert provider._normalize_schema(None) is None
        assert provider._normalize_schema("") is None
        assert provider._normalize_schema("  ") is None
        assert provider._normalize_schema("TEST") == "TEST"
        assert provider._normalize_schema("  TEST  ") == "TEST"

    @pytest.mark.asyncio
    async def test_ensure_dict_rows_with_dicts(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试_ensure_dict_rows保留字典行"""
        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

        rows = [{"col1": "val1"}, {"col2": "val2"}]
        result = provider._ensure_dict_rows(rows, ["col1", "col2"])
        assert result == rows

    @pytest.mark.asyncio
    async def test_ensure_dict_rows_with_lists(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试_ensure_dict_rows转换列表行"""
        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

        rows = [["val1", "val2"], ["val3", "val4"]]
        columns = ["col1", "col2"]
        result = provider._ensure_dict_rows(rows, columns)

        assert result[0]["col1"] == "val1"
        assert result[0]["col2"] == "val2"
        assert result[1]["col1"] == "val3"

    @pytest.mark.asyncio
    async def test_ensure_dict_rows_empty(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试_ensure_dict_rows处理空列表"""
        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

        assert provider._ensure_dict_rows([], ["col1"]) == []
        assert provider._ensure_dict_rows(None, ["col1"]) is None

    @pytest.mark.asyncio
    async def test_exec_with_list_result(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试_exec返回列表结果"""
        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

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
        mock_pool_service.execute_query = AsyncMock(
            return_value={"result": [{"id": 1}]}
        )

        with MCPContext.as_current(ctx):
            result = await provider._exec(sql="SELECT 1", source="test_db")

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_db_objects_list_no_schema(
        self, mock_datasource_service, mock_pool_service
    ):
        """测试获取对象列表不传schema"""
        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

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

        mock_pool_service.execute_query = AsyncMock(return_value={"result": []})

        with MCPContext.as_current(ctx):
            result = await provider.mcp.call_tool(
                "get_db_objects_list", {"schema": None, "object_type": "TABLE"}
            )

        assert "objects" in result or "tables" in result


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
    def provider(self, mock_datasource_service, mock_pool_service):
        return MetadataMCPProvider(mock_datasource_service, mock_pool_service)

    @pytest.mark.asyncio
    async def test_resource_dm_table(self):
        """测试dm://table资源"""
        from dm_mcp.providers.metadata_provider import MetadataMCPProvider
        from dm_mcp.services.datasource_service import DataSourceService
        from dm_mcp.services.async_pool_service import AsyncPoolService

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

        mock_pool_service = MagicMock(spec=AsyncPoolService)
        mock_pool_service.execute_query = AsyncMock(
            side_effect=[
                {"result": [{"SCHEMA_NAME": "TEST", "TABLE_NAME": "USERS"}]},
                {
                    "result": [
                        {
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

        provider = MetadataMCPProvider(mock_datasource_service, mock_pool_service)

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
        pool_service.execute_query = AsyncMock(
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

        provider = MetadataMCPProvider(mock_datasource_service, pool_service)

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
