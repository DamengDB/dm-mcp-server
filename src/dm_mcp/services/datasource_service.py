"""
DataSourceService（控制面 + 元数据查询）

提供服务功能：
- 数据源配置的持久化
- 数据源配置的 CRUD 操作
- 配置验证（名称唯一等）
"""

import logging
import uuid
from typing import List, Optional

from pydantic import SecretStr
from sqlalchemy import select

from dm_mcp.core.db import (
    AppSettingsModel,
    DataSourceModel,
    create_tables,
    get_async_session,
    init_db,
)
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.services.base_service import BaseService
from dm_mcp.settings import Settings
from dm_mcp.settings.datasource_config import DataSourceConfig
from dm_mcp.settings.pool_config import DmPoolConfig

logger = logging.getLogger(__name__)


class DataSourceService(BaseService):
    """
    数据源配置管理服务

    职责：
    - 持久化数据源配置到数据库
    - CRUD 操作数据源配置
    - 配置验证（名称唯一等）
    """

    def __init__(
        self,
        settings: Settings,
        pool_cfg: DmPoolConfig,
    ) -> None:
        self.settings = settings
        self.pool_cfg = pool_cfg

    async def startup(self) -> None:
        """服务启动：初始化数据库并迁移现有数据"""
        # 初始化数据库
        init_db(self.settings.database)
        await create_tables()

        # 迁移：为现有数据源生成 UUID（如果还没有 id）
        await self._migrate_datasource_ids()

        logger.info(f"数据源服务已初始化: {self.settings.database.db_type}")

    async def _migrate_datasource_ids(self) -> None:
        """迁移：为现有数据源生成 UUID

        如果数据源表中存在没有 id 的记录（旧数据），为它们生成 UUID。
        注意：这需要数据库支持 ALTER TABLE，SQLite 可能需要重建表。
        """
        async with get_async_session() as session:
            # 检查是否有数据源需要迁移
            result = await session.execute(select(DataSourceModel))
            models = result.scalars().all()

            migrated_count = 0
            for model in models:
                # 如果模型没有 id（旧数据），生成一个
                if not hasattr(model, "id") or model.id is None:
                    # 注意：这需要数据库表已经更新了结构
                    # 如果表结构还没更新，这个迁移会在表结构更新后自动处理
                    try:
                        if not hasattr(model, "id"):
                            # 表结构还没更新，跳过（会在下次启动时处理）
                            continue
                        model.id = uuid.uuid4()
                        migrated_count += 1
                    except Exception as e:
                        logger.warning(f"迁移数据源 {model.name} 的 UUID 失败: {e}")

            if migrated_count > 0:
                logger.info(f"已为 {migrated_count} 个数据源生成 UUID")

    async def shutdown(self) -> None:
        """服务关闭"""
        pass

    # ============================================================
    # CRUD 操作
    # ============================================================

    async def list_datasources(self) -> List[DataSourceConfig]:
        """列出所有数据源配置

        Returns:
            数据源配置列表
        """
        async with get_async_session() as session:
            result = await session.execute(select(DataSourceModel))
            models = result.scalars().all()
            return [self._model_to_config(model) for model in models]

    async def get_datasource(self, name: str) -> Optional[DataSourceConfig]:
        """获取单个数据源配置（通过名称）

        Args:
            name: 数据源名称

        Returns:
            数据源配置，如果不存在返回 None
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if model:
                return self._model_to_config(model)
            return None

    async def get_datasource_by_id(
        self, datasource_id: uuid.UUID
    ) -> Optional[DataSourceConfig]:
        """获取单个数据源配置（通过 UUID）

        Args:
            datasource_id: 数据源 UUID

        Returns:
            数据源配置，如果不存在返回 None
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.id == datasource_id)
            )
            model = result.scalar_one_or_none()
            if model:
                return self._model_to_config(model)
            return None

    async def add_datasource(self, config: DataSourceConfig) -> None:
        """添加数据源配置

        Args:
            config: 数据源配置

        Raises:
            ValueError: 数据源名称已存在或配置验证失败
        """
        async with get_async_session() as session:
            # 检查名称是否重复
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == config.name)
            )
            if result.scalar_one_or_none():
                raise ValueError(f"数据源名称已存在: {config.name}")

            # 获取所有数据源用于验证
            all_result = await session.execute(select(DataSourceModel))
            all_models = all_result.scalars().all()
            all_configs = [self._model_to_config(m) for m in all_models]

            # 验证配置（添加新数据源后）
            all_configs.append(config)
            self._validate_datasources(all_configs)

            # 创建新模型
            model = self._config_to_model(config)
            session.add(model)
            # get_async_session 会自动提交

        logger.info(f"已添加数据源: {config.name}")

    async def update_datasource(self, name: str, config: DataSourceConfig) -> None:
        """更新数据源配置

        Args:
            name: 要更新的数据源名称
            config: 新的数据源配置

        Raises:
            ValueError: 数据源不存在、新名称已存在或配置验证失败
        """
        async with get_async_session() as session:
            # 查找现有数据源
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(f"数据源不存在: {name}")

            # 如果修改了名称，检查新名称是否重复
            if config.name != name:
                existing_result = await session.execute(
                    select(DataSourceModel).where(DataSourceModel.name == config.name)
                )
                if existing_result.scalar_one_or_none():
                    raise ValueError(f"数据源名称已存在: {config.name}")

            # 获取所有数据源用于验证（排除当前要更新的）
            all_result = await session.execute(select(DataSourceModel))
            all_models = all_result.scalars().all()
            all_configs = [
                self._model_to_config(m) for m in all_models if m.name != name
            ]

            # 添加新的配置
            all_configs.append(config)

            # 验证配置
            self._validate_datasources(all_configs)

            # 更新模型（如果名称改变，需要先删除旧的再创建新的）
            if config.name != name:
                await session.delete(model)
                await session.flush()  # 确保删除操作先执行
                new_model = self._config_to_model(config)
                session.add(new_model)
            else:
                # 更新现有模型
                self._update_model_from_config(model, config)
                # get_async_session 会自动提交

        logger.info(f"已更新数据源: {name} -> {config.name}")

    async def delete_datasource(self, name: str) -> None:
        """删除数据源配置

        如果删除的数据源是默认数据源，会同时清理默认数据源设置。

        Args:
            name: 要删除的数据源名称

        Raises:
            ValueError: 数据源不存在
        """
        async with get_async_session() as session:
            # 查找并删除
            result = await session.execute(
                select(DataSourceModel).where(DataSourceModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(f"数据源不存在: {name}")

            # 检查是否是默认数据源
            is_default = False
            default_setting_result = await session.execute(
                select(AppSettingsModel).where(
                    AppSettingsModel.key == "default_datasource"
                )
            )
            default_setting = default_setting_result.scalar_one_or_none()
            if default_setting and default_setting.value == name:
                is_default = True

            # 获取所有数据源用于验证（删除前）
            all_result = await session.execute(select(DataSourceModel))
            all_models = all_result.scalars().all()
            all_configs = [
                self._model_to_config(m) for m in all_models if m.name != name
            ]

            # 验证配置（删除后至少保留一个 primary）
            self._validate_datasources(all_configs)

            # 如果删除的是默认数据源，清理默认数据源设置
            if is_default and default_setting:
                await session.delete(default_setting)
                logger.warning(f"已删除默认数据源 '{name}'，已同时清理默认数据源设置")

            # 删除数据源
            await session.delete(model)
            # get_async_session 会自动提交

        logger.info(f"已删除数据源: {name}")

    async def enable_datasource(self, name: str) -> None:
        """启用数据源

        Args:
            name: 数据源名称

        Raises:
            ValueError: 数据源不存在
        """
        ds = await self.get_datasource(name)
        if not ds:
            raise ValueError(f"数据源不存在: {name}")

        if ds.enabled:
            logger.info(f"数据源已启用: {name}")
            return

        ds.enabled = True
        await self.update_datasource(name, ds)

    async def disable_datasource(self, name: str) -> None:
        """禁用数据源

        Args:
            name: 数据源名称

        Raises:
            ValueError: 数据源不存在
        """
        ds = await self.get_datasource(name)
        if not ds:
            raise ValueError(f"数据源不存在: {name}")

        if not ds.enabled:
            logger.info(f"数据源已禁用: {name}")
            return

        ds.enabled = False
        await self.update_datasource(name, ds)

    # ============================================================
    # 数据转换方法
    # ============================================================

    def _config_to_model(self, config: DataSourceConfig) -> DataSourceModel:
        """将 DataSourceConfig 转换为 DataSourceModel

        Args:
            config: 数据源配置

        Returns:
            数据源模型对象
        """
        return DataSourceModel(
            id=config.id,
            name=config.name,
            enabled=config.enabled,
            deploy_type=config.deploy_type,
            read_only=config.read_only,
            dsn=config.dsn,
            host=config.host,
            port=config.port,
            user=config.user,
            password=(
                config.password.get_secret_value()
                if isinstance(config.password, SecretStr)
                else str(config.password)
            ),
            dpc_cluster=None,
            minsize=config.minsize,
            maxsize=config.maxsize,
            timeout=config.timeout,
            weight=config.weight,
        )

    def _model_to_config(self, model: DataSourceModel) -> DataSourceConfig:
        """将 DataSourceModel 转换为 DataSourceConfig

        Args:
            model: 数据源模型对象

        Returns:
            数据源配置对象

        Raises:
            ValueError: deploy_type 值无效
        """
        deploy_type: str = model.deploy_type
        if deploy_type not in ("dmstandonle", "dmwatcher", "dmdsc", "dmdpc"):
            raise ValueError(f"无效的 deploy_type 值: {deploy_type}")

        return DataSourceConfig(
            id=model.id,
            name=model.name,
            enabled=model.enabled,
            deploy_type=deploy_type,
            read_only=model.read_only,
            dsn=model.dsn,
            host=model.host,
            port=model.port,
            user=model.user,
            password=SecretStr(model.password),
            minsize=model.minsize,
            maxsize=model.maxsize,
            timeout=model.timeout,
            weight=model.weight,
        )

    def _update_model_from_config(
        self, model: DataSourceModel, config: DataSourceConfig
    ) -> None:
        """使用 DataSourceConfig 更新 DataSourceModel

        Args:
            model: 要更新的数据源模型对象
            config: 数据源配置
        """
        model.enabled = config.enabled
        model.deploy_type = config.deploy_type
        model.read_only = config.read_only
        model.dsn = config.dsn
        model.host = config.host
        model.port = config.port
        model.user = config.user
        model.password = (
            config.password.get_secret_value()
            if isinstance(config.password, SecretStr)
            else str(config.password)
        )
        model.minsize = config.minsize
        model.maxsize = config.maxsize
        model.timeout = config.timeout
        model.weight = config.weight

    # ============================================================
    # 配置验证
    # ============================================================

    def _validate_datasources(self, datasources: List[DataSourceConfig]) -> None:
        """验证数据源配置

        验证规则：
        - 数据源名称必须唯一

        Args:
            datasources: 数据源配置列表

        Raises:
            ValueError: 配置验证失败（如名称重复）
        """
        # 如果列表为空，不需要验证（允许删除所有数据源）
        if not datasources:
            return

        names = [ds.name for ds in datasources]
        if len(names) != len(set(names)):
            raise ValueError("数据源名称必须唯一")

    # ============================================================
    # 默认数据源管理
    # ============================================================

    async def get_default_datasource(self) -> str:
        """获取默认数据源名称

        优先从数据库读取持久化的默认数据源设置，
        如果不存在或该数据源已被删除，则返回配置中的默认值。

        Returns:
            str: 默认数据源名称
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(AppSettingsModel).where(
                    AppSettingsModel.key == "default_datasource"
                )
            )
            setting = result.scalar_one_or_none()
            if setting:
                ds_name = setting.value
                # 验证默认数据源是否仍然存在
                ds_result = await session.execute(
                    select(DataSourceModel).where(DataSourceModel.name == ds_name)
                )
                ds_model = ds_result.scalar_one_or_none()
                if ds_model:
                    # 默认数据源存在，直接返回
                    return ds_name
                else:
                    # 默认数据源不存在，清理设置并记录警告
                    logger.warning(
                        f"默认数据源 '{ds_name}' 不存在，已清理默认数据源设置"
                    )
                    await session.delete(setting)
                    await session.commit()

        # 回退到配置中的默认值
        if hasattr(self.pool_cfg, "default_source"):
            return self.pool_cfg.default_source
        return "primary"

    async def set_default_datasource(self, name: str) -> None:
        """设置默认数据源名称

        验证数据源是否存在，然后将默认数据源名称持久化到数据库。

        Args:
            name: 数据源名称

        Raises:
            ValueError: 数据源不存在
        """
        # 验证数据源是否存在
        ds = await self.get_datasource(name)
        if not ds:
            raise ValueError(f"数据源不存在: {name}")

        # 持久化到数据库
        async with get_async_session() as session:
            result = await session.execute(
                select(AppSettingsModel).where(
                    AppSettingsModel.key == "default_datasource"
                )
            )
            setting = result.scalar_one_or_none()

            if setting:
                # 更新现有设置
                setting.value = name
            else:
                # 创建新设置
                setting = AppSettingsModel(key="default_datasource", value=name)
                session.add(setting)
            # get_async_session 会自动提交

        logger.info(f"已设置默认数据源: {name}")


# =========================================================
# Factory
# =========================================================
class DataSourceServiceFactory(ServiceFactory):
    """数据源管理服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="datasource_service",
            service_type=DataSourceService,
            description="数据源配置管理服务（SQLite 持久化 + CRUD）",
            author="DM MCP Team",
            dependencies=[],  # 不依赖其他服务
            priority=10,  # 优先级较高，早启动
        )

    def create(self, settings, **deps) -> DataSourceService:
        pool_cfg = getattr(settings, "pool", None)
        if pool_cfg is None:
            pool_cfg = DmPoolConfig()

        return DataSourceService(settings, pool_cfg)
