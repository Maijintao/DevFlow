from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy.orm import Session

from app.api.routes.auth import password_hasher, require_login
from app.db.models import GitHubIdentity, Issue, LocalCredential, ProjectMember, PullRequest, Repository, User, UserProfile
from app.db.session import get_db
from app.services.github.client import GitHubClient
from app.services.github.user_auth import github_user_token
from app.services.permissions import write_audit_log
from app.services.repos_sync import parse_github_datetime

router = APIRouter()
ProjectRole = Literal["leader", "developer", "product_manager"]


class MemberRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: SecretStr | None = None
    role: ProjectRole


class IssueRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = ""


class PullRequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = ""
    head: str = Field(min_length=1)
    base: str = Field(min_length=1)
    issue_id: UUID


class MergeRequest(BaseModel):
    head_sha: str = Field(min_length=1)
    merge_method: Literal["merge", "squash", "rebase"]


class AssignmentRequest(BaseModel):
    user_id: UUID | None


def _repo(db: Session, repo_id: UUID) -> Repository:
    repo = db.get(Repository, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="未找到仓库")
    if repo.provider != "github":
        raise HTTPException(status_code=400, detail="当前操作需要 GitHub 仓库")
    return repo


def _member(db: Session, repo_id: UUID, user: User, roles: set[str]) -> ProjectMember:
    membership = db.get(ProjectMember, (repo_id, user.id))
    if membership is None or membership.role not in roles:
        raise HTTPException(status_code=403, detail="当前账号没有此项目操作权限")
    return membership


async def _client(db: Session, user: User, repo: Repository) -> GitHubClient:
    return GitHubClient(token=await github_user_token(db, user), base_url=repo.api_base_url)


