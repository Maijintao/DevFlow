from alembic import op
import sqlalchemy as sa


revision = "20261110_pr_conflict"
down_revision = "20261110_preflight_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pr_conflict_poll_states",
        sa.Column("repo_id", sa.Uuid(), sa.ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
    )
    op.create_table(
        "pr_conflict_checks",
        sa.Column("pr_id", sa.Uuid(), sa.ForeignKey("pull_requests.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("head_sha", sa.String(64), nullable=False),
        sa.Column("base_sha", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text()),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("detail_status", sa.String(24), nullable=False),
        sa.Column("detail_error", sa.Text()),
        sa.Column("detail_lease_until", sa.DateTime(timezone=True)),
        sa.Column("detail_lease_token", sa.String(36)),
        sa.Column("conflict_files", sa.JSON(), nullable=False),
        sa.Column("related_prs", sa.JSON(), nullable=False),
        sa.Column("advice_status", sa.String(24), nullable=False),
        sa.Column("advice_error", sa.Text()),
        sa.Column("advice_lease_until", sa.DateTime(timezone=True)),
        sa.Column("advice_lease_token", sa.String(36)),
        sa.Column("advice", sa.JSON()),
    )
    for column in ("status", "detail_status", "advice_status"):
        op.create_index(f"ix_pr_conflict_checks_{column}", "pr_conflict_checks", [column])


def downgrade() -> None:
    op.drop_table("pr_conflict_checks")
    op.drop_table("pr_conflict_poll_states")
