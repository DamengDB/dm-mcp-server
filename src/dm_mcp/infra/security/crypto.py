"""加密工具模块

提供基于 Fernet 的对称加解密封装，用于敏感配置（如 OAuth client_secret）的落库加密。
"""

import logging

from cryptography.fernet import Fernet, InvalidToken

from dm_mcp.common import messages

logger = logging.getLogger(__name__)


class FernetCrypto:
    """Fernet 加解密封装

    使用 cryptography 库的 Fernet（AES-128-CBC + HMAC-SHA256）进行对称加密。
    支持双密钥轮转：新 key 用于加密，previous_key 用于兼容解密旧数据。
    """

    def __init__(self, key: str, previous_key: str | None = None) -> None:
        """初始化 FernetCrypto

        Args:
            key: base64 编码的 32 字节 Fernet 密钥
            previous_key: 可选的旧密钥，用于解密轮转前的数据

        Raises:
            ValueError: 当 key 格式无效时
        """
        self._fernet = Fernet(key.encode())
        self._previous_fernet = Fernet(previous_key.encode()) if previous_key else None

    def encrypt(self, plaintext: str) -> str:
        """加密明文

        Args:
            plaintext: 待加密的明文字符串

        Returns:
            str: base64 编码的密文字符串
        """
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """解密密文

        先尝试用当前 key 解密，失败后再尝试 previous_key（如果配置了）。

        Args:
            ciphertext: base64 编码的密文字符串

        Returns:
            str: 解密后的明文字符串

        Raises:
            ValueError: 当密文无法被任何可用密钥解密时
        """
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            if self._previous_fernet is not None:
                try:
                    return self._previous_fernet.decrypt(ciphertext.encode()).decode()
                except InvalidToken:
                    pass
            raise ValueError("无法解密：密文无效或密钥不匹配") from None

    def is_rotated(self, ciphertext: str) -> bool:
        """判断密文是否是用旧密钥加密的

        用于密钥轮转场景：如果旧 key 能解密但新 key 不能，
        说明该密文需要重新用新 key 加密。

        Args:
            ciphertext: base64 编码的密文字符串

        Returns:
            bool: 是否需要轮转（True = 旧 key 能解、新 key 不能解）
        """
        try:
            self._fernet.decrypt(ciphertext.encode())
            return False  # 新 key 能解，不需要轮转
        except InvalidToken:
            pass

        if self._previous_fernet is not None:
            try:
                self._previous_fernet.decrypt(ciphertext.encode())
                return True  # 旧 key 能解、新 key 不能解，需要轮转
            except InvalidToken:
                pass

        return False  # 两个 key 都不能解（可能是损坏的密文）