@router.post("/repos/{repo_id}/bootstrap")
async def bootstrap_project(repo_id: UUID, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    repo = _repo(db, repo_id)
    credential = db.get(LocalCredential, user.id)
    if credential is None or not credential.is_admin:
        raise HTTPException(status_code=403, detail="需要系统管理员权限才能初始化项目")
    repo = db.query(Repository).filter(Repository.id == repo.id).with_for_update().one()
    if db.query(ProjectMember).filter(ProjectMember.repo_id == repo.id).first():
        raise HTTPException(status_code=409, detail="项目成员已经初始化")
    db.add(ProjectMember(repo_id=repo.id, user_id=user.id, role="leader"))
    write_audit_log(db, user=user, repo_id=repo.id, action="project.bootstrap", target_type="repository", target_id=str(repo.id))
    db.commit()
    return {"role": "leader"}


@router.get("/repos/{repo_id}/members")
async def list_members(repo_id: UUID, user: User = Depends(require_login), db: Session = Depends(get_db)) -> list[dict]:
    _repo(db, repo_id)
    _member(db, repo_id, user, {"leader", "developer", "product_manager"})
    rows = db.query(ProjectMember, LocalCredential).join(LocalCredential, LocalCredential.user_id == ProjectMember.user_id).filter(ProjectMember.repo_id == repo_id).all()
    result = []
    for member, credential in rows:
        identity = db.get(GitHubIdentity, member.user_id)
        account = db.get(User, member.user_id)
        profile = db.get(UserProfile, member.user_id)
        result.append({"user_id": str(member.user_id), "username": credential.username, "name": account.name, "avatar_url": profile.avatar_url if profile else None, "github_login": identity.login if identity else None, "role": member.role})
    return result


@router.put("/repos/{repo_id}/members")
async def add_member(repo_id: UUID, payload: MemberRequest, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    _repo(db, repo_id)
    _member(db, repo_id, user, {"leader"})
    username = payload.username.strip().casefold()
    if not username:
        raise HTTPException(status_code=400, detail="请输入账号")
    credential = db.query(LocalCredential).filter(LocalCredential.username == username).one_or_none()
    if credential is None:
        if payload.password is None or not payload.password.get_secret_value():
            raise HTTPException(status_code=400, detail="创建账号时需要设置密码")
        account = User(name=username, role="viewer")
        db.add(account)
        db.flush()
        credential = LocalCredential(user_id=account.id, username=username, password_hash=password_hasher.hash(payload.password.get_secret_value()), is_admin=False)
        db.add(credential)
    elif payload.password is not None:
        raise HTTPException(status_code=400, detail="已有账号不需要重新设置密码")
    member = db.get(ProjectMember, (repo_id, credential.user_id))
    if member is None:
        member = ProjectMember(repo_id=repo_id, user_id=credential.user_id, role=payload.role)
        db.add(member)
    else:
        if member.user_id == user.id and payload.role != "leader":
            raise HTTPException(status_code=400, detail="不能修改自己的组长权限")
        member.role = payload.role
    write_audit_log(db, user=user, repo_id=repo_id, action="project.member.save", target_type="user", target_id=str(credential.user_id), request_json={"role": payload.role})
    db.commit()
    return {"user_id": str(credential.user_id), "username": username, "role": member.role}


@router.delete("/repos/{repo_id}/members/{member_id}")
async def remove_member(repo_id: UUID, member_id: UUID, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    _repo(db, repo_id)
    _member(db, repo_id, user, {"leader"})
    if member_id == user.id:
        raise HTTPException(status_code=400, detail="不能移除自己的组长权限")
    member = db.get(ProjectMember, (repo_id, member_id))
    if member is None:
        raise HTTPException(status_code=404, detail="未找到项目成员")
    db.delete(member)
    write_audit_log(db, user=user, repo_id=repo_id, action="project.member.remove", target_type="user", target_id=str(member_id))
    db.commit()
    return {"status": "ok"}


@router.post("/repos/{repo_id}/issues")
async def create_issue(repo_id: UUID, payload: IssueRequest, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    repo = _repo(db, repo_id)
    _member(db, repo_id, user, {"leader", "developer", "product_manager"})
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="请输入 Issue 标题")
    client = await _client(db, user, repo)
    remote = await client.create_issue(repo.owner, repo.name, payload.title.strip(), payload.body)
    issue = Issue(repo_id=repo.id, github_issue_id=remote["id"], number=remote["number"], title=remote["title"], body=remote.get("body"), state=remote["state"], author=remote["user"]["login"], labels=[], assignees=[], created_at=parse_github_datetime(remote.get("created_at")), updated_at=parse_github_datetime(remote.get("updated_at")))
    db.add(issue)
    write_audit_log(db, user=user, repo_id=repo.id, action="github.issue.create", target_type="issue", target_id=str(remote["number"]))
    db.commit()
    return {"issue_id": str(issue.id), "number": issue.number, "url": remote["html_url"]}


@router.get("/repos/{repo_id}/branches")
async def list_branches(repo_id: UUID, user: User = Depends(require_login), db: Session = Depends(get_db)) -> list[str]:
    repo = _repo(db, repo_id)
    _member(db, repo.id, user, {"leader", "developer"})
    client = await _client(db, user, repo)
    branches = await client.get_all(f"/repos/{repo.owner}/{repo.name}/branches")
    return [branch["name"] for branch in branches]


@router.post("/issues/{issue_id}/claim")
async def claim_issue(issue_id: UUID, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="未找到 Issue")
    repo = _repo(db, issue.repo_id)
    _member(db, repo.id, user, {"leader", "developer"})
    identity = db.get(GitHubIdentity, user.id)
    if identity is None:
        raise HTTPException(status_code=400, detail="请先绑定个人 GitHub Token")
    client = await _client(db, user, repo)
    issue = db.query(Issue).filter(Issue.id == issue_id).with_for_update().one()
    path = f"/repos/{repo.owner}/{repo.name}/issues/{issue.number}"
    remote = await client.get(path)
    if remote["state"] != "open":
        raise HTTPException(status_code=409, detail="该 Issue 已关闭")
    current = [item["login"] for item in remote.get("assignees", [])]
    if len(current) > 1:
        raise HTTPException(status_code=409, detail="该 Issue 已有多位负责人，请由组长调整")
    if current and identity.login.lower() not in {login.lower() for login in current}:
        raise HTTPException(status_code=409, detail="该 Issue 已有负责人，请刷新后查看")
    if not current:
        remote = await client.post(f"{path}/assignees", {"assignees": [identity.login]})
    issue.assignees = [item["login"] for item in remote.get("assignees", [])]
    if identity.login.lower() not in {login.lower() for login in issue.assignees}:
        raise HTTPException(status_code=409, detail="GitHub 没有设置该负责人，请检查仓库权限")
    write_audit_log(db, user=user, repo_id=repo.id, action="github.issue.claim", target_type="issue", target_id=str(issue.id))
    db.commit()
    if len(issue.assignees) != 1:
        raise HTTPException(status_code=409, detail="GitHub 负责人发生变化，请由组长确认")
    return {"assignees": issue.assignees}


@router.put("/issues/{issue_id}/assignee")
async def assign_issue(issue_id: UUID, payload: AssignmentRequest, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="未找到 Issue")
    repo = _repo(db, issue.repo_id)
    _member(db, repo.id, user, {"leader"})
    assignees = []
    if payload.user_id is not None:
        target = db.get(ProjectMember, (repo.id, payload.user_id))
        if target is None:
            raise HTTPException(status_code=404, detail="未找到项目成员")
        if target.role not in {"leader", "developer"}:
            raise HTTPException(status_code=400, detail="请选择组长或组员")
        identity = db.get(GitHubIdentity, payload.user_id)
        if identity is None:
            raise HTTPException(status_code=400, detail="该成员尚未关联 GitHub 账号")
        assignees = [identity.login]
    client = await _client(db, user, repo)
    db.query(Issue).filter(Issue.id == issue_id).with_for_update().one()
    path = f"/repos/{repo.owner}/{repo.name}/issues/{issue.number}"
    current = await client.get(path)
    if current["state"] != "open":
        raise HTTPException(status_code=409, detail="该 Issue 已关闭")
    remote = await client.patch(path, {"assignees": assignees})
    issue.assignees = [item["login"] for item in remote.get("assignees", [])]
    if {item.lower() for item in issue.assignees} != {item.lower() for item in assignees}:
        raise HTTPException(status_code=409, detail="GitHub 未更新负责人，请检查成员的仓库访问权限")
    write_audit_log(db, user=user, repo_id=repo.id, action="github.issue.assign", target_type="issue", target_id=str(issue.id), request_json={"user_id": str(payload.user_id) if payload.user_id else None})
    db.commit()
    return {"assignees": issue.assignees}


@router.post("/repos/{repo_id}/pull-requests")
async def create_pull_request(repo_id: UUID, payload: PullRequestCreate, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    repo = _repo(db, repo_id)
    _member(db, repo.id, user, {"leader", "developer"})
    issue = db.get(Issue, payload.issue_id)
    if issue is None or issue.repo_id != repo.id:
        raise HTTPException(status_code=404, detail="未找到项目 Issue")
    if not payload.title.strip() or not payload.head.strip() or not payload.base.strip():
        raise HTTPException(status_code=400, detail="请填写 PR 标题和分支")
    client = await _client(db, user, repo)
    remote_issue = await client.get(f"/repos/{repo.owner}/{repo.name}/issues/{issue.number}")
    if remote_issue["state"] != "open":
        raise HTTPException(status_code=409, detail="该 Issue 已关闭")
    body = f"{payload.body.strip()}\n\nFixes #{issue.number}".strip()
    remote = await client.post(f"/repos/{repo.owner}/{repo.name}/pulls", {
        "title": payload.title.strip(), "body": body, "head": payload.head.strip(), "base": payload.base.strip(),
    })
    pr = PullRequest(repo_id=repo.id, github_pr_id=remote["id"], number=remote["number"], title=remote["title"], body=remote.get("body"), state=remote["state"], author=remote["user"]["login"], base_branch=remote["base"]["ref"], head_branch=remote["head"]["ref"], created_at=parse_github_datetime(remote.get("created_at")), updated_at=parse_github_datetime(remote.get("updated_at")))
    db.add(pr)
    write_audit_log(db, user=user, repo_id=repo.id, action="github.pull_request.create", target_type="pull_request", target_id=str(remote["number"]), request_json={"issue_number": issue.number, "head": payload.head, "base": payload.base})
    db.commit()
    return {"pr_id": str(pr.id), "number": pr.number, "url": remote["html_url"]}


@router.get("/pull-requests/{pr_id}/merge-preview")
async def merge_preview(pr_id: UUID, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    pr = db.get(PullRequest, pr_id)
    if pr is None:
        raise HTTPException(status_code=404, detail="未找到 PR")
    repo = _repo(db, pr.repo_id)
    _member(db, repo.id, user, {"leader"})
    client = await _client(db, user, repo)
    remote = await client.get(f"/repos/{repo.owner}/{repo.name}/pulls/{pr.number}")
    return {"title": remote["title"], "state": remote["state"], "head_sha": remote["head"]["sha"], "head": remote["head"]["ref"], "base": remote["base"]["ref"], "mergeable": remote.get("mergeable"), "url": remote["html_url"]}


@router.post("/pull-requests/{pr_id}/merge")
async def merge_pull_request(pr_id: UUID, payload: MergeRequest, user: User = Depends(require_login), db: Session = Depends(get_db)) -> dict:
    pr = db.get(PullRequest, pr_id)
    if pr is None:
        raise HTTPException(status_code=404, detail="未找到 PR")
    repo = _repo(db, pr.repo_id)
    _member(db, repo.id, user, {"leader"})
    client = await _client(db, user, repo)
    result = await client.put(f"/repos/{repo.owner}/{repo.name}/pulls/{pr.number}/merge", {"sha": payload.head_sha, "merge_method": payload.merge_method})
    if not result.get("merged"):
        raise HTTPException(status_code=409, detail=result.get("message") or "GitHub 未完成合并")
    pr.state = "closed"
    pr.merged_at = datetime.now(timezone.utc)
    write_audit_log(db, user=user, repo_id=repo.id, action="github.pull_request.merge", target_type="pull_request", target_id=str(pr.id), request_json={"merge_method": payload.merge_method, "head_sha": payload.head_sha})
    db.commit()
    return {"merged": True, "message": result.get("message")}
