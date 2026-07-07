"""SSH 主机相关业务事件"""

from uuid import UUID

from dm_mcp.core.events import Event


class SSHHostCreated(Event):
    """SSH 主机已创建"""

    host_id: UUID
    name: str
    host: str
    port: int
    username: str
    key_based: bool
    description: str
    owner_id: str | None = None

    @classmethod
    def from_model(cls, model) -> "SSHHostCreated":
        import uuid as _uuid

        hid = model.id if isinstance(model.id, _uuid.UUID) else _uuid.uuid4()
        return cls(
            host_id=hid,
            name=model.name or "",
            host=model.host or "",
            port=model.port if model.port is not None else 22,
            username=model.username or "",
            key_based=model.key_based if model.key_based is not None else False,
            description=model.description or "",
            owner_id=model.owner_id,
        )


class SSHHostUpdated(Event):
    """SSH 主机已更新"""

    host_id: UUID
    name: str
    host: str
    port: int
    username: str
    key_based: bool
    description: str
    owner_id: str | None = None

    @classmethod
    def from_model(cls, model) -> "SSHHostUpdated":
        import uuid as _uuid

        hid = model.id if isinstance(model.id, _uuid.UUID) else _uuid.uuid4()
        return cls(
            host_id=hid,
            name=model.name or "",
            host=model.host or "",
            port=model.port if model.port is not None else 22,
            username=model.username or "",
            key_based=model.key_based if model.key_based is not None else False,
            description=model.description or "",
            owner_id=model.owner_id,
        )


class SSHHostDeleted(Event):
    """SSH 主机已删除"""

    host_id: UUID
    name: str
    owner_id: str | None = None

    @classmethod
    def from_model(cls, model) -> "SSHHostDeleted":
        import uuid as _uuid

        hid = model.id if isinstance(model.id, _uuid.UUID) else _uuid.uuid4()
        return cls(
            host_id=hid,
            name=model.name or "",
            owner_id=model.owner_id,
        )
