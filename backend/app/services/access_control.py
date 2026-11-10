import json
from contextvars import ContextVar
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.api.routes.auth import require_login
from app.db.models import ActionDraft, Issue, LocalCredential, ProjectMember, PullRequest, Repository, User, WorkflowRun

current_user_id: ContextVar[UUID | None] = ContextVar("current_user_id", default=None)


def _uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None


def _path_repo(db: Session, parts: list[str]) -> UUID | None:
    if len(parts) < 3:
        return None
    if parts[1] == "github" and len(parts) >= 4:
        parts = [parts[0], *parts[2:]]
    if parts[1] == "rag":
        if len(parts) >= 4 and parts[2] == "repositories":
            return _uuid(parts[3])
        return _uuid(parts[2])
    object_id = _uuid(parts[2])
    if object_id is None:
        return None
    if parts[1] == "repos":
        return object_id
    models = {"issues": Issue, "pull-requests": PullRequest, "workflow-runs": WorkflowRun, "action-drafts": ActionDraft}
    model = models.get(parts[1])
    if model is None:
        return None
    obj = db.get(model, object_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="未找到请求的项目内容")
    return obj.repo_id


async def authorize_request(request: Request, db: Session) -> User:
    user = require_login(request, db)
    credential = db.get(LocalCredential, user.id)
    path = request.url.path
    parts = path.strip("/").split("/")
    request.state.user_id = user.id
    request.state.is_admin = credential.is_admin
    request.state.project_role = "leader" if credential.is_admin else None

    if path == "/api/repos/connect":
        if not credential.is_admin:
            raise HTTPException(status_code=403, detail="只有系统管理员可以连接项目")
        return user

    if not credential.is_admin:
        if path.startswith("/api/workspaces"):
            raise HTTPException(status_code=403, detail="当前账号没有此操作权限")
        if path.startswith("/api/evals/") and path != "/api/evals/suites":
            raise HTTPException(status_code=403, detail="当前账号没有此操作权限")
        if path.startswith("/api/chat/feedback/"):
            raise HTTPException(status_code=403, detail="当前账号没有此操作权限")

    if path in {"/api/repos", "/api/rag/repositories"} and request.method == "GET":
        return user
    if path.startswith("/api/skills") and request.method == "GET":
        return user

    repo_ids: set[UUID] = set()
    path_repo = _path_repo(db, parts)
    if path_repo:
        repo_ids.add(path_repo)
    query_repo = _uuid(request.query_params.get("repo_id"))
    if query_repo:
        repo_ids.add(query_repo)
    if request.headers.get("content-type", "").startswith("application/json"):
        raw_body = await request.body()
        try:
            payload = json.loads(raw_body) if raw_body else None
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="请求内容格式不正确") from exc
        if isinstance(payload, dict):
            body_repo = _uuid(payload.get("repo_id"))
            if body_repo:
                repo_ids.add(body_repo)
            for value in payload.get("repo_ids") or []:
                item = _uuid(value)
                if item:
                    repo_ids.add(item)
    if not repo_ids:
        if credential.is_admin:
            return user
        raise HTTPException(status_code=403, detail="当前账号没有此操作权限")
    memberships = []
    for repo_id in repo_ids:
        if db.get(Repository, repo_id) is None:
            raise HTTPException(status_code=404, detail="未找到项目")
        member = db.get(ProjectMember, (repo_id, user.id))
        if member is None:
            if credential.is_admin and path == f"/api/github/repos/{repo_id}/bootstrap":
                return user
            raise HTTPException(status_code=403, detail="当前账号没有此项目的访问权限")
        memberships.append(member)
    request.state.project_role = "leader" if all(item.role == "leader" for item in memberships) else "developer" if all(item.role != "product_manager" for item in memberships) else "product_manager"
    request.state.repo_id = next(iter(repo_ids)) if len(repo_ids) == 1 else None

    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        privileged = (
            (parts[1] == "repos" and len(parts) == 3 and request.method == "DELETE")
            or (parts[1] == "repos" and "team-members" in parts)
            or (parts[1] == "rag" and parts[-1] in {"config", "reindex"})
            or (parts[1] == "repos" and "memory-index" in parts)
            or (parts[1] == "action-drafts" and parts[-1] == "confirm")
        )
        if privileged and any(member.role != "leader" for member in memberships):
            raise HTTPException(status_code=403, detail="此操作需要组长权限")
    return user
