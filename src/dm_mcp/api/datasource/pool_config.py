"""连接池行为配置控制器模块

提供 Admin-only 的连接池全局行为配置管理 API：
- 查询当前配置
- 更新配置（热生效，持久化到数据库）

所有写操作要求 admin 权限。
"""

import logging

from pydantic import BaseModel, Field, ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse

from dm_mcp.domain.datasource.services.datasource import DataSourceService

from dm_mcp.api.base import BaseController

logger = logging.getLogger(__name__)

_VALID_STRATEGIES = {"round_robin", "least_connections", "weighted_round_robin"}


class PutPoolConfigRequest(BaseModel):
    """PUT /pool-config 请求体"""

    read_write_split: bool | None = None
    load_balancing_strategy: str | None = Field(None, pattern=r"^(round_robin|least_connections|weighted_round_robin)$")
    default_source: str | None = None
    max_retries: int | None = Field(None, ge=0, le=10)
    retry_backoff_ms: int | None = Field(None, ge=0, le=10000)


class PoolConfigController(BaseController):
    """连接池行为配置控制器"""

    def __init__(self, datasource_service: DataSourceService) -> None:
        self._datasource_service = datasource_service

    def _check_admin(self, request: Request) -> JSONResponse | None:
        if not self.is_admin(request):
            return self.error(
                "需要管理员权限",
                code="FORBIDDEN",
                status_code=403,
            )
        return None

    async def handle_get(self, request: Request) -> JSONResponse:
        """GET /pool-config — 获取当前连接池行为配置"""
        cfg = self._datasource_service.pool_cfg
        return self.success(
            data={
                "read_write_split": cfg.read_write_split,
                "load_balancing_strategy": cfg.load_balancing_strategy,
                "default_source": cfg.default_source,
                "max_retries": cfg.max_retries,
                "retry_backoff_ms": cfg.retry_backoff_ms,
            }
        )

    async def handle_put(self, request: Request) -> JSONResponse:
        """PUT /pool-config — 更新连接池行为配置"""
        if resp := self._check_admin(request):
            return resp

        try:
            body = await request.json()
            req = PutPoolConfigRequest(**body)
        except ValidationError as e:
            return self.error(
                self.format_validation_error(e),
                code="VALIDATION_ERROR",
                status_code=400,
            )
        except Exception as e:
            return self.error(f"无效的请求体: {e}", status_code=400)

        updates: dict[str, object] = {}
        if req.read_write_split is not None:
            updates["read_write_split"] = req.read_write_split
        if req.load_balancing_strategy is not None:
            updates["load_balancing_strategy"] = req.load_balancing_strategy
        if req.default_source is not None:
            updates["default_source"] = req.default_source
        if req.max_retries is not None:
            updates["max_retries"] = req.max_retries
        if req.retry_backoff_ms is not None:
            updates["retry_backoff_ms"] = req.retry_backoff_ms

        if not updates:
            return self.error("未提供任何要更新的字段", status_code=400)

        try:
            result = await self._datasource_service.update_pool_config(updates)
        except ValueError as e:
            return self.error(str(e), status_code=400)

        actor = self.get_current_user_id(request)
        logger.info(f"actor={actor}, action=update_pool_config, updates={updates}")

        return self.success(data=result)
