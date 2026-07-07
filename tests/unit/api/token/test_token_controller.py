"""Token控制器测试模块"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from starlette.authentication import AuthCredentials, BaseUser
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.api.token.token import (
    CreateTokenRequest,
    ErrorCode,
    TokenController,
    UpdateTokenRequest,
)
from dm_mcp.infra.config.token_auth_config import TokenConfig


# ============================================================
# Module-level fixtures
# ============================================================
@pytest.fixture
def mock_token_service():
    """创建Mock Token服务"""
    service = MagicMock()
    service.create_token = AsyncMock()
    service.list_tokens = AsyncMock(return_value=[])
    service.get_token = AsyncMock(return_value=None)
    service.get_by_token_id = AsyncMock(return_value=None)
    service.update_token = AsyncMock()
    service.delete_token = AsyncMock()
    return service


@pytest.fixture
def mock_datasource_service():
    """创建Mock数据源服务"""
    service = MagicMock()
    ds_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    mock_ds = MagicMock()
    mock_ds.id = ds_id
    mock_ds.enabled = True
    mock_ds.name = "primary"
    service.get_datasource = AsyncMock(return_value=mock_ds)
    service.get_datasource_by_id = AsyncMock(return_value=mock_ds)
    return service


@pytest.fixture
def controller(mock_token_service, mock_datasource_service):
    """创建Token控制器"""
    return TokenController(
        token_service=mock_token_service, datasource_service=mock_datasource_service
    )


@pytest.fixture
def mock_request():
    """创建Mock请求"""
    request = MagicMock(spec=Request)
    request.user = BaseUser()
    request.user.auth_context = AuthContext(
        user_id="test_user",
        auth_type="token",
        token="test-token",
        datasource_names=["primary"], default_datasource_name="primary",
    )
    request.auth = AuthCredentials(scopes=["authenticated"])
    request.path_params = {}
    request.json = AsyncMock(return_value={})
    return request


@pytest.fixture
def sample_token_config():
    """示例Token配置"""
    return TokenConfig(
        token="test-token-123",
        token_id="testtoken001",
        user_id="test_user",
        datasource_ids=["550e8400-e29b-41d4-a716-446655440000"],
        default_datasource_id="550e8400-e29b-41d4-a716-446655440000",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc).replace(year=2025),
        name="测试Token",
    )


class TestTokenController:
    """Token控制器测试类"""

    # ============================================================
    # 辅助方法测试
    # ============================================================

    def test_success_response(self, controller):
        """测试成功响应格式"""
        response = controller.success(
            data={"key": "value"}, message="成功", status_code=201
        )

        assert isinstance(response, JSONResponse)
        assert response.status_code == 201
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        assert data["data"] == {"key": "value"}
        assert data["message"] == "成功"

    def test_error_response(self, controller):
        """测试错误响应格式"""
        response = controller.error(
            error="操作失败", code=ErrorCode.OPERATION_FAILED, status_code=400
        )

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["error"] == "操作失败"
        assert data["code"] == ErrorCode.OPERATION_FAILED

    def test_get_auth_context(self, controller, mock_request):
        """测试获取认证上下文"""
        context = controller.get_auth_context(mock_request)

        assert isinstance(context, AuthContext)
        assert context.user_id == "test_user"

    def test_get_auth_context_anonymous(self, controller):
        """测试获取匿名认证上下文"""
        request = MagicMock(spec=Request)
        request.user = None

        context = controller.get_auth_context(request)

        assert isinstance(context, AuthContext)
        assert context.user_id == "anonymous"

    @pytest.mark.asyncio
    async def test_token_to_dict(self, controller, sample_token_config):
        """测试Token配置转字典"""
        result = await controller._token_to_dict(
            sample_token_config, check_validity=False
        )

        assert result["token"] == "test-token-123"
        assert result["user_id"] == "test_user"
        assert result["datasource_names"] == ["primary"]
        assert result["default_datasource_name"] == "primary"
        assert "created_at" in result
        assert "expires_at" in result

    # ============================================================
    # CRUD 操作测试
    # ============================================================

    @pytest.mark.asyncio
    async def test_handle_create_success(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试创建Token成功"""
        mock_request.json.return_value = {
            "datasource_names": ["primary"],
            "default_datasource_name": "primary",
            "expires_in": 3600,
            "name": "测试Token",
        }
        mock_token_service.create_token.return_value = sample_token_config

        response = await controller.handle_create(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 201
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        assert data["data"]["token"] == "test-token-123"
        assert data["data"]["datasource_names"] == ["primary"]
        assert data["data"]["default_datasource_name"] == "primary"
        mock_token_service.create_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_create_validation_error(self, controller, mock_request):
        """测试创建Token验证错误"""
        mock_request.json.return_value = {"invalid": "data"}

        response = await controller.handle_create(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.VALIDATION_ERROR

    @pytest.mark.asyncio
    async def test_handle_list_success(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试列出Token成功"""
        mock_token_service.list_tokens.return_value = [sample_token_config]

        response = await controller.handle_list(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        assert len(data["data"]) == 1
        mock_token_service.list_tokens.assert_called_once_with(user_id="test_user")

    @pytest.mark.asyncio
    async def test_handle_get_success(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试获取Token成功"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config

        response = await controller.handle_get(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        assert data["data"]["token"] == "test-token-123"

    @pytest.mark.asyncio
    async def test_handle_get_not_found(
        self, controller, mock_request, mock_token_service
    ):
        """测试获取不存在的Token"""
        mock_request.path_params["token_id"] = "nonexisten1"
        mock_token_service.get_by_token_id.return_value = None

        response = await controller.handle_get(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.TOKEN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_get_unauthorized(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试获取其他用户的Token"""
        mock_request.path_params["token_id"] = "testtoken001"
        sample_token_config.user_id = "other_user"
        mock_token_service.get_by_token_id.return_value = sample_token_config

        response = await controller.handle_get(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.TOKEN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_update_success(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新Token成功"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        # 确保返回的token_config是可序列化的
        updated_config = TokenConfig(
            token="test-token-123",
            token_id="testtoken001",
            user_id="test_user",
            datasource_ids=sample_token_config.datasource_ids,
            default_datasource_id=sample_token_config.default_datasource_id,
            created_at=sample_token_config.created_at,
            expires_at=sample_token_config.expires_at,
            name="更新后的名称",
        )
        mock_token_service.update_token.return_value = updated_config
        mock_request.json.return_value = {
            "datasource_names": ["primary", "replica2"], "default_datasource_name": "primary",
            "name": "更新后的名称",
        }

        response = await controller.handle_update(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        mock_token_service.update_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_update_with_expires_at(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新Token带过期时间"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_token_service.update_token.return_value = sample_token_config
        expires_at = datetime.now(timezone.utc).replace(year=2026)
        mock_request.json.return_value = {
            "expires_at": expires_at.isoformat(),
        }

        response = await controller.handle_update(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_handle_update_validation_error(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新Token验证错误"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        # 使用无效的expires_at格式来触发验证错误
        # 注意：datetime.fromisoformat可能会抛出ValueError而不是ValidationError
        mock_request.json.return_value = {"expires_at": "not-a-date"}

        response = await controller.handle_update(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        # 根据代码，datetime解析错误会被捕获为ValueError，然后可能返回400
        # 或者如果UpdateTokenRequest验证失败，会返回VALIDATION_ERROR
        # 实际行为：如果expires_at格式无效，datetime.fromisoformat会抛出ValueError
        # 这个ValueError会被捕获并返回400，但code可能是OPERATION_FAILED
        assert response.status_code == 400
        assert data["code"] in [
            ErrorCode.VALIDATION_ERROR,
            ErrorCode.OPERATION_FAILED,
            ErrorCode.INTERNAL_ERROR,
        ]

    @pytest.mark.asyncio
    async def test_handle_update_unauthorized(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新其他用户的Token"""
        mock_request.path_params["token_id"] = "testtoken001"
        sample_token_config.user_id = "other_user"
        mock_token_service.get_by_token_id.return_value = sample_token_config

        response = await controller.handle_update(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.TOKEN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_delete_success(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试删除Token成功"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config

        response = await controller.handle_delete(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        mock_token_service.delete_token.assert_called_once_with("testtoken001")

    @pytest.mark.asyncio
    async def test_handle_delete_not_found(
        self, controller, mock_request, mock_token_service
    ):
        """测试删除不存在的Token"""
        mock_request.path_params["token_id"] = "nonexisten1"
        mock_token_service.get_by_token_id.return_value = None

        response = await controller.handle_delete(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.TOKEN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_delete_unauthorized(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试删除其他用户的Token"""
        mock_request.path_params["token_id"] = "testtoken001"
        sample_token_config.user_id = "other_user"
        mock_token_service.get_by_token_id.return_value = sample_token_config

        response = await controller.handle_delete(mock_request)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.TOKEN_NOT_FOUND


# ============================================================
# 扩展测试：数据源有效性检查
# ============================================================
class TestTokenControllerDataSourceValidation:
    """测试数据源有效性检查"""

    @pytest.fixture
    def mock_token_service_for_ds_check(self):
        """创建用于数据源检查的Mock Token服务"""
        service = MagicMock()
        return service

    @pytest.fixture
    def controller_without_ds_service(self, mock_token_service):
        """创建不带数据源服务的控制器"""
        return TokenController(
            token_service=mock_token_service, datasource_service=None
        )

    @pytest.mark.asyncio
    async def test_token_to_dict_with_valid_datasource(
        self, controller, sample_token_config, mock_datasource_service
    ):
        """测试有效数据源的Token转换"""
        result = await controller._token_to_dict(
            sample_token_config, check_validity=True
        )

        assert result["valid"] is True
        assert result["datasource_names"] == ["primary"]

    @pytest.mark.asyncio
    async def test_token_to_dict_with_disabled_datasource(
        self, controller, sample_token_config, mock_datasource_service
    ):
        """测试禁用数据源的Token转换"""
        mock_ds = MagicMock()
        mock_ds.enabled = False
        mock_ds.name = "disabled_ds"
        mock_datasource_service.get_datasource_by_id.return_value = mock_ds

        result = await controller._token_to_dict(
            sample_token_config, check_validity=True
        )

        assert result["valid"] is False
        assert result["datasource_names"] == []

    @pytest.mark.asyncio
    async def test_token_to_dict_with_missing_datasource(
        self, controller, sample_token_config, mock_datasource_service
    ):
        """测试不存在的数据源"""
        mock_datasource_service.get_datasource_by_id.return_value = None

        result = await controller._token_to_dict(
            sample_token_config, check_validity=True
        )

        assert result["valid"] is False
        assert result["datasource_names"] == []

    @pytest.mark.asyncio
    async def test_token_to_dict_with_datasource_error(
        self, controller, sample_token_config, mock_datasource_service
    ):
        """测试检查数据源时出错"""
        mock_datasource_service.get_datasource_by_id.side_effect = Exception(
            "Database error"
        )

        result = await controller._token_to_dict(
            sample_token_config, check_validity=True
        )

        assert result["valid"] is False
        assert "invalid_reason" in result

    @pytest.mark.asyncio
    async def test_token_to_dict_without_datasource_service(
        self, controller_without_ds_service, sample_token_config
    ):
        """测试没有数据源服务时的转换"""
        result = await controller_without_ds_service._token_to_dict(
            sample_token_config, check_validity=True
        )

        assert result["valid"] is None
        assert result["datasource_names"] == []

    @pytest.mark.asyncio
    async def test_token_to_dict_without_check_validity(
        self, controller, sample_token_config
    ):
        """测试不检查有效性时的转换"""
        result = await controller._token_to_dict(
            sample_token_config, check_validity=False
        )

        assert result["valid"] is None


# ============================================================
# 扩展测试：错误处理
# ============================================================
class TestTokenControllerErrors:
    """测试错误处理"""

    @pytest.mark.asyncio
    async def test_handle_create_datasource_service_unavailable(
        self, mock_token_service, mock_datasource_service
    ):
        """测试数据源服务不可用"""
        # 创建一个没有数据源服务的控制器
        controller = TokenController(
            token_service=mock_token_service, datasource_service=None
        )

        # 创建 mock 请求
        request = MagicMock(spec=Request)
        request.user = BaseUser()
        request.user.auth_context = AuthContext(
            user_id="test_user",
            auth_type="token",
            token="test-token",
        )
        request.auth = AuthCredentials(scopes=["authenticated"])
        request.path_params = {}
        # 提供有效的请求体（通过验证）
        request.json = AsyncMock(return_value={"datasource_names": ["primary"], "default_datasource_name": "primary", "name": "t"})

        response = await controller.handle_create(request)

        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.INTERNAL_ERROR
        assert "数据源服务不可用" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_create_datasource_not_found(
        self, controller, mock_request, mock_token_service, mock_datasource_service
    ):
        """测试创建Token时数据源不存在"""
        mock_request.json.return_value = {"datasource_names": ["nonexistent"], "default_datasource_name": "nonexistent", "name": "t"}
        mock_datasource_service.get_datasource.return_value = None

        response = await controller.handle_create(mock_request)

        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert "数据源不存在" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_create_general_exception(
        self, controller, mock_request, mock_token_service, mock_datasource_service
    ):
        """测试创建Token时通用异常"""
        mock_request.json.return_value = {"datasource_names": ["primary"], "default_datasource_name": "primary", "name": "t"}
        mock_token_service.create_token.side_effect = Exception(
            "Database connection failed"
        )

        response = await controller.handle_create(mock_request)

        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.INTERNAL_ERROR

    @pytest.mark.asyncio
    async def test_handle_list_general_exception(
        self, controller, mock_request, mock_token_service
    ):
        """测试列出Token时通用异常"""
        mock_token_service.list_tokens.side_effect = Exception("Database error")

        response = await controller.handle_list(mock_request)

        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.INTERNAL_ERROR

    @pytest.mark.asyncio
    async def test_handle_get_general_exception(
        self, controller, mock_request, mock_token_service
    ):
        """测试获取Token时通用异常"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.side_effect = Exception("Database error")

        response = await controller.handle_get(mock_request)

        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.INTERNAL_ERROR

    @pytest.mark.asyncio
    async def test_handle_update_token_not_found(
        self, controller, mock_request, mock_token_service
    ):
        """测试更新不存在的Token"""
        mock_request.path_params["token_id"] = "nonexisten1"
        mock_token_service.get_by_token_id.return_value = None

        response = await controller.handle_update(mock_request)

        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.TOKEN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_update_datasource_service_unavailable(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新时数据源服务不可用"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        controller.datasource_service = None
        mock_request.json.return_value = {"datasource_names": ["new_ds"], "default_datasource_name": "new_ds"}

        response = await controller.handle_update(mock_request)

        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_handle_update_datasource_not_found(
        self,
        controller,
        mock_request,
        mock_token_service,
        mock_datasource_service,
        sample_token_config,
    ):
        """测试更新时数据源不存在"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_datasource_service.get_datasource.return_value = None
        mock_request.json.return_value = {"datasource_names": ["nonexistent"], "default_datasource_name": "nonexistent"}

        response = await controller.handle_update(mock_request)

        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert "数据源不存在" in data["error"]

    @pytest.mark.asyncio
    async def test_handle_update_general_exception(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新Token时通用异常"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_token_service.update_token.side_effect = Exception("Database error")
        mock_request.json.return_value = {"name": "new name"}

        response = await controller.handle_update(mock_request)

        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.INTERNAL_ERROR

    @pytest.mark.asyncio
    async def test_handle_update_with_value_error(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新Token时ValueError"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_token_service.update_token.side_effect = ValueError("Invalid value")
        mock_request.json.return_value = {"name": "new name"}

        response = await controller.handle_update(mock_request)

        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_handle_delete_general_exception(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试删除Token时通用异常"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_token_service.delete_token.side_effect = Exception("Database error")

        response = await controller.handle_delete(mock_request)

        assert response.status_code == 500
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False
        assert data["code"] == ErrorCode.INTERNAL_ERROR

    @pytest.mark.asyncio
    async def test_handle_delete_value_error_not_found(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试删除Token时ValueError - not found"""
        mock_request.path_params["token_id"] = "testtoken001"
        # get_by_token_id 命中，但 delete_token 抛出 ValueError("not found")
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_token_service.delete_token.side_effect = ValueError(
            "Token not found in database"
        )

        response = await controller.handle_delete(mock_request)

        # ValueError 消息包含 "not found"，返回 404
        assert response.status_code == 404
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["code"] == ErrorCode.TOKEN_NOT_FOUND

    @pytest.mark.asyncio
    async def test_handle_delete_value_error_other(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试删除Token时ValueError - 其他错误"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        # delete_token 抛出 ValueError
        mock_token_service.delete_token.side_effect = ValueError("Invalid token format")

        response = await controller.handle_delete(mock_request)

        # ValueError 消息不包含 "not found"，返回 400
        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is False

    @pytest.mark.asyncio
    async def test_handle_update_expires_at_with_z_suffix(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新Token带Z后缀的过期时间"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_token_service.update_token.return_value = sample_token_config
        mock_request.json.return_value = {"expires_at": "2026-12-31T23:59:59Z"}

        response = await controller.handle_update(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_handle_update_expires_at_naive_datetime(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试更新Token带无时区信息的过期时间"""
        mock_request.path_params["token_id"] = "testtoken001"
        mock_token_service.get_by_token_id.return_value = sample_token_config
        mock_token_service.update_token.return_value = sample_token_config
        mock_request.json.return_value = {"expires_at": "2026-12-31T23:59:59"}

        response = await controller.handle_update(mock_request)

        assert isinstance(response, JSONResponse)
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True


# ============================================================
# 扩展测试：IP 白名单/黑名单
# ============================================================
class TestTokenControllerIPWhitelist:
    """测试IP白名单/黑名单"""

    @pytest.mark.asyncio
    async def test_handle_create_with_ip_whitelist(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试创建Token带IP白名单"""
        mock_request.json.return_value = {
            "datasource_names": ["primary"],
            "default_datasource_name": "primary",
            "ip_whitelist": ["192.168.1.1", "10.0.0.0/24"],
            "name": "Test",
        }
        mock_token_service.create_token.return_value = sample_token_config

        response = await controller.handle_create(mock_request)

        assert response.status_code == 201
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        mock_token_service.create_token.assert_called_once()
        call_kwargs = mock_token_service.create_token.call_args[1]
        assert call_kwargs.get("ip_whitelist") == ["192.168.1.1", "10.0.0.0/24"]

    @pytest.mark.asyncio
    async def test_handle_create_with_ip_blacklist(
        self, controller, mock_request, mock_token_service, sample_token_config
    ):
        """测试创建Token带IP黑名单"""
        mock_request.json.return_value = {
            "datasource_names": ["primary"],
            "default_datasource_name": "primary",
            "ip_blacklist": ["203.0.113.0/24"],
            "name": "Test",
        }
        mock_token_service.create_token.return_value = sample_token_config

        response = await controller.handle_create(mock_request)

        assert response.status_code == 201
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True


# ============================================================
# 扩展测试：请求模型
# ============================================================
class TestTokenControllerRequestModels:
    """测试请求模型"""

    def test_create_token_request_defaults(self):
        """测试创建Token请求最小必填参数（默认其他字段）"""
        from dm_mcp.api.token.token import CreateTokenRequest

        req = CreateTokenRequest(
            datasource_names=["primary"],
            default_datasource_name="primary",
            name="test",
        )

        assert req.datasource_names == ["primary"]
        assert req.default_datasource_name == "primary"
        assert req.name == "test"
        assert req.expires_in is None
        assert req.ip_whitelist is None
        assert req.ip_blacklist is None

    def test_create_token_request_full(self):
        """测试创建Token请求完整参数"""
        from dm_mcp.api.token.token import CreateTokenRequest

        req = CreateTokenRequest(
            datasource_names=["primary", "replica"],
            default_datasource_name="primary",
            expires_in=3600,
            name="Test token",
            ip_whitelist=["192.168.1.1"],
            ip_blacklist=["10.0.0.0/8"],
        )

        assert req.datasource_names == ["primary", "replica"]
        assert req.default_datasource_name == "primary"
        assert req.expires_in == 3600
        assert req.name == "Test token"
        assert req.ip_whitelist == ["192.168.1.1"]
        assert req.ip_blacklist == ["10.0.0.0/8"]

    def test_update_token_request_partial(self):
        """测试更新Token请求部分参数"""
        from dm_mcp.api.token.token import UpdateTokenRequest

        req = UpdateTokenRequest(name="Updated")

        assert req.datasource_names is None
        assert req.default_datasource_name is None
        assert req.expires_at is None
        assert req.name == "Updated"


# ============================================================
# 扩展测试：辅助方法
# ============================================================
class TestTokenControllerHelpers:
    """测试辅助方法"""

    def test_error_code_constants(self):
        """测试错误码常量"""
        assert ErrorCode.TOKEN_NOT_FOUND == "TOKEN_NOT_FOUND"
        assert ErrorCode.VALIDATION_ERROR == "VALIDATION_ERROR"
        assert ErrorCode.OPERATION_FAILED == "OPERATION_FAILED"
        assert ErrorCode.INTERNAL_ERROR == "INTERNAL_ERROR"

    def test_success_response_with_none_data(self, controller):
        """测试空数据的成功响应"""
        response = controller.success(data=None, message="No data")

        assert response.status_code == 200
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["success"] is True
        assert "data" not in data

    def test_error_response_default_code(self, controller):
        """测试错误响应默认错误码"""
        response = controller.error(error="Test error")

        assert response.status_code == 400
        body = response.body.decode()
        import json

        data = json.loads(body)
        assert data["code"] == ErrorCode.OPERATION_FAILED
