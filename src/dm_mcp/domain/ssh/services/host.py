"""SSH 主机配置管理服务

提供 SSH 主机的 CRUD、密码加解密、权限校验、Token 关联查询。
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from dm_mcp.infra.persistence import OwnedQuery, SSHHostModel, get_async_session
from dm_mcp.infra.security.crypto import FernetCrypto
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.domain.ssh.events import SSHHostCreated, SSHHostDeleted, SSHHostUpdated
from dm_mcp.core.service import BaseService
from dm_mcp.infra.messaging.event import EventService
from dm_mcp.infra.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class SSHHostConfig:
    """SSH 主机配置内存结构"""

    id: str
    name: str
    host: str
    port: int
    username: str
    key_based: bool
    password: str | None
    description: str
    owner_id: str | None


class SSHHostService(BaseService):
    """SSH 主机配置管理服务

    提供 SSH 主机的 CRUD、密码加解密、Token 关联查询。
    """

    def __init__(
        self,
        settings: Settings,
        event_service: EventService,
        crypto: FernetCrypto | None = None,
    ) -> None:
        self.settings = settings
        self._event_service = event_service
        self._crypto = crypto

    def _encrypt_password(self, plaintext: str) -> str:
        """加密密码（空值不加密）"""
        if not plaintext or self._crypto is None:
            return plaintext
        return "enc$" + self._crypto.encrypt(plaintext)

    def _decrypt_password(self, ciphertext: str) -> str:
        """解密密码（enc$ 前缀标识加密内容）"""
        if not ciphertext or self._crypto is None:
            return ciphertext
        if ciphertext.startswith("enc$"):
            return self._crypto.decrypt(ciphertext[4:])
        return ciphertext

    def _model_to_config(self, model: SSHHostModel) -> SSHHostConfig:
        """将模型转换为内存配置对象（含解密密码）"""
        return SSHHostConfig(
            id=str(model.id),
            name=model.name,
            host=model.host,
            port=model.port,
            username=model.username,
            key_based=model.key_based,
            password=self._decrypt_password(model.password_enc)
            if model.password_enc
            else None,
            description=model.description,
            owner_id=model.owner_id,
        )

    # ============================================================
    # CRUD 操作
    # ============================================================

    async def list_hosts(self) -> list[SSHHostModel]:
        """列出当前用户可见的 SSH 主机"""
        async with get_async_session() as session:
            result = await session.execute(
                OwnedQuery.filter(select(SSHHostModel), SSHHostModel)
            )
            return list(result.scalars().all())

    async def get_host(self, host_id: str, skip_authz: bool = False) -> SSHHostModel | None:
        """按 ID 获取 SSH 主机"""
        async with get_async_session() as session:
            result = await session.execute(
                select(SSHHostModel).where(SSHHostModel.id == uuid.UUID(host_id))
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            if not skip_authz:
                OwnedQuery.check_access(model)
        return model

    async def get_host_by_name(self, name: str, skip_authz: bool = False) -> SSHHostModel | None:
        """按名称获取 SSH 主机"""
        async with get_async_session() as session:
            result = await session.execute(
                select(SSHHostModel).where(SSHHostModel.name == name)
            )
            model = result.scalar_one_or_none()
            if not model:
                return None
            if not skip_authz:
                OwnedQuery.check_access(model)
        return model

    async def create_host(
        self,
        name: str,
        host: str,
        port: int,
        username: str,
        key_based: bool = False,
        password: str | None = None,
        description: str = "",
    ) -> SSHHostConfig:
        """创建 SSH 主机配置"""
        user_id = self.current_user_id

        async with get_async_session() as session:
            result = await session.execute(
                select(SSHHostModel).where(SSHHostModel.name == name)
            )
            if result.scalar_one_or_none():
                raise ValueError(f"SSH 主机名称已存在: {name}")

            encrypted_password = ""
            if not key_based and password:
                encrypted_password = self._encrypt_password(password)

            model = SSHHostModel(
                name=name,
                host=host,
                port=port,
                username=username,
                key_based=key_based,
                password_enc=encrypted_password,
                description=description,
                owner_id=user_id,
            )
            session.add(model)

        logger.info(f"已创建 SSH 主机: {name} (owner={user_id})")
        await self._event_service.publish_strict(SSHHostCreated.from_model(model))
        return self._model_to_config(model)

    async def update_host(
        self,
        host_id: str,
        name: str | None = None,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        key_based: bool | None = None,
        password: str | None = None,
        description: str | None = None,
    ) -> SSHHostConfig:
        """更新 SSH 主机配置（PATCH 语义）"""
        async with get_async_session() as session:
            result = await session.execute(
                select(SSHHostModel).where(SSHHostModel.id == uuid.UUID(host_id))
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(f"SSH 主机不存在: {host_id}")
            OwnedQuery.check_access(model)

            if name is not None and name != model.name:
                existing = await session.execute(
                    select(SSHHostModel).where(SSHHostModel.name == name)
                )
                if existing.scalar_one_or_none():
                    raise ValueError(f"SSH 主机名称已存在: {name}")
                model.name = name
            if host is not None:
                model.host = host
            if port is not None:
                model.port = port
            if username is not None:
                model.username = username
            if key_based is not None:
                model.key_based = key_based
            if description is not None:
                model.description = description
            if password is not None:
                if key_based if key_based is not None else model.key_based:
                    model.password_enc = ""
                else:
                    model.password_enc = self._encrypt_password(password)
            elif key_based is not None and key_based:
                model.password_enc = ""

        logger.info(f"已更新 SSH 主机: {model.name}")
        await self._event_service.publish_strict(SSHHostUpdated.from_model(model))
        return self._model_to_config(model)

    async def delete_host(self, host_id: str) -> None:
        """删除 SSH 主机"""
        async with get_async_session() as session:
            result = await session.execute(
                select(SSHHostModel).where(SSHHostModel.id == uuid.UUID(host_id))
            )
            model = result.scalar_one_or_none()
            if not model:
                raise ValueError(f"SSH 主机不存在: {host_id}")
            OwnedQuery.check_access(model)

            await session.delete(model)

        logger.info(f"已删除 SSH 主机: {model.name}")
        await self._event_service.publish_strict(SSHHostDeleted.from_model(model))

    # ============================================================
    # 工具方法
    # ============================================================

    async def get_host_config(self, host_id: str) -> SSHHostConfig | None:
        """获取解密的 SSH 主机配置（供执行服务使用）"""
        model = await self.get_host(host_id, skip_authz=True)
        if not model:
            return None
        return self._model_to_config(model)

    async def resolve_host_ids_by_names(self, names: list[str]) -> list[str]:
        """将 SSH 主机名称列表解析为 UUID 列表"""
        ids: list[str] = []
        for name in names:
            model = await self.get_host_by_name(name, skip_authz=True)
            if not model:
                raise ValueError(f"SSH 主机不存在或无权限: {name}")
            ids.append(str(model.id))
        return ids

    async def list_hosts_by_ids(self, host_ids: list[str]) -> list[SSHHostModel]:
        """按 ID 列表批量查询 SSH 主机（仅返回当前用户可见的）"""
        if not host_ids:
            return []
        user_id = self.current_user_id
        async with get_async_session() as session:
            uuids = [uuid.UUID(hid) for hid in host_ids]
            result = await session.execute(
                select(SSHHostModel).where(
                    SSHHostModel.id.in_(uuids),
                    (SSHHostModel.owner_id == user_id)
                    | (SSHHostModel.owner_id.is_(None)),
                )
            )
            return list(result.scalars().all())


# =========================================================
# Factory
# =========================================================
class SSHHostServiceFactory(ServiceFactory):
    """SSH 主机配置管理服务工厂"""

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="ssh_host_service",
            service_type=SSHHostService,
            description="SSH 主机配置管理服务（CRUD + 加密 + 权限）",
            dependencies=["event_service"],
            priority=12,
        )

    def create(self, settings, event_service, **deps) -> SSHHostService:
        from dm_mcp.common.utils.crypto import to_fernet_key

        app_secret = settings.app_secret.get_secret_value()
        if not app_secret:
            raise ValueError("APP_SECRET 是必填项，用于加密 SSH 密码。")
        crypto = FernetCrypto(to_fernet_key(app_secret))
        return SSHHostService(settings, event_service, crypto)
