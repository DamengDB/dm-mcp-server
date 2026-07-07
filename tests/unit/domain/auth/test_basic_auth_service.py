"""BasicAuth 服务单元测试

测试 BasicAuth 密码管理、验证等功能。
"""

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone

from dm_mcp.domain.auth.services.basic_auth import BasicAuthService, ADMIN_USERNAME
from dm_mcp.domain.auth.services.jwt import JwtService
from dm_mcp.infra.config import Settings


class TestBasicAuthService:
    """BasicAuth 服务测试类"""

    @pytest.fixture
    def mock_auth_config_service(self):
        """Mock 认证配置服务 fixture"""
        mock = MagicMock()
        mock.jwt_token_expire_seconds = 3600
        return mock

    @pytest.fixture
    def jwt_service(self, mock_auth_config_service):
        """JWT 服务 fixture"""
        return JwtService(
            auth_config_service=mock_auth_config_service,
            app_secret="test-secret-key-for-basic-auth-testing",
        )

    @pytest.fixture
    def mock_settings(self):
        """Mock 设置 fixture"""
        return MagicMock(spec=Settings)

    @pytest.fixture
    def basic_auth_service(self, mock_settings, jwt_service):
        """BasicAuth 服务 fixture"""
        return BasicAuthService(mock_settings, jwt_service)

    @pytest.mark.asyncio
    async def test_is_initialized_false(self, basic_auth_service):
        """测试检查未初始化状态"""
        with patch(
            "dm_mcp.domain.auth.services.basic_auth.get_async_session"
        ) as mock_session:
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.scalar_one_or_none = Mock(
                return_value=None
            )

            result = await basic_auth_service.is_initialized()
            assert result is False

    @pytest.mark.asyncio
    async def test_is_initialized_true(self, basic_auth_service):
        """测试检查已初始化状态"""
        mock_admin_user = MagicMock()
        with patch(
            "dm_mcp.domain.auth.services.basic_auth.get_async_session"
        ) as mock_session:
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.scalar_one_or_none = Mock(
                return_value=mock_admin_user
            )

            result = await basic_auth_service.is_initialized()
            assert result is True

    @pytest.mark.asyncio
    async def test_init_password_too_short(self, basic_auth_service):
        """测试初始化密码时密码太短"""
        with pytest.raises(ValueError) as exc_info:
            await basic_auth_service.init_password("12345")  # 少于6位

        assert "6位" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_init_password_already_initialized(self, basic_auth_service):
        """测试初始化密码时已经初始化"""
        with patch(
            "dm_mcp.domain.auth.services.basic_auth.get_async_session"
        ) as mock_session:
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.scalar_one_or_none = Mock(
                return_value=MagicMock()
            )  # 已存在

            with pytest.raises(ValueError) as exc_info:
                await basic_auth_service.init_password("password123")

            assert "已初始化" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_change_password_too_short(self, basic_auth_service):
        """测试修改密码时新密码太短"""
        with pytest.raises(ValueError) as exc_info:
            await basic_auth_service.change_password("oldpass", "12345")

        assert "6位" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_change_password_user_not_found(self, basic_auth_service):
        """测试修改密码时用户不存在"""
        with patch(
            "dm_mcp.domain.auth.services.basic_auth.get_async_session"
        ) as mock_session:
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.scalar_one_or_none = Mock(
                return_value=None
            )

            with pytest.raises(ValueError) as exc_info:
                await basic_auth_service.change_password("oldpass", "newpass123")

            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_password_correct(self, basic_auth_service):
        """测试验证正确密码"""
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
        password_hash = pwd_context.hash("correct_password")

        mock_admin_user = MagicMock()
        mock_admin_user.password_hash = password_hash

        with patch(
            "dm_mcp.domain.auth.services.basic_auth.get_async_session"
        ) as mock_session:
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.scalar_one_or_none = Mock(
                return_value=mock_admin_user
            )

            result = await basic_auth_service.verify_password("correct_password")
            assert result is True

    @pytest.mark.asyncio
    async def test_verify_password_incorrect(self, basic_auth_service):
        """测试验证错误密码"""
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
        password_hash = pwd_context.hash("correct_password")

        mock_admin_user = MagicMock()
        mock_admin_user.password_hash = password_hash

        with patch(
            "dm_mcp.domain.auth.services.basic_auth.get_async_session"
        ) as mock_session:
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.scalar_one_or_none = Mock(
                return_value=mock_admin_user
            )

            result = await basic_auth_service.verify_password("wrong_password")
            assert result is False

    @pytest.mark.asyncio
    async def test_verify_password_user_not_found(self, basic_auth_service):
        """测试验证密码时用户不存在"""
        with patch(
            "dm_mcp.domain.auth.services.basic_auth.get_async_session"
        ) as mock_session:
            mock_session.return_value.__aenter__.return_value.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value.execute.return_value.scalar_one_or_none = Mock(
                return_value=None
            )

            result = await basic_auth_service.verify_password("any_password")
            assert result is False

    def test_create_jwt_token(self, basic_auth_service):
        """测试创建 JWT Token"""
        token = basic_auth_service.create_jwt_token()

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

        # 验证 token 可以解码
        decoded = basic_auth_service.jwt_service.decode_token(token)
        assert decoded["sub"] == ADMIN_USERNAME
        assert decoded["username"] == ADMIN_USERNAME
        assert decoded["auth_type"] == "basic_auth"

    def test_decode_basic_auth_valid(self):
        """测试解码有效的 Basic Auth header"""
        username = "admin"
        password = "password123"
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        auth_header = f"Basic {encoded}"

        result = BasicAuthService.decode_basic_auth(auth_header)

        assert result is not None
        assert result == (username, password)

    def test_decode_basic_auth_invalid_prefix(self):
        """测试解码无效前缀的 Basic Auth header"""
        result = BasicAuthService.decode_basic_auth("Bearer token123")
        assert result is None

    def test_decode_basic_auth_invalid_format(self):
        """测试解码格式错误的 Basic Auth header"""
        # 没有冒号
        encoded = base64.b64encode("nocolon".encode()).decode()
        auth_header = f"Basic {encoded}"

        result = BasicAuthService.decode_basic_auth(auth_header)
        assert result is None

    def test_decode_basic_auth_invalid_base64(self):
        """测试解码无效 Base64 的 Basic Auth header"""
        auth_header = "Basic invalid_base64!!!"

        result = BasicAuthService.decode_basic_auth(auth_header)
        assert result is None
