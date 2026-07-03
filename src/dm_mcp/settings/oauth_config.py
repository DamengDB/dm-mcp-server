from typing import List, Optional

from pydantic import BaseModel, SecretStr, model_validator


class OAuthConfig(BaseModel):
    """
    OAuth 2.0/OIDC Configuration

    Validated using Pydantic. Logic for default scopes/endpoints
    has been moved to OAuthService.
    """

    # Switch & Provider
    enabled: bool = False

    # 核心凭证
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")

    microsoft_client_id: str = ""
    microsoft_client_secret: SecretStr = SecretStr("")

    github_client_id: str = ""
    github_client_secret: SecretStr = SecretStr("")

    custom_provider: str = "custom"
    custom_client_id: str = ""
    custom_client_secret: SecretStr = SecretStr("")
    custom_scopes: List[str] = ["openid", "email", "profile"]

    # 自动发现端点
    custom_discovery_url: Optional[str] = None

    # 手动配置端点（当 custom_discovery_url 未设置时，启用功能必填）
    custom_authorization_endpoint: Optional[str] = None
    custom_token_endpoint: Optional[str] = None
    custom_userinfo_endpoint: Optional[str] = None
    custom_jwks_uri: Optional[str] = None

    @model_validator(mode="after")
    def check_url_configuration_group(self):
        # 1. 提取这 5 个相关参数的值
        discovery = self.custom_discovery_url
        auth = self.custom_authorization_endpoint
        token = self.custom_token_endpoint
        # userinfo 和 jwks 是可选的辅助参数，但它们属于这个组
        userinfo = self.custom_userinfo_endpoint
        jwks = self.custom_jwks_uri

        # 2. 判断是否有“任意一个”被设置了
        # 只要组里有一个不是空字符串，就视为用户想要配置这部分功能
        is_any_set = any([discovery, auth, token, userinfo, jwks])

        # 【场景一：要么都不设置】
        if not is_any_set:
            return self  # 全空，合法，直接通过

        # 【场景二：设置了其一，就要检查完整性】
        # 逻辑：如果没提供 discovery，就强制要求 auth 和 token 必须存在

        if not discovery:
            # 进入这里说明：Discovery 为空，但其他 4 个参数里至少有一个有值
            # 此时必须校验手动模式的核心参数
            if not auth or not token:
                raise ValueError(
                    "OAuth配置不完整：检测到你设置了部分 custom URL 参数。"
                    "如果未提供 custom_discovery_url，则必须提供 "
                    "custom_authorization_endpoint 和 custom_token_endpoint。"
                )

        return self
