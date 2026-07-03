"""MCP中间件模块

提供MCP中间件的抽象基类和中间件栈实现，用于实现横切关注点（认证、审计、监控等）。
"""

import functools
from abc import ABC
from typing import Any, Awaitable, Callable, List, Optional

# 假设这些是第三方库的引用
from mcp import Resource, Tool, types
from pydantic import AnyUrl

# 定义通用的 Next 类型，表示链条中的下一个函数
# 它是一个异步函数，返回特定类型 T
NextCallable = Callable[..., Awaitable[Any]]


class BaseMCPMiddleware(ABC):
    """MCP中间件基类

    所有MCP中间件的抽象基类。每个方法的签名都增加了`call_next`参数，
    指向下一个中间件或最终实现，形成调用链。
    """

    def __init__(self):
        """初始化中间件"""
        pass

    async def on_message(self, call_next: NextCallable, message: Any):
        """处理消息的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数
            message: 消息内容
        """
        await call_next(message)

    async def on_list_tools(self, call_next: NextCallable) -> List[Tool]:
        """列出工具的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数

        Returns:
            List[Tool]: 工具列表
        """
        return await call_next()

    async def on_call_tool(
        self, call_next: NextCallable, name: str, arguments: dict
    ) -> str:
        """调用工具的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数
            name: 工具名称
            arguments: 工具参数

        Returns:
            str: 工具执行结果
        """
        return await call_next(name, arguments)

    async def on_list_prompts(self, call_next: NextCallable) -> List[types.Prompt]:
        """列出提示词的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数

        Returns:
            List[types.Prompt]: 提示词列表
        """
        return await call_next()

    async def on_get_prompt(
        self, call_next: NextCallable, name: str, arguments: Optional[dict] = None
    ) -> types.GetPromptResult:
        """获取提示词的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数
            name: 提示词名称
            arguments: 提示词参数（可选）

        Returns:
            types.GetPromptResult: 提示词结果
        """
        return await call_next(name, arguments)

    async def on_list_resources(self, call_next: NextCallable) -> List[Resource]:
        """列出资源的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数

        Returns:
            List[Resource]: 资源列表
        """
        return await call_next()

    async def on_list_resource_templates(
        self, call_next: NextCallable
    ) -> List[types.ResourceTemplate]:
        """列出资源模板的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数

        Returns:
            List[types.ResourceTemplate]: 资源模板列表
        """
        return await call_next()

    async def on_read_resource(self, call_next: NextCallable, uri: AnyUrl) -> str:
        """读取资源的中间件方法

        Args:
            call_next: 下一个中间件或最终处理函数
            uri: 资源URI

        Returns:
            str: 资源内容
        """
        return await call_next(uri)


