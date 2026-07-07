import logging

from pydantic import AnyUrl

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.mcp.middleware import BaseMCPMiddleware, NextCallable
from dm_mcp.domain.system.services.logging import LoggingService

logger = logging.getLogger(__name__)


class AuditMCPMiddleware(BaseMCPMiddleware):

    def __init__(self, audit_enabled: bool, logging_service: LoggingService) -> None:
        self.audit_enabled = audit_enabled
        self.logging_service = logging_service

    async def on_list_tools(self, call_next: NextCallable):
        if self.audit_enabled:
            audit_logger = self.logging_service.get_audit_logger()
            try:
                auth_context = AuthContext.get()
                audit_logger.info(f"列出工具, 用户: {auth_context.user_id}")
            except ValueError:
                audit_logger.info(f"列出工具, 用户: anonymous")

        return await call_next()

    async def on_call_tool(
        self, call_next: NextCallable, name: str, arguments: dict
    ) -> str:
        if self.audit_enabled:
            audit_logger = self.logging_service.get_audit_logger()
            try:
                auth_context = AuthContext.get()
                audit_logger.info(
                    f"调用工具: {name}, 参数: {arguments}, 用户: {auth_context.user_id}"
                )
            except ValueError:
                audit_logger.info(
                    f"调用工具: {name}, 参数: {arguments}, 用户: anonymous"
                )
        return await call_next(name, arguments)

    async def on_list_prompts(self, call_next: NextCallable):
        if self.audit_enabled:
            audit_logger = self.logging_service.get_audit_logger()
            try:
                auth_context = AuthContext.get()
                audit_logger.info(f"列出提示词, 用户: {auth_context.user_id}")
            except ValueError:
                audit_logger.info(f"列出提示词: {call_next}, 用户: anonymous")
        return await call_next()

    async def on_get_prompt(
        self, call_next: NextCallable, name: str, arguments: dict | None = None
    ):
        if self.audit_enabled:
            audit_logger = self.logging_service.get_audit_logger()
            try:
                auth_context = AuthContext.get()
                audit_logger.info(
                    f"获取提示词: {name}, 参数: {arguments}, 用户: {auth_context.user_id}"
                )
            except ValueError:
                audit_logger.info(
                    f"获取提示词: {name}, 参数: {arguments}, 用户: anonymous"
                )
        return await call_next(name, arguments)

    async def on_list_resources(self, call_next: NextCallable):
        if self.audit_enabled:
            audit_logger = self.logging_service.get_audit_logger()
            try:
                auth_context = AuthContext.get()
                audit_logger.info(f"列出资源, 用户: {auth_context.user_id}")
            except ValueError:
                audit_logger.info(f"列出资源, 用户: anonymous")
        return await call_next()

    async def on_list_resource_templates(self, call_next: NextCallable):
        if self.audit_enabled:
            audit_logger = self.logging_service.get_audit_logger()
            try:
                auth_context = AuthContext.get()
                audit_logger.info(f"列出资源模板, 用户: {auth_context.user_id}")
            except ValueError:
                audit_logger.info(f"列出资源模板, 用户: anonymous")
        return await call_next()

    async def on_read_resource(self, call_next: NextCallable, uri: AnyUrl):
        if self.audit_enabled:
            audit_logger = self.logging_service.get_audit_logger()
            try:
                auth_context = AuthContext.get()
                audit_logger.info(f"读取资源: {uri}, 用户: {auth_context.user_id}")
            except ValueError:
                audit_logger.info(f"读取资源: {uri}, 用户: anonymous")
        return await call_next(uri)
