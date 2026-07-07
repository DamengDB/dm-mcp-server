"""加密工具函数"""

import base64
import hashlib


def to_fernet_key(secret: str) -> str:
    """把任意字符串转换为 Fernet 合法的 32 字节 URL-safe base64 密钥

    Fernet 要求密钥必须是 32 字节经 URL-safe base64 编码后的字符串。
    此函数使用 SHA-256 将任意长度的 secret 哈希为 32 字节，再做 base64 编码，
    保证输出始终满足 Fernet 的格式要求。
    """
    key_bytes = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key_bytes).decode()
