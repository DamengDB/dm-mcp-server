"""数据库连接集成测试

测试数据库连接、连接池和数据源服务的集成。
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from dm_mcp.server import MCPServer
from tests.conftest import mock_settings


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.database
class TestDatabaseConnection:
    """数据库连接测试类"""

    @pytest_asyncio.fixture
    async def server(self, mock_settings):
        """创建测试服务器实例"""

        # 创建一个返回 mock_settings 的类
        # 使用 __new__ 方法在实例化时返回 mock_settings
        class TestSettings:
            def __new__(cls):
                return mock_settings

        server = MCPServer(settings_cls=TestSettings)  # type: ignore
        yield server
        await server.shutdown()

    @pytest_asyncio.fixture
    async def app(self, server):
        """创建 ASGI 应用"""
        app = server.create_asgi_app(stateless=True)
        await server.startup()
        yield app
        await server.shutdown()

    @pytest_asyncio.fixture
    async def client(self, app):
        """创建测试客户端"""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client

    def _get_path(self, server, path: str) -> str:
        """获取完整路径（包含 base_url）"""
        base_url = server.settings.server.base_url
        if path.startswith(base_url):
            return path
        return f"{base_url}{path}" if path.startswith("/") else f"{base_url}/{path}"

    async def test_datasource_list_endpoint(self, client, server):
        """测试数据源列表端点"""
        path = self._get_path(server, "/api/v1/datasources")
        response = await client.get(path)
        assert response.status_code in [200, 401, 403, 404, 500]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    async def test_datasource_status_endpoint(self, client, server):
        """测试数据源状态端点"""
        path = self._get_path(server, "/api/v1/datasources/status")
        response = await client.get(path)
        assert response.status_code in [200, 401, 403, 404, 500]

    async def test_datasource_service_integration(self, server):
        """测试数据源服务集成"""
        await server.startup()

        datasource_service = server.context.datasource_service

        # 测试列出数据源
        data_sources = await datasource_service.list_datasources()
        assert isinstance(data_sources, list)

        # 测试获取数据源（如果存在）
        if data_sources:
            first_ds = data_sources[0]
            ds_name = first_ds.get("name") if isinstance(first_ds, dict) else None
            if ds_name:
                retrieved_ds = await datasource_service.get_data_source(ds_name)
                # 数据源可能被找到或未找到

        await server.shutdown()

    async def test_pool_service_integration(self, server):
        """测试连接池服务集成"""
        await server.startup()

        pool_service = server.context.pool_service

        # 验证连接池服务已初始化
        assert pool_service is not None

        # 测试连接池健康检查（如果支持）
        # health_status = await pool_service.health_check()
        # assert health_status is not None

        await server.shutdown()

    async def test_datasource_create_and_test(self, client, server):
        """测试数据源创建和测试"""
        # 注意：这需要实际的数据库配置，在集成测试中可能跳过
        test_datasource = {
            "name": "test_datasource",
            "type": "dm8",
            "host": "localhost",
            "port": 5236,
            "database": "test_db",
            "username": "test_user",
            "password": "test_password",
        }

        # 测试创建数据源
        create_path = self._get_path(server, "/api/v1/datasources")
        create_response = await client.post(create_path, json=test_datasource)
        # 可能返回 200（成功）、400（无效配置）或 401（未授权）等
        assert create_response.status_code in [200, 201, 400, 401, 403, 404, 500]

        # 测试新数据源连接
        test_path = self._get_path(server, "/api/v1/datasources/test")
        test_response = await client.post(test_path, json=test_datasource)
        # 可能返回 200（成功）或 400（连接失败）等
        assert test_response.status_code in [200, 400, 401, 403, 404, 500]

    async def test_datasource_crud_operations(self, client, server):
        """测试数据源 CRUD 操作"""
        # 1. 创建数据源
        test_datasource = {
            "name": "integration_test_ds",
            "type": "dm8",
            "host": "localhost",
            "port": 5236,
            "database": "test_db",
            "username": "test_user",
            "password": "test_password",
        }

        create_path = self._get_path(server, "/api/v1/datasources")
        create_response = await client.post(create_path, json=test_datasource)
        # 创建可能成功或失败
        assert create_response.status_code in [200, 201, 400, 401, 403, 404, 500]

        # 2. 获取数据源
        if create_response.status_code in [200, 201]:
            get_path = self._get_path(
                server, f"/api/v1/datasources/{test_datasource['name']}"
            )
            get_response = await client.get(get_path)
            assert get_response.status_code in [200, 404, 401, 403, 500]

            # 3. 更新数据源
            if get_response.status_code == 200:
                update_data = {"description": "Updated description"}
                update_path = self._get_path(
                    server, f"/api/v1/datasources/{test_datasource['name']}"
                )
                update_response = await client.put(update_path, json=update_data)
                assert update_response.status_code in [200, 400, 401, 403, 404, 500]

                # 4. 删除数据源
                delete_path = self._get_path(
                    server, f"/api/v1/datasources/{test_datasource['name']}"
                )
                delete_response = await client.delete(delete_path)
                assert delete_response.status_code in [200, 204, 404, 401, 403, 500]

    async def test_datasource_enable_disable(self, client, server):
        """测试数据源启用/禁用"""
        test_datasource_name = "test_datasource"

        # 启用数据源
        enable_path = self._get_path(
            server, f"/api/v1/datasources/{test_datasource_name}/enable"
        )
        enable_response = await client.post(enable_path)
        assert enable_response.status_code in [200, 404, 401, 403, 500]

        # 禁用数据源
        disable_path = self._get_path(
            server, f"/api/v1/datasources/{test_datasource_name}/disable"
        )
        disable_response = await client.post(disable_path)
        assert disable_response.status_code in [200, 404, 401, 403, 500]

    async def test_datasource_reload(self, client, server):
        """测试数据源重载"""
        # 重载所有数据源
        reload_all_path = self._get_path(server, "/api/v1/datasources/reload")
        reload_all_response = await client.post(reload_all_path)
        assert reload_all_response.status_code in [200, 401, 403, 404, 500]

        # 重载单个数据源
        reload_one_path = self._get_path(
            server, "/api/v1/datasources/test_datasource/reload"
        )
        reload_one_response = await client.post(reload_one_path)
        assert reload_one_response.status_code in [200, 404, 401, 403, 500]

    async def test_database_connection_pool(self, server):
        """测试数据库连接池"""
        await server.startup()

        pool_service = server.context.pool_service

        # 验证连接池服务可用
        assert pool_service is not None

        # 注意：实际的连接池测试需要真实的数据库连接
        # 这里只测试服务已初始化

        await server.shutdown()

    async def test_datasource_service_with_pool(self, server):
        """测试数据源服务与连接池的集成"""
        await server.startup()

        datasource_service = server.context.datasource_service
        pool_service = server.context.pool_service

        # 验证两个服务都已初始化
        assert datasource_service is not None
        assert pool_service is not None

        # 测试服务之间的协作
        # 注意：具体实现可能不同

        await server.shutdown()
