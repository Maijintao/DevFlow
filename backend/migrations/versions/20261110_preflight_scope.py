from alembic import op
import sqlalchemy as sa


revision = "20261110_preflight_scope"
down_revision = "20261110_preflight_remote"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "issue_preflight_scopes",
        sa.Column("issue_id", sa.Uuid(), sa.ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("paths", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("issue_preflight_scopes")
