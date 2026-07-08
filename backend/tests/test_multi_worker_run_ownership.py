"""Tests for multi-worker run ownership (work items 2–3).

Coverage:
- create_or_reject with reject strategy blocks duplicate active runs
- create_or_reject with interrupt strategy claims and cancels old runs
- create_run_atomic refuses to interrupt a run owned by another live worker
- reconcile_orphaned_inflight_runs uses lease-based detection
- Worker reconciliation skips runs with unexpired leases
- Lease heartbeat renews active run leases
- GATEWAY_WORKERS=1 + heartbeat_enabled=false behaviour unchanged
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from deerflow.config.run_ownership_config import RunOwnershipConfig
from deerflow.runtime import RunManager, RunStatus
from deerflow.runtime.runs.manager import ConflictError, _generate_worker_id
from deerflow.runtime.runs.store.memory import MemoryRunStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _lease_config(**kwargs) -> RunOwnershipConfig:
    return RunOwnershipConfig(
        lease_seconds=kwargs.get("lease_seconds", 30),
        grace_seconds=kwargs.get("grace_seconds", 10),
        heartbeat_enabled=kwargs.get("heartbeat_enabled", False),
    )


def _make_manager(store=None, **kwargs) -> RunManager:
    return RunManager(
        store=store or MemoryRunStore(),
        run_ownership_config=kwargs.pop("run_ownership_config", _lease_config()),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# create_or_reject — reject strategy
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_reject_blocks_when_active_run_exists():
    """reject strategy must raise ConflictError when thread has an active run."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)
    await manager.create("thread-1")
    await manager.set_status((await manager.list_by_thread("thread-1"))[0].run_id, RunStatus.running)

    with pytest.raises(ConflictError, match="already has an active run"):
        await manager.create_or_reject("thread-1", multitask_strategy="reject")


@pytest.mark.anyio
async def test_reject_succeeds_when_no_active_run():
    """reject strategy must succeed when the thread has no active run."""
    store = MemoryRunStore()
    manager = _make_manager(store=store, run_ownership_config=_lease_config(heartbeat_enabled=True))
    record = await manager.create_or_reject("thread-1", multitask_strategy="reject")
    assert record is not None
    assert record.status == RunStatus.pending
    assert record.owner_worker_id is not None
    assert record.lease_expires_at is not None


@pytest.mark.anyio
async def test_reject_blocks_reentrant_same_thread_locally():
    """reject must also block when a local in-memory active run exists."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)
    await manager.create_or_reject("thread-1", multitask_strategy="reject")

    with pytest.raises(ConflictError, match="already has an active run"):
        await manager.create_or_reject("thread-1", multitask_strategy="reject")


# ---------------------------------------------------------------------------
# create_or_reject — interrupt strategy
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_interrupt_cancels_old_run_and_creates_new():
    """interrupt must cancel the previous active run and create a new one."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)
    old = await manager.create_or_reject("thread-1", multitask_strategy="reject")
    await manager.set_status(old.run_id, RunStatus.running)

    new = await manager.create_or_reject("thread-1", multitask_strategy="interrupt")

    assert new.run_id != old.run_id
    assert new.status == RunStatus.pending

    # Old run must be interrupted locally
    assert old.status == RunStatus.interrupted
    assert old.abort_event.is_set()

    # Old run must be marked interrupted in-store (persist_status after local cancel)
    old_after = await store.get(old.run_id)
    assert old_after["status"] == "interrupted"


