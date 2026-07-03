from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from dm_mcp.providers.metadata_provider import MetadataMCPProvider
from dm_mcp.services.async_pool_service import AsyncPoolService
from dm_mcp.settings.pool_config import DmPoolConfig


@pytest.fixture
def metadata_provider(mock_datasource_service, mock_metrics_service):
    pool_cfg = DmPoolConfig(enabled=False)
    pool_service = AsyncPoolService(
        pool_cfg, mock_datasource_service, mock_metrics_service
    )
    pool_service.execute_query = AsyncMock()

    provider = MetadataMCPProvider(mock_datasource_service, pool_service)
    provider._get_current_datasource_name = AsyncMock(return_value="primary")
    return provider


@pytest.mark.asyncio
async def test_des_3_tc_01_routes_and_tools_registered(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-01 资源与工具注册覆盖检查。"""
    resources = metadata_provider.list_resources()
    resource_templates = metadata_provider.list_resource_templates()
    tools = metadata_provider.list_tools()

    uris = {str(r.uri) for r in resources}
    templates = {t.uriTemplate for t in resource_templates}
    tool_names = {t.name for t in tools}

    assert "dm://schema/{schema}" in templates or "dm://schema/{schema}" in uris
    assert (
        "dm://table/{schema}/{table}" in templates
        or "dm://table/{schema}/{table}" in uris
    )
    assert (
        "dm://view/{schema}/{view}" in templates or "dm://view/{schema}/{view}" in uris
    )
    assert "dm://database/{db}" in templates or "dm://database/{db}" in uris

    expected_tools = {
        "get_db_schemas_list",
        "get_db_objects_list",
        "get_table_describe",
        "get_view_describe",
        "get_view_definition",
        "get_table_comment",
        "get_table_column_comments",
        "get_table_indexes_list",
        "get_table_constraints_list",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_des_3_tc_02_res_get_table_returns_overview(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-02 Resource 表概览返回摘要信息。"""
    metadata_provider._query_table_info = AsyncMock(return_value={"TABLE_NAME": "EMP"})
    metadata_provider._query_table_columns = AsyncMock(
        return_value=[{"COLUMN_NAME": "ID"}]
    )
    metadata_provider._query_table_indexes = AsyncMock(
        return_value=[{"INDEX_NAME": "PK"}]
    )

    result = await metadata_provider._res_get_table("TEST", "EMP")

    assert result["schema"] == "TEST"
    assert result["table"] == "EMP"
    assert result["table_info"]["TABLE_NAME"] == "EMP"
    assert result["columns_preview"][0]["COLUMN_NAME"] == "ID"
    assert result["indexes_preview"][0]["INDEX_NAME"] == "PK"


@pytest.mark.asyncio
async def test_des_3_tc_03_res_get_schema_aggregates_tables_and_views(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-03 Resource schema 概览聚合表和视图。"""
    metadata_provider._query_tables = AsyncMock(return_value=[{"TABLE_NAME": "T1"}])
    metadata_provider._query_views = AsyncMock(return_value=[{"VIEW_NAME": "V1"}])
    metadata_provider._query_schema_info = AsyncMock(
        return_value={"SCHEMA_NAME": "TEST"}
    )

    result = await metadata_provider._res_get_schema("TEST")
    assert result["schema"] == "TEST"
    assert result["schema_info"]["SCHEMA_NAME"] == "TEST"
    assert result["tables"][0]["TABLE_NAME"] == "T1"
    assert result["views"][0]["VIEW_NAME"] == "V1"


@pytest.mark.asyncio
async def test_des_3_tc_04_res_get_database_counts_objects(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-04 Resource 数据库概览统计对象数量。"""
    metadata_provider._tool_get_db_schemas_list = AsyncMock(
        return_value=[{"SCHEMA_NAME": "A"}, {"SCHEMA_NAME": "B"}]
    )
    metadata_provider._query_tables = AsyncMock(return_value=[{"TABLE_NAME": "T1"}])
    metadata_provider._query_views = AsyncMock(
        return_value=[{"VIEW_NAME": "V1"}, {"VIEW_NAME": "V2"}]
    )

    result = await metadata_provider._res_get_database("DM")

    assert result["db"] == "DM"
    assert result["schema_count"] == 2
    assert result["table_count"] == 1
    assert result["view_count"] == 2


@pytest.mark.asyncio
async def test_des_3_tc_05_tool_get_db_objects_list_filters_by_type(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-05 Tool 对象列表支持按类型过滤。"""
    metadata_provider._query_tables = AsyncMock(return_value=[{"TABLE_NAME": "T1"}])
    metadata_provider._query_views = AsyncMock(return_value=[{"VIEW_NAME": "V1"}])

    # TABLE only
    res_table = await metadata_provider._tool_get_db_objects_list(
        schema="TEST", object_type="TABLE", include_comments=False
    )
    assert res_table["object_type"] == "TABLE"
    assert res_table["objects"][0]["TABLE_NAME"] == "T1"

    # VIEW only
    res_view = await metadata_provider._tool_get_db_objects_list(
        schema="TEST", object_type="VIEW", include_comments=False
    )
    assert res_view["object_type"] == "VIEW"
    assert res_view["objects"][0]["VIEW_NAME"] == "V1"

    # None: both
    res_both = await metadata_provider._tool_get_db_objects_list(
        schema="TEST", object_type=None, include_comments=False
    )
    assert "tables" in res_both and "views" in res_both
    assert res_both["tables"][0]["TABLE_NAME"] == "T1"
    assert res_both["views"][0]["VIEW_NAME"] == "V1"


@pytest.mark.asyncio
async def test_des_3_tc_06_table_describe_includes_columns_and_constraints(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-06 表结构明细包含列与约束。"""
    metadata_provider._query_table_info = AsyncMock(return_value={"TABLE_NAME": "EMP"})
    metadata_provider._query_table_columns = AsyncMock(
        return_value=[{"COLUMN_NAME": "ID"}]
    )
    metadata_provider._query_table_constraints = AsyncMock(
        return_value=[{"CONSTRAINT_NAME": "PK_EMP"}]
    )

    result = await metadata_provider._tool_get_table_describe(
        schema="TEST", table="EMP", table_comment="EMP TABLE"
    )

    assert result["schema"] == "TEST"
    assert result["table"] == "EMP"
    assert result["table_info"]["COMMENT"] == "EMP TABLE"
    assert result["columns"][0]["COLUMN_NAME"] == "ID"
    assert result["constraints"][0]["CONSTRAINT_NAME"] == "PK_EMP"


@pytest.mark.asyncio
async def test_des_3_tc_07_view_describe_and_definition(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-07 视图结构与定义能力。"""
    metadata_provider._query_view_info = AsyncMock(
        return_value={"VIEW_NAME": "V1", "DEFINITION": "select 1"}
    )
    metadata_provider._query_view_columns = AsyncMock(
        return_value=[{"COLUMN_NAME": "C1"}]
    )

    # describe
    describe = await metadata_provider._tool_get_view_describe(
        schema="TEST", view="V1", view_comment="VIEW COMMENT"
    )
    assert describe["schema"] == "TEST"
    assert describe["view"] == "V1"
    assert "DEFINITION" not in describe["view_info"]
    assert describe["columns"][0]["COLUMN_NAME"] == "C1"

    # definition
    metadata_provider._query_view_info.reset_mock()
    metadata_provider._query_view_info.return_value = {
        "VIEW_NAME": "V1",
        "DEFINITION": "select 1",
    }
    definition = await metadata_provider._tool_get_view_definition(
        schema="TEST", view="V1", view_comment="VC"
    )
    assert definition["view"] == "V1"
    assert definition["definition"] == "select 1"
    assert definition["comment"] == "VC"


@pytest.mark.asyncio
async def test_des_3_tc_08_indexes_and_constraints_shapes(
    metadata_provider: MetadataMCPProvider,
):
    """[DM_MCP-des-3] DES-3-TC-08 索引与约束列表字段规范。"""
    metadata_provider._query_table_indexes = AsyncMock(
        return_value=[{"INDEX_NAME": "IDX1", "IS_UNIQUE": "UNIQUE"}]
    )
    metadata_provider._query_table_constraints = AsyncMock(
        return_value=[{"CONSTRAINT_NAME": "PK1", "CONSTRAINT_TYPE": "P"}]
    )

    idx_res = await metadata_provider._tool_get_table_indexes_list(
        schema="TEST", table="EMP", table_comment=None
    )
    assert idx_res["indexes"][0]["INDEX_NAME"] == "IDX1"
    assert "IS_UNIQUE" in idx_res["indexes"][0]

    cons_res = await metadata_provider._tool_get_table_constraints_list(
        schema="TEST", table="EMP", table_comment=None
    )
    assert cons_res["constraints"][0]["CONSTRAINT_NAME"] == "PK1"
    assert cons_res["constraints"][0]["CONSTRAINT_TYPE"] == "P"