class MCPMiddlewareStack:
    """MCP中间件栈

    管理中间件的有序列表，并提供执行中间件调用链的功能。
    """

    def __init__(self, middlewares: List[BaseMCPMiddleware] = []):
        """初始化中间件栈

        Args:
            middlewares: 初始中间件列表（可选）
        """
        # Stack 只持有中间件列表，不持有 Target
        self.middlewares = middlewares or []

    def is_empty(self):
        """检查中间件栈是否为空

        Returns:
            bool: 如果栈为空则返回True
        """
        return len(self.middlewares) == 0

    def add_middleware(self, middleware: BaseMCPMiddleware):
        """添加单个中间件到栈中

        Args:
            middleware: 要添加的中间件实例
        """
        self.middlewares.append(middleware)

    def add_middlewares(self, middlewares: List[BaseMCPMiddleware]):
        """批量添加中间件到栈中

        Args:
            middlewares: 要添加的中间件列表
        """
        self.middlewares.extend(middlewares)

    def __len__(self):
        """返回中间件栈的长度

        Returns:
            int: 中间件数量
        """
        return len(self.middlewares)

    async def _run(
        self, method_name: str, handler: Callable[..., Awaitable[Any]], *args, **kwargs
    ):
        """动态构建并执行调用链

        从后往前依次用中间件包裹handler，形成调用链。当调用链执行时，
        每个中间件可以在调用前后执行额外逻辑。

        Args:
            method_name: 中间件上要调用的方法名（如'on_call_tool'）
            handler: 最终要执行的目标函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            Any: 调用链的执行结果
        """
        # 1. 链条的终点是传入的 handler
        chain = handler

        # 2. 从后往前，用中间件包裹 chain
        # 这里的逻辑是：
        # new_chain = partial(middleware.method, old_chain)
        # 这样 middleware.method 被调用时，第一个参数(call_next) 自动变成 old_chain
        for mw in reversed(self.middlewares):
            mw_method = getattr(mw, method_name)
            chain = functools.partial(mw_method, chain)

        # 3. 执行组装好的链条
        # 此时 chain 是最外层中间件的 partial 对象
        return await chain(*args, **kwargs)

    # --- 对外暴露的 API ---
    # 每个方法都接收一个 `handler` 参数

    async def on_message(self, handler: Callable[[Any], Awaitable[None]], message: Any):
        """执行消息处理的中间件调用链

        Args:
            handler: 最终处理函数
            message: 消息内容
        """
        return await self._run("on_message", handler, message=message)

    async def on_list_tools(
        self, handler: Callable[[], Awaitable[List[Tool]]]
    ) -> List[Tool]:
        """执行列出工具的中间件调用链

        Args:
            handler: 最终处理函数

        Returns:
            List[Tool]: 工具列表
        """
        return await self._run("on_list_tools", handler)

    async def on_call_tool(
        self, handler: Callable[[str, dict], Awaitable[Any]], name: str, arguments: dict
    ) -> str:
        """执行调用工具的中间件调用链

        Args:
            handler: 最终处理函数
            name: 工具名称
            arguments: 工具参数

        Returns:
            str: 工具执行结果
        """
        return await self._run("on_call_tool", handler, name=name, arguments=arguments)

    async def on_list_prompts(
        self, handler: Callable[[], Awaitable[List[types.Prompt]]]
    ) -> List[types.Prompt]:
        """执行列出提示词的中间件调用链

        Args:
            handler: 最终处理函数

        Returns:
            List[types.Prompt]: 提示词列表
        """
        return await self._run("on_list_prompts", handler)

    async def on_get_prompt(
        self,
        handler: Callable[[str, Optional[dict]], Awaitable[Any]],
        name: str,
        arguments: Optional[dict] = None,
    ) -> types.GetPromptResult:
        """执行获取提示词的中间件调用链

        Args:
            handler: 最终处理函数
            name: 提示词名称
            arguments: 提示词参数（可选）

        Returns:
            types.GetPromptResult: 提示词结果
        """
        return await self._run("on_get_prompt", handler, name=name, arguments=arguments)

    async def on_list_resources(
        self, handler: Callable[[], Awaitable[list[Resource]]]
    ) -> list[Resource]:
        """执行列出资源的中间件调用链

        Args:
            handler: 最终处理函数

        Returns:
            list[Resource]: 资源列表
        """
        return await self._run("on_list_resources", handler)

    async def on_list_resource_templates(
        self, handler: Callable[[], Awaitable[list[types.ResourceTemplate]]]
    ) -> list[types.ResourceTemplate]:
        """执行列出资源模板的中间件调用链

        Args:
            handler: 最终处理函数

        Returns:
            list[types.ResourceTemplate]: 资源模板列表
        """
        return await self._run("on_list_resource_templates", handler)

    async def on_read_resource(
        self, handler: Callable[[AnyUrl], Awaitable[str]], uri: AnyUrl
    ) -> str:
        """执行读取资源的中间件调用链

        Args:
            handler: 最终处理函数
            uri: 资源URI

        Returns:
            str: 资源内容
        """
        return await self._run("on_read_resource", handler, uri=uri)
