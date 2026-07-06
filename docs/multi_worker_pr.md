# PR — Multi-worker P0: cross-process run atomicity, lease, takeover

Issue: bytedance/deer-flow#3948 (work items 2/3/4)
Follows: #3960 (work item 1, refuse multi-worker startup on non-Postgres)

## Why

PR #3960 stopped SQLite from silently corrupting under `GATEWAY_WORKERS>1`,
but the four P0 breakers in `docs/multi_worker.md` are still open:

1. `create_or_reject` only holds an in-process `asyncio.Lock`. Two workers
   that simultaneously receive a request for the same thread both observe
   "no inflight run", both INSERT, and the checkpoint writes overwrite each
   other. **Not recoverable.**
2. `reconcile_orphaned_inflight_runs` is gated on `backend == "sqlite"` in
   `app/gateway/deps.py:252`. Postgres — i.e. every multi-worker deploy —
   never runs it. Pod crash / OOM / rolling update leaves the run row stuck
   in `pending`/`running` forever; the UI spins indefinitely.
3. `cancel()` returns 409 whenever the run is not in this worker's memory.
   With no sticky routing, the cancel button fails on roughly every
   non-owner pod.

Work item 1 made these safe to *attempt* by guaranteeing Postgres; this PR
makes them actually correct by:

- Adding a partial unique index `uq_runs_thread_active` that the database
  enforces "one pending/running row per thread" via INSERT-time constraint.
- Stamping each active row with `owner_worker_id` + `lease_expires_at`,
  renewed by a per-worker heartbeat task. Reconciliation now keys on the
  lease, not process liveness, so it is safe to run on Postgres.
- De-opinionating the deps.py `sqlite-only` reconciliation gate so Postgres
  deployments also recover crashed runs.
- Letting cancel take over an expired-lease run directly (mark `error` so
  the partial index releases the thread) and answering a live-lease
  request with `409 + Retry-After` instead of an unconditional 409.

The `multitask_strategy` parameter (`reject` / `interrupt` / `rollback`)
already proves the codebase treats concurrent run requests as real — this
PR makes the parameter actually hold its contract across processes.

## What changes

### Schema (`packages/harness/deerflow/persistence/`)

- New revision `0004_run_ownership` adds:
  - `runs.owner_worker_id VARCHAR(128) NULL`
  - `runs.lease_expires_at TIMESTAMPTZ NULL`
  - `idx_runs_lease (lease_expires_at)` for the reconciliation scan.
  - Partial unique index `uq_runs_thread_active ON runs(thread_id) WHERE
    status IN ('pending', 'running')` — the single source of truth for
    "one active run per thread". Uses the `sqlite_where` / `postgresql_where`
    pattern from `0001_baseline.py` (channel connections).
- `RunRow` model updated with both columns and the partial unique index so
  fresh DBs that go through `create_all` are byte-identical to migrated
  ones. Reconciliation treats `lease_expires_at IS NULL` as "always stale"
  so single-worker deployments that flip `heartbeat_enabled` on later do
  not strand pre-existing rows.

### Lease primitives (`runtime/runs/store/base.py`, `persistence/run/sql.py`)

- `RunStore.put` now accepts `owner_worker_id` / `lease_expires_at`
  (default `None`; legacy callers unchanged).
- New optional interface methods on `RunStore`:
  - `insert_active_run_atomic` — INSERT relying on the partial unique index
    to raise `ActiveRunConflict`.
  - `claim_inflight_for_thread` — `SELECT … FOR UPDATE` plus a computed
    `lease_live` flag for each row.
  - `renew_lease` — owner-scoped UPDATE used by the heartbeat.
  - `takeover_expired_active_run` — `UPDATE … SET status=terminal` only
    when the lease is past the caller-supplied cutoff.
- `supports_lease_takeover` defaults to `False`. `MemoryRunStore` keeps the
  default; `RunRepository` returns `True`.
- New `ActiveRunConflict` exception carries the `thread_id` so the caller
  does not have to re-derive it from the request.

### RunManager (`runtime/runs/manager.py`)

- Constructor accepts `worker_id: str | None` and
  `ownership_config: RunOwnershipConfig | None`. Both stay `None` in
  single-worker deployments, so the legacy code path is selected by the
  `_multi_worker_enabled()` predicate (heartbeat on + worker_id set +
  store supports takeover).
