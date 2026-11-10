from alembic import op
import sqlalchemy as sa


revision = "20261110_issue_preflight"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issue_poll_cursors",
        sa.Column("repo_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("synced_through", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
    )
    op.create_table(
        "issue_preflight_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("error", sa.Text()),
        sa.Column("base_commit_sha", sa.String(64)),
        sa.Column("working_tree_dirty", sa.Boolean()),
        sa.Column("analyzer_version", sa.String(40), nullable=False),
        sa.Column("result_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    for column in ("issue_id", "fingerprint", "status", "created_at"):
        op.create_index(f"ix_issue_preflight_jobs_{column}", "issue_preflight_jobs", [column])


def downgrade() -> None:
    op.drop_table("issue_preflight_jobs")
    op.drop_table("issue_poll_cursors")
