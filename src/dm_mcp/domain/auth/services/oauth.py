"""OAuth 认证服务模块

提供服务功能：
- OAuth/OIDC 第三方认证支持
- 支持 Google、Microsoft、GitHub 等常见提供商
- 自定义 OAuth 提供商配置
- OAuth 流程管理和 JWT Token 生成
- 无状态 OAuth 实现（使用加密 Cookie 存储 state）
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

from authlib.integrations.starlette_client import OAuth
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.datastructures import URL
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from dm_mcp.common import messages
from dm_mcp.core.auth.auth_context import AuthContext
from dm_mcp.core.exceptions import OAuthError
from dm_mcp.core.service import ServiceFactory, ServiceMetadata
from dm_mcp.domain.auth.events import OAuthConfigChanged

from dm_mcp.core.service import BaseService
from .auth_config import AuthConfigService
from .jwt import JwtService

logger = logging.getLogger(__name__)

# OAuth 常量
OAUTH_STATE_COOKIE_PREFIX = "oauth_state_"
OAUTH_STATE_COOKIE_MAX_AGE = 600  # 10 分钟过期

# OAuth 提供商默认端点配置
OAUTH_PROVIDER_ENDPOINTS = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_endpoint": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://openidconnect.googleapis.com/v1/userinfo",
        "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
        "default_scope": ["openid", "email", "profile"],
    },
    "microsoft": {
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "discovery_url": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
        "default_scope": ["openid", "profile", "email", "User.Read"],
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_endpoint": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "api_base_url": "https://api.github.com/",
        "default_scope": ["openid", "email", "profile"],
    },
}


class OAuthService(BaseService):
    """OAuth 认证服务

    管理 OAuth/OIDC 第三方认证流程。

    主要功能：
    - OAuth/OIDC 第三方认证支持
    - 支持 Google、Microsoft、GitHub 等常见提供商
    - 自定义 OAuth 提供商配置
    - OAuth 流程管理（登录、回调）
    - JWT Token 生成和认证
    """

    def __init__(self, jwt_service: JwtService, auth_config_service: AuthConfigService):
        self.jwt_service = jwt_service
        self._auth_config_service = auth_config_service
        self.providers = {}  # Authlib 客户端对象
        self.provider_configs = {}  # 存储每个提供商的配置信息

        # 用于加密/解密 OAuth state 的序列化器（无状态模式）
        # 使用 app_secret 作为签名密钥，确保安全
        self.state_serializer = URLSafeTimedSerializer(
            jwt_service.app_secret,
            salt="oauth-state",  # 用于区分不同用途的加密数据
        )

    async def startup(self) -> None:
        """服务启动：加载并注册 OAuth 提供商"""
        await self._auth_config_service.ensure_slots_seeded()
        await self._load_and_register_providers()
        logger.info("OAuth 服务已启动")

    async def _load_and_register_providers(self) -> None:
        """从 AuthConfigService 加载并注册所有启用的提供商"""
        self.providers.clear()
        self.provider_configs.clear()

        global_config = await self._auth_config_service.get_oauth_global_config()
        if not global_config.enabled:
            return

        providers_data = await self._auth_config_service.list_providers(include_secrets=True)
        for provider_data in providers_data:
            if not provider_data.get("enabled"):
                continue

            slot = provider_data["slot"]
            name = provider_data["name"]
            client_id = provider_data.get("client_id", "")
            client_secret = provider_data.get("client_secret", "")
            scopes = provider_data.get("scopes", [])

            if not client_id or not client_secret:
                continue

            if provider_data.get("is_builtin"):
                config = self._build_builtin_provider_config(
                    slot, name, client_id, client_secret, scopes
                )
            else:
                config = self._build_custom_provider_config_from_data(
                    name, client_id, client_secret, scopes, provider_data
                )

            if config:
                self.providers[name] = OAuth().register(**config)
                self.provider_configs[name] = self._extract_provider_config_info(name, config)

    def _build_builtin_provider_config(
        self,
        provider_name: str,
        name: str,
        client_id: str,
        client_secret: str,
        scope: list[str],
    ) -> dict[str, Any] | None:
        """构建内置 OAuth 提供商的配置字典（用于 authlib 注册）"""
        if not client_id or not client_secret:
            return None

        endpoints = OAUTH_PROVIDER_ENDPOINTS.get(provider_name, {})
        config = {
            "name": name,
            "client_id": client_id,
            "client_secret": client_secret,
            "client_kwargs": {"scope": scope or endpoints.get("default_scope", [])},
        }

        # 如果有 discovery URL（OIDC），使用它
        if "discovery_url" in endpoints:
            config["server_metadata_url"] = endpoints["discovery_url"]
        else:
            # 手动配置端点（映射端点键名到 authlib 配置键名）
            endpoint_mapping = {
                "authorize_url": "authorize_url",
                "token_endpoint": "access_token_url",
                "userinfo_url": "userinfo_endpoint",
                "api_base_url": "api_base_url",
            }
            config.update(
                {
                    authlib_key: endpoints[endpoint_key]
                    for endpoint_key, authlib_key in endpoint_mapping.items()
                    if endpoint_key in endpoints
                }
            )

        return config

    def _build_custom_provider_config_from_data(
        self,
        name: str,
        client_id: str,
        client_secret: str,
        scope: list[str],
        provider_data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """构建自定义 OAuth 提供商的配置"""
        if not client_id or not client_secret:
            return None

        base_config = {
            "name": name,
            "client_id": client_id,
            "client_secret": client_secret,
            "client_kwargs": {"scope": scope or ["openid", "email", "profile"]},
        }

        discovery_url = provider_data.get("discovery_url")
        if discovery_url:
            base_config["server_metadata_url"] = discovery_url
            return base_config

        auth_endpoint = provider_data.get("authorization_endpoint")
        token_endpoint = provider_data.get("token_endpoint")

        if auth_endpoint and token_endpoint:
            base_config["authorize_url"] = auth_endpoint
            base_config["access_token_url"] = token_endpoint

            if provider_data.get("userinfo_endpoint"):
                base_config["userinfo_url"] = provider_data["userinfo_endpoint"]
            if provider_data.get("jwks_uri"):
                base_config["jwks_uri"] = provider_data["jwks_uri"]

            return base_config

        return None

    def _extract_provider_config_info(
        self, provider_name: str, provider_kwargs: dict[str, Any]
    ) -> dict[str, Any]:
        """从 provider_kwargs 中提取并存储配置信息"""
        config_info = {
            "client_id": provider_kwargs.get("client_id"),
            "client_secret": provider_kwargs.get("client_secret"),
            "scope": provider_kwargs.get("client_kwargs", {}).get("scope", []),
        }

        default_endpoints = OAUTH_PROVIDER_ENDPOINTS.get(provider_name, {})

        # 处理端点 URL（优先使用手动配置，否则使用默认值）
        if "server_metadata_url" in provider_kwargs:
            config_info["discovery_url"] = provider_kwargs["server_metadata_url"]
            config_info["authorize_url"] = default_endpoints.get("authorize_url")
            config_info["token_endpoint"] = default_endpoints.get("token_endpoint")
            config_info["userinfo_url"] = default_endpoints.get("userinfo_url")
        else:
            config_info["authorize_url"] = provider_kwargs.get(
                "authorize_url"
            ) or default_endpoints.get("authorize_url")
            config_info["token_endpoint"] = (
                provider_kwargs.get("access_token_url")
                or provider_kwargs.get("token_endpoint")
                or default_endpoints.get("token_endpoint")
            )
            config_info["userinfo_url"] = (
                provider_kwargs.get("userinfo_endpoint")
                or provider_kwargs.get("userinfo_url")
                or default_endpoints.get("userinfo_url")
            )

        return config_info

    async def reload_providers(self) -> None:
        """重新加载并注册 OAuth 提供商（热更新）"""
        self.providers.clear()
        self.provider_configs.clear()
        await self._load_and_register_providers()
        logger.info("OAuth 提供商已重新加载")

    def get_providers(self) -> list[str]:
        """获取已注册的 OAuth 提供商列表"""
        return list(self.providers.keys())

    def _get_state_cookie_name(self, provider_name: str) -> str:
        """获取 state cookie 名称"""
        return f"{OAUTH_STATE_COOKIE_PREFIX}{provider_name}"

    async def handle_login(
        self, provider_name: str, request: Request, callback_uri: str | URL
    ) -> RedirectResponse:
        """处理 OAuth 登录请求（无状态模式）

        前端点击登录后调用此方法，将重定向到 OAuth 提供商的登录页面。
        使用加密的 Cookie 存储 state，而不是 Session，实现无状态架构。

        Args:
            provider_name: OAuth 提供商名称
            request: Starlette 请求对象
            callback_uri: 回调 URI

        Returns:
            RedirectResponse 重定向到 OAuth 提供商

        Raises:
            OAuthError: OAuth 未启用或提供商未注册
        """
        global_config = await self._auth_config_service.get_oauth_global_config()
        if not global_config.enabled:
            raise OAuthError(messages.MSG_OAUTH_DISABLED, provider=provider_name)

        client = self.providers.get(provider_name)
        if not client:
            raise OAuthError(
                messages.MSG_OAUTH_PROVIDER_NOT_REGISTERED.format(provider_name=provider_name), provider=provider_name
            )

        # 生成随机 state 值
        state = secrets.token_urlsafe(32)

        # 将 state 加密后存储在 Cookie 中（无状态模式）
        encrypted_state = self.state_serializer.dumps(state)

        # 手动构建授权 URL（避免 authlib 使用 session）
        # authlib 的 authorize_redirect 会尝试访问 request.session，但我们使用无状态架构
        redirect_uri = str(callback_uri)

        # 获取提供商配置
        provider_config = self.provider_configs.get(provider_name)
        if not provider_config:
            raise OAuthError(
                messages.MSG_OAUTH_PROVIDER_CONFIG_NOT_FOUND.format(provider_name=provider_name),
                provider=provider_name,
            )

        # 获取授权端点 URL
        authorize_url = provider_config.get("authorize_url")

        if not authorize_url:
            raise OAuthError(
                messages.MSG_OAUTH_AUTH_ENDPOINT_NOT_CONFIGURED, provider=provider_name
            )

        # 构建授权 URL 参数
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

        # 获取 client 的配置参数
        client_id = provider_config["client_id"]
        scope = provider_config.get("scope", [])
        if isinstance(scope, list):
            scope = " ".join(scope)

        # 构建查询参数
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "state": state,
        }

        if scope:
            params["scope"] = scope

        # 处理已有的查询参数（如果有）
        parsed_url = urlparse(authorize_url)
        existing_params = parse_qs(parsed_url.query)
        # 合并参数（新参数优先）
        for key, value in params.items():
            existing_params[key] = [str(value)]

        # 重新构建 URL
        new_query = urlencode(existing_params, doseq=True)
        auth_url = urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                new_query,
                parsed_url.fragment,
            )
        )

        # 创建重定向响应
        response = RedirectResponse(url=auth_url, status_code=302)

        # 在响应上设置加密的 state Cookie
        response.set_cookie(
            key=self._get_state_cookie_name(provider_name),
            value=encrypted_state,
            max_age=OAUTH_STATE_COOKIE_MAX_AGE,
            httponly=True,
            secure=False,  # 开发环境，生产环境应设为 True
            samesite="lax",
        )

        return response

    def _verify_oauth_state(self, request: Request, provider_name: str) -> str:
        """验证 OAuth state（无状态模式）

        Args:
            request: Starlette 请求对象
            provider_name: OAuth 提供商名称

        Returns:
            str: 验证通过后的 state 值

        Raises:
            OAuthError: state 验证失败
        """
        # 从 Cookie 中读取加密的 state
        cookie_name = self._get_state_cookie_name(provider_name)
        encrypted_state = request.cookies.get(cookie_name)
        if not encrypted_state:
            raise OAuthError(
                messages.MSG_OAUTH_STATE_COOKIE_MISSING,
                provider=provider_name,
            )

        # 解密 state
        try:
            expected_state = self.state_serializer.loads(
                encrypted_state, max_age=OAUTH_STATE_COOKIE_MAX_AGE
            )
        except SignatureExpired:
            raise OAuthError(
                messages.MSG_OAUTH_STATE_EXPIRED,
                provider=provider_name,
            )
        except BadSignature:
            raise OAuthError(
                messages.MSG_OAUTH_STATE_SIGNATURE_INVALID,
                provider=provider_name,
            )
        except Exception as e:
            logger.warning(f"Failed to decrypt OAuth state: {e}", exc_info=True)
            raise OAuthError(
                messages.MSG_OAUTH_STATE_INVALID_OR_EXPIRED.format(error=str(e)), provider=provider_name
            ) from e

        # 从 URL 参数中获取回调的 state
        callback_state = request.query_params.get("state")
        if not callback_state:
            raise OAuthError(
                messages.MSG_OAUTH_STATE_PARAM_MISSING, provider=provider_name
            )

        # 验证 state 是否匹配（防止 CSRF 攻击）
        if callback_state != expected_state:
            logger.warning(
                f"OAuth state mismatch for provider {provider_name}. "
                f"Expected: {expected_state[:8]}..., Got: {callback_state[:8]}..."
            )
            raise OAuthError(
                messages.MSG_OAUTH_STATE_MISMATCH, provider=provider_name
            )

        return expected_state

    def _get_token_endpoint(self, provider_name: str) -> str:
        """获取 OAuth token 端点 URL

        Args:
            provider_name: OAuth 提供商名称

        Returns:
            str: token 端点 URL

        Raises:
            OAuthError: token 端点未配置
        """
        provider_config = self.provider_configs.get(provider_name)
        if not provider_config:
            raise OAuthError(
                messages.MSG_OAUTH_PROVIDER_CONFIG_NOT_FOUND.format(provider_name=provider_name), provider=None
            )

        token_endpoint = provider_config.get("token_endpoint")

        if not token_endpoint:
            raise OAuthError(messages.MSG_OAUTH_TOKEN_ENDPOINT_NOT_CONFIGURED, provider=provider_name)

        return token_endpoint

    async def _extract_user_info(
        self, token_response: dict[str, Any], provider_name: str
    ) -> dict[str, Any]:
        """从 token 响应中提取用户信息

        Args:
            token_response: OAuth token 响应字典
            provider_name: OAuth 提供商名称

        Returns:
            dict[str, Any]: 用户信息字典

        Raises:
            OAuthError: 无法获取用户信息
        """

        def _sanitize_user_info(info: dict[str, Any]) -> dict[str, Any]:
            """过滤掉敏感字段，只保留必要的用户信息"""
            allowed_fields = [
                "sub", "email", "name", "given_name", "family_name",
                "preferred_username", "picture", "locale", "zoneinfo",
            ]
            return {k: v for k, v in info.items() if k in allowed_fields}

        # 1. 优先从 userinfo 字段获取（某些 OIDC 提供商）
        user_info = token_response.get("userinfo")
        if user_info:
            return _sanitize_user_info(user_info)

        # 2. 尝试从 id_token 解析（OIDC 标准）
        id_token = token_response.get("id_token")
        if id_token:
            try:
                # 使用 JWT service 解析 id_token payload（不验证签名）
                # OAuth 提供商的 id_token 是用提供商的密钥签名的
                user_info = self.jwt_service.parse_jwt_payload(
                    id_token, verify_signature=False
                )
                if user_info:
                    return _sanitize_user_info(user_info)
            except Exception as e:
                logger.debug(
                    f"Failed to parse id_token for {provider_name}: {e}",
                    exc_info=True,
                )

        # 3. 调用 userinfo 端点获取用户信息
        provider_config = self.provider_configs.get(provider_name, {})
        userinfo_url = provider_config.get("userinfo_url")

        if userinfo_url:
            try:
                access_token = token_response.get("access_token")
                if access_token:
                    # 使用 httpx 调用 userinfo 端点
                    import httpx

                    async with httpx.AsyncClient() as http_client:
                        resp = await http_client.get(
                            userinfo_url,
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        resp.raise_for_status()
                        user_info = resp.json()
                        if user_info:
                            return _sanitize_user_info(user_info)
            except Exception as e:
                logger.warning(
                    f"Failed to fetch userinfo from {userinfo_url} for {provider_name}: {e}",
                    exc_info=True,
                )

        # 所有方法都失败
        raise OAuthError(
            messages.MSG_OAUTH_USER_INFO_FAILED,
            provider=provider_name,
        )

    async def handle_callback(
        self, request: Request, provider_name: str, redirect_uri: str | None
    ) -> RedirectResponse | JSONResponse:
        """处理 OAuth 回调（无状态模式）

        OAuth 提供商认证成功后，会重定向回此方法。
        从加密的 Cookie 中读取 state 并验证，不使用 Session。

        Args:
            request: Starlette 请求对象
            provider_name: OAuth 提供商名称
            redirect_uri: 重定向 URI（可选）

        Returns:
            RedirectResponse 或 JSONResponse，包含 JWT Token

        Raises:
            OAuthError: OAuth 未启用、提供商未注册或回调失败
        """
        global_config = await self._auth_config_service.get_oauth_global_config()
        if not global_config.enabled:
            raise OAuthError(messages.MSG_OAUTH_DISABLED, provider=provider_name)

        client = self.providers.get(provider_name)
        if not client:
            raise OAuthError(
                messages.MSG_OAUTH_PROVIDER_NOT_REGISTERED.format(provider_name=provider_name), provider=provider_name
            )

        try:
            # 1. 验证 OAuth state（防止 CSRF 攻击）
            self._verify_oauth_state(request, provider_name)

            # 2. 获取授权码
            code = request.query_params.get("code")
            if not code:
                raise OAuthError(messages.MSG_OAUTH_AUTH_CODE_MISSING, provider=provider_name)

            # 3. 获取 token 端点并交换 token
            redirect_uri_str = str(request.url).split("?")[0]  # 移除查询参数
            token_endpoint = self._get_token_endpoint(provider_name)
            provider_config = self.provider_configs[provider_name]

            try:
                # 使用 httpx 手动交换 token（避免 authlib 的 session 依赖）
                import httpx

                token_data = {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri_str,
                    "client_id": provider_config["client_id"],
                    "client_secret": provider_config["client_secret"],
                }

                async with httpx.AsyncClient() as http_client:
                    response = await http_client.post(
                        token_endpoint,
                        data=token_data,
                        headers={"Accept": "application/json"},
                    )
                    response.raise_for_status()
                    token_response = response.json()

            except Exception as e:
                logger.error(
                    f"Failed to exchange authorization code for {provider_name}: {e}",
                    exc_info=True,
                )
                raise OAuthError(
                    messages.MSG_OAUTH_AUTH_CODE_EXCHANGE_FAILED.format(error=str(e)),
                    provider=provider_name,
                ) from e

            # 4. 提取用户信息
            user_info = await self._extract_user_info(token_response, provider_name)

            # 5. 生成 JWT token
            jwt_token = self.jwt_service.create_token(user_info)

            # 6. 创建响应并清理 state Cookie
            if redirect_uri:
                response = RedirectResponse(url=redirect_uri, status_code=307)
                response.set_cookie(
                    key="jwt_token",
                    value=jwt_token,
                    max_age=self.jwt_service.token_expire_seconds,
                    httponly=False,
                    secure=False,  # 开发环境，生产环境应设为 True
                    samesite="lax",
                )
            else:
                response = JSONResponse({"jwt": jwt_token})

            # 删除 state Cookie（安全措施）
            response.delete_cookie(
                key=self._get_state_cookie_name(provider_name),
                httponly=True,
                samesite="lax",
            )

            return response

        except OAuthError:
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error in OAuth callback for {provider_name}: {e}",
                exc_info=True,
            )
            raise OAuthError(
                messages.MSG_OAUTH_CALLBACK_FAILED.format(error=str(e)), provider=provider_name
            ) from e

    def authenticate_token(self, token: str) -> AuthContext:
        """验证 JWT Token 并创建 AuthContext

        Args:
            token: JWT Token 字符串

        Returns:
            AuthContext 认证上下文对象

        Raises:
            InvalidTokenError: Token 无效
            TokenExpiredError: Token 已过期
        """
        claims = self.jwt_service.decode_token(token)
        return self._create_auth_context(claims)

    def _create_auth_context(self, user_info: dict[str, Any]) -> AuthContext:
        """创建认证上下文

        Args:
            user_info: 用户信息字典（来自 OAuth 提供商）

        Returns:
            AuthContext 认证上下文对象
        """
        return AuthContext(
            user_id=user_info["sub"],
            login_time=datetime.now(timezone.utc),
            last_activity=datetime.now(timezone.utc),
            token=None,
            auth_type=user_info.get("auth_type", "oauth"),
            allowed_datasources=user_info.get("allowed_datasources", []),
        )


class OAuthServiceFactory(ServiceFactory):
    """OAuth 认证服务工厂

    负责创建和配置 OAuthService 实例。
    """

    def metadata(self) -> ServiceMetadata:
        return ServiceMetadata(
            name="oauth_service",
            service_type=OAuthService,
            description="OAuth 认证服务",
            author="DM MCP Team",
            dependencies=["jwt_service", "auth_config_service"],
            priority=30,
        )

    def create(self, settings, **deps) -> OAuthService:
        # 传递 session_secret 用于加密 OAuth state（无状态模式）
        return OAuthService(deps["jwt_service"], deps["auth_config_service"])
