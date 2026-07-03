"""Provider相关异常模块

提供MCP Provider相关的异常类定义，包括加载、未找到、依赖错误等异常。
"""

from typing import List

from .base_error import DmMCPError


class MCPProviderError(DmMCPError):
    """MCP Provider系统基础异常

    所有Provider相关异常的基类，HTTP状态码为500。
    """

    def __init__(self, message: str, provider_name: str | None = None, **kwargs):
        """初始化Provider异常

        Args:
            message: 错误消息
            provider_name: Provider名称（可选）
            **kwargs: 其他参数传递给基类
        """
        error_code = kwargs.pop("error_code", "PROVIDER_ERROR")
        status_code = kwargs.pop("status_code", 500)
        super().__init__(
            message=message, error_code=error_code, status_code=status_code, **kwargs
        )
        if provider_name:
            self.details["provider_name"] = provider_name


class MCPProviderLoadError(MCPProviderError):
    """MCP Provider加载失败异常

    当Provider加载失败时抛出，继承自MCPProviderError。
    """

    def __init__(self, message: str, provider_name: str | None = None, **kwargs):
        """初始化Provider加载异常

        Args:
            message: 错误消息
            provider_name: Provider名称（可选）
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=message,
            provider_name=provider_name,
            error_code="PROVIDER_LOAD_ERROR",
            status_code=500,
            **kwargs,
        )


class MCPProviderNotFoundError(MCPProviderError):
    """MCP Provider未找到异常

    当指定的Provider不存在时抛出，继承自MCPProviderError，HTTP状态码为404。
    """

    def __init__(self, provider_name: str, **kwargs):
        """初始化Provider未找到异常

        Args:
            provider_name: Provider名称
            **kwargs: 其他参数传递给基类
        """
        super().__init__(
            message=f"Provider '{provider_name}' not found",
            provider_name=provider_name,
            error_code="PROVIDER_NOT_FOUND",
            status_code=404,
            **kwargs,
        )


class MCPProviderDependencyError(MCPProviderError):
    """MCP Provider依赖错误异常

    当Provider缺少必要的依赖时抛出，继承自MCPProviderError。
    """

    def __init__(self, provider_name: str, missing_dependencies: List[str], **kwargs):
        """初始化Provider依赖异常

        Args:
            provider_name: Provider名称
            missing_dependencies: 缺失的依赖列表
            **kwargs: 其他参数传递给基类
        """
        message = (
            f"Provider '{provider_name}' missing dependencies: "
            f"{', '.join(missing_dependencies)}"
        )
        super().__init__(
            message=message,
            provider_name=provider_name,
            error_code="PROVIDER_DEPENDENCY_ERROR",
            status_code=500,
            **kwargs,
        )
        self.details["missing_dependencies"] = missing_dependencies

        # 保持向后兼容，保留原有属性
        self.provider_name = provider_name
        self.missing_dependencies = missing_dependencies
