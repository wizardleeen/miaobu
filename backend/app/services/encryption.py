"""
Encryption service for environment variable values.

Uses Fernet symmetric encryption from the cryptography library.
"""
from cryptography.fernet import Fernet
from ..config import get_settings


def _get_fernet() -> Fernet:
    """Get Fernet instance with configured key."""
    settings = get_settings()
    key = settings.env_encryption_key
    if not key:
        raise ValueError("env_encryption_key is not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a plaintext string.

    Args:
        plaintext: The value to encrypt

    Returns:
        Base64-encoded encrypted string
    """
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt an encrypted string.

    Args:
        ciphertext: Base64-encoded encrypted value

    Returns:
        Decrypted plaintext string
    """
    f = _get_fernet()
    return f.decrypt(ciphertext.encode()).decode()


def generate_key() -> str:
    """Generate a new Fernet encryption key (for initial setup)."""
    return Fernet.generate_key().decode()
