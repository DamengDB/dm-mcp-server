"""统一缓存服务模块

提供服务功能：
- 自动 JSON 序列化/反序列化
- 统一 Key 前缀管理（Namespacing）
- 支持 Pydantic 模型直接存储
- 异常安全（缓存失败不应阻塞主流程）
"""

import json
import logging
from typing import Any, Optional, Type, TypeVar, Union

from pydantic import BaseModel

from dm_mcp.core.cache import BaseCacheBackend

from .base_service import BaseService

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class CacheService(BaseService):
    """统一缓存服务

    提供统一的缓存接口，支持多种数据类型的存储和检索。

    主要功能：
    - 自动 JSON 序列化/反序列化
    - 统一 Key 前缀管理（Namespacing）
    - 支持 Pydantic 模型直接存储和获取
    - 异常安全：缓存失败不会阻塞主流程
    """

    def __init__(self, backend: BaseCacheBackend, prefix: str = "mcp:"):
        """初始化缓存服务

        Args:
            backend: 缓存后端实现
            prefix: Key 前缀，默认为 "mcp:"
        """
        self.backend = backend
        self.prefix = prefix

    def _make_key(self, key: str) -> str:
        """为 Key 自动添加前缀

        Args:
            key: 原始 Key

        Returns:
            带前缀的完整 Key
        """
        if key.startswith(self.prefix):
            return key
        return f"{self.prefix}{key}"

    def set(
        self, key: str, value: Union[str, dict, list, BaseModel], ttl: int = 3600
    ) -> bool:
        """存储数据到缓存

        Args:
            key: 缓存键
            value: 缓存值，支持 str、dict、list 或 Pydantic Model
            ttl: 过期时间（秒），默认 3600 秒

        Returns:
            True 存储成功，False 存储失败
        """
        full_key = self._make_key(key)
        try:
            # 1. 序列化处理
            if isinstance(value, BaseModel):
                # Pydantic 转 JSON 字符串
                payload = value.model_dump_json()
            elif isinstance(value, (dict, list)):
                # 字典/列表 转 JSON 字符串
                payload = json.dumps(value, ensure_ascii=False)
            else:
                # 其他转字符串
                payload = str(value)

            # 2. 存入后端
            self.backend.set(full_key, payload, ttl)
            return True
        except Exception as e:
            logger.error(f"缓存设置失败: {full_key}, 错误: {e}", exc_info=True)
            return False

    def get(self, key: str) -> Any:
        """从缓存获取数据（尝试自动解析 JSON）

        Args:
            key: 缓存键

        Returns:
            缓存的值，如果不存在返回 None
        """
        full_key = self._make_key(key)
        try:
            raw = self.backend.get(full_key)
            if raw is None:
                return None

            # 尝试 JSON 反序列化
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw
        except Exception as e:
            logger.error(f"缓存获取失败: {full_key}, 错误: {e}", exc_info=True)
            return None

    def get_model(self, key: str, model_cls: Type[T]) -> Optional[T]:
        """获取并转换为 Pydantic 模型（强类型安全）

        Args:
            key: 缓存键
            model_cls: 目标 Pydantic 模型类

        Returns:
            Pydantic 模型实例，如果不存在或解析失败返回 None
        """
        data = self.get(key)
        if not data:
            return None

        try:
            if isinstance(data, str):
                return model_cls.model_validate_json(data)
            return model_cls.model_validate(data)
        except Exception as e:
            logger.error(f"缓存模型验证失败: {e}", exc_info=True)
            return None

    def delete(self, key: str) -> None:
        """删除缓存中的键

        Args:
            key: 要删除的缓存键
        """
        full_key = self._make_key(key)
        try:
            self.backend.delete(full_key)
        except Exception as e:
            logger.error(f"缓存删除失败: {e}", exc_info=True)

    def scan_keys(self, pattern: str = "*") -> list[str]:
        """扫描匹配模式的缓存键

        Args:
            pattern: 匹配模式，默认 "*" 匹配所有

        Returns:
            匹配的键列表（会自动去除前缀返回给业务层）
        """
        full_pattern = self._make_key(pattern)
        try:
            keys = self.backend.keys(full_pattern)
            # 去除前缀，让业务层看到的是原始 Key
            return [k[len(self.prefix) :] for k in keys]
        except Exception as e:
            logger.error(f"缓存扫描失败: {e}", exc_info=True)
            return []
