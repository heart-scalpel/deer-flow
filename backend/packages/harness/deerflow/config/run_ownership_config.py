from pydantic import BaseModel, Field


class RunOwnershipConfig(BaseModel):
    """Multi-worker run ownership / lease configuration.

    ``GATEWAY_WORKERS=1`` deployments leave ``heartbeat_enabled=False`` and the
    run path behaves as before — the in-process ``asyncio.Lock`` serialises
    ``create_or_reject`` and the SQLite/Postgres reconciliation step at startup
    marks any leftover active row as error.

    Multi-worker deployments (``GATEWAY_WORKERS>1``) flip on
    ``heartbeat_enabled`` so the run path pivots to DB-level atomicity: each
    worker writes ``runs.owner_worker_id`` + ``runs.lease_expires_at`` when it
    inserts a run, renews the lease from a background task, and a worker that
    crashes is detected by the surviving workers once ``lease_expires_at`` runs
    past ``NOW() + grace_seconds``. Cancel requests that land on a non-owner
    worker can either wait for the live owner (409 + Retry-After) or take over
    directly when the lease has already expired.
    """

    lease_seconds: int = Field(default=30, ge=5, le=600, description="How long an active run lease stays valid before another worker may take over. The heartbeat task renews it at lease_seconds / 3.")
    grace_seconds: int = Field(default=10, ge=0, le=300, description="Extra slack added to lease_seconds before a stale run is treated as orphaned. Cushions clock skew and in-flight heartbeat writes.")
    heartbeat_enabled: bool = Field(default=False, description="Enable the per-worker lease heartbeat. Required for safe multi-worker operation; single-worker deployments leave this off for zero behavior change.")
