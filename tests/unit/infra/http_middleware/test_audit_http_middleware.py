"""HTTP审计中间件测试模块"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.infra.middleware.audit_http import AuditHTTPMiddleware


class TestAuditHTTPMiddleware:
    """HTTP审计中间件测试类"""

    @pytest.fixture
    def mock_logging_service(self):
        """创建Mock日志服务"""
        service = MagicMock()
        audit_logger = MagicMock()
        audit_logger.info = MagicMock()
        service.get_audit_logger = MagicMock(return_value=audit_logger)
        return service

    @pytest.fixture
    def mock_app(self):
        """创建Mock应用"""
        app = MagicMock()
        return app

    @pytest.fixture
    def middleware_enabled(self, mock_app, mock_logging_service):
        """创建启用的审计中间件"""
        return AuditHTTPMiddleware(
            app=mock_app,
            audit_enabled=True,
            logging_service=mock_logging_service,
            base_url="",
        )

    @pytest.fixture
    def middleware_disabled(self, mock_app, mock_logging_service):
        """创建禁用的审计中间件"""
        return AuditHTTPMiddleware(
            app=mock_app,
            audit_enabled=False,
            logging_service=mock_logging_service,
            base_url="",
        )

    @pytest.fixture
    def mock_request(self):
        """创建Mock请求"""
        request = MagicMock(spec=Request)
        request.method = "GET"
        request.url = MagicMock()
        request.url.path = "/api/v1/datasources"
        request.headers = {}
        request.query_params = {}
        request.path_params = {}
        request.json = AsyncMock(return_value={})
        request.cookies = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.fixture
    def mock_response(self):
        """创建Mock响应"""
        response = MagicMock(spec=Response)
        response.status_code = 200
        return response

    @pytest.fixture
    def mock_call_next(self, mock_response):
        """创建Mock call_next函数"""
        return AsyncMock(return_value=mock_response)

    @pytest.mark.asyncio
    async def test_dispatch_audit_disabled(
        self, middleware_disabled, mock_request, mock_call_next
    ):
        """测试审计禁用时直接通过"""
        response = await middleware_disabled.dispatch(mock_request, mock_call_next)

        assert response == mock_call_next.return_value
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_audit_enabled(
        self, middleware_enabled, mock_request, mock_call_next, mock_logging_service
    ):
        """测试审计启用时记录日志"""
        response = await middleware_enabled.dispatch(mock_request, mock_call_next)

        assert response == mock_call_next.return_value
        mock_call_next.assert_called_once()
        # 验证审计日志被记录
        audit_logger = mock_logging_service.get_audit_logger()
        audit_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_audit_api_path(self, middleware_enabled, mock_request):
        """测试API路径需要审计"""
        mock_request.url.path = "/api/v1/datasources"

        result = middleware_enabled._should_audit(mock_request)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_audit_static_path(self, middleware_enabled, mock_request):
        """测试静态资源路径不需要审计"""
        mock_request.url.path = "/static/index.html"

        result = middleware_enabled._should_audit(mock_request)

        assert result is False

    @pytest.mark.asyncio
    async def test_should_audit_health_path(self, middleware_enabled, mock_request):
        """测试健康检查路径不需要审计"""
        mock_request.url.path = "/health"

        result = middleware_enabled._should_audit(mock_request)

        assert result is False

    @pytest.mark.asyncio
    async def test_should_audit_custom_paths(self, mock_app, mock_logging_service):
        """测试自定义审计路径"""
        middleware = AuditHTTPMiddleware(
            app=mock_app,
            audit_enabled=True,
            logging_service=mock_logging_service,
            base_url="",
            audit_paths=["/api/v1/tokens", "/api/v1/datasources"],
        )

        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/v1/tokens"

        assert middleware._should_audit(request) is True

        request.url.path = "/api/v1/other"
        assert middleware._should_audit(request) is False

    @pytest.mark.asyncio
    async def test_get_user_id_from_auth_context(
        self, middleware_enabled, mock_request
    ):
        """测试从AuthContext获取用户ID"""
        with AuthContext.as_current(
            AuthContext(user_id="test_user", auth_type="token")
        ):
            user_id = middleware_enabled._get_user_id(mock_request)
            assert user_id == "test_user"

    @pytest.mark.asyncio
    async def test_get_user_id_from_request_user(
        self, middleware_enabled, mock_request
    ):
        """测试无 AuthContext 时回退为 anonymous"""
        user = MagicMock()
        user.auth_context = AuthContext(user_id="request_user", auth_type="token")
        mock_request.user = user

        user_id = middleware_enabled._get_user_id(mock_request)

        assert user_id == "anonymous"

    @pytest.mark.asyncio
    async def test_get_user_id_anonymous(self, middleware_enabled, mock_request):
        """测试匿名用户"""
        mock_request.user = None

        user_id = middleware_enabled._get_user_id(mock_request)

        assert user_id == "anonymous"

    @pytest.mark.asyncio
    async def test_get_auth_type(self, middleware_enabled, mock_request):
        """测试获取认证类型"""
        with AuthContext.as_current(
            AuthContext(user_id="test_user", auth_type="oauth")
        ):
            auth_type = middleware_enabled._get_auth_type(mock_request)
            assert auth_type == "oauth"

    @pytest.mark.asyncio
    async def test_get_request_data(self, middleware_enabled, mock_request):
        """测试获取请求数据"""
        mock_request.method = "POST"
        mock_request.json.return_value = {"name": "test", "password": "secret123"}

        data = await middleware_enabled._get_request_data(mock_request)

        assert data["method"] == "POST"
        assert data["path"] == "/api/v1/datasources"
        # 验证密码被脱敏
        assert "password" in data["body"]
        assert data["body"]["password"] != "secret123"

    @pytest.mark.asyncio
    async def test_sanitize_data_password(self, middleware_enabled):
        """测试脱敏密码字段"""
        data = {"password": "mysecretpassword123"}
        sanitized = middleware_enabled._sanitize_data(data)

        assert sanitized["password"] != "mysecretpassword123"
        assert sanitized["password"].startswith("my")
        assert "*" in sanitized["password"]

    @pytest.mark.asyncio
    async def test_sanitize_data_token(self, middleware_enabled):
        """测试脱敏Token字段"""
        data = {"token": "abc123xyz"}
        sanitized = middleware_enabled._sanitize_data(data)

        assert sanitized["token"] != "abc123xyz"
        assert "*" in sanitized["token"]

    @pytest.mark.asyncio
    async def test_sanitize_data_nested(self, middleware_enabled):
        """测试脱敏嵌套数据"""
        data = {"user": {"password": "secret", "email": "test@example.com"}}
        sanitized = middleware_enabled._sanitize_data(data)

        assert sanitized["user"]["password"] != "secret"
        assert sanitized["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_client_ip_from_forwarded_for(
        self, middleware_enabled, mock_request
    ):
        """测试从X-Forwarded-For获取客户端IP"""
        mock_request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}

        ip = middleware_enabled._get_client_ip(mock_request)

        assert ip == "192.168.1.1"

    @pytest.mark.asyncio
    async def test_get_client_ip_from_real_ip(self, middleware_enabled, mock_request):
        """测试从X-Real-IP获取客户端IP"""
        mock_request.headers = {"X-Real-IP": "192.168.1.2"}

        ip = middleware_enabled._get_client_ip(mock_request)

        assert ip == "192.168.1.2"

    @pytest.mark.asyncio
    async def test_get_client_ip_from_client(self, middleware_enabled, mock_request):
        """测试从client获取客户端IP"""
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.3"

        ip = middleware_enabled._get_client_ip(mock_request)

        assert ip == "192.168.1.3"

    @pytest.mark.asyncio
    async def test_log_audit(
        self, middleware_enabled, mock_request, mock_response, mock_logging_service
    ):
        """测试记录审计日志"""
        request_data = {
            "method": "POST",
            "path": "/api/v1/datasources",
            "body": {"name": "test"},
        }

        middleware_enabled._log_audit(
            request=mock_request,
            response=mock_response,
            user_id="test_user",
            auth_type="token",
            request_data=request_data,
        )

        audit_logger = mock_logging_service.get_audit_logger()
        audit_logger.info.assert_called_once()
        call_args = audit_logger.info.call_args[0][0]
        assert "操作: POST /api/v1/datasources" in call_args
        assert "用户: test_user" in call_args

    @pytest.mark.asyncio
    async def test_summarize_body(self, middleware_enabled):
        """测试摘要请求体"""
        body = {
            "name": "test_datasource",
            "token": "abc123",
            "description": "A test datasource",
            "other": "ignored",
        }

        summary = middleware_enabled._summarize_body(body)

        assert "name=test_datasource" in summary
        assert "description=A test datasource" in summary
