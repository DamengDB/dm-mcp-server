"""Provider相关异常模块

提供MCP Provider相关的异常类定义，包括加载、未找到、依赖错误等异常。
"""

from dm_mcp.common import messages
from .base_error import DmMCPError


class MCPProviderError(DmMCPError):
    """MCP Provider系统基础异常

    所有Provider相关异常的基类，HTTP状态码为500。
    """

    def __init__(self, message: str, provider_name: str | None = None, **kwargs):
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
        super().__init__(
            message=messages.MSG_PROVIDER_NOT_FOUND.format(provider_name=provider_name),
            provider_name=provider_name,
            error_code="PROVIDER_NOT_FOUND",
            status_code=404,
            **kwargs,
        )


class CliGroupNotFoundError(MCPProviderError):
    """CLI 分组在库中不存在。"""

    def __init__(self, path: str, **kwargs):
        super().__init__(
            message=messages.MSG_CLI_GROUP_NOT_FOUND.format(path=path),
            error_code="CLI_GROUP_NOT_FOUND",
            status_code=404,
            **kwargs,
        )
        self.details["path"] = path


class CliGroupPathInUseError(MCPProviderError):
    """CLI 分组 path 仍被工具引用，禁止重命名或删除。"""

    def __init__(
        self,
        path: str,
        tool_names: list[str],
        **kwargs,
    ):
        names_preview = ", ".join(tool_names[:20])
        if len(tool_names) > 20:
            names_preview += ", ..."
        super().__init__(
            message=messages.MSG_CLI_GROUP_PATH_IN_USE.format(
                path=path, count=len(tool_names), names_preview=names_preview
            ),
            error_code="CLI_GROUP_PATH_IN_USE",
            status_code=409,
            **kwargs,
        )
        self.details["path"] = path
        self.details["tool_names"] = tool_names


class CliGroupMissingForToolsError(MCPProviderError):
    """已注册工具声明了 group，但数据库中缺少对应 path。"""

    def __init__(self, missing_paths: list[str], **kwargs):
        super().__init__(
            message=messages.MSG_CLI_GROUP_MISSING_FOR_TOOLS.format(
                missing_paths=", ".join(missing_paths)
            ),
            error_code="CLI_GROUP_MISSING_FOR_TOOLS",
            status_code=500,
            **kwargs,
        )
        self.details["missing_paths"] = missing_paths


class CliGroupConflictError(MCPProviderError):
    """目标 path 已存在等冲突。"""

    def __init__(self, path: str, **kwargs):
        super().__init__(
            message=messages.MSG_CLI_GROUP_CONFLICT.format(path=path),
            error_code="CLI_GROUP_CONFLICT",
            status_code=409,
            **kwargs,
        )
        self.details["path"] = path


class CommandTreeConflictError(MCPProviderError):
    """命令树拓扑冲突异常

    当构建 CLI 命令树发生拓扑冲突时抛出，如同一节点既是工具又是分组。
    """

    def __init__(self, node_path: str, conflict_type: str, **kwargs):
        super().__init__(
            message=messages.MSG_COMMAND_TREE_CONFLICT.format(
                node_path=node_path, conflict_type=conflict_type
            ),
            error_code="COMMAND_TREE_CONFLICT",
            status_code=400,
            **kwargs,
        )
        self.details["node_path"] = node_path
        self.details["conflict_type"] = conflict_type


class MCPExecutionError(MCPProviderError):
    """MCP 实体执行过程中因前置条件不满足而终止

    用于 Provider 内部主动抛出的"预期错误"（如审计未开启、SQL被拦截等），
    由 Formatter 统一捕获并包装为标准 envelope。
    """

    def __init__(self, error_code: str, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code=error_code,
            status_code=400,
            **kwargs,
        )


class ToolNotFoundError(MCPProviderError):
    """工具未找到异常"""

    def __init__(self, tool_name: str, **kwargs):
        super().__init__(
            message=messages.MSG_TOOL_NOT_FOUND_DEFAULT.format(tool_name=tool_name),
            error_code="TOOL_NOT_FOUND",
            status_code=404,
            **kwargs,
        )
        self.details["tool_name"] = tool_name


class ToolMetadataConflictError(MCPProviderError):
    """工具元数据冲突异常"""

    def __init__(self, tool_name: str, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code="TOOL_METADATA_CONFLICT",
            status_code=409,
            **kwargs,
        )
        self.details["tool_name"] = tool_name


class ResourceNotFoundError(MCPProviderError):
    """资源未找到异常"""

    def __init__(self, resource_uri: str, **kwargs):
        super().__init__(
            message=messages.MSG_RESOURCE_NOT_FOUND_DEFAULT.format(resource_uri=resource_uri),
            error_code="RESOURCE_NOT_FOUND",
            status_code=404,
            **kwargs,
        )
        self.details["resource_uri"] = resource_uri


class PromptNotFoundError(MCPProviderError):
    """提示词未找到异常"""

    def __init__(self, prompt_name: str, **kwargs):
        super().__init__(
            message=messages.MSG_PROMPT_NOT_FOUND_DEFAULT.format(prompt_name=prompt_name),
            error_code="PROMPT_NOT_FOUND",
            status_code=404,
            **kwargs,
        )
        self.details["prompt_name"] = prompt_name