@pytest.mark.anyio
async def test_interrupt_creates_new_when_old_completed():
    """interrupt must succeed when the previous run already reached a terminal status."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)
    old = await manager.create_or_reject("thread-1")
    await manager.set_status(old.run_id, RunStatus.success)

    new = await manager.create_or_reject("thread-1", multitask_strategy="interrupt")
    assert new.run_id != old.run_id
    assert new.status == RunStatus.pending


# ---------------------------------------------------------------------------
# create_or_reject — run ownership metadata
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_run_record_stores_owner_and_lease():
    """Newly created runs must carry owner_worker_id and lease_expires_at (when heartbeat is on)."""
    store = MemoryRunStore()
    manager = _make_manager(store=store, run_ownership_config=_lease_config(heartbeat_enabled=True))
    record = await manager.create_or_reject("thread-1")

    assert record.owner_worker_id == manager.worker_id
    assert isinstance(record.owner_worker_id, str) and len(record.owner_worker_id) > 0
    assert record.lease_expires_at is not None

    # Store row must also carry the fields
    stored = await store.get(record.run_id)
    assert stored is not None
    assert stored["owner_worker_id"] == manager.worker_id
    assert stored["lease_expires_at"] is not None


@pytest.mark.anyio
async def test_store_row_roundtrips_ownership_fields():
    """Records hydrated from the store must surface ownership fields."""
    store = MemoryRunStore()
    manager = _make_manager(store=store, run_ownership_config=_lease_config(heartbeat_enabled=True))
    record = await manager.create_or_reject("thread-1")

    hydrated = await manager.get(record.run_id)
    assert hydrated is not None
    assert hydrated.owner_worker_id == manager.worker_id
    assert hydrated.lease_expires_at is not None


# ---------------------------------------------------------------------------
# reconcile_orphaned_inflight_runs — lease-based
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_reconciliation_claims_expired_lease_runs():
    """A run with an expired lease must be reclaimed as orphaned."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)

    # Insert a run with an already-expired lease
    expired_lease = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()
    await store.put(
        "expired-run",
        thread_id="thread-1",
        status="running",
        owner_worker_id="worker-dead",
        lease_expires_at=expired_lease,
        created_at=(datetime.now(UTC) - timedelta(seconds=120)).isoformat(),
    )

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
    )

    assert len(recovered) == 1
    assert recovered[0].run_id == "expired-run"
    assert recovered[0].status == RunStatus.error

    stored = await store.get("expired-run")
    assert stored["status"] == "error"


@pytest.mark.anyio
async def test_reconciliation_skips_active_lease_runs():
    """A run with a still-valid lease must NOT be reclaimed."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)

    # Insert a run with a still-valid lease
    valid_lease = (datetime.now(UTC) + timedelta(seconds=60)).isoformat()
    await store.put(
        "live-run",
        thread_id="thread-1",
        status="running",
        owner_worker_id="worker-alive",
        lease_expires_at=valid_lease,
        created_at=(datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
    )

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
    )

    # Live run's lease is still valid — must not be reclaimed
    assert all(r.run_id != "live-run" for r in recovered)

    stored = await store.get("live-run")
    assert stored["status"] == "running"


@pytest.mark.anyio
async def test_reconciliation_claims_null_lease_runs():
    """Pre-ownership rows (NULL lease) must be reclaimed."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)

    await store.put(
        "legacy-run",
        thread_id="thread-1",
        status="running",
        created_at=(datetime.now(UTC) - timedelta(seconds=120)).isoformat(),
    )

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
    )

    assert len(recovered) == 1
    assert recovered[0].run_id == "legacy-run"


@pytest.mark.anyio
async def test_heartbeat_disabled_crashed_run_reclaimed_immediately():
    """Single-worker regression: when heartbeat is off, a crashed run must be
    reclaimed on the next restart without waiting for lease expiry.

    The run is created with lease_expires_at=NULL (no heartbeat => no lease),
    so reconciliation treats it as an orphan and reclaims it right away —
    preserving the pre-ownership recovery latency.
    """
    store = MemoryRunStore()
    # Worker A: heartbeat disabled (single-worker default)
    manager_a = _make_manager(store=store, run_ownership_config=_lease_config(heartbeat_enabled=False))
    record = await manager_a.create("thread-1")
    await manager_a.set_status(record.run_id, RunStatus.running)

    # Verify the run was stored WITHOUT a lease (heartbeat off)
    stored = await store.get(record.run_id)
    assert stored is not None
    assert stored["lease_expires_at"] is None

    # Simulate crash: drop manager_a's local state, build a fresh manager
    # (same store) as if Worker A restarted.
    manager_b = _make_manager(store=store, run_ownership_config=_lease_config(heartbeat_enabled=False))

    # Reconciliation must reclaim the run IMMEDIATELY — no lease to wait out.
    recovered = await manager_b.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
    )

    assert len(recovered) == 1
    assert recovered[0].run_id == record.run_id
    assert recovered[0].status == RunStatus.error


