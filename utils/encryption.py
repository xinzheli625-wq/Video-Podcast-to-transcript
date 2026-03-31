"""
加密工具 - 用于保护敏感的 API Keys
使用 Fernet 对称加密
"""
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def get_master_key() -> bytes:
    """
    获取主密钥。优先从环境变量获取，否则使用默认（仅开发环境）。
    生产环境必须设置 MASTER_KEY 环境变量。
    """
    master_key = os.environ.get("MASTER_KEY")
    if not master_key:
        # 开发环境默认密钥（仅本地测试使用）
        master_key = "xiaoyuzhou-transcriber-dev-key-32bytes"
    
    # 确保密钥长度符合要求（32字节）
    key_bytes = master_key.encode('utf-8')
    if len(key_bytes) < 32:
        # 填充到32字节
        key_bytes = key_bytes + b'0' * (32 - len(key_bytes))
    elif len(key_bytes) > 32:
        # 截取前32字节
        key_bytes = key_bytes[:32]
    
    return key_bytes


def generate_fernet_key(master_key: bytes = None) -> bytes:
    """从主密钥生成 Fernet 密钥"""
    if master_key is None:
        master_key = get_master_key()
    
    # 使用 PBKDF2 派生密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'xiaoyuzhou_salt_v1',  # 固定 salt（简化方案）
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(master_key))
    return key


def encrypt_api_key(plain_text: str) -> str:
    """加密 API Key"""
    key = generate_fernet_key()
    f = Fernet(key)
    encrypted = f.encrypt(plain_text.encode('utf-8'))
    return encrypted.decode('utf-8')


def decrypt_api_key(encrypted_text: str) -> str:
    """解密 API Key"""
    key = generate_fernet_key()
    f = Fernet(key)
    decrypted = f.decrypt(encrypted_text.encode('utf-8'))
    return decrypted.decode('utf-8')


def main():
    """命令行工具：加密 API Key"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m utils.encryption <api_key_to_encrypt>")
        print("\nExample:")
        print('  python -m utils.encryption "2a42f31c-c77e-4da5-b157-610c05e38011"')
        print("\nThen copy the encrypted string to your .env file:")
        print("  VOLCENGINE_API_KEY_ENC=<encrypted_string>")
        sys.exit(1)
    
    api_key = sys.argv[1]
    encrypted = encrypt_api_key(api_key)
    
    print("\n" + "="*60)
    print("API Key 加密成功！")
    print("="*60)
    print(f"\n加密后的 Key:\n{encrypted}")
    print("\n请将此值复制到 .env 文件中：")
    print(f"  VOLCENGINE_API_KEY_ENC={encrypted}")
    print("\n可选：设置环境变量增强安全性：")
    print("  MASTER_KEY=your-secret-master-key")
    print("="*60)
    
    # 验证加密/解密
    decrypted = decrypt_api_key(encrypted)
    if decrypted == api_key:
        print("\n✓ 加密/解密验证通过")
    else:
        print("\n✗ 验证失败！")


if __name__ == "__main__":
    main()
