"""Token 相关业务事件"""

from typing import Literal

from dm_mcp.core.events import Event


class TokenRevoked(Event):
    """Token 已被吊销

    主动删除或过期清理时发布，订阅者应清理与该 token 关联的派生数据
    （例如内存策略缓存等）。

    Attributes:
        token: 被吊销的 token 字符串（完整值，订阅者用作 WHERE 条件）
        reason: 吊销原因 — "deleted"=主动删除，"expired"=过期清理
        user_id: token 所属用户 ID，主动删除时已知，过期清理时也可拿到
    """

    token: str
    reason: Literal["deleted", "expired"]
    user_id: str
