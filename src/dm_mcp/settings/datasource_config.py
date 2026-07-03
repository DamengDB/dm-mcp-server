import uuid
from typing import List, Literal

from pydantic import BaseModel, Field, SecretStr


class DataSourceConfig(BaseModel):
    """
    单个数据源配置

    支持三种数据源类型：
    1. DM单实例：deploy_type="dmstandonle"
    2. DM主备：deploy_type="dmwatcher"
    3. DSC集群：deploy_type="dmdsc"，包含多个节点的连接信息

    说明：
    - id：UUID，唯一标识符，即使删除重建同名数据源也不会复用
    - read_only：是否只读数据源（True=只读库，False=读写库）
    - weight：仅在 weighted_round_robin 时生效
    - name：唯一标识符，必须唯一且不可修改（通过数据源名称进行识别和授权）
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="数据源 UUID")
    name: str = "primary"
    enabled: bool = True

    # 部署类型：达梦数据库部署模式
    deploy_type: Literal["dmstandonle", "dmwatcher", "dmdsc", "dmdpc"] = "dmstandonle"
    read_only: bool = False

    # 单实例连接参数
    dsn: str = ""  #  "127.0.0.1:5236"
    host: str = "localhost"
    port: int = 5236
    user: str = "SYSDBA"
    password: SecretStr = Field(default=SecretStr("SYSDBA"), validate_default=False)

    # pool 参数（每个数据源的连接池参数）
    minsize: int = 1
    maxsize: int = 10
    timeout: float = 30.0

    # 负载均衡参数
    weight: int = 1  # weighted_round_robin 时使用


class DataSourcesConfig(BaseModel):
    """数据源集合配置（用于启动时提供初始数据源列表/从环境变量注入）"""

    data_sources: List[DataSourceConfig] = Field(default_factory=list)