- `RunRecord` carries the new `owner_worker_id` / `lease_expires_at` fields;
  `_record_from_store` and `_store_put_payload` round-trip them.
- `create_or_reject` splits into two paths:
  - **Legacy (single-worker)**: in-process `asyncio.Lock` + `_persist_new_run_to_store`
    exactly as today. Zero behavior change for `GATEWAY_WORKERS=1`.
  - **Lease-aware (multi-worker)**:
    1. For `interrupt` / `rollback`, `claim_inflight_for_thread` returns the
       active rows. Own-lease rows are added to the in-process cancel list;
       foreign live-lease rows raise `ConflictError`; foreign dead-lease
       rows are marked `error` via `takeover_expired_active_run`.
    2. `insert_active_run_atomic` INSERTs the new row. The partial unique
       index is the only arbiter now — a peer INSERT that won the race
       surfaces as `ActiveRunConflict` → `ConflictError`.
    3. Only after the INSERT commits do we register the in-memory
       `RunRecord` and fire the in-process cancel signals. A failed INSERT
       never produces a half-cancelled peer run or a phantom `RunRecord`.
- `cancel()` returns a new `CancelOutcome` dataclass instead of `bool`:
  - `initiated` keeps the legacy truthiness (via `__bool__`) so the two
    non-router callers (`sse_consumer`, `wait_for_run_completion`) are
    unchanged.
  - `owner_live_elsewhere=True` + `retry_after_seconds` lets the router
    emit `409 + Retry-After`.
  - When the lease has expired, this worker calls
    `takeover_expired_active_run` directly. The router then returns `202`
    and the caller can immediately retry the create / cancel sequence.
- `reconcile_orphaned_inflight_runs` now:
  - Always runs (the sqlite-only gate in `deps.py` is gone) because the
    lease check inside is the safety net for Postgres: live foreign leases
    are skipped, NULL leases are recovered (legacy data), expired leases
    are recovered (crashed owner).
  - Treats self-owned live leases as orphans because no in-memory task
    exists for them after a restart.
- New `start_heartbeat()` / `stop_heartbeat()` methods back the per-worker
  renewer. Interval is `lease_seconds / 3` so a single missed tick still
  leaves ~⅔ of the lease window before another worker can take over.

### Gateway (`app/gateway/`)

- `deps.py`:
  - Generates a per-process `worker_id` (`hostname:uuid8hex`, 128-char cap)
    and passes it plus `config.run_ownership` to `RunManager`.
  - Removes the `if backend == "sqlite":` gate around
    `reconcile_orphaned_inflight_runs`. The lease check inside makes it
    safe on Postgres and a no-op on a clean shutdown.
  - Calls `start_heartbeat()` after reconciliation (so only runs this
    worker actually owns get renewed) and `stop_heartbeat()` is the first
    teardown step (before the in-flight run drain, so a heartbeat tick
    cannot renew a lease for a run whose task is being cancelled).
- `routers/thread_runs.py`:
  - `cancel_run` and `stream_existing_run` read the new `CancelOutcome`
    and emit `409` + `Retry-After` when `owner_live_elsewhere=True`. The
    takeover path still returns `202` (the run is now in a terminal state
    and the caller can retry the create sequence immediately).

### Config

- New `RunOwnershipConfig` (`config/run_ownership_config.py`):
  ```yaml
  run_ownership:
    lease_seconds: 30
    grace_seconds: 10
    heartbeat_enabled: false  # GATEWAY_WORKERS=1 stays on false
  ```
- Registered as restart-required in `config/reload_boundary.py` because
  the worker id and heartbeat task are bound at `langgraph_runtime`
  startup; downstream code reads the snapshot off `RunManager`, not the
  live `AppConfig`.
- Field description on `AppConfig.run_ownership` carries the standard
  `startup-only:` prefix so the boundary surfaces in IDE hover.

## How a single-worker deploy stays unchanged

- `heartbeat_enabled=false` (the default) keeps `_multi_worker_enabled()`
  returning `False`. `create_or_reject` runs the original asyncio.Lock
  path. `cancel()` runs the original in-memory branch and never reaches
  `_cancel_via_lease_takeover`.
- The reconciliation step was sqlite-only before; it now runs on every
  backend, but the legacy branch (no `lease_expires_at` on the row, no
  `owner_worker_id`) recovers exactly the rows the sqlite branch used to.
