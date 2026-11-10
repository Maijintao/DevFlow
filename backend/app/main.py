import asyncio

import httpx
from alembic import command
from alembic.config import Config
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from pathlib import Path

from app.api.routes import (
    action_drafts,
    auth,
    chat,
    ci,
    code_graph,
    conversations,
    evaluations,
    feedback,
    github_collaboration,
    issues,
    knowledge,
    project_index,
    pull_requests,
    rag,
    repos,
    reports,
    search,
    skills,
    webhooks,
    workspaces,
)
from app.core.config import settings
from app.db.models import Base
from app.db.session import SessionLocal, engine
from app.services.access_control import authorize_request, current_user_id
from app.services.scheduler import periodic_repo_sync_loop
from app.services.issue_preflight import issue_poll_loop, issue_preflight_worker
from app.services.pr_conflict import poll_loop as pr_conflict_poll_loop, worker as pr_conflict_worker
from app.services.rag.vector_store import MilvusUnavailableError


def _cors_origins() -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]


def _cors_origin_regex() -> str | None:
    if settings.app_env.lower() == "production":
        return None
    return r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$"


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version="0.1.0")

    @app.exception_handler(MilvusUnavailableError)
    async def milvus_unavailable_handler(_request, exc: MilvusUnavailableError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": str(exc), "service": "milvus", "status": "degraded"},
        )

    @app.exception_handler(httpx.HTTPStatusError)
    async def github_http_error_handler(_request, exc: httpx.HTTPStatusError) -> JSONResponse:
        status = exc.response.status_code
        if status == 401:
            detail = "GitHub Token 无效或已过期，请重新关联"
        elif status == 403:
            detail = "GitHub 拒绝了操作，请检查账号、Token 和仓库权限"
        elif status == 404:
            detail = "GitHub 未找到仓库或内容，请检查账号权限"
        elif status in {405, 409, 422}:
            detail = "GitHub 未能完成操作，请检查分支、PR 状态及仓库规则"
        else:
            detail = f"GitHub 请求失败（HTTP {status}）"
        return JSONResponse(status_code=status if 400 <= status <= 599 else 502, content={"detail": detail})
    @app.middleware("http")
    async def protect_api(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api/") or path.startswith("/api/auth/") or path == "/api/webhooks/github":
            return await call_next(request)
        db = SessionLocal()
        try:
            user = await authorize_request(request, db)
        except HTTPException as exc:
            db.close()
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        db.close()
        context = current_user_id.set(user.id)
        try:
            return await call_next(request)
        finally:
            current_user_id.reset(context)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_origin_regex=_cors_origin_regex(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(github_collaboration.router, prefix="/api/github", tags=["github_collaboration"])
    app.include_router(repos.router, prefix="/api/repos", tags=["repos"])
    app.include_router(conversations.router, prefix="/api/repos", tags=["conversations"])
    app.include_router(workspaces.router, prefix="/api/workspaces", tags=["workspaces"])
    app.include_router(issues.router, prefix="/api", tags=["issues"])
    app.include_router(pull_requests.router, prefix="/api", tags=["pull_requests"])
    app.include_router(ci.router, prefix="/api", tags=["ci"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(feedback.router, prefix="/api/chat/feedback", tags=["chat_feedback"])
    app.include_router(action_drafts.router, prefix="/api/action-drafts", tags=["action_drafts"])
    app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
    app.include_router(knowledge.router, prefix="/api/repos", tags=["knowledge"])
    app.include_router(project_index.router, prefix="/api/repos", tags=["project_index"])
    app.include_router(rag.router, prefix="/api/rag", tags=["rag"])
    app.include_router(code_graph.router, prefix="/api", tags=["code_graph"])
    app.include_router(evaluations.router, prefix="/api/evals", tags=["evaluations"])
    app.include_router(webhooks.router, prefix="/api/webhooks", tags=["webhooks"])
    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    @app.on_event("startup")
    async def create_demo_tables() -> None:
        # 课程项目默认自动建表；生产风格流程会在后续加入 Alembic 迁移。
        preflight_tables = {"issue_poll_cursors", "issue_preflight_jobs", "issue_preflight_scopes", "pr_conflict_checks", "pr_conflict_poll_states"}
        Base.metadata.create_all(bind=engine, tables=[table for table in Base.metadata.sorted_tables if table.name not in preflight_tables])
        migration_config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('devflow_schema_migrations'))"))
            migration_config.attributes["connection"] = connection
            command.upgrade(migration_config, "head")
        inspector = inspect(engine)
        if "users" in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns("users")}
            if "role" not in columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(80) DEFAULT 'owner'"))
        if "repositories" in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns("repositories")}
            with engine.begin() as connection:
                if "provider" not in columns:
                    connection.execute(text("ALTER TABLE repositories ADD COLUMN provider VARCHAR(80) DEFAULT 'github'"))
                if "api_base_url" not in columns:
                    connection.execute(text("ALTER TABLE repositories ADD COLUMN api_base_url TEXT"))
                if "clone_url" not in columns:
                    connection.execute(text("ALTER TABLE repositories ADD COLUMN clone_url TEXT"))
                if "local_path" not in columns:
                    connection.execute(text("ALTER TABLE repositories ADD COLUMN local_path TEXT"))
                if "checkout_mode" not in columns:
                    connection.execute(text("ALTER TABLE repositories ADD COLUMN checkout_mode VARCHAR(80) DEFAULT 'managed'"))
                if "github_token_encrypted" not in columns:
                    connection.execute(text("ALTER TABLE repositories ADD COLUMN github_token_encrypted TEXT"))
        if "workflow_runs" in inspector.get_table_names():
            columns = {column["name"] for column in inspector.get_columns("workflow_runs")}
            if "jobs" not in columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE workflow_runs ADD COLUMN jobs JSON"))
        for table_name in ["code_symbols", "code_relations"]:
            if table_name in inspector.get_table_names():
                columns = {column["name"] for column in inspector.get_columns(table_name)}
                with engine.begin() as connection:
                    if "pr_id" not in columns:
                        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN pr_id UUID"))
                    if "pr_number" not in columns:
                        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN pr_number INTEGER"))
        for table_name in ["chat_messages", "chat_sessions", "agent_runs", "evidence_items"]:
            if table_name in inspector.get_table_names():
                columns = {column["name"] for column in inspector.get_columns(table_name)}
                if "conversation_id" not in columns:
                    with engine.begin() as connection:
                        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN conversation_id UUID"))
        for table_name in ["thread_memories", "conversation_memories"]:
            if table_name in inspector.get_table_names():
                columns = {column["name"] for column in inspector.get_columns(table_name)}
                for column_name in ["facts", "tasks", "user_preferences", "repo_context", "citations"]:
                    if column_name not in columns:
                        with engine.begin() as connection:
                            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} JSON"))
        if "documents" in inspector.get_table_names():
            document_columns = {column["name"] for column in inspector.get_columns("documents")}
            if "embedding" in document_columns:
                with engine.begin() as connection:
                    connection.execute(text("ALTER TABLE documents DROP COLUMN embedding"))
        from app.db.session import SessionLocal
        from app.services.conversations import backfill_all_default_conversations
        from app.services.code_analysis import purge_legacy_code_documents
        from app.services.rag.vector_store import delete_milvus_documents, milvus_runtime_status

        db = SessionLocal()
        try:
            backfill_all_default_conversations(db)
            if purge_legacy_code_documents(db):
                db.commit()
        finally:
            db.close()
        app.state.rag_vector_status = milvus_runtime_status()
        delete_milvus_documents(source_types=["code_file"], strict=False)
        if settings.auto_sync_enabled:
            app.state.repo_sync_task = asyncio.create_task(periodic_repo_sync_loop())
        if settings.issue_preflight_enabled:
            app.state.issue_poll_task = asyncio.create_task(issue_poll_loop())
            app.state.issue_preflight_tasks = [asyncio.create_task(issue_preflight_worker()) for _ in range(settings.issue_preflight_workers)]
        if settings.pr_conflict_enabled:
            app.state.pr_conflict_poll_task = asyncio.create_task(pr_conflict_poll_loop())
            app.state.pr_conflict_tasks = [asyncio.create_task(pr_conflict_worker("check")) for _ in range(settings.pr_conflict_workers)]
            app.state.pr_conflict_tasks += [asyncio.create_task(pr_conflict_worker("detail")) for _ in range(settings.pr_conflict_detail_workers)]
            app.state.pr_conflict_tasks.append(asyncio.create_task(pr_conflict_worker("advice")))

    @app.on_event("shutdown")
    async def stop_background_tasks() -> None:
        task = getattr(app.state, "repo_sync_task", None)
        if task:
            task.cancel()
        poll_task = getattr(app.state, "issue_poll_task", None)
        if poll_task:
            poll_task.cancel()
        for worker in getattr(app.state, "issue_preflight_tasks", []):
            worker.cancel()
        pr_poll = getattr(app.state, "pr_conflict_poll_task", None)
        if pr_poll:
            pr_poll.cancel()
        for worker in getattr(app.state, "pr_conflict_tasks", []):
            worker.cancel()

    return app


app = create_app()
