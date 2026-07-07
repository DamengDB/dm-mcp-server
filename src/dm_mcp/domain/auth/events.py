"""OAuth 相关业务事件"""

from dm_mcp.core.events import Event


class OAuthConfigChanged(Event):
    """OAuth 配置已变更

    当 admin 通过 API 修改 OAuth provider 配置或全局开关后触发，
    订阅者可据此刷新本地缓存或重新加载 provider。
    """

    pass
