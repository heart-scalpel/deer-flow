"""Add multi-worker run ownership columns.

Revision ID: 0004_run_ownership
Revises: 0003_scheduled_tasks
Create Date: 2026-07-06

Adds ``runs.owner_worker_id`` and ``runs.lease_expires_at`` plus a partial
unique index that gives ``create_or_reject`` a database-level atomicity
guarantee across worker processes. Without this index the in-memory
``asyncio.Lock`` only protects a single process: two Gateway workers can
both observe "no inflight run" and INSERT, leaving the same thread with
two concurrent runs whose checkpoint writes overwrite each other.

The partial unique index ``uq_runs_thread_active`` allows only one row per
``thread_id`` whose ``status`` is in ``('pending', 'running')``. ``reject``
strategy INSERTs directly and relies on the index to raise
``IntegrityError``; ``interrupt``/``rollback`` strategies lock the active
row ``FOR UPDATE``, decide whether the lease is live, mark it ``error`` or
``interrupted`` to drop out of the partial-index predicate, then INSERT.

The plain index ``ix_runs_lease`` supports the lease-reconciliation scan
that turns stale active rows into ``error`` after a worker crash.

Backward compatibility: existing rows get ``owner_worker_id IS NULL`` and
``lease_expires_at IS NULL``, which the reconciliation logic treats as
"always stale" so a single-worker Gateway that predates this PR keeps
behaving exactly like before (the heartbeat task is opt-in via
``run_ownership.heartbeat_enabled`` and is off by default).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from deerflow.persistence.migrations._helpers import safe_add_column, safe_drop_column

# revision identifiers, used by Alembic.
revision: str = "0004_run_ownership"
down_revision: str | Sequence[str] | None = "0003_scheduled_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_PARTIAL_ACTIVE_WHERE = sa.text("status IN ('pending', 'running')")


def _index_exists(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def upgrade() -> None:
    safe_add_column("runs", sa.Column("owner_worker_id", sa.String(length=128), nullable=True))
    safe_add_column("runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _index_exists(inspector, "runs", "ix_runs_lease"):
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.create_index("ix_runs_lease", ["lease_expires_at"], unique=False)

    if not _index_exists(inspector, "runs", "uq_runs_thread_active"):
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.create_index(
                "uq_runs_thread_active",
                ["thread_id"],
                unique=True,
                sqlite_where=_PARTIAL_ACTIVE_WHERE,
                postgresql_where=_PARTIAL_ACTIVE_WHERE,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _index_exists(inspector, "runs", "uq_runs_thread_active"):
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.drop_index("uq_runs_thread_active", sqlite_where=_PARTIAL_ACTIVE_WHERE, postgresql_where=_PARTIAL_ACTIVE_WHERE)
    if _index_exists(inspector, "runs", "ix_runs_lease"):
        with op.batch_alter_table("runs", schema=None) as batch_op:
            batch_op.drop_index("ix_runs_lease")

    safe_drop_column("runs", "lease_expires_at")
    safe_drop_column("runs", "owner_worker_id")
