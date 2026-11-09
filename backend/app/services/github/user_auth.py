from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.personal_tokens import decrypt_personal_token
from app.db.models import GitHubIdentity, User


async def github_user_token(db: Session, user: User) -> str:
    identity = db.get(GitHubIdentity, user.id)
    if identity is None:
        raise HTTPException(status_code=401, detail="请先绑定个人 GitHub Token")
    return decrypt_personal_token(identity.access_token_encrypted)
