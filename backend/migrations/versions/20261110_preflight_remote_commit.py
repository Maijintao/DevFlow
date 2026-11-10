from alembic import op
import sqlalchemy as sa


revision = "20261110_preflight_remote"
down_revision = "20261110_issue_preflight"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("issue_poll_cursors", sa.Column("remote_commit_sha", sa.String(64)))
    op.add_column("issue_poll_cursors", sa.Column("remote_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("issue_poll_cursors", "remote_error")
    op.drop_column("issue_poll_cursors", "remote_commit_sha")
