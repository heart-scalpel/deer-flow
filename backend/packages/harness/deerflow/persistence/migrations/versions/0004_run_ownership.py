"""run ownership.

Revision ID: 0004_run_ownership
Revises: 0003_scheduled_tasks
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_run_ownership"
down_revision: str | Sequence[str] | None = "0003_scheduled_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from deerflow.persistence.migrations._helpers import safe_add_column

    safe_add_column("runs", sa.Column("owner_worker_id", sa.String(length=128), nullable=True))
    safe_add_column("runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))

    # Idempotent index creation: the legacy bootstrap path runs create_all
    # (which creates the index from the ORM __table_args__) before upgrade
    # head, so the migration must not fail when the index already exists.
    insp = sa.inspect(op.get_bind())
    existing = {ix["name"] for ix in insp.get_indexes("runs")}
    if "ix_runs_lease" not in existing:
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.create_index("ix_runs_lease", ["lease_expires_at"], unique=False)
    if "uq_runs_thread_active" not in existing:
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.create_index(
                "uq_runs_thread_active",
                ["thread_id"],
                unique=True,
                sqlite_where=sa.text("status IN ('pending', 'running')"),
                postgresql_where=sa.text("status IN ('pending', 'running')"),
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {ix["name"] for ix in insp.get_indexes("runs")}
    if "uq_runs_thread_active" in existing:
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.drop_index("uq_runs_thread_active")
    if "ix_runs_lease" in existing:
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.drop_index("ix_runs_lease")

    from deerflow.persistence.migrations._helpers import safe_drop_column

    safe_drop_column("runs", "lease_expires_at")
    safe_drop_column("runs", "owner_worker_id")
