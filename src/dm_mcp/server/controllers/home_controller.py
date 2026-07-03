"""主页控制器模块

提供主页路由处理，支持重定向到前端URL或返回静态页面。
"""

import os

from starlette.requests import Request
from starlette.responses import FileResponse, RedirectResponse

from dm_mcp.settings.settings import Settings


class HomeController(object):
    """主页控制器

    处理主页请求，根据配置返回重定向或静态文件。
    """

    def __init__(self, settings: Settings) -> None:
        """初始化主页控制器

        Args:
            settings: 服务器设置
        """
        self.settings = settings

    async def handle_home_page(self, request: Request):
        """处理主页请求

        如果配置了frontend_url，则重定向到前端URL；
        否则返回静态页面（index.html）。

        Args:
            request: HTTP请求对象

        Returns:
            RedirectResponse | FileResponse: 重定向响应或文件响应
        """
        # 如果配置了 frontend_url，则重定向到前端 URL
        frontend_url = self.settings.server.frontend_url
        if frontend_url:
            return RedirectResponse(url=frontend_url)

        # 否则返回静态页面
        static_dir = self.settings.server.static_path
        return FileResponse(os.path.join(static_dir, "index.html"))
