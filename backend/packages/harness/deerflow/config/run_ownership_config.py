"""Run ownership configuration for multi-worker deployments."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RunOwnershipConfig(BaseModel):
    """Per-run ownership and lease configuration.

    When ``heartbeat_enabled`` is True, each worker periodically renews
    the lease on its active runs. This is required for multi-worker
    deployments to detect orphaned runs from crashed workers.
    """

    lease_seconds: int = Field(
        default=30,
        ge=5,
        description="Seconds before a run lease expires if not renewed.",
    )
    grace_seconds: int = Field(
        default=10,
        ge=0,
        description="Extra seconds past lease expiry before an orphaned run is reclaimed.",
    )
    heartbeat_enabled: bool = Field(
        default=False,
        description="When True, the worker periodically renews leases on its active runs. Enable for multi-worker deployments (GATEWAY_WORKERS > 1).",
    )
