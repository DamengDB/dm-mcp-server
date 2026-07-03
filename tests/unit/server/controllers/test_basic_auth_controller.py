"""BasicAuth控制器测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.authentication import AuthCredentials, BaseUser
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.server.controllers.basic_auth_controller import BasicAuthController


class TestBasicAuthController:
    """BasicAuth控制器测试类"""

    @pytest.fixture
    def mock_basic_auth_service(self):
        """创建Mock BasicAuth服务"""
        service = MagicMock()
        service.verify_password = AsyncMock(return_value=True)
        service.create_jwt_token = MagicMock(return_value="test-jwt-token")
        service.decode_basic_auth = MagicMock(return_value=("admin", "password"))
        return service

    @pytest.fixture
    def controller(self, mock_basic_auth_service):
        """创建BasicAuth控制器"""
        return BasicAuthController(basic_auth_service=mock_basic_auth_service)

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.json = AsyncMock(return_value={})
        return request

    @pytest.fixture
    def authenticated_request(self, mock_request):
        """创建已认证的请求"""
        request = mock_request
        request.user = BaseUser()
        request.auth = AuthCredentials(scopes=["authenticated"])
        return request

    @pytest.mark.asyncio
    async def test_handle_login_success(
        self, controller, mock_request, mock_basic_auth_service
    ):
        """测试登录成功"""
        import base64

        credentials = base64.b64encode(b"admin:password").decode()
        mock_request.headers["Authorization"] = f"Basic {credentials}"
        mock_basic_auth_service.decode_basic_auth.return_value = ("admin", "password")

        response = await controller.handle_login(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        assert data["jwt"] == "test-jwt-token"
        mock_basic_auth_service.verify_password.assert_called_once_with("password")
        mock_basic_auth_service.create_jwt_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_login_invalid_auth_format(self, controller, mock_request):
        """测试无效的Basic Auth格式"""
        mock_request.headers["Authorization"] = "InvalidFormat"

        response = await controller.handle_login(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 401
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_AUTH"

    @pytest.mark.asyncio
    async def test_handle_login_invalid_username(
        self, controller, mock_request, mock_basic_auth_service
    ):
        """测试无效用户名"""
        import base64

        credentials = base64.b64encode(b"wronguser:password").decode()
        mock_request.headers["Authorization"] = f"Basic {credentials}"
        mock_basic_auth_service.decode_basic_auth.return_value = (
            "wronguser",
            "password",
        )

        response = await controller.handle_login(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 401
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_USERNAME"

    @pytest.mark.asyncio
    async def test_handle_login_invalid_password(
        self, controller, mock_request, mock_basic_auth_service
    ):
        """测试无效密码"""
        import base64

        credentials = base64.b64encode(b"admin:wrongpassword").decode()
        mock_request.headers["Authorization"] = f"Basic {credentials}"
        mock_basic_auth_service.decode_basic_auth.return_value = (
            "admin",
            "wrongpassword",
        )
        mock_basic_auth_service.verify_password.return_value = False

        response = await controller.handle_login(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 401
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_PASSWORD"

    @pytest.mark.asyncio
    async def test_handle_init_password_success(
        self, controller, mock_request, mock_basic_auth_service
    ):
        """测试初始化密码成功"""
        mock_request.json.return_value = {"password": "newpassword123"}
        mock_basic_auth_service.init_password = AsyncMock()

        response = await controller.handle_init_password(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        mock_basic_auth_service.init_password.assert_called_once_with("newpassword123")

    @pytest.mark.asyncio
    async def test_handle_init_password_missing_password(
        self, controller, mock_request
    ):
        """测试初始化密码缺少密码字段"""
        mock_request.json.return_value = {}

        response = await controller.handle_init_password(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "MISSING_PASSWORD"

    @pytest.mark.asyncio
    async def test_handle_init_password_validation_error(
        self, controller, mock_request, mock_basic_auth_service
    ):
        """测试初始化密码验证错误"""
        mock_request.json.return_value = {"password": "short"}
        mock_basic_auth_service.init_password = AsyncMock(
            side_effect=ValueError("Password too short")
        )

        response = await controller.handle_init_password(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_PASSWORD"

    @pytest.mark.asyncio
    async def test_handle_change_password_success(
        self, controller, authenticated_request, mock_basic_auth_service
    ):
        """测试修改密码成功"""
        authenticated_request.json.return_value = {
            "old_password": "oldpass",
            "new_password": "newpass123",
        }
        mock_basic_auth_service.change_password = AsyncMock()

        response = await controller.handle_change_password(authenticated_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        mock_basic_auth_service.change_password.assert_called_once_with(
            "oldpass", "newpass123"
        )

    @pytest.mark.asyncio
    async def test_handle_change_password_missing_fields(
        self, controller, authenticated_request
    ):
        """测试修改密码缺少字段"""
        authenticated_request.json.return_value = {"old_password": "oldpass"}

        response = await controller.handle_change_password(authenticated_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "MISSING_PASSWORD"

    @pytest.mark.asyncio
    async def test_handle_change_password_validation_error(
        self, controller, authenticated_request, mock_basic_auth_service
    ):
        """测试修改密码验证错误"""
        authenticated_request.json.return_value = {
            "old_password": "wrong",
            "new_password": "newpass",
        }
        mock_basic_auth_service.change_password = AsyncMock(
            side_effect=ValueError("Old password incorrect")
        )

        response = await controller.handle_change_password(authenticated_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "INVALID_PASSWORD"

    @pytest.mark.asyncio
    async def test_handle_change_password_internal_error(
        self, controller, authenticated_request, mock_basic_auth_service
    ):
        """测试修改密码内部错误"""
        authenticated_request.json.return_value = {
            "old_password": "oldpass",
            "new_password": "newpass",
        }
        mock_basic_auth_service.change_password = AsyncMock(
            side_effect=Exception("Database error")
        )

        response = await controller.handle_change_password(authenticated_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"]["code"] == "INTERNAL_ERROR"
