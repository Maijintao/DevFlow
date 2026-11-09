import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, HttpUrl, SecretStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.personal_tokens import encrypt_personal_token
from app.core.security import decrypt_token
from app.db.models import BootstrapState, GitHubIdentity, LocalCredential, LoginSession, ProjectMember, Repository, User, UserProfile
from app.db.session import get_db

router = APIRouter()
SESSION_COOKIE = "devflow_session"
password_hasher = PasswordHasher()


class LoginRequest(BaseModel):
    username: str
    password: SecretStr


class TokenRequest(BaseModel):
    token: SecretStr


class ProfileRequest(BaseModel):
    name: str
    avatar_url: HttpUrl | None = None


class PasswordRequest(BaseModel):
    current_password: SecretStr
    new_password: SecretStr


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_login(request: Request, db: Session = Depends(get_db)) -> User:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") not in {item.strip() for item in settings.cors_origins.split(",")}:
            raise HTTPException(status_code=403, detail="请求来源未获授权")
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    session = db.get(LoginSession, token_hash(token))
    if session is None or session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = db.get(User, session.user_id)
    if user is None or db.get(LocalCredential, session.user_id) is None:
        raise HTTPException(status_code=401, detail="登录账号不存在")
    return user


def _set_session(response: Response, db: Session, user: User) -> None:
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=token_hash(token), user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.login_session_hours)))
    db.commit()
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=settings.app_env.lower() == "production", samesite="lax", max_age=settings.login_session_hours * 3600, path="/")


@router.get("/status")
async def auth_status(db: Session = Depends(get_db)) -> dict:
    return {"setup_required": db.get(BootstrapState, "initial") is None}


@router.post("/setup")
async def setup_account(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="请在本机完成初始账号设置")
    if request.headers.get("origin") not in {item.strip() for item in settings.cors_origins.split(",")}:
        raise HTTPException(status_code=403, detail="请求来源未获授权")
    if db.get(BootstrapState, "initial") is not None:
        raise HTTPException(status_code=409, detail="初始账号已经创建")
    username = payload.username.strip().casefold()
    password = payload.password.get_secret_value()
    if not username or not password:
        raise HTTPException(status_code=400, detail="请输入账号和密码")
    db.add(BootstrapState(name="initial"))
    db.flush()
    user = User(name=username, role="viewer")
    db.add(user)
    db.flush()
    db.add(LocalCredential(user_id=user.id, username=username, password_hash=password_hasher.hash(password), is_admin=True))
    for repo in db.query(Repository).filter(Repository.provider != "knowledge_base").all():
        db.add(ProjectMember(repo_id=repo.id, user_id=user.id, role="leader"))
    _set_session(response, db, user)
    return {"id": str(user.id), "username": username}


@router.post("/login")
async def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    if request.headers.get("origin") not in {item.strip() for item in settings.cors_origins.split(",")}:
        raise HTTPException(status_code=403, detail="请求来源未获授权")
    credential = db.query(LocalCredential).filter(LocalCredential.username == payload.username.strip().casefold()).one_or_none()
    if credential is None:
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    try:
        password_hasher.verify(credential.password_hash, payload.password.get_secret_value())
    except (VerifyMismatchError, InvalidHashError):
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    user = db.get(User, credential.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    if password_hasher.check_needs_rehash(credential.password_hash):
        credential.password_hash = password_hasher.hash(payload.password.get_secret_value())
    _set_session(response, db, user)
    return {"id": str(user.id), "username": credential.username}


@router.get("/me")
async def current_user(user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    credential = db.get(LocalCredential, user.id)
    identity = db.get(GitHubIdentity, user.id)
    profile = db.get(UserProfile, user.id)
    memberships = db.query(ProjectMember).filter(ProjectMember.user_id == user.id).all()
    return {"id": str(user.id), "username": credential.username, "name": user.name, "avatar_url": profile.avatar_url if profile else None, "github_login": identity.login if identity else None, "is_admin": credential.is_admin, "projects": [{"repo_id": str(item.repo_id), "role": item.role} for item in memberships]}


@router.patch("/profile")
async def update_profile(payload: ProfileRequest, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请输入昵称")
    user.name = name
    profile = db.get(UserProfile, user.id)
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    profile.avatar_url = str(payload.avatar_url) if payload.avatar_url else None
    db.commit()
    return {"name": user.name, "avatar_url": profile.avatar_url}


async def _bind_github_token(token: str, user: User, db: Session) -> dict:
    token = token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="请输入 GitHub Token")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get("https://api.github.com/user", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        if response.status_code in {401, 403}:
            raise HTTPException(status_code=400, detail="GitHub Token 无效或没有用户访问权限")
        response.raise_for_status()
        profile = response.json()
    duplicate = db.query(GitHubIdentity).filter(GitHubIdentity.github_id == profile["id"], GitHubIdentity.user_id != user.id).one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="该 GitHub 账号已绑定其他 DevFlow 用户")
    identity = db.get(GitHubIdentity, user.id)
    if identity is None:
        identity = GitHubIdentity(user_id=user.id, github_id=profile["id"], login=profile["login"], access_token_encrypted="")
        db.add(identity)
    identity.github_id = profile["id"]
    identity.login = profile["login"]
    identity.access_token_encrypted = encrypt_personal_token(token)
    db.commit()
    return {"github_login": identity.login}


@router.put("/github-token")
async def set_github_token(payload: TokenRequest, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    return await _bind_github_token(payload.token.get_secret_value(), user, db)


@router.post("/github-token/from-project/{repo_id}")
async def use_project_token(repo_id: UUID, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    credential = db.get(LocalCredential, user.id)
    member = db.get(ProjectMember, (repo_id, user.id))
    if not credential.is_admin or member is None or member.role != "leader":
        raise HTTPException(status_code=403, detail="只有系统管理员可以使用项目现有 Token")
    repo = db.get(Repository, repo_id)
    if repo is None or not repo.github_token_encrypted:
        raise HTTPException(status_code=400, detail="该项目尚未保存 GitHub Token")
    token = decrypt_token(repo.github_token_encrypted, settings.token_encryption_key)
    if not token:
        raise HTTPException(status_code=400, detail="无法读取项目 Token")
    return await _bind_github_token(token, user, db)


@router.put("/password")
async def change_password(payload: PasswordRequest, request: Request, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    credential = db.get(LocalCredential, user.id)
    try:
        password_hasher.verify(credential.password_hash, payload.current_password.get_secret_value())
    except (VerifyMismatchError, InvalidHashError):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    password = payload.new_password.get_secret_value()
    if not password:
        raise HTTPException(status_code=400, detail="请输入新密码")
    credential.password_hash = password_hasher.hash(password)
    current_hash = token_hash(request.cookies[SESSION_COOKIE])
    db.query(LoginSession).filter(LoginSession.user_id == user.id, LoginSession.token_hash != current_hash).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok"}


@router.post("/logout")
async def logout(request: Request, response: Response, _user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    session = db.get(LoginSession, token_hash(token)) if token else None
    if session is not None:
        db.delete(session)
        db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}
