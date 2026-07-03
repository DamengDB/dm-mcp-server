"""审计中间件测试模块"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.middlewares.audit_middleware import AuditMCPMiddleware


class TestAuditMCPMiddleware:
    """审计中间件测试类"""

    @pytest.fixture
    def mock_logging_service(self):
        """创建Mock日志服务"""
        service = MagicMock()
        audit_logger = MagicMock()
        service.get_audit_logger.return_value = audit_logger
        return service

    @pytest.fixture
    def middleware_enabled(self, mock_logging_service):
        """创建启用的审计中间件"""
        return AuditMCPMiddleware(
            audit_enabled=True, logging_service=mock_logging_service
        )

    @pytest.fixture
    def middleware_disabled(self, mock_logging_service):
        """创建禁用的审计中间件"""
        return AuditMCPMiddleware(
            audit_enabled=False, logging_service=mock_logging_service
        )

    @pytest.fixture
    def mock_call_next(self):
        """创建Mock的call_next函数"""
        return AsyncMock(return_value="result")

    @pytest.mark.asyncio
    async def test_on_list_tools_enabled_with_auth(
        self, middleware_enabled, mock_call_next
    ):
        """测试启用状态下列出工具（已认证）"""
        auth_context = AuthContext(user_id="user123", auth_type="token")
        with AuthContext.as_current(auth_context):
            result = await middleware_enabled.on_list_tools(mock_call_next)
            assert result == "result"
            mock_call_next.assert_called_once()
            # 验证审计日志被记录
            audit_logger = middleware_enabled.logging_service.get_audit_logger()
            audit_logger.info.assert_called_once()
            call_args = audit_logger.info.call_args[0][0]
            assert "列出工具" in call_args
            assert "user123" in call_args

    @pytest.mark.asyncio
    async def test_on_list_tools_enabled_without_auth(
        self, middleware_enabled, mock_call_next
    ):
        """测试启用状态下列出工具（未认证）"""
        result = await middleware_enabled.on_list_tools(mock_call_next)
        assert result == "result"
        mock_call_next.assert_called_once()
        audit_logger = middleware_enabled.logging_service.get_audit_logger()
        audit_logger.info.assert_called_once()
        call_args = audit_logger.info.call_args[0][0]
        assert "列出工具" in call_args
        assert "anonymous" in call_args

    @pytest.mark.asyncio
    async def test_on_list_tools_disabled(self, middleware_disabled, mock_call_next):
        """测试禁用状态下列出工具"""
        result = await middleware_disabled.on_list_tools(mock_call_next)
        assert result == "result"
        mock_call_next.assert_called_once()
        # 禁用时不应该记录日志
        audit_logger = middleware_disabled.logging_service.get_audit_logger()
        audit_logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_call_tool_enabled_with_auth(
        self, middleware_enabled, mock_call_next
    ):
        """测试启用状态下调用工具（已认证）"""
        auth_context = AuthContext(user_id="user123", auth_type="token")
        with AuthContext.as_current(auth_context):
            result = await middleware_enabled.on_call_tool(
                mock_call_next, "test_tool", {"param": "value"}
            )
            assert result == "result"
            mock_call_next.assert_called_once_with("test_tool", {"param": "value"})
            audit_logger = middleware_enabled.logging_service.get_audit_logger()
            audit_logger.info.assert_called_once()
            call_args = audit_logger.info.call_args[0][0]
            assert "调用工具" in call_args
            assert "test_tool" in call_args
            assert "user123" in call_args

    @pytest.mark.asyncio
    async def test_on_call_tool_enabled_without_auth(
        self, middleware_enabled, mock_call_next
    ):
        """测试启用状态下调用工具（未认证）"""
        result = await middleware_enabled.on_call_tool(
            mock_call_next, "test_tool", {"param": "value"}
        )
        assert result == "result"
        audit_logger = middleware_enabled.logging_service.get_audit_logger()
        audit_logger.info.assert_called_once()
        call_args = audit_logger.info.call_args[0][0]
        assert "anonymous" in call_args

    @pytest.mark.asyncio
    async def test_on_list_prompts_enabled(self, middleware_enabled, mock_call_next):
        """测试启用状态下列出提示词"""
        auth_context = AuthContext(user_id="user123", auth_type="token")
        with AuthContext.as_current(auth_context):
            result = await middleware_enabled.on_list_prompts(mock_call_next)
            assert result == "result"
            audit_logger = middleware_enabled.logging_service.get_audit_logger()
            audit_logger.info.assert_called_once()
            call_args = audit_logger.info.call_args[0][0]
            assert "列出提示词" in call_args

    @pytest.mark.asyncio
    async def test_on_get_prompt_enabled(self, middleware_enabled, mock_call_next):
        """测试启用状态下获取提示词"""
        auth_context = AuthContext(user_id="user123", auth_type="token")
        with AuthContext.as_current(auth_context):
            result = await middleware_enabled.on_get_prompt(
                mock_call_next, "test_prompt", {"arg": "value"}
            )
            assert result == "result"
            mock_call_next.assert_called_once_with("test_prompt", {"arg": "value"})
            audit_logger = middleware_enabled.logging_service.get_audit_logger()
            audit_logger.info.assert_called_once()
            call_args = audit_logger.info.call_args[0][0]
            assert "获取提示词" in call_args
            assert "test_prompt" in call_args

    @pytest.mark.asyncio
    async def test_on_get_prompt_without_arguments(
        self, middleware_enabled, mock_call_next
    ):
        """测试获取提示词时没有参数"""
        result = await middleware_enabled.on_get_prompt(
            mock_call_next, "test_prompt", None
        )
        assert result == "result"
        mock_call_next.assert_called_once_with("test_prompt", None)

    @pytest.mark.asyncio
    async def test_on_list_resources_enabled(self, middleware_enabled, mock_call_next):
        """测试启用状态下列出资源"""
        auth_context = AuthContext(user_id="user123", auth_type="token")
        with AuthContext.as_current(auth_context):
            result = await middleware_enabled.on_list_resources(mock_call_next)
            assert result == "result"
            audit_logger = middleware_enabled.logging_service.get_audit_logger()
            audit_logger.info.assert_called_once()
            call_args = audit_logger.info.call_args[0][0]
            assert "列出资源" in call_args

    @pytest.mark.asyncio
    async def test_on_list_resource_templates_enabled(
        self, middleware_enabled, mock_call_next
    ):
        """测试启用状态下列出资源模板"""
        auth_context = AuthContext(user_id="user123", auth_type="token")
        with AuthContext.as_current(auth_context):
            result = await middleware_enabled.on_list_resource_templates(mock_call_next)
            assert result == "result"
            audit_logger = middleware_enabled.logging_service.get_audit_logger()
            audit_logger.info.assert_called_once()
            call_args = audit_logger.info.call_args[0][0]
            assert "列出资源模板" in call_args

    @pytest.mark.asyncio
    async def test_on_read_resource_enabled(self, middleware_enabled, mock_call_next):
        """测试启用状态下读取资源"""
        from pydantic import AnyUrl

        auth_context = AuthContext(user_id="user123", auth_type="token")
        with AuthContext.as_current(auth_context):
            uri = AnyUrl("dameng://resource/1")
            result = await middleware_enabled.on_read_resource(mock_call_next, uri)
            assert result == "result"
            mock_call_next.assert_called_once_with(uri)
            audit_logger = middleware_enabled.logging_service.get_audit_logger()
            audit_logger.info.assert_called_once()
            call_args = audit_logger.info.call_args[0][0]
            assert "读取资源" in call_args
            assert str(uri) in call_args
