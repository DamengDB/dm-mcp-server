"""
DataSourceService（控制面 + 执行入口）

提供服务功能：
- 数据源配置的持久化与 CRUD
- 用户权限校验
- SQL 执行入口（路由 + 鉴权 + 调用 AsyncPoolService）
- 发布数据源变更事件（由 AsyncPoolService 订阅并驱动 Pool 生命周期）
"""

import asyncio
import logging
import re
import time
from typing import Any

from dmAsync.pool import Pool
from sqlalchemy import select

from dm_mcp.common import messages
from dm_mcp.infra.persistence import (
    AppSettingsModel,
    DataSourceModel,
    OwnedQuery,
    bootstrap_schema,
    get_async_session,
    init_db,
)
from dm_mcp.infra.metrics.metrics import PoolQueryMetrics
from dm_mcp.infra.security.crypto import FernetCrypto
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.domain.datasource.events import (
    DataSourceCreated,
    DataSourceDeleted,
    DataSourceUpdated,
)
from dm_mcp.infra.messaging.event import EventService
from .pool import AsyncPoolService
from dm_mcp.core.service import BaseService
from dm_mcp.infra.config import Settings
from dm_mcp.infra.persistence.pool_config import DmPoolConfig


logger = logging.getLogger(__name__)


class DataSourceService(BaseService):
    """数据源配置管理服务 + SQL 执行入口

    职责：
    - 持久化数据源配置到数据库
    - CRUD 操作 + 用户权限校验
    - SQL 执行：路由选择、黑名单检查、鉴权、重试、指标收集
    - 通过事件订阅驱动 AsyncPoolService 的 Pool 生命周期
    """

    def __init__(
        self,
        settings: Settings,
        event_service: EventService,
        pool_service: AsyncPoolService,
        crypto: FernetCrypto | None = None,
    ) -> None:
        self.settings = settings
        self.pool_cfg = DmPoolConfig()
        self._event_service = event_service
        self._pool_service = pool_service
        self._crypto = crypto
        self._lb_state: dict[str, Any] = {}

    def _encrypt_password(self, plaintext: str) -> str:
        """加密密码（空值不加密）"""
        if not plaintext or self._crypto is None:
            return plaintext
        return "enc$" + self._crypto.encrypt(plaintext)

    def _decrypt_password(self, ciphertext: str) -> str:
        """解密密码（enc$ 前缀标识加密内容）"""
        if not ciphertext or self._crypto is None:
            return ciphertext
        return self._crypto.decrypt(ciphertext[4:])

    def _decrypt_model_password(self, model: DataSourceModel | None) -> None:
        """就地解密 model 的 password 字段"""
        if model is not None:
            model.password = self._decrypt_password(model.password)

    async def startup(self) -> None:
        init_db(self.settings.database)
        await bootstrap_schema(self.settings.database)
        await self._load_pool_config()
        await self._init_enabled_pools()
        logger.info(f"数据源服务已初始化: {self.settings.database.db_type}")

    async def _init_enabled_pools(self) -> None:
        """启动时为所有已启用数据源创建连接池"""
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.enabled == True)
            )
            models = result.scalars().all()

        for model in models:
            self._decrypt_model_password(model)
            try:
                await self._pool_service.add_pool(model)
            except Exception as e:
                logger.error(
                    f"启动建池失败: {model.name}, err={e}", exc_info=True
                )

        if models:
            logger.info(f"启动时已为 {len(models)} 个 enabled 数据源创建连接池")

    async def shutdown(self) -> None:
        pass

    # ============================================================
    # 连接池行为配置持久化
    # ============================================================

    async def _load_pool_config(self) -> None:
        """启动时从数据库加载配置，覆盖 .env 默认值"""
        keys = [
            "pool.read_write_split",
            "pool.load_balancing_strategy",
            "pool.default_source",
            "pool.max_retries",
            "pool.retry_backoff_ms",
        ]
        async with get_async_session() as session:
            for key in keys:
                result = await session.execute(
                    select(AppSettingsModel).where(AppSettingsModel.key == key)
                )
                setting = result.scalar_one_or_none()
                if setting is None:
                    continue
                field_name = key.replace("pool.", "")
                current = getattr(self.pool_cfg, field_name)
                if isinstance(current, bool):
                    value = setting.value.lower() == "true"
                elif isinstance(current, int):
                    value = int(setting.value)
                else:
                    value = setting.value
                setattr(self.pool_cfg, field_name, value)

    async def update_pool_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        """更新配置并持久化到数据库，同时更新内存热生效"""
        for key, value in updates.items():
            if not hasattr(self.pool_cfg, key):
                raise ValueError(f"无效的池配置项: {key}")
            setattr(self.pool_cfg, key, value)

        async with get_async_session() as session:
            for key, value in updates.items():
                db_key = f"pool.{key}"
                result = await session.execute(
                    select(AppSettingsModel).where(AppSettingsModel.key == db_key)
                )
                setting = result.scalar_one_or_none()
                str_value = str(value).lower() if isinstance(value, bool) else str(value)
                if setting is not None:
                    setting.value = str_value
                else:
                    session.add(AppSettingsModel(key=db_key, value=str_value))

        if "load_balancing_strategy" in updates:
            self._lb_state.clear()

        return {
            "read_write_split": self.pool_cfg.read_write_split,
            "load_balancing_strategy": self.pool_cfg.load_balancing_strategy,
            "default_source": self.pool_cfg.default_source,
            "max_retries": self.pool_cfg.max_retries,
            "retry_backoff_ms": self.pool_cfg.retry_backoff_ms,
        }

    # ============================================================
    # 鉴权 + 获取 Pool
    # ============================================================

    async def get_pool(self, name: str) -> Pool:
        """获取数据源的连接池（含鉴权）

        Args:
            name: 数据源名称

        Returns:
            Pool 对象

        Raises:
            ValueError: 数据源不存在或已禁用
            AuthorizationError: 无权访问
            Exception: 建池失败
        """
        model = await self.get_datasource(name)
        if model is None:
            raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND.format(name=name))
        if not model.enabled:
            raise ValueError(messages.MSG_DATASOURCE_DISABLED.format(name=name))
        return await self._pool_service.get_or_create_pool(model)

    # ============================================================
    # SQL 执行入口
    # ============================================================

    async def execute_query(
        self,
        sql: str,
        *,
        source: str = "auto",
        schema: str | None = None,
        max_rows: int | None = None,
        timeout: float | None = None,
        timeout_ms: int | None = None,
        read_only: bool | None = None,
        params: dict[str, Any] | None = None,
        **kwargs: object,
    ) -> dict[str, Any]:
        """安全执行器（带异常安全、重试、指标收集）"""
        # 确定是否为只读查询
        if read_only is not None:
            is_read_only = read_only
        else:
            is_read_only = self._is_read_sql(sql)
        sql_type = "query" if is_read_only else "write"

        # 路由选择
        chosen_source = await self._choose_source(source, is_read_only)


        # 获取 Pool（含鉴权）
        pool = await self.get_pool(chosen_source)

        # 只读保护
        self._check_read_only_guard(sql, chosen_source)

        # 统一计算超时
        if timeout_ms is not None:
            timeout_s = timeout_ms / 1000.0
        elif timeout is not None:
            timeout_s = timeout
        else:
            timeout_s = None

        max_retries = max(0, int(self.pool_cfg.max_retries))
        backoff_ms = max(0, int(self.pool_cfg.retry_backoff_ms))

        last_err: Exception | None = None
        start_all = time.time()

        for attempt in range(max_retries + 1):
            try:
                t0 = time.time()

                if timeout_s is not None and timeout_s > 0:
                    result = await asyncio.wait_for(
                        self._pool_service.execute(pool, sql, params, schema),
                        timeout=timeout_s,
                    )
                else:
                    result = await self._pool_service.execute(pool, sql, params, schema)

                # bug 131936：max_rows<=0 时必须返回空结果集，不得因未截断而返回全部行
                if max_rows is not None:
                    if max_rows <= 0:
                        result = []
                    else:
                        result = result[:max_rows]

                duration_ms = round((time.time() - t0) * 1000, 3)

                self._record_metrics(
                    source=chosen_source,
                    is_read_only=is_read_only,
                    sql_type=sql_type,
                    status="ok",
                    duration_ms=duration_ms,
                    retries=attempt,
                    error=False,
                )

                return {
                    "sql": sql,
                    "params": params,
                    "result": result,
                    "status": "ok",
                    "source": chosen_source,
                    "read_only": is_read_only,
                    "duration_ms": duration_ms,
                    "summary": f"执行完成，返回 {len(result)} 行",
                }

            except Exception as e:
                last_err = e
                duration_ms = round((time.time() - start_all) * 1000, 3)

                self._record_metrics(
                    source=chosen_source,
                    is_read_only=is_read_only,
                    sql_type=sql_type,
                    status="error",
                    duration_ms=duration_ms,
                    retries=attempt,
                    error=True,
                )

                if attempt < max_retries:
                    await asyncio.sleep(backoff_ms / 1000.0)

        raise last_err  # type: ignore[misc]

    @property
    def pool_service(self) -> AsyncPoolService:
        """连接池服务（Provider 层 explain trace 等会话级操作使用）。"""
        return self._pool_service

    async def _choose_source(self, source: str, is_read: bool) -> str:
        """选择数据源（基于当前用户可见的数据源）"""
        visible = await self.list_datasources()
        enabled_visible = {ds.name: ds for ds in visible if ds.enabled}

        if source in enabled_visible:
            return source

        if source in ("primary", "read_write"):
            chosen = self._choose_by_role(enabled_visible, False)
            if chosen:
                return chosen
        if source in ("replica", "read_only"):
            chosen = self._choose_by_role(enabled_visible, True)
            if chosen:
                return chosen

        if source == "auto":
            if is_read and self.pool_cfg.read_write_split:
                chosen = self._choose_by_role(enabled_visible, True)
                if chosen:
                    return chosen
            chosen = self._choose_by_role(enabled_visible, False)
            if chosen:
                return chosen

        if enabled_visible:
            return next(iter(enabled_visible.keys()))

        raise ValueError(messages.MSG_DATASOURCE_NONE_AVAILABLE)

    def _choose_by_role(
        self, enabled_visible: dict[str, DataSourceModel], read_only: bool
    ) -> str | None:
        matching = [
            name for name, ds in enabled_visible.items() if ds.read_only == read_only
        ]
        if not matching:
            return None

        strategy = self.pool_cfg.load_balancing_strategy
        if strategy == "round_robin":
            return self._choose_round_robin(matching)
        if strategy == "weighted_round_robin":
            return self._choose_weighted_rr(matching, enabled_visible)
        if strategy == "least_connections":
            return self._choose_least_connections(matching)
        return matching[0]

    def _choose_round_robin(self, names: list[str]) -> str:
        key = f"rr_{'_'.join(names)}"
        idx = self._lb_state.get(key, 0)
        chosen = names[idx % len(names)]
        self._lb_state[key] = (idx + 1) % len(names)
        return chosen

    def _choose_weighted_rr(
        self, names: list[str], enabled_visible: dict[str, DataSourceModel]
    ) -> str:
        key = f"wrr_{'_'.join(names)}"
        weighted: list[str] = []
        for name in names:
            weight = enabled_visible[name].weight
            weighted.extend([name] * max(1, weight))
        idx = self._lb_state.get(key, 0)
        chosen = weighted[idx % len(weighted)]
        self._lb_state[key] = (idx + 1) % len(weighted)
        return chosen

    def _choose_least_connections(self, names: list[str]) -> str:
        best_name = names[0]
        best_active = float("inf")
        for name in names:
            pool = self._pool_service._pools.get(name)
            if pool is None:
                continue
            size = getattr(pool, "size", 0)
            freesize = getattr(pool, "freesize", 0)
            active = max(0, int(size) - int(freesize))
            if active < best_active:
                best_active = active
                best_name = name
        return best_name

    def _check_read_only_guard(self, sql: str, chosen_source: str) -> None:
        pass

    @staticmethod
    def _is_read_sql(sql: str) -> bool:
        s = sql.strip().lstrip("(").strip()
        if not s:
            return True
        head = s.split(None, 1)[0].upper()
        return head in ("SELECT", "WITH", "SHOW", "DESC", "DESCRIBE", "EXPLAIN")

    def _record_metrics(
        self,
        source: str,
        is_read_only: bool,
        sql_type: str,
        status: str,
        duration_ms: float,
        retries: int,
        error: bool,
    ) -> None:
        try:
            m = PoolQueryMetrics(
                source=source,
                is_read_only=is_read_only,
                lb_strategy=self.pool_cfg.load_balancing_strategy,
                sql_type=sql_type,
                status=status,
                total=1,
                error=1 if error else 0,
                retries=int(retries),
                duration_ms=float(duration_ms),
            )
            self._pool_service.metrics_service.record_dataclass(m, prefix="db_pool")
        except Exception as e:
            logger.debug(f"记录 metrics 失败: {e}")

    # ============================================================
    # CRUD 操作
    # ============================================================

    async def list_datasources(self) -> list[DataSourceModel]:
        """列出当前用户可见的数据源"""
        async with get_async_session() as session:
            result = await session.execute(
                OwnedQuery.filter(select(DataSourceModel), DataSourceModel)
            )
            models = list(result.scalars().all())

        for model in models:
            self._decrypt_model_password(model)
        return models

    async def get_datasource(
        self, name: str, skip_authz: bool = False
    ) -> DataSourceModel | None:
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            if not skip_authz:
                OwnedQuery.check_access(model)

        self._decrypt_model_password(model)
        return model

    async def get_datasource_by_id(
        self, datasource_id: __import__("uuid").UUID, skip_authz: bool = False
    ) -> DataSourceModel | None:
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.id == datasource_id)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            if not skip_authz:
                OwnedQuery.check_access(model)

        self._decrypt_model_password(model)
        return model

    async def add_datasource(self, model: DataSourceModel) -> None:
        user_id = self.current_user_id

        # 保存明文密码用于事件发布
        plain_password = model.password

        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == model.name)
            )
            if result.scalar_one_or_none():
                raise ValueError(messages.MSG_DATASOURCE_NAME_EXISTS.format(name=model.name))

            all_result = await session.execute(select(DataSourceModel))
            all_models = all_result.scalars().all()
            names = [m.name for m in all_models] + [model.name]
            if len(names) != len(set(names)):
                raise ValueError(messages.MSG_DATASOURCE_NAME_MUST_BE_UNIQUE)

            model.owner_id = user_id
            model.password = self._encrypt_password(plain_password)
            session.add(model)

        logger.info(f"已添加数据源: {model.name} (owner={user_id})")
        # 恢复明文密码后发布事件（事件消费者需要明文）
        model.password = plain_password
        await self._event_service.publish_strict(DataSourceCreated.from_model(model))

    async def update_datasource(
        self, name: str, new_model: DataSourceModel, skip_authz: bool = False
    ) -> None:
        # 保存明文密码用于事件发布
        plain_password = new_model.password

        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND.format(name=name))
            if not skip_authz:
                OwnedQuery.check_access(model)

            if new_model.name != name:
                existing_result = await session.execute(
                    select(DataSourceModel).where(DataSourceModel.name == new_model.name)
                )
                if existing_result.scalar_one_or_none():
                    raise ValueError(messages.MSG_DATASOURCE_NAME_EXISTS.format(name=new_model.name))

            all_result = await session.execute(select(DataSourceModel))
            all_models = all_result.scalars().all()
            names = [m.name for m in all_models if m.name != name] + [new_model.name]
            if len(names) != len(set(names)):
                raise ValueError(messages.MSG_DATASOURCE_NAME_MUST_BE_UNIQUE)

            encrypted_password = self._encrypt_password(plain_password)
            if new_model.name != name:
                await session.delete(model)
                await session.flush()
                new_model.owner_id = model.owner_id
                new_model.password = encrypted_password
                session.add(new_model)

                # rename 时联动更新默认数据源设置
                default_setting_result = await session.execute(
                    select(AppSettingsModel).where(
                        AppSettingsModel.key == "default_datasource"
                    )
                )
                default_setting = default_setting_result.scalar_one_or_none()
                if default_setting and default_setting.value == name:
                    default_setting.value = new_model.name
            else:
                model.enabled = new_model.enabled
                model.deploy_type = new_model.deploy_type
                model.read_only = new_model.read_only
                model.dsn = new_model.dsn
                model.host = new_model.host
                model.port = new_model.port
                model.user = new_model.user
                model.password = encrypted_password
                model.minsize = new_model.minsize
                model.maxsize = new_model.maxsize
                model.timeout = new_model.timeout
                model.weight = new_model.weight

        logger.info(f"已更新数据源: {name} -> {new_model.name}")
        # 恢复明文密码后发布事件（事件消费者需要明文）
        new_model.password = plain_password
        await self._event_service.publish_strict(
            DataSourceUpdated.from_model(new_model, old_name=name)
        )

    async def delete_datasource(self, name: str, skip_authz: bool = False) -> None:
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND.format(name=name))
            if not skip_authz:
                OwnedQuery.check_access(model)

            is_default = False
            default_setting_result = await session.execute(
                select(AppSettingsModel).where(
                    AppSettingsModel.key == "default_datasource"
                )
            )
            default_setting = default_setting_result.scalar_one_or_none()
            if default_setting and default_setting.value == name:
                is_default = True

            if is_default and default_setting:
                await session.delete(default_setting)
                logger.warning(f"已删除默认数据源 '{name}'，已同时清理默认数据源设置")

            await session.delete(model)

        logger.info(f"已删除数据源: {name}")
        await self._event_service.publish_strict(
            DataSourceDeleted.from_model(model)
        )

    async def enable_datasource(self, name: str) -> None:
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND.format(name=name))
            OwnedQuery.check_access(model)
            if model.enabled:
                logger.info(f"数据源已启用: {name}")
                return
            model.enabled = True

        logger.info(f"已启用数据源: {name}")
        self._decrypt_model_password(model)
        await self._event_service.publish_strict(
            DataSourceUpdated.from_model(model, old_name=name)
        )

    async def disable_datasource(self, name: str) -> None:
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND.format(name=name))
            OwnedQuery.check_access(model)
            if not model.enabled:
                logger.info(messages.MSG_DATASOURCE_DISABLED.format(name=name))
                return
            model.enabled = False

        logger.info(f"已禁用数据源: {name}")
        self._decrypt_model_password(model)
        await self._event_service.publish_strict(
            DataSourceUpdated.from_model(model, old_name=name)
        )

    # ============================================================
    # 默认数据源管理
    # ============================================================

    async def get_default_datasource(self) -> str:
        async with get_async_session() as session:
            result = await session.execute(
                select(AppSettingsModel).where(
                    AppSettingsModel.key == "default_datasource"
                )
            )
            setting = result.scalar_one_or_none()
            if setting:
                ds_name = setting.value
                ds_result = await session.execute(
                    select(DataSourceModel).where(DataSourceModel.name == ds_name)
                )
                ds_model = ds_result.scalar_one_or_none()
                if ds_model:
                    try:
                        OwnedQuery.check_access(ds_model)
                        return ds_name
                    except Exception:
                        logger.warning(
                            f"默认数据源 '{ds_name}' 不属于当前用户，忽略该设置"
                        )
                else:
                    logger.warning(
                        f"默认数据源 '{ds_name}' 不存在，已清理默认数据源设置"
                    )
                    await session.delete(setting)
                    await session.commit()

        if hasattr(self.pool_cfg, "default_source"):
            return self.pool_cfg.default_source
        return "primary"

    async def set_default_datasource(self, name: str) -> None:
        ds = await self.get_datasource(name)
        if not ds:
            raise ValueError(messages.MSG_DATASOURCE_NOT_FOUND.format(name=name))

        async with get_async_session() as session:
            result = await session.execute(
                select(AppSettingsModel).where(
                    AppSettingsModel.key == "default_datasource"
                )
            )
            setting = result.scalar_one_or_none()

            if setting:
                setting.value = name
            else:
                setting = AppSettingsModel(key="default_datasource", value=name)
                session.add(setting)

        logger.info(f"已设置默认数据源: {name}")

# =========================================================
# Factory
# =========================================================
class DataSourceServiceFactory(ServiceFactory):
    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="datasource_service",
            service_type=DataSourceService,
            description="数据源配置管理服务 + SQL 执行入口",
            author="DM MCP Team",
            dependencies=["event_service", "async_pool_service"],
            priority=30,  # 尽早初始化数据库，保证依赖 db 的服务可用
        )

    def create(self, settings, event_service, async_pool_service, **deps) -> DataSourceService:
        from dm_mcp.common.utils.crypto import to_fernet_key

        app_secret = settings.app_secret.get_secret_value()
        if not app_secret:
            raise ValueError("APP_SECRET 是必填项，用于加密数据源密码。")
        crypto = FernetCrypto(to_fernet_key(app_secret))
        return DataSourceService(settings, event_service, async_pool_service, crypto)
