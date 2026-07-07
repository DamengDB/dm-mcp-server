"""CLI 下载控制器（/cli-download/{program}/{platform}）

供客户端下载 dmctl / dmctlx 可执行文件，无需认证。
"""

import logging
import os

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse

from dm_mcp.api.base import BaseController
from dm_mcp.infra.config.settings import Settings
from dm_mcp.infra.web.error_codes import ErrorCode

logger = logging.getLogger(__name__)

SUPPORTED_PROGRAMS = {"dmctl", "dmctlx"}
SUPPORTED_PLATFORMS = {"windows", "linux"}


def _build_filename(program: str, platform: str) -> str:
    """根据程序名和平台构造文件名。"""
    ext = ".exe" if platform == "windows" else ""
    return f"{program}{ext}"


class CLIDownloadController(BaseController):
    """CLI 下载控制器"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def handle_download(self, request: Request) -> FileResponse | JSONResponse:
        """处理 CLI 下载请求

        路由: /cli-download/{program}/{platform}
        program: dmctl | dmctlx
        platform: windows | linux
        """
        program = request.path_params.get("program", "").lower()
        platform = request.path_params.get("platform", "").lower()

        if program not in SUPPORTED_PROGRAMS:
            return self.error(
                error=f"不支持的程序: '{program}'。支持的程序: {', '.join(sorted(SUPPORTED_PROGRAMS))}",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )

        if platform not in SUPPORTED_PLATFORMS:
            return self.error(
                error=f"不支持的平台: '{platform}'。支持的平台: {', '.join(sorted(SUPPORTED_PLATFORMS))}",
                code=ErrorCode.VALIDATION_ERROR,
                status_code=400,
            )

        filename = _build_filename(program, platform)
        cli_dir = self.settings.server.cli_path
        file_path = os.path.join(cli_dir, filename)

        if not os.path.isfile(file_path):
            logger.warning("CLI 文件不存在: %s", file_path)
            return self.error(
                error=f"该文件暂不可用: {filename}",
                code=ErrorCode.OPERATION_FAILED,
                status_code=404,
            )

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/octet-stream",
        )
