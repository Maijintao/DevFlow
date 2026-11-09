import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

from app.core.config import settings


def _key() -> bytes:
    if settings.personal_token_encryption_key:
        return settings.personal_token_encryption_key.encode("ascii")
    if settings.app_env.lower() == "production":
        raise RuntimeError("生产环境需要配置 PERSONAL_TOKEN_ENCRYPTION_KEY")
    path = Path(settings.personal_token_key_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            temporary.write(Fernet.generate_key())
            temporary_path = Path(temporary.name)
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            pass
        finally:
            temporary_path.unlink()
    return path.read_bytes().strip()


def encrypt_personal_token(token: str) -> str:
    return Fernet(_key()).encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_personal_token(token: str) -> str:
    return Fernet(_key()).decrypt(token.encode("ascii")).decode("utf-8")
