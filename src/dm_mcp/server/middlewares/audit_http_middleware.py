"""HTTP审计中间件模块

提供HTTP请求的审计功能，记录关键操作和敏感行为。
"""

import json
import logging
from typing import Any, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.services.logging_service import LoggingService

logger = logging.getLogger(__name__)


class AuditHTTPMiddleware(BaseHTTPMiddleware):
    """HTTP审计中间件

    拦截HTTP请求，记录关键操作和敏感行为到审计日志。
    支持敏感信息脱敏、操作分类、用户追踪等功能。
    """

    def __init__(
        self,
        app,
        audit_enabled: bool,
        logging_service: LoggingService,
        base_url: str = "",
        audit_paths: Optional[list] = None,
    ):
        """初始化HTTP审计中间件

        Args:
            app: ASGI应用实例
            audit_enabled: 是否启用审计
            logging_service: 日志服务实例
            base_url: 服务器基础URL前缀（如 "/dm-mcp"）
            audit_paths: 需要审计的路径列表（None表示审计所有路径）
        """
        super().__init__(app)
        self.audit_enabled = audit_enabled
        self.logging_service = logging_service
        self.base_url = base_url.rstrip("/")  # 移除尾部斜杠，统一处理
        self.audit_paths = audit_paths

        # 定义需要审计的路径模式（如果未指定，则审计所有路径）
        if audit_paths is None:
            # 默认审计所有 API 路径，结合 base_url 前缀
            api_prefix = f"{self.base_url}/api/v1" if self.base_url else "/api/v1"
            self.audit_paths = [
                f"{api_prefix}/auth/",
                f"{api_prefix}/datasources",
                f"{api_prefix}/tokens",
            ]

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求并记录审计日志

        Args:
            request: HTTP请求对象
            call_next: 下一个中间件或路由处理器

        Returns:
            Response: HTTP响应对象
        """
        # 如果审计未启用，直接跳过
        if not self.audit_enabled:
            return await call_next(request)

        # 检查是否需要审计此路径
        if not self._should_audit(request):
            return await call_next(request)

        # 获取用户信息
        user_id = self._get_user_id(request)
        auth_type = self._get_auth_type(request)
        request_data = await self._get_request_data(request)

        # 执行请求
        response = await call_next(request)

        # 记录审计日志
        self._log_audit(
            request=request,
            response=response,
            user_id=user_id,
            auth_type=auth_type,
            request_data=request_data,
        )

        return response

    def _should_audit(self, request: Request) -> bool:
        """判断是否需要审计此请求

        Args:
            request: HTTP请求对象

        Returns:
            bool: 是否需要审计
        """
        path = request.url.path

        # 排除静态资源和健康检查（考虑 base_url 前缀）
        static_prefix = f"{self.base_url}/static" if self.base_url else "/static"
        health_path = f"{self.base_url}/health" if self.base_url else "/health"

        if path.startswith(static_prefix) or path == health_path:
            return False

        # 如果指定了审计路径列表，只审计匹配的路径
        if self.audit_paths:
            return any(path.startswith(prefix) for prefix in self.audit_paths)

        # 默认审计所有 API 路径（结合 base_url 前缀）
        api_prefix = f"{self.base_url}/api" if self.base_url else "/api"
        return path.startswith(api_prefix)

    def _get_user_id(self, request: Request) -> str:
        """从请求中获取用户ID

        Args:
            request: HTTP请求对象

        Returns:
            str: 用户ID，如果未认证则返回 "anonymous"
        """
        try:
            # 尝试从 AuthContext 获取
            auth_context = AuthContext.get()
            return auth_context.user_id
        except (ValueError, AttributeError):
            # 尝试从 request.user 获取
            if hasattr(request, "user") and request.user:
                if hasattr(request.user, "auth_context"):
                    return request.user.auth_context.user_id
                if hasattr(request.user, "username"):
                    return request.user.username
            return "anonymous"

    def _get_auth_type(self, request: Request) -> str:
        """从请求中获取认证类型

        Args:
            request: HTTP请求对象

        Returns:
            str: 认证类型（oauth, basic_auth, token, anonymous）
        """
        try:
            auth_context = AuthContext.get()
            return auth_context.auth_type
        except (ValueError, AttributeError):
            if hasattr(request, "user") and request.user:
                if hasattr(request.user, "auth_context"):
                    return request.user.auth_context.auth_type
            return "anonymous"

    async def _get_request_data(self, request: Request) -> Dict[str, Any]:
        """获取请求数据（已脱敏）

        Args:
            request: HTTP请求对象

        Returns:
            Dict[str, Any]: 请求数据字典（敏感信息已脱敏）
        """
        data = {
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "path_params": dict(request.path_params),
        }

        # 获取请求体（如果有）
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                # 使用 request.json() 读取 JSON 请求体
                # Starlette 会缓存结果，不会影响后续处理
                body = await request.json()
                # 脱敏处理
                body = self._sanitize_data(body)
                data["body"] = body
            except (json.JSONDecodeError, ValueError, TypeError):
                # 如果不是 JSON 格式，不记录请求体
                # 避免读取原始 body 导致后续处理无法读取
                pass

        return data

    def _sanitize_data(self, data: Any) -> Any:
        """脱敏敏感数据

        Args:
            data: 需要脱敏的数据

        Returns:
            Any: 脱敏后的数据
        """
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                # 敏感字段脱敏
                if key.lower() in [
                    "password",
                    "old_password",
                    "new_password",
                    "token",
                    "jwt",
                    "secret",
                    "api_key",
                    "access_token",
                    "refresh_token",
                ]:
                    if value:
                        # 保留前2个字符，其余用 * 替换
                        if isinstance(value, str) and len(value) > 2:
                            sanitized[key] = value[:2] + "*" * min(len(value) - 2, 10)
                        else:
                            sanitized[key] = "***"
                    else:
                        sanitized[key] = value
                else:
                    # 递归处理嵌套数据
                    sanitized[key] = self._sanitize_data(value)
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_data(item) for item in data]
        else:
            return data

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端IP地址

        Args:
            request: HTTP请求对象

        Returns:
            str: 客户端IP地址
        """
        # 优先从 X-Forwarded-For 获取（代理场景）
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For 可能包含多个IP，取第一个
            return forwarded_for.split(",")[0].strip()

        # 从 X-Real-IP 获取
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 从客户端信息获取
        if hasattr(request, "client") and request.client:
            return request.client.host

        return "unknown"

    def _log_audit(
        self,
        request: Request,
        response: Response,
        user_id: str,
        auth_type: str,
        request_data: Dict[str, Any],
    ) -> None:
        """记录审计日志

        Args:
            request: HTTP请求对象
            response: HTTP响应对象
            user_id: 用户ID
            auth_type: 认证类型
            request_data: 请求数据（已脱敏）
        """
        audit_logger = self.logging_service.get_audit_logger()

        # 构建审计日志消息
        status_code = response.status_code
        client_ip = self._get_client_ip(request)
        method = request_data["method"]
        path = request_data["path"]

        # 格式化审计日志：直接使用 {method} {path} 作为操作标识
        audit_message = (
            f"操作: {method} {path}, "
            f"用户: {user_id}, "
            f"认证类型: {auth_type}, "
            f"状态码: {status_code}, "
            f"IP: {client_ip}"
        )

        # 添加请求参数（如果有）
        if "body" in request_data:
            # 只记录关键字段，避免日志过大
            body_summary = self._summarize_body(request_data["body"])
            if body_summary:
                audit_message += f", 参数: {body_summary}"

        # 记录审计日志
        audit_logger.info(audit_message)

    def _summarize_body(self, body: Any) -> str:
        """摘要请求体，只保留关键信息

        Args:
            body: 请求体数据

        Returns:
            str: 摘要字符串
        """
        if isinstance(body, dict):
            # 提取关键字段
            summary_parts = []
            for key in ["name", "token", "provider", "datasource", "description"]:
                if key in body:
                    value = body[key]
                    if isinstance(value, str) and len(value) > 20:
                        value = value[:20] + "..."
                    summary_parts.append(f"{key}={value}")
            if summary_parts:
                return ", ".join(summary_parts)
        elif isinstance(body, str):
            if len(body) > 50:
                return body[:50] + "..."
            return body

        return ""
