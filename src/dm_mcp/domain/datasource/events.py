"""数据源相关业务事件

订阅者(主要是 AsyncPoolService)根据这些事件维护连接池生命周期,
取代过去由 controller 同时调 datasource_service / pool_service 的 god handler 模式。

启停事件不单独建模:enable/disable 内部走 update_datasource,自然产生
DataSourceUpdated,订阅者用 has_pool(old_name) + new_name 判定动作。
"""

from uuid import UUID

from dm_mcp.core.events import Event


class DataSourceCreated(Event):
    """数据源已创建"""

    datasource_id: UUID
    name: str
    enabled: bool
    host: str
    port: int
    user: str
    password: str
    minsize: int
    maxsize: int
    timeout: float
    weight: int
    read_only: bool = False
    deploy_type: str = "dmstandalone"
    dsn: str = ""
    owner_id: str | None = None

    @classmethod
    def from_model(cls, model) -> "DataSourceCreated":
        import uuid as _uuid

        ds_id = model.id if isinstance(model.id, _uuid.UUID) else _uuid.uuid4()
        return cls(
            datasource_id=ds_id,
            name=model.name or "",
            enabled=model.enabled if model.enabled is not None else True,
            host=model.host or "localhost",
            port=model.port if model.port is not None else 5236,
            user=model.user or "SYSDBA",
            password=model.password or "",
            minsize=model.minsize if model.minsize is not None else 1,
            maxsize=model.maxsize if model.maxsize is not None else 10,
            timeout=model.timeout if model.timeout is not None else 30.0,
            weight=model.weight if model.weight is not None else 1,
            read_only=model.read_only if model.read_only is not None else False,
            deploy_type=model.deploy_type or "dmstandalone",
            dsn=model.dsn or "",
            owner_id=model.owner_id,
        )


class DataSourceUpdated(Event):
    """数据源已更新"""

    old_name: str
    datasource_id: UUID
    name: str
    enabled: bool
    host: str
    port: int
    user: str
    password: str
    minsize: int
    maxsize: int
    timeout: float
    weight: int
    read_only: bool = False
    deploy_type: str = "dmstandalone"
    dsn: str = ""
    owner_id: str | None = None

    @classmethod
    def from_model(cls, model, old_name: str) -> "DataSourceUpdated":
        import uuid as _uuid

        ds_id = model.id if isinstance(model.id, _uuid.UUID) else _uuid.uuid4()
        return cls(
            old_name=old_name,
            datasource_id=ds_id,
            name=model.name or "",
            enabled=model.enabled if model.enabled is not None else True,
            host=model.host or "localhost",
            port=model.port if model.port is not None else 5236,
            user=model.user or "SYSDBA",
            password=model.password or "",
            minsize=model.minsize if model.minsize is not None else 1,
            maxsize=model.maxsize if model.maxsize is not None else 10,
            timeout=model.timeout if model.timeout is not None else 30.0,
            weight=model.weight if model.weight is not None else 1,
            read_only=model.read_only if model.read_only is not None else False,
            deploy_type=model.deploy_type or "dmstandalone",
            dsn=model.dsn or "",
            owner_id=model.owner_id,
        )


class DataSourceDeleted(Event):
    """数据源已删除"""

    name: str
    datasource_id: UUID

    @classmethod
    def from_model(cls, model) -> "DataSourceDeleted":
        import uuid as _uuid

        ds_id = model.id if isinstance(model.id, _uuid.UUID) else _uuid.uuid4()
        return cls(name=model.name or "", datasource_id=ds_id)
