"""计时工具模块

提供高精度计时器，支持直接访问和上下文管理器两种用法。
"""

import time
from typing import Self


class Timer:
    """高精度计时器，基于 time.perf_counter()。

    支持两种用法：

    1. 直接用法（适合异步函数中分散的计时点）：

        timer = Timer()
        result = await some_async_action()
        elapsed_ms = timer.elapsed_ms

    2. with 用法（适合需要明确标记计时段边界的场景）：

        timer = Timer()
        try:
            with timer:
                result = await some_async_action()
            elapsed_ms = timer.elapsed_ms   # with 正常结束
            ...
        except SomeError:
            elapsed_ms = timer.elapsed_ms   # with 内抛异常，__exit__ 已记录结束时间
            ...
    """

    __slots__ = ("_start", "_end")

    def __init__(self) -> None:
        self._start: float = time.perf_counter()
        self._end: float | None = None

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        self._end = None
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._end = time.perf_counter()
        # 不 suppress 异常，让异常继续向外传播

    @property
    def elapsed_ms(self) -> int:
        """返回已流逝的毫秒数。

        如果计时器通过 with 使用且 __exit__ 已调用，返回固定的耗时。
        否则返回当前实时耗时。
        """
        end = self._end if self._end is not None else time.perf_counter()
        return int((end - self._start) * 1000)
