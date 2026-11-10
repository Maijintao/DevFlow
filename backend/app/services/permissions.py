from collections.abc import Callable

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.models import AuditLog, User
from app.db.session import get_db
from app.services.access_control import current_user_id

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {"repo:read", "repo:sync", "agent:run", "draft:create", "draft:approve", "eval:read", "settings:manage"},
    "maintainer": {"repo:read", "repo:sync", "agent:run", "draft:create", "draft:approve", "eval:read"},
    "developer": {"repo:read", "agent:run", "draft:create", "eval:read"},
    "viewer": {"repo:read", "eval:read"},
    "product_manager": {"repo:read", "agent:run", "draft:create", "eval:read"},
}


def require_current_user(db: Session) -> User:
    user_id = current_user_id.get()
    if user_id is None:
        raise HTTPException(status_code=401, detail="请先登录")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="登录账号不存在")
    return user


def has_permission(user: User, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get((user.role or "viewer").lower(), set())


def require_permission(permission: str) -> Callable:
    def dependency(request: Request, db: Session = Depends(get_db)) -> User:
        user_id = getattr(request.state, "user_id", None)
        user = db.get(User, user_id) if user_id else None
        if user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        role = getattr(request.state, "project_role", None)
        role_key = {"leader": "owner", "developer": "developer", "product_manager": "product_manager"}.get(role, "viewer")
        if permission not in ROLE_PERMISSIONS.get(role_key, set()):
            raise HTTPException(status_code=403, detail=f"需要权限：{permission}")
        return user

    return dependency


def write_audit_log(
    db: Session,
    *,
    user: User | None,
    repo_id=None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    status: str = "success",
    request_json: dict | None = None,
    result_json: dict | None = None,
) -> AuditLog:
    row = AuditLog(
        user_id=user.id if user else None,
        repo_id=repo_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        status=status,
        request_json=request_json or {},
        result_json=result_json or {},
    )
    db.add(row)
    db.flush()
    return row
