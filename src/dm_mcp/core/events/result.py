"""发布结果模型"""

from pydantic import BaseModel


class FailedHandler(BaseModel):
    """单个失败的 handler 信息"""

    owner: str | None
    handler_name: str
    error_type: str
    error_message: str


class PublishResult(BaseModel):
    """publish 调用的聚合结果

    Attributes:
        event_type: 事件类型名称
        succeeded: 成功执行的 handler owner 列表
        failed: 失败的 handler 信息列表
    """

    event_type: str
    succeeded: list[str] = []
    failed: list[FailedHandler] = []

    @property
    def has_failures(self) -> bool:
        return bool(self.failed)
