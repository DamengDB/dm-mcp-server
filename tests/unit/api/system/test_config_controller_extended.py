"""ConfigController 扩展测试"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request

from dm_mcp.api.system.config import ConfigController


@pytest.fixture
def mock_request():
    return MagicMock(spec=Request)


@pytest.fixture
def mock_settings():
    return MagicMock()


@pytest.fixture
def mock_auth_config_service():
    service = MagicMock()
    service.oauth_enabled = False
    service.token_auth_enabled = True
    service.list_providers = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_basic_auth_service():
    service = MagicMock()
    service.is_initialized = AsyncMock(return_value=False)
    return service


@pytest.fixture
def controller(mock_settings, mock_basic_auth_service, mock_auth_config_service):
    return ConfigController(
        settings=mock_settings,
        basic_auth_service=mock_basic_auth_service,
        auth_config_service=mock_auth_config_service,
    )


def _body(response) -> dict:
    return json.loads(response.body.decode())


class TestConfigControllerExtended:
    """配置端点扩展场景"""

    @pytest.mark.asyncio
    async def test_handle_config_uninitialized_admin(
        self, controller, mock_request, mock_basic_auth_service
    ):
        mock_basic_auth_service.is_initialized.return_value = False

        data = _body(await controller.handle_config(mock_request))

        assert data["data"]["initialized"] is False

    @pytest.mark.asyncio
    async def test_handle_config_token_auth_enabled(
        self, controller, mock_request, mock_auth_config_service
    ):
        mock_auth_config_service.token_auth_enabled = True

        data = _body(await controller.handle_config(mock_request))

        assert data["data"]["token_auth_enabled"] is True

    @pytest.mark.asyncio
    async def test_handle_config_oauth_with_providers(
        self, controller, mock_request, mock_auth_config_service
    ):
        mock_auth_config_service.oauth_enabled = True
        mock_auth_config_service.list_providers = AsyncMock(
            return_value=[
                {
                    "slot": "github",
                    "name": "github",
                    "display_name": "GitHub",
                    "enabled": True,
                    "visible": True,
                },
                {
                    "slot": "hidden",
                    "name": "hidden",
                    "display_name": "Hidden",
                    "enabled": True,
                    "visible": False,
                },
            ]
        )

        data = _body(await controller.handle_config(mock_request))

        assert data["data"]["oauth_enabled"] is True
        assert len(data["data"]["oauth_providers"]) == 1
        assert data["data"]["oauth_providers"][0]["slot"] == "github"

    @pytest.mark.asyncio
    async def test_handle_config_without_auth_config_service(
        self, mock_settings, mock_request, mock_basic_auth_service
    ):
        controller = ConfigController(
            settings=mock_settings,
            basic_auth_service=mock_basic_auth_service,
            auth_config_service=None,
        )

        data = _body(await controller.handle_config(mock_request))

        assert data["data"]["oauth_enabled"] is False
        assert data["data"]["token_auth_enabled"] is False


class TestConfigControllerSecurity:
    """安全相关响应"""

    @pytest.mark.asyncio
    async def test_handle_config_does_not_expose_secrets(
        self, controller, mock_request, mock_auth_config_service
    ):
        mock_auth_config_service.list_providers = AsyncMock(
            return_value=[
                {
                    "slot": "github",
                    "name": "github",
                    "display_name": "GitHub",
                    "enabled": True,
                    "visible": True,
                    "client_secret": "should-not-appear",
                }
            ]
        )

        raw = _body(await controller.handle_config(mock_request))

        assert "client_secret" not in raw["data"]["oauth_providers"][0]