@pytest.mark.anyio
async def test_reconciliation_skips_locally_active_runs():
    """An active local run (owned by this worker) must NOT be reclaimed even with an expired lease."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)

    # Create a live local run
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)

    # Its lease hasn't expired yet, so this is mostly testing the local-ownership guard
    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
    )

    assert all(r.run_id != record.run_id for r in recovered)


@pytest.mark.anyio
async def test_reconciliation_returns_empty_when_no_orphaned_runs():
    """Reconciliation must return empty when there are no orphaned runs."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)

    recovered = await manager.reconcile_orphaned_inflight_runs(
        error="Gateway restarted before this run reached a durable final state.",
    )

    assert recovered == []


# ---------------------------------------------------------------------------
# Lease heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_heartbeat_renews_active_run_leases():
    """Heartbeat must extend the lease on active runs owned by this worker."""
    config = _lease_config(lease_seconds=30, heartbeat_enabled=True)
    store = MemoryRunStore()
    manager = _make_manager(store=store, run_ownership_config=config)

    record = await manager.create_or_reject("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)

    original_lease = record.lease_expires_at
    assert original_lease is not None

    # Start heartbeat and let it tick once
    await manager.start_heartbeat()
    await asyncio.sleep(0.2)  # heartbeat interval = 10s, too long; manually renew

    await manager._renew_leases()
    await manager.stop_heartbeat()

    assert record.lease_expires_at is not None
    # Lease should have been extended
    assert record.lease_expires_at >= original_lease


@pytest.mark.anyio
async def test_heartbeat_skips_runs_not_owned_by_this_worker():
    """Heartbeat must only renew leases for runs owned by this worker."""
    config = _lease_config(lease_seconds=30, heartbeat_enabled=True)
    store = MemoryRunStore()
    manager = _make_manager(store=store, run_ownership_config=config)

    # Create a run owned by a different worker
    old_lease = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    await store.put(
        "other-worker-run",
        thread_id="thread-1",
        status="running",
        owner_worker_id="other-worker",
        lease_expires_at=old_lease,
        created_at=(datetime.now(UTC) - timedelta(seconds=10)).isoformat(),
    )

    await manager._renew_leases()

    stored = await store.get("other-worker-run")
    # Lease should be unchanged (other worker's run)
    assert stored["lease_expires_at"] == old_lease


@pytest.mark.anyio
async def test_heartbeat_not_started_when_disabled():
    """When heartbeat_enabled is False, start_heartbeat must be a no-op."""
    config = _lease_config(heartbeat_enabled=False)
    store = MemoryRunStore()
    manager = _make_manager(store=store, run_ownership_config=config)

    assert manager.heartbeat_enabled is False
    await manager.start_heartbeat()
    assert manager._heartbeat_task is None
    assert manager._heartbeat_stop is None


# ---------------------------------------------------------------------------
# cancel with cross-worker lease awareness
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cancel_local_run_succeeds():
    """Cancel must succeed for a locally-owned active run."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.running)

    result = await manager.cancel(record.run_id)
    assert result is True
    assert record.status == RunStatus.interrupted


@pytest.mark.anyio
async def test_cancel_unknown_run_returns_false():
    """Cancel must return False for a run not known to this worker."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)

    result = await manager.cancel("nonexistent-run")
    assert result is False


@pytest.mark.anyio
async def test_cancel_idempotent():
    """Cancel must return True when the run is already interrupted."""
    store = MemoryRunStore()
    manager = _make_manager(store=store)
    record = await manager.create("thread-1")
    await manager.set_status(record.run_id, RunStatus.interrupted)

    result = await manager.cancel(record.run_id)
    assert result is True


# ---------------------------------------------------------------------------
# GATEWAY_WORKERS=1 backward compatibility
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_single_worker_default_config_behavior_unchanged():
    """With default config (heartbeat_enabled=False), behavior must match pre-ownership code."""
    config = _lease_config(heartbeat_enabled=False)
    store = MemoryRunStore()
    manager = _make_manager(store=store, run_ownership_config=config)

    # Create runs, cancel, create_or_reject — all must work
    r1 = await manager.create("thread-1")
    assert r1.owner_worker_id is not None

    r2 = await manager.create_or_reject("thread-2", multitask_strategy="reject")
    assert r2.owner_worker_id is not None

    await manager.cancel(r2.run_id)
    stored = await store.get(r2.run_id)
    assert stored["status"] == "interrupted"


@pytest.mark.anyio
async def test_manager_without_run_ownership_config():
    """Manager without run_ownership_config must still work (backward compat)."""
    store = MemoryRunStore()
    manager = RunManager(store=store)  # no run_ownership_config

    record = await manager.create_or_reject("thread-1")
    assert record is not None
    assert record.owner_worker_id is not None  # always set, even without config

    # Heartbeat must be a no-op without config
    assert manager.heartbeat_enabled is False
    await manager.start_heartbeat()
    assert manager._heartbeat_task is None


# ---------------------------------------------------------------------------
# worker_id uniqueness
# ---------------------------------------------------------------------------


def test_worker_id_is_generated():
    """worker_id must be a non-empty string containing hostname."""
    wid = _generate_worker_id()
    assert isinstance(wid, str)
    assert len(wid) > 0
    assert ":" in wid


def test_two_managers_have_different_default_ids():
    """Two managers without explicit worker_id must get unique ids."""
    m1 = RunManager()
    m2 = RunManager()
    assert m1.worker_id != m2.worker_id


# ---------------------------------------------------------------------------
# Store atomic methods
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_create_run_atomic_reject_prevents_duplicate():
    """store.create_run_atomic with reject must raise ConflictError on duplicate."""
    store = MemoryRunStore()
    config = _lease_config()

    store.create_run_atomic = AsyncMock(wraps=store.create_run_atomic)

    await store.create_run_atomic(
        run_id="run-1",
        thread_id="thread-1",
        owner_worker_id="w1",
        lease_expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        multitask_strategy="reject",
        grace_seconds=config.grace_seconds,
    )

    with pytest.raises(ConflictError, match="already has an active run"):
        await store.create_run_atomic(
            run_id="run-2",
            thread_id="thread-1",
            owner_worker_id="w2",
            lease_expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            multitask_strategy="reject",
            grace_seconds=config.grace_seconds,
        )


@pytest.mark.anyio
async def test_create_run_atomic_interrupt_claims_and_creates():
    """store.create_run_atomic with interrupt must claim old and create new."""
    store = MemoryRunStore()
    config = _lease_config()
    # Create an active run with an expired lease (simulating a crashed worker)
    expired_lease = (datetime.now(UTC) - timedelta(seconds=60)).isoformat()

    await store.create_run_atomic(
        run_id="run-old",
        thread_id="thread-1",
        owner_worker_id="w1",
        lease_expires_at=expired_lease,
        multitask_strategy="reject",
        grace_seconds=config.grace_seconds,
    )

    new_row, claimed = await store.create_run_atomic(
        run_id="run-new",
        thread_id="thread-1",
        owner_worker_id="w2",
        lease_expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        multitask_strategy="interrupt",
        grace_seconds=config.grace_seconds,
    )

    assert new_row["run_id"] == "run-new"
    assert new_row["status"] == "pending"
    assert len(claimed) == 1
    assert claimed[0]["run_id"] == "run-old"

    # Old run must be interrupted in-store
    old_row = await store.get("run-old")
    assert old_row["status"] == "interrupted"


@pytest.mark.anyio
async def test_create_run_atomic_interrupt_rejects_other_worker_valid_lease():
    """Interrupt must raise ConflictError when a valid-lease run is owned by another worker.

    The partial unique index ``uq_runs_thread_active`` would reject the INSERT
    anyway; surfacing ConflictError here gives the caller a clean signal
    instead of a futile retry loop on IntegrityError.
    """
    store = MemoryRunStore()
    config = _lease_config(grace_seconds=10)
    valid_lease = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()

    await store.create_run_atomic(
        run_id="valid-lease-run",
        thread_id="thread-1",
        owner_worker_id="other-worker",
        lease_expires_at=valid_lease,
        multitask_strategy="reject",
        grace_seconds=config.grace_seconds,
    )

    with pytest.raises(ConflictError, match="another worker"):
        await store.create_run_atomic(
            run_id="run-new",
            thread_id="thread-1",
            owner_worker_id="w2",
            lease_expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
            multitask_strategy="interrupt",
            grace_seconds=config.grace_seconds,
        )

    # The valid-lease run must be untouched (transaction rolled back).
    old_row = await store.get("valid-lease-run")
    assert old_row["status"] == "pending"
    assert old_row["owner_worker_id"] == "other-worker"


@pytest.mark.anyio
async def test_create_run_atomic_interrupt_allows_self_owned_valid_lease():
    """Interrupt must succeed when the existing valid-lease run is owned by this worker."""
    store = MemoryRunStore()
    config = _lease_config(grace_seconds=10)
    valid_lease = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()

    await store.create_run_atomic(
        run_id="self-run",
        thread_id="thread-1",
        owner_worker_id="w1",
        lease_expires_at=valid_lease,
        multitask_strategy="reject",
        grace_seconds=config.grace_seconds,
    )

    new_row, claimed = await store.create_run_atomic(
        run_id="run-new",
        thread_id="thread-1",
        owner_worker_id="w1",  # same worker
        lease_expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        multitask_strategy="interrupt",
        grace_seconds=config.grace_seconds,
    )

    assert new_row["run_id"] == "run-new"
    assert len(claimed) == 1
    assert claimed[0]["run_id"] == "self-run"
    assert claimed[0]["status"] == "interrupted"


# ---------------------------------------------------------------------------
# update_lease
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_lease_renews_row():
    """update_lease must update the lease_expires_at on the stored row."""
    store = MemoryRunStore()
    old_lease = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    await store.put(
        "run-1",
        thread_id="thread-1",
        status="running",
        owner_worker_id="w1",
        lease_expires_at=old_lease,
    )

    new_lease = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    updated = await store.update_lease(
        "run-1",
        owner_worker_id="w1",
        lease_expires_at=new_lease,
    )
    assert updated is True

    stored = await store.get("run-1")
    assert stored["lease_expires_at"] == new_lease


@pytest.mark.anyio
async def test_update_lease_returns_false_for_terminal_run():
    """update_lease must return False when the run is not pending/running."""
    store = MemoryRunStore()
    await store.put("run-1", thread_id="thread-1", status="success", owner_worker_id="w1")

    new_lease = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    updated = await store.update_lease(
        "run-1",
        owner_worker_id="w1",
        lease_expires_at=new_lease,
    )
    assert updated is False

    stored = await store.get("run-1")
    assert stored["status"] == "success"


# ---------------------------------------------------------------------------
# list_inflight_with_expired_lease
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_list_inflight_with_expired_lease_filters_correctly():
    """Only runs with expired or NULL leases must be returned."""
    store = MemoryRunStore()
    now = datetime.now(UTC)
    grace = 10

    # Expired lease
    expired = (now - timedelta(seconds=60)).isoformat()
    await store.put("expired-run", thread_id="t1", status="running", owner_worker_id="w1", lease_expires_at=expired, created_at=expired)

    # Valid lease
    valid = (now + timedelta(seconds=60)).isoformat()
    await store.put("valid-run", thread_id="t2", status="running", owner_worker_id="w2", lease_expires_at=valid, created_at=valid)

    # NULL lease (legacy)
    await store.put("null-lease-run", thread_id="t3", status="running", created_at=(now - timedelta(seconds=30)).isoformat())

    # Terminal status (should not appear)
    await store.put("success-run", thread_id="t4", status="success", created_at=(now - timedelta(seconds=60)).isoformat())

    results = await store.list_inflight_with_expired_lease(grace_seconds=grace)

    result_ids = {r["run_id"] for r in results}
    assert "expired-run" in result_ids
    assert "null-lease-run" in result_ids
    assert "valid-run" not in result_ids
    assert "success-run" not in result_ids