- Tests for `GATEWAY_WORKERS=1` (`tests/test_compose_default_workers.py`,
  the existing `RunManager` suite) should pass without modification.

## Tests (planned, follow-up commit)

- 100× concurrent `create_or_reject(reject)` ⇒ exactly one success, the
  rest get `ConflictError`.
- `interrupt` with one expired-lease foreign run ⇒ new run created, old
  one transitions to `error`.
- `interrupt` with one live-lease foreign run ⇒ `ConflictError`.
- Reconciliation skips a live-lease foreign run and recovers an
  expired-lease one within `lease_seconds + grace_seconds`.
- `cancel` on non-owner pod:
  - lease live ⇒ `409` + `Retry-After`.
  - lease expired ⇒ run marked `error`, response `202`.
- `GATEWAY_WORKERS=1` + `heartbeat_enabled=false` ⇒ all suites above
  behave as before (no partial index trip, no lease column read).
- `GATEWAY_WORKERS=2` + SQLite ⇒ startup fails with exit code 1 (covered
  by #3960).

## Rollout

| Stage | Content | Workers |
|---|---|---|
| Stage 0 | #3960 landed | 1 |
| Stage 1 | This PR lands; `heartbeat_enabled=true` opt-in | 2 |
| Stage 2 | 7-day watch + alert tuning | 2 |
| Stage 3 | Open production `GATEWAY_WORKERS=4` | 4 |

Rollback: `GATEWAY_WORKERS=1` (heartbeat auto-disables via
`_multi_worker_enabled()`) — no code revert needed.

## Out of scope (deferred to follow-up feats)

- nginx sticky routing + frontend `X-Thread-ID` header.
- `worker_id` injection into logs and `X-Worker-ID` response header.
- IM Channel leader election.
- Subagent global semaphore.
- Memory cache pub/sub.
- HTTP internal endpoint for cross-process cancel forwarding (the lease
  takeover path covers sticky-miss cases without adding an RPC failure
  mode).

---

## Commit message

```
feat(runtime): cross-process run atomicity via lease + partial unique index (#3961)

Why: issue #3948 work items 2/3/4. PR #3960 made multi-worker safe to
attempt by enforcing Postgres; this PR makes it actually correct.

The four P0 breakers — TOCTOU in create_or_reject, sqlite-only
reconciliation, non-owner cancel 409, checkpoint overwrites — all
reduce to "the in-process asyncio.Lock is the only arbiter of who
owns a thread's active run". Adds a partial unique index
uq_runs_thread_active so the database becomes the arbiter, stamps
each row with owner_worker_id + lease_expires_at, and lets a
per-worker heartbeat task keep the lease alive. Reconciliation now
keys on the lease so it is safe on Postgres (the sqlite-only gate
in deps.py is gone), and cancel either takes over an expired lease
directly or returns 409 + Retry-After for a live one.

Single-worker deployments are unchanged: heartbeat_enabled defaults
to false, _multi_worker_enabled() falls back to the legacy code
path, and the RunRow changes are additive (NULL columns + a partial
index that never trips because there is only one writer).

What:
- 0004_run_ownership: runs.owner_worker_id, runs.lease_expires_at,
  idx_runs_lease, uq_runs_thread_active (sqlite_where +
  postgresql_where partial unique).
- RunStore: optional insert_active_run_atomic /
  claim_inflight_for_thread / renew_lease /
  takeover_expired_active_run; supports_lease_takeover property
  gates the new path. MemoryRunStore stays on defaults.
- RunManager: worker_id + RunOwnershipConfig at construction;
  create_or_reject branches between the legacy asyncio.Lock path
  and the lease-aware path; cancel returns a CancelOutcome that
  carries owner_live_elsewhere + retry_after_seconds; reconcile
  skips live foreign leases; start_heartbeat / stop_heartbeat
  drive the renewer.
- Gateway: deps.py generates worker_id, drops the sqlite-only
  reconciliation gate, starts/stops the heartbeat around the run
  drain; cancel_run + stream_existing_run emit 409 + Retry-After
  on a live foreign lease and let an expired-lease takeover
  succeed with 202.
- Config: RunOwnershipConfig (lease_seconds / grace_seconds /
  heartbeat_enabled) registered as startup-only.
```
