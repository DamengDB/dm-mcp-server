"""UTF-8 编码中间件

确保所有 HTTP 响应都包含正确的 UTF-8 字符集声明。
"""

import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class UTF8ResponseMiddleware(BaseHTTPMiddleware):
    """UTF-8 响应头中间件

    为所有 JSON 响应自动添加 UTF-8 字符集声明，确保中文等非 ASCII 字符正确显示。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求并设置UTF-8编码头

        Args:
            request: HTTP请求对象
            call_next: 下一个中间件或路由处理器

        Returns:
            Response: HTTP响应对象（已设置UTF-8编码头）
        """
        response = await call_next(request)

        # 获取当前的 Content-Type 头
        content_type = response.headers.get("content-type", "")

        # 如果是 JSON 响应且未指定字符集，则添加 UTF-8 字符集
        if "application/json" in content_type.lower():
            if "charset" not in content_type.lower():
                # 确保 Content-Type 包含 UTF-8 字符集
                response.headers["content-type"] = "application/json; charset=utf-8"

        # 对于其他文本类型的响应，也确保使用 UTF-8（如果适用）
        elif content_type and any(
            text_type in content_type.lower()
            for text_type in ["text/", "application/xml", "application/javascript"]
        ):
            if "charset" not in content_type.lower():
                response.headers["content-type"] = f"{content_type}; charset=utf-8"

        return response
