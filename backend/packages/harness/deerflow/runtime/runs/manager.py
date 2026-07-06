"""In-memory run registry with optional persistent RunStore backing."""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from deerflow.config.run_ownership_config import RunOwnershipConfig
from deerflow.utils.time import now_iso as _now_iso

from .schemas import DisconnectMode, RunStatus

if TYPE_CHECKING:
    from deerflow.runtime.runs.store.base import RunStore

logger = logging.getLogger(__name__)

_RETRYABLE_SQLITE_MESSAGES = (
    "database is locked",
    "database table is locked",
    "database is busy",
)

_RETRYABLE_SQLITE_ERROR_CODES = {
    sqlite3.SQLITE_BUSY,
    sqlite3.SQLITE_LOCKED,
}


def _coerce_lease(raw: Any) -> datetime | None:
    """Normalise a stored ``lease_expires_at`` value into a UTC ``datetime``.

    SQL stores return a timezone-aware ``datetime`` on Postgres and a naive
    one on SQLite; legacy rows and JSON-formatted fixtures carry an ISO
    string. Anything we cannot parse returns ``None`` so the caller treats
    the row as "no lease yet".
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return None


def _is_retryable_persistence_error(exc: BaseException) -> bool:
    """Return True for transient SQLite persistence failures.

    SQLite lock contention normally surfaces through either sqlite3 exceptions
    or SQLAlchemy wrappers.  The short bounded retry here protects run status
    finalization from transient writer pressure without hiding permanent
    failures forever.
    """

    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))

        message = str(current).lower()
        if any(fragment in message for fragment in _RETRYABLE_SQLITE_MESSAGES):
            return True
        if isinstance(current, (sqlite3.OperationalError, sqlite3.DatabaseError)):
            error_code = getattr(current, "sqlite_errorcode", None)
            if error_code in _RETRYABLE_SQLITE_ERROR_CODES:
                return True
        for chained in (getattr(current, "orig", None), current.__cause__, current.__context__):
            if isinstance(chained, BaseException):
                pending.append(chained)
    return False


@dataclass(frozen=True)
class PersistenceRetryPolicy:
    """Bounded retry policy for short run-store writes."""

    max_attempts: int = 5
    initial_delay: float = 0.05
    max_delay: float = 1.0
    backoff_factor: float = 2.0


@dataclass
class RunRecord:
    """Mutable record for a single run."""

    run_id: str
    thread_id: str
    assistant_id: str | None
    status: RunStatus
    on_disconnect: DisconnectMode
    multitask_strategy: str = "reject"
    metadata: dict = field(default_factory=dict)
    kwargs: dict = field(default_factory=dict)
    user_id: str | None = None
    created_at: str = ""
    updated_at: str = ""
    task: asyncio.Task | None = field(default=None, repr=False)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    abort_action: str = "interrupt"
    error: str | None = None
    model_name: str | None = None
    store_only: bool = False
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    llm_call_count: int = 0
    lead_agent_tokens: int = 0
    subagent_tokens: int = 0
    middleware_tokens: int = 0
    # Per-model token breakdown
    token_usage_by_model: dict[str, dict[str, int]] = field(default_factory=dict)
    message_count: int = 0
    last_ai_message: str | None = None
    first_human_message: str | None = None
    finalizing: bool = False
    # Multi-worker run ownership (issue: multi-worker P0). NULL on rows that
    # pre-date this column or on single-worker deployments that never enable
    # the heartbeat. ``store_only`` records hydrate these so cancel / takeover
    # decisions can compare against the local worker id.
    owner_worker_id: str | None = None
    lease_expires_at: str | None = None


@dataclass(frozen=True)
class CancelOutcome:
    """Structured result of :meth:`RunManager.cancel`.

    ``initiated`` is the boolean that legacy callers (sse_consumer /
    wait_for_run_completion) care about — cancellation fired, or it did not.
    The router reads ``owner_live_elsewhere`` to distinguish "run is alive on
    another worker" (409 + Retry-After) from the plain unknown / terminal
    miss (409 without Retry-After). ``retry_after_seconds`` is non-empty only
    when ``owner_live_elsewhere`` is ``True``.
    """

    initiated: bool
    owner_live_elsewhere: bool = False
    retry_after_seconds: float | None = None
    reason: str = ""

    def __bool__(self) -> bool:
        """Legacy truthiness maps to ``initiated``.

        Lets existing call sites that read ``cancelled`` as a boolean keep
        working unchanged; new callers should prefer the explicit field.
        """
        return self.initiated


class RunManager:
    """In-memory run registry with optional persistent RunStore backing.

    All mutations are protected by an asyncio lock. When a ``store`` is
    provided, serializable metadata is also persisted to the store so
    that run history survives process restarts.
    """

    def __init__(
        self,
        store: RunStore | None = None,
        *,
        persistence_retry_policy: PersistenceRetryPolicy | None = None,
        worker_id: str | None = None,
        ownership_config: RunOwnershipConfig | None = None,
    ) -> None:
        self._runs: dict[str, RunRecord] = {}
        # Secondary index: thread_id -> insertion-ordered run_id set (a dict is
        # used as an ordered set), maintained in lockstep with ``_runs`` so
        # per-thread queries avoid O(total in-memory runs) full scans while
        # preserving ``_runs`` iteration order (see ``_thread_records_locked``).
        self._runs_by_thread: dict[str, dict[str, None]] = {}
        self._lock = asyncio.Lock()
        self._store = store
        self._persistence_retry_policy = persistence_retry_policy or PersistenceRetryPolicy()
        # Multi-worker ownership. ``worker_id`` identifies this process;
        # ``ownership_config`` is the snapshot captured at Gateway startup
        # (``heartbeat_enabled=False`` keeps the legacy single-worker code path).
        # ``_heartbeat_task`` is the background renewer started by
        # :meth:`start_heartbeat` from ``langgraph_runtime`` once the store is
        # wired and ``heartbeat_enabled`` is on.
        self._worker_id = worker_id
        self._ownership_config = ownership_config
        self._heartbeat_task: asyncio.Task | None = None
        self._heartbeat_stop = asyncio.Event()

    def _index_run_locked(self, record: RunRecord) -> None:
        """Register *record* in the thread index. Caller must hold ``self._lock``."""
        self._runs_by_thread.setdefault(record.thread_id, {})[record.run_id] = None

    @property
    def worker_id(self) -> str | None:
        """Stable identifier of this worker process (``hostname:uuid8`` form)."""
        return self._worker_id

    def _multi_worker_enabled(self) -> bool:
        """Return ``True`` when this manager should use the lease-aware path.

        The legacy single-worker path is preserved unless *all three* hold:
        the operator opted into ``run_ownership.heartbeat_enabled``, the
        manager was constructed with a ``worker_id`` (so it can stamp rows),
        and the backing store implements the lease primitives (SQL store).
        """
        return (
            self._ownership_config is not None
            and bool(self._ownership_config.heartbeat_enabled)
            and self._worker_id is not None
            and self._store is not None
            and getattr(self._store, "supports_lease_takeover", False)
        )

    def _fresh_lease_expires_at(self, now: datetime | None = None) -> datetime:
        """Return the next lease expiry this worker should stamp on a row."""
        assert self._ownership_config is not None  # caller guards via _multi_worker_enabled
        return (now or datetime.now(UTC)) + timedelta(seconds=self._ownership_config.lease_seconds)

    def _unindex_run_locked(self, run_id: str, thread_id: str) -> None:
        """Drop *run_id* from the thread index. Caller must hold ``self._lock``."""
        bucket = self._runs_by_thread.get(thread_id)
        if bucket is not None:
            bucket.pop(run_id, None)
            if not bucket:
                self._runs_by_thread.pop(thread_id, None)

    def _thread_records_locked(self, thread_id: str) -> list[RunRecord]:
        """Return live in-memory records for *thread_id*. Caller must hold ``self._lock``.

        Uses the ``_runs_by_thread`` index for O(runs-in-thread) lookup instead of
        scanning every in-memory run. Correctness rests on the index and ``_runs``
        being mutated in lockstep under ``self._lock`` (no ``await`` between the two
        writes), so any holder of the lock sees them agree. The ``self._runs.get``
        filter is defense-in-depth, not reconciliation: it drops a stale id still in
        the index but already gone from ``_runs``, yet it cannot recover a run that is
        in ``_runs`` but missing from the index (such a run would be silently
        omitted). It guards only that one direction, should a future refactor ever
        break the lockstep invariant.
        """
        run_ids = self._runs_by_thread.get(thread_id)
        if not run_ids:
            return []
        return [record for run_id in run_ids if (record := self._runs.get(run_id)) is not None]

    @staticmethod
    def _store_put_payload(record: RunRecord, *, error: str | None = None) -> dict[str, Any]:
        payload = {
            "thread_id": record.thread_id,
            "assistant_id": record.assistant_id,
            "status": record.status.value,
            "multitask_strategy": record.multitask_strategy,
            "metadata": record.metadata or {},
            "kwargs": record.kwargs or {},
            "error": error if error is not None else record.error,
            "created_at": record.created_at,
            "model_name": record.model_name,
            "owner_worker_id": record.owner_worker_id,
        }
        if record.lease_expires_at is not None:
            # ``put`` accepts either an ISO string (legacy ``RunManager.create``
            # path) or a ``datetime``; coerce here so callers do not have to.
            try:
                payload["lease_expires_at"] = datetime.fromisoformat(record.lease_expires_at)
            except ValueError:
                payload["lease_expires_at"] = None
        else:
            payload["lease_expires_at"] = None
        if record.user_id is not None:
            payload["user_id"] = record.user_id
        return payload

    async def _call_store_with_retry(
        self,
        operation_name: str,
        run_id: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Run a short store operation with bounded retries for SQLite pressure."""
        policy = self._persistence_retry_policy
        attempt = 1
        delay = policy.initial_delay
        while True:
            try:
                return await operation()
            except Exception as exc:
                retryable = _is_retryable_persistence_error(exc)
                if attempt >= policy.max_attempts or not retryable:
                    raise
                logger.warning(
                    "Transient persistence failure during %s for run %s (attempt %d/%d); retrying",
                    operation_name,
                    run_id,
                    attempt,
                    policy.max_attempts,
                    exc_info=True,
                )
                if delay > 0:
                    await asyncio.sleep(delay)
                delay = min(policy.max_delay, delay * policy.backoff_factor if delay else policy.initial_delay)
                attempt += 1

    async def _persist_snapshot_to_store(self, run_id: str, payload: dict[str, Any]) -> bool:
        """Best-effort persist a previously captured run snapshot."""
        if self._store is None:
            return True
        try:
            await self._call_store_with_retry(
                "put",
                run_id,
                lambda: self._store.put(run_id, **payload),
            )
            return True
        except Exception:
            logger.warning("Failed to persist run %s to store", run_id, exc_info=True)
            return False

    async def _persist_new_run_to_store(self, record: RunRecord) -> None:
        """Persist a newly created run record to the backing store.

        Initial run creation is part of the run visibility boundary: callers
        should not observe a run in memory unless its backing store row exists.
        Unlike follow-up status/model updates, failures are propagated so the
        caller can treat creation as failed. Rollback is the caller's
        responsibility after inserting the record into ``_runs``.
        """
        if self._store is None:
            return
        await self._call_store_with_retry(
            "put",
            record.run_id,
            lambda: self._store.put(record.run_id, **self._store_put_payload(record)),
        )

    async def _persist_to_store(self, record: RunRecord, *, error: str | None = None) -> bool:
        """Best-effort persist run record to backing store."""
        return await self._persist_snapshot_to_store(
            record.run_id,
            self._store_put_payload(record, error=error),
        )

    async def _persist_status(self, record: RunRecord, status: RunStatus, *, error: str | None = None) -> bool:
        """Best-effort persist a status transition to the backing store."""
        if self._store is None:
            return True
        row_recovery_payload = self._store_put_payload(record, error=error)
        try:
            updated = await self._call_store_with_retry(
                "update_status",
                record.run_id,
                lambda: self._store.update_status(record.run_id, status.value, error=error),
            )
            if updated is False:
                return await self._persist_snapshot_to_store(record.run_id, row_recovery_payload)
            return True
        except Exception:
            logger.warning("Failed to persist status update for run %s", record.run_id, exc_info=True)
            return False

    @staticmethod
    def _record_from_store(row: dict[str, Any]) -> RunRecord:
        """Build a read-only runtime record from a serialized store row.

        NULL status/on_disconnect columns (e.g. from rows written before those
        columns were added) default to ``pending`` and ``cancel`` respectively.
        """
        return RunRecord(
            run_id=row["run_id"],
            thread_id=row["thread_id"],
            assistant_id=row.get("assistant_id"),
            status=RunStatus(row.get("status") or RunStatus.pending.value),
            on_disconnect=DisconnectMode(row.get("on_disconnect") or DisconnectMode.cancel.value),
            multitask_strategy=row.get("multitask_strategy") or "reject",
            metadata=row.get("metadata") or {},
            kwargs=row.get("kwargs") or {},
            created_at=row.get("created_at") or "",
            updated_at=row.get("updated_at") or "",
            user_id=row.get("user_id"),
            error=row.get("error"),
            model_name=row.get("model_name"),
            store_only=True,
            total_input_tokens=row.get("total_input_tokens") or 0,
            total_output_tokens=row.get("total_output_tokens") or 0,
            total_tokens=row.get("total_tokens") or 0,
            llm_call_count=row.get("llm_call_count") or 0,
            lead_agent_tokens=row.get("lead_agent_tokens") or 0,
            subagent_tokens=row.get("subagent_tokens") or 0,
            middleware_tokens=row.get("middleware_tokens") or 0,
            token_usage_by_model=row.get("token_usage_by_model") or {},
            message_count=row.get("message_count") or 0,
            last_ai_message=row.get("last_ai_message"),
            first_human_message=row.get("first_human_message"),
            owner_worker_id=row.get("owner_worker_id"),
            lease_expires_at=row.get("lease_expires_at"),
        )

    async def update_run_completion(self, run_id: str, **kwargs) -> None:
        """Persist token usage and completion data to the backing store."""
        row_recovery_payload: dict[str, Any] | None = None
        async with self._lock:
            record = self._runs.get(run_id)
            if record is not None:
                for key, value in kwargs.items():
                    if key == "status":
                        continue
                    if hasattr(record, key) and value is not None:
                        setattr(record, key, value)
                record.updated_at = _now_iso()
                row_recovery_payload = self._store_put_payload(record, error=kwargs.get("error"))
        if self._store is None:
            return
        try:
            updated = await self._call_store_with_retry(
                "update_run_completion",
                run_id,
                lambda: self._store.update_run_completion(run_id, **kwargs),
            )
            if updated is False:
                if row_recovery_payload is None:
                    logger.warning("Failed to recreate missing run %s for completion persistence", run_id)
                    return
                if not await self._persist_snapshot_to_store(run_id, row_recovery_payload):
                    return
                recovered = await self._call_store_with_retry(
                    "update_run_completion",
                    run_id,
                    lambda: self._store.update_run_completion(run_id, **kwargs),
                )
                if recovered is False:
                    logger.warning("Run completion update for %s affected no rows after row recreation", run_id)
        except Exception:
            logger.warning("Failed to persist run completion for %s", run_id, exc_info=True)

    async def update_run_progress(self, run_id: str, **kwargs) -> None:
        """Persist a running token/message snapshot without changing status."""
        should_persist = True
        async with self._lock:
            record = self._runs.get(run_id)
            if record is not None:
                should_persist = record.status == RunStatus.running
            if record is not None and should_persist:
                for key, value in kwargs.items():
                    if hasattr(record, key) and value is not None:
                        setattr(record, key, value)
                record.updated_at = _now_iso()
        if should_persist and self._store is not None:
            try:
                await self._store.update_run_progress(run_id, **kwargs)
            except Exception:
                logger.warning("Failed to persist run progress for %s", run_id, exc_info=True)

    async def create(
        self,
        thread_id: str,
        assistant_id: str | None = None,
        *,
        on_disconnect: DisconnectMode = DisconnectMode.cancel,
        metadata: dict | None = None,
        kwargs: dict | None = None,
        multitask_strategy: str = "reject",
        user_id: str | None = None,
    ) -> RunRecord:
        """Create a new pending run and register it."""
        run_id = str(uuid.uuid4())
        now = _now_iso()
        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id=assistant_id,
            status=RunStatus.pending,
            on_disconnect=on_disconnect,
            multitask_strategy=multitask_strategy,
            metadata=metadata or {},
            kwargs=kwargs or {},
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self._runs[run_id] = record
            self._index_run_locked(record)
            persisted = False
            try:
                await self._persist_new_run_to_store(record)
                persisted = True
            except Exception:
                logger.warning("Failed to persist run %s; rolled back in-memory record", run_id, exc_info=True)
                raise
            finally:
                # Also covers cancellation, which bypasses ``except Exception``.
                if not persisted:
                    self._runs.pop(run_id, None)
                    self._unindex_run_locked(run_id, record.thread_id)
        logger.info("Run created: run_id=%s thread_id=%s", run_id, thread_id)
        return record

    async def get(self, run_id: str, *, user_id: str | None = None) -> RunRecord | None:
        """Return a run record by ID, or ``None``.

        Args:
            run_id: The run ID to look up.
            user_id: Optional user ID for permission filtering when hydrating from store.
        """
        async with self._lock:
            record = self._runs.get(run_id)
        if record is not None:
            return record
        if self._store is None:
            return None
        try:
            row = await self._store.get(run_id, user_id=user_id)
        except Exception:
            logger.warning("Failed to hydrate run %s from store", run_id, exc_info=True)
            return None
        # Re-check after store await: a concurrent create() may have inserted the
        # in-memory record while the store call was in flight.
        async with self._lock:
            record = self._runs.get(run_id)
        if record is not None:
            return record
        if row is None:
            return None
        try:
            return self._record_from_store(row)
        except Exception:
            logger.warning("Failed to map store row for run %s", run_id, exc_info=True)
            return None

    async def aget(self, run_id: str, *, user_id: str | None = None) -> RunRecord | None:
        """Return a run record by ID, checking the persistent store as fallback.

        Alias for :meth:`get` for backward compatibility.
        """
        return await self.get(run_id, user_id=user_id)

    async def list_by_thread(self, thread_id: str, *, user_id: str | None = None, limit: int = 100) -> list[RunRecord]:
        """Return runs for a given thread, newest first, at most ``limit`` records.

        In-memory runs take precedence only when the same ``run_id`` exists in both
        memory and the backing store. The merged result is then sorted newest-first
        by ``created_at`` and trimmed to ``limit`` (default 100).

        Args:
            thread_id: The thread ID to filter by.
            user_id: Optional user ID for permission filtering when hydrating from store.
            limit: Maximum number of runs to return.
        """
        async with self._lock:
            memory_records = self._thread_records_locked(thread_id)
        if self._store is None:
            return sorted(memory_records, key=lambda r: r.created_at, reverse=True)[:limit]
        records_by_id = {record.run_id: record for record in memory_records}
        store_limit = max(0, limit - len(memory_records))
        try:
            rows = await self._store.list_by_thread(thread_id, user_id=user_id, limit=store_limit)
        except Exception:
            logger.warning("Failed to hydrate runs for thread %s from store", thread_id, exc_info=True)
            return sorted(memory_records, key=lambda r: r.created_at, reverse=True)[:limit]
        for row in rows:
            run_id = row.get("run_id")
            if run_id and run_id not in records_by_id:
                try:
                    records_by_id[run_id] = self._record_from_store(row)
                except Exception:
                    logger.warning("Failed to map store row for run %s", run_id, exc_info=True)
        return sorted(records_by_id.values(), key=lambda record: record.created_at, reverse=True)[:limit]

    async def set_status(self, run_id: str, status: RunStatus, *, error: str | None = None) -> None:
        """Transition a run to a new status."""
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                logger.warning("set_status called for unknown run %s", run_id)
                return
            record.status = status
            record.updated_at = _now_iso()
            if error is not None:
                record.error = error
        await self._persist_status(record, status, error=error)
        logger.info("Run %s -> %s", run_id, status.value)

    async def set_finalizing(self, run_id: str, finalizing: bool) -> None:
        """Mark whether a run is performing post-cancel cleanup."""
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                logger.warning("set_finalizing called for unknown run %s", run_id)
                return
            record.finalizing = finalizing
            record.updated_at = _now_iso()

    async def wait_for_prior_finalizing(
        self,
        thread_id: str,
        run_id: str,
        *,
        poll_interval: float = 0.01,
    ) -> None:
        """Wait until older same-thread runs have finished post-cancel cleanup."""
        while True:
            async with self._lock:
                found_current = False
                prior_finalizing = False
                for record in self._thread_records_locked(thread_id):
                    if record.run_id == run_id:
                        found_current = True
                        break
                    if record.finalizing:
                        prior_finalizing = True

                if not found_current or not prior_finalizing:
                    return

            await asyncio.sleep(poll_interval)

    async def has_later_run(self, thread_id: str, run_id: str) -> bool:
        """Return whether a newer in-memory run has been admitted for the thread."""
        async with self._lock:
            seen_current = False
            for record in self._thread_records_locked(thread_id):
                if record.run_id == run_id:
                    seen_current = True
                    continue
                if seen_current:
                    return True
        return False

    async def has_later_started_run(self, thread_id: str, run_id: str) -> bool:
        """Return whether a newer same-thread run may have already advanced state."""
        async with self._lock:
            seen_current = False
            for record in self._thread_records_locked(thread_id):
                if record.run_id == run_id:
                    seen_current = True
                    continue
                if seen_current and (record.status != RunStatus.pending or record.finalizing):
                    return True
        return False

    async def _persist_model_name(self, run_id: str, model_name: str | None) -> None:
        """Best-effort persist model_name update to the backing store."""
        if self._store is None:
            return
        try:
            await self._call_store_with_retry(
                "update_model_name",
                run_id,
                lambda: self._store.update_model_name(run_id, model_name),
            )
        except Exception:
            logger.warning("Failed to persist model_name update for run %s", run_id, exc_info=True)

    async def update_model_name(self, run_id: str, model_name: str | None) -> None:
        """Update the model name for a run."""
        async with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                logger.warning("update_model_name called for unknown run %s", run_id)
                return
            record.model_name = model_name
            record.updated_at = _now_iso()
        await self._persist_model_name(run_id, model_name)
        logger.info("Run %s model_name=%s", run_id, model_name)

    async def cancel(self, run_id: str, *, action: str = "interrupt") -> CancelOutcome:
        """Request cancellation of a run.

        Args:
            run_id: The run ID to cancel.
            action: "interrupt" keeps checkpoint, "rollback" reverts to pre-run state.

        Sets the abort event with the action reason and cancels the asyncio task
        for runs owned by this worker. When the run is owned by another worker
        (multi-worker path), inspects the lease instead:

        - lease past ``grace_seconds`` ⇒ take over: mark the row ``error`` so
          the partial unique index releases the thread, then return
          ``CancelOutcome(initiated=True, ...)``. The caller can retry the
          create / cancel sequence as if the original owner never existed.
        - lease still live ⇒ return ``CancelOutcome(owner_live_elsewhere=True,
          retry_after_seconds=...)`` so the router can emit ``409 +
          Retry-After``.

        ``initiated`` is ``True`` for an in-process cancel that fired (or an
        idempotent re-cancel of an already interrupted run) and for a takeover
        that succeeded; ``False`` otherwise. ``owner_live_elsewhere`` disambiguates
        the ``False`` case so the HTTP layer can pick the right status code.
        Legacy callers that read the return value as a boolean keep working via
        :meth:`CancelOutcome.__bool__`.
        """
        async with self._lock:
            record = self._runs.get(run_id)
            if record is not None:
                if record.status == RunStatus.interrupted:
                    return CancelOutcome(initiated=True, reason="already interrupted")
                if record.status not in (RunStatus.pending, RunStatus.running):
                    return CancelOutcome(initiated=False, reason=f"run is terminal: {record.status.value}")
                record.abort_action = action
                record.abort_event.set()
                task_active = record.task is not None and not record.task.done()
                record.finalizing = task_active
                if task_active:
                    record.task.cancel()
                record.status = RunStatus.interrupted
                record.updated_at = _now_iso()
        if record is not None:
            await self._persist_status(record, RunStatus.interrupted)
            logger.info("Run %s cancelled (action=%s)", run_id, action)
            return CancelOutcome(initiated=True, reason="local cancel")

        # Memory miss on a worker that owns no task for this run: only the
        # multi-worker lease path can do something useful here.
        return await self._cancel_via_lease_takeover(run_id)

    async def _cancel_via_lease_takeover(self, run_id: str) -> CancelOutcome:
        """Resolve a cancel request when the run is not in this worker's memory.

        Single-worker deployments (no store / heartbeat disabled) cannot take
        over a run that is not in their memory: there is no lease to consult
        and no other worker could have started it, so we report "unknown" and
        let the router map that to 404/409.
        """
        if not self._multi_worker_enabled() or self._store is None:
            return CancelOutcome(initiated=False, reason="run not in memory and lease takeover is disabled")
        try:
            row = await self._store.get(run_id)
        except Exception:
            logger.warning("Failed to hydrate run %s for lease takeover", run_id, exc_info=True)
            return CancelOutcome(initiated=False, reason="store lookup failed")
        if row is None:
            return CancelOutcome(initiated=False, reason="run not found")
        status = row.get("status")
        if status not in (RunStatus.pending.value, RunStatus.running.value):
            return CancelOutcome(initiated=False, reason=f"run is terminal: {status}")
        # Compute the live lease deadline and decide between takeover / wait.
        now = datetime.now(UTC)
        grace = self._ownership_config.grace_seconds if self._ownership_config else 0
        cutoff = now - timedelta(seconds=grace)
        lease_at_raw = row.get("lease_expires_at")
        lease_at = _coerce_lease(lease_at_raw)
        if lease_at is None or lease_at < cutoff:
            error = "owning worker lease expired; run taken over by cancel request"
            try:
                took = await self._store.takeover_expired_active_run(
                    run_id,
                    caller_worker_id=self._worker_id or "",
                    error=error,
                    new_status=RunStatus.error.value,
                    lease_cutoff=cutoff,
                )
            except Exception:
                logger.warning("Failed to take over expired active run %s", run_id, exc_info=True)
                return CancelOutcome(initiated=False, reason="takeover store call failed")
            if not took:
                # Lost the race — another worker took it over first, or the
                # owner just renewed. Treat as "still alive elsewhere" so the
                # caller can retry against the live owner.
                return CancelOutcome(initiated=False, owner_live_elsewhere=True, retry_after_seconds=max(0.0, grace), reason="takeover raced")
            logger.info("Run %s taken over (lease expired)", run_id)
            return CancelOutcome(initiated=True, reason="lease expired; taken over")
        retry_after = max(0.0, (lease_at - cutoff).total_seconds())
        return CancelOutcome(initiated=False, owner_live_elsewhere=True, retry_after_seconds=retry_after, reason="lease still live on another worker")

    async def create_or_reject(
        self,
        thread_id: str,
        assistant_id: str | None = None,
        *,
        on_disconnect: DisconnectMode = DisconnectMode.cancel,
        metadata: dict | None = None,
        kwargs: dict | None = None,
        multitask_strategy: str = "reject",
        model_name: str | None = None,
        user_id: str | None = None,
    ) -> RunRecord:
        """Atomically check for inflight runs and create a new one.

        For ``reject`` strategy, raises ``ConflictError`` if thread already
        has a pending/running run.  For ``interrupt``/``rollback``, cancels
        inflight runs before creating.

        Single-worker deployments (``run_ownership.heartbeat_enabled=False``)
        keep the original in-process path: this method holds the lock across
        both the check and the insert, eliminating the TOCTOU race in separate
        ``has_inflight`` + ``create``.

        Multi-worker deployments (``heartbeat_enabled=True`` + SQL store) pivot
        to the lease-aware path: the partial unique index ``uq_runs_thread_active``
        is the single source of truth. ``reject`` INSERTs and translates the
        resulting ``IntegrityError`` into ``ConflictError``; ``interrupt`` /
        ``rollback`` lock the active rows ``FOR UPDATE``, decide whether each
        lease is live (own-lease ⇒ in-process cancel, foreign live lease ⇒
        ``ConflictError``, foreign dead lease ⇒ mark ``error`` to release the
        index), then INSERT. The in-memory record is created only after the
        store commits so a rollback never leaks a phantom RunRecord.
        """
        _supported_strategies = ("reject", "interrupt", "rollback")
        if multitask_strategy not in _supported_strategies:
            raise UnsupportedStrategyError(f"Multitask strategy '{multitask_strategy}' is not yet supported. Supported strategies: {', '.join(_supported_strategies)}")

        if self._multi_worker_enabled():
            return await self._create_or_reject_multi_worker(
                thread_id,
                assistant_id,
                on_disconnect=on_disconnect,
                metadata=metadata,
                kwargs=kwargs,
                multitask_strategy=multitask_strategy,
                model_name=model_name,
                user_id=user_id,
            )

        run_id = str(uuid.uuid4())
        now = _now_iso()
        interrupted_records: list[RunRecord] = []

        async with self._lock:
            inflight = [r for r in self._thread_records_locked(thread_id) if r.status in (RunStatus.pending, RunStatus.running) or r.finalizing]

            if multitask_strategy == "reject" and inflight:
                raise ConflictError(f"Thread {thread_id} already has an active run")

            if multitask_strategy in ("interrupt", "rollback") and inflight:
                logger.info(
                    "Preparing to cancel %d inflight run(s) on thread %s (strategy=%s)",
                    len(inflight),
                    thread_id,
                    multitask_strategy,
                )

            record = RunRecord(
                run_id=run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                status=RunStatus.pending,
                on_disconnect=on_disconnect,
                multitask_strategy=multitask_strategy,
                metadata=metadata or {},
                kwargs=kwargs or {},
                user_id=user_id,
                created_at=now,
                updated_at=now,
                model_name=model_name,
            )
            self._runs[run_id] = record
            self._index_run_locked(record)
            persisted = False
            try:
                await self._persist_new_run_to_store(record)
                persisted = True
            except Exception:
                logger.warning("Failed to persist run %s; rolled back in-memory record", run_id, exc_info=True)
                raise
            finally:
                # Also covers cancellation, which bypasses ``except Exception``.
                if not persisted:
                    self._runs.pop(run_id, None)
                    self._unindex_run_locked(run_id, record.thread_id)

            if multitask_strategy in ("interrupt", "rollback") and inflight:
                for r in inflight:
                    if r.finalizing:
                        continue
                    r.abort_action = multitask_strategy
                    r.abort_event.set()
                    task_active = r.task is not None and not r.task.done()
                    r.finalizing = task_active
                    if task_active:
                        r.task.cancel()
                    r.status = RunStatus.interrupted
                    r.updated_at = now
                    interrupted_records.append(r)

        for interrupted_record in interrupted_records:
            await self._persist_status(interrupted_record, RunStatus.interrupted)
        logger.info("Run created: run_id=%s thread_id=%s", run_id, thread_id)
        return record

    async def _create_or_reject_multi_worker(
        self,
        thread_id: str,
        assistant_id: str | None,
        *,
        on_disconnect: DisconnectMode,
        metadata: dict | None,
        kwargs: dict | None,
        multitask_strategy: str,
        model_name: str | None,
        user_id: str | None,
    ) -> RunRecord:
        """Lease-aware ``create_or_reject`` path used when ``heartbeat_enabled``.

        See :meth:`create_or_reject` for the high-level contract. The store
        calls here are the atomic primitives declared on :class:`RunStore`:
        ``claim_inflight_for_thread`` / ``insert_active_run_atomic`` plus the
        shared ``takeover_expired_active_run`` used by the cancel path.
        """
        assert self._store is not None and self._worker_id is not None and self._ownership_config is not None  # for type checkers
        from deerflow.runtime.runs.store.base import ActiveRunConflict

        run_id = str(uuid.uuid4())
        now_dt = datetime.now(UTC)
        now = _now_iso()
        lease_at = self._fresh_lease_expires_at(now_dt)
        grace = self._ownership_config.grace_seconds

        # ``interrupt`` / ``rollback`` need to drain the thread's active rows
        # before INSERT. Foreign rows with a live lease abort the request;
        # own-lease rows are cancelled in-process; foreign rows whose lease is
        # past grace are marked ``error`` to release the partial unique index.
        interrupt_targets: list[RunRecord] = []
        if multitask_strategy in ("interrupt", "rollback"):
            try:
                inflight_rows = await self._store.claim_inflight_for_thread(
                    thread_id,
                    now=now_dt,
                    grace_seconds=grace,
                )
            except Exception:
                logger.warning("Failed to claim inflight runs for thread %s", thread_id, exc_info=True)
                raise
            for row in inflight_rows:
                other_id = row.get("run_id")
                owner = row.get("owner_worker_id")
                lease_live = bool(row.get("lease_live"))
                if owner == self._worker_id:
                    # Self-owned — there must be an in-memory record unless the
                    # process restarted. Resolve via the in-process cancel path
                    # so the task / abort_event get signalled correctly.
                    async with self._lock:
                        local = self._runs.get(other_id) if other_id else None
                    if local is not None and local.status in (RunStatus.pending, RunStatus.running) and not local.finalizing:
                        interrupt_targets.append(local)
                    else:
                        # Process restarted with a stale self-lease. Mark the
                        # row error so the partial unique index releases it;
                        # the heartbeat task is fresh and never renewed it.
                        await self._store.takeover_expired_active_run(
                            other_id,
                            caller_worker_id=self._worker_id,
                            error="owning worker restarted; run orphaned",
                            new_status=RunStatus.error.value,
                            lease_cutoff=now_dt - timedelta(seconds=grace),
                        )
                elif lease_live:
                    raise ConflictError(f"Thread {thread_id} already has an active run owned by another worker")
                else:
                    # Foreign + dead lease: take it over to release the index.
                    await self._store.takeover_expired_active_run(
                        other_id,
                        caller_worker_id=self._worker_id,
                        error="previous run lease expired; replaced by new request",
                        new_status=RunStatus.error.value,
                        lease_cutoff=now_dt - timedelta(seconds=grace),
                    )

        # Atomic INSERT — partial unique index is the only arbiter now. Any
        # row still active on this thread (own-lease ones we have not yet
        # cancelled in-memory, or a peer INSERT that won the race) trips it.
        try:
            await self._store.insert_active_run_atomic(
                run_id,
                thread_id=thread_id,
                assistant_id=assistant_id,
                user_id=user_id,
                model_name=model_name,
                multitask_strategy=multitask_strategy,
                metadata=metadata or {},
                kwargs=kwargs or {},
                created_at=now_dt,
                owner_worker_id=self._worker_id,
                lease_expires_at=lease_at,
            )
        except ActiveRunConflict:
            if interrupt_targets:
                # We attempted an in-process cancel but the row had not yet
                # left the partial-index predicate (status flip is async).
                raise ConflictError(f"Thread {thread_id} still has an active run after interrupt cleanup raced")
            raise ConflictError(f"Thread {thread_id} already has an active run")

        record = RunRecord(
            run_id=run_id,
            thread_id=thread_id,
            assistant_id=assistant_id,
            status=RunStatus.pending,
            on_disconnect=on_disconnect,
            multitask_strategy=multitask_strategy,
            metadata=metadata or {},
            kwargs=kwargs or {},
            user_id=user_id,
            created_at=now,
            updated_at=now,
            model_name=model_name,
            owner_worker_id=self._worker_id,
            lease_expires_at=lease_at.isoformat(),
        )
        async with self._lock:
            self._runs[run_id] = record
            self._index_run_locked(record)

        # Apply in-process cancel signals only after the INSERT committed so a
        # failed INSERT never produces a half-cancelled peer run.
        for local in interrupt_targets:
            async with self._lock:
                if local.status not in (RunStatus.pending, RunStatus.running) or local.finalizing:
                    continue
                local.abort_action = multitask_strategy
                local.abort_event.set()
                task_active = local.task is not None and not local.task.done()
                local.finalizing = task_active
                if task_active:
                    local.task.cancel()
                local.status = RunStatus.interrupted
                local.updated_at = now
            await self._persist_status(local, RunStatus.interrupted)

        logger.info("Run created: run_id=%s thread_id=%s (multi-worker)", run_id, thread_id)
        return record

    async def reconcile_orphaned_inflight_runs(
        self,
        *,
        error: str,
        before: str | None = None,
    ) -> list[RunRecord]:
        """Mark persisted active runs as failed when no local task owns them.

        Gateway runs are process-local: the asyncio task and abort event live in
        memory, while the run row is durable.  After a SQLite-backed gateway
        restart, any persisted ``pending`` or ``running`` row created before
        startup cannot still have a local worker.  This recovery step turns that
        ambiguous state into an explicit error instead of letting the UI show an
        indefinite active run.

        Multi-worker note: when ``run_ownership.heartbeat_enabled=True`` the
        lease is the source of truth, not process liveness. A row whose lease
        is still live (or within ``grace_seconds``) is left alone because its
        owning worker may still be running on another pod; only expired-lease
        rows are recovered. ``lease_expires_at IS NULL`` rows are always stale
        (legacy data / heartbeat off) and recover normally so a single-worker
        deployment that flips the feature on later does not strand old rows.
        """
        if self._store is None:
            return []
        try:
            rows = await self._call_store_with_retry(
                "list_inflight",
                "*",
                lambda: self._store.list_inflight(before=before),
            )
        except Exception:
            logger.warning("Failed to list orphaned inflight runs for reconciliation", exc_info=True)
            return []

        now_dt = datetime.now(UTC)
        now = _now_iso()
        grace = self._ownership_config.grace_seconds if self._ownership_config else 0
        cutoff = now_dt - timedelta(seconds=grace)
        multi_worker = self._multi_worker_enabled()

        recovered: list[RunRecord] = []
        for row in rows:
            try:
                record = self._record_from_store(row)
            except Exception:
                logger.warning("Failed to map orphaned run row during reconciliation", exc_info=True)
                continue

            async with self._lock:
                live_record = self._runs.get(record.run_id)
                if live_record is not None and live_record.status in (RunStatus.pending, RunStatus.running):
                    continue

            if multi_worker:
                # Skip runs whose lease is still live — another worker may be
                # actively executing them. NULL leases pre-date the heartbeat
                # column and are always considered stale.
                lease_at = _coerce_lease(row.get("lease_expires_at"))
                owner = row.get("owner_worker_id")
                if (
                    owner is not None
                    and owner != self._worker_id
                    and lease_at is not None
                    and lease_at >= cutoff
                ):
                    continue
                if (
                    owner == self._worker_id
                    and lease_at is not None
                    and lease_at >= cutoff
                ):
                    # Self-owned but missing from memory: this worker restarted
                    # with a live lease on its own row. Treat as orphan so we
                    # do not block the thread until the lease would expire.
                    pass

            record.status = RunStatus.error
            record.error = error
            record.updated_at = now
            persisted = await self._persist_status(record, RunStatus.error, error=error)
            if not persisted:
                logger.warning("Skipped orphaned run %s recovery because error status was not persisted", record.run_id)
                continue
            recovered.append(record)

        if recovered:
            logger.warning("Recovered %d orphaned inflight run(s) as error", len(recovered))
        return recovered

    async def start_heartbeat(self) -> None:
        """Start the per-worker lease heartbeat (multi-worker only).

        The task wakes every ``lease_seconds / 3`` and refreshes
        ``lease_expires_at`` on every active run this worker owns. Idempotent:
        calling it twice is a no-op so ``langgraph_runtime`` can call it
        unconditionally after wiring the store.
        """
        if not self._multi_worker_enabled():
            return
        if self._heartbeat_task is not None and not self._heartbeat_task.done():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """Stop the heartbeat task started by :meth:`start_heartbeat`.

        Called from ``langgraph_runtime`` teardown so the worker does not leave
        a zombie task behind on shutdown. A no-op when heartbeat was never
        started.
        """
        if self._heartbeat_task is None:
            return
        self._heartbeat_stop.set()
        task = self._heartbeat_task
        self._heartbeat_task = None
        if not task.done():
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                task.cancel()

    async def _heartbeat_loop(self) -> None:
        """Background renewer for active runs owned by this worker."""
        assert self._ownership_config is not None and self._store is not None and self._worker_id is not None
        # Renew at ``lease_seconds / 3`` so a single missed tick still leaves
        # ~⅔ of the lease window before another worker can take over.
        interval = max(1.0, self._ownership_config.lease_seconds / 3.0)
        while not self._heartbeat_stop.is_set():
            try:
                async with self._lock:
                    owned = [
                        record
                        for record in self._runs.values()
                        if record.owner_worker_id == self._worker_id
                        and record.status in (RunStatus.pending, RunStatus.running)
                    ]
                if owned:
                    new_expiry = self._fresh_lease_expires_at()
                    for record in owned:
                        try:
                            renewed = await self._store.renew_lease(
                                record.run_id,
                                owner_worker_id=self._worker_id,
                                lease_expires_at=new_expiry,
                            )
                        except Exception:
                            logger.warning("Failed to renew lease for run %s", record.run_id, exc_info=True)
                            continue
                        if renewed:
                            record.lease_expires_at = new_expiry.isoformat()
                        else:
                            # Row was lost (taken over / went terminal). Stop
                            # advertising the lease locally; the run is no
                            # longer ours to keep alive.
                            record.lease_expires_at = None
                            record.owner_worker_id = None
            except Exception:
                logger.exception("Heartbeat iteration failed; will retry next interval")
            try:
                await asyncio.wait_for(self._heartbeat_stop.wait(), timeout=interval)
            except TimeoutError:
                continue

    async def has_inflight(self, thread_id: str) -> bool:
        """Return ``True`` if *thread_id* has a pending or running run."""
        async with self._lock:
            return any(r.status in (RunStatus.pending, RunStatus.running) or r.finalizing for r in self._thread_records_locked(thread_id))

    async def cleanup(self, run_id: str, *, delay: float = 300) -> None:
        """Remove a run record after an optional delay."""
        if delay > 0:
            await asyncio.sleep(delay)
        async with self._lock:
            record = self._runs.pop(run_id, None)
            if record is not None:
                self._unindex_run_locked(run_id, record.thread_id)
        logger.debug("Run record %s cleaned up", run_id)

    async def shutdown(self, *, timeout: float = 5.0) -> None:
        """Cancel and bounded-await all in-flight runs on process shutdown.

        Chat runs execute in fire-and-forget background ``asyncio`` tasks that
        write checkpoints through a shared checkpointer. On shutdown the
        checkpointer's resources (e.g. the postgres connection pool owned by the
        gateway's ``AsyncExitStack``) are torn down; if a run task is still
        mid-graph at that point, langgraph's
        ``AsyncPregelLoop._checkpointer_put_after_previous`` runs its
        ``finally: await checkpointer.aput(...)`` against the closed pool. Because
        that put runs in a langgraph-internal task (not on ``run_agent``'s call
        stack), the resulting ``psycopg_pool.PoolClosed`` is not catchable by the
        worker and surfaces as an unhandled exception during ``asyncio.run()``
        shutdown (bytedance/deer-flow issue #3373).

        Draining in-flight runs *before* the checkpointer is closed lets each
        run that settles within ``timeout`` flush its final checkpoint while
        resources are still open. Only runs that do **not** settle on their own
        are marked ``interrupted`` — a run that completes (e.g. ``success``)
        during the drain keeps its real terminal status instead of being
        blanket-overwritten. The whole drain, including the trailing status
        persistence, is bounded by ``timeout`` so a run stuck in cleanup (or a
        slow store under DB pressure) cannot hang worker shutdown — the
        precondition for the signal-reentrancy deadlock guarded by
        ``app.gateway.app._SHUTDOWN_HOOK_TIMEOUT_SECONDS``. Runs still active
        after ``timeout`` are logged and may still race teardown.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        async with self._lock:
            inflight = [record for record in self._runs.values() if record.status in (RunStatus.pending, RunStatus.running) and record.task is not None and not record.task.done()]
            for record in inflight:
                record.abort_action = "interrupt"
                record.abort_event.set()
                record.task.cancel()  # type: ignore[union-attr]  # filtered above
                # Status is decided AFTER the drain (below), not here: a run that
                # completes on its own during the drain must keep its real status.

        if not inflight:
            return

        tasks = [record.task for record in inflight]
        _, pending = await asyncio.wait(tasks, timeout=timeout)

        # Only mark/persist ``interrupted`` for runs that did not settle on their
        # own (still pending after the timeout, or ended cancelled). A run that
        # finished normally during the drain keeps the status it set for itself.
        to_persist: list[RunRecord] = []
        async with self._lock:
            for record in inflight:
                task = record.task
                if task not in pending and not task.cancelled():
                    # Completed on its own — retrieve any surfaced exception so it
                    # is not reported as "never retrieved", and keep its status.
                    task.exception()  # type: ignore[union-attr]  # done & not cancelled
                    continue
                if record.status in (RunStatus.pending, RunStatus.running):
                    record.status = RunStatus.interrupted
                    record.updated_at = _now_iso()
                to_persist.append(record)

        # Bound the trailing status persistence within the remaining budget so a
        # slow store (``_call_store_with_retry`` can back off under DB pressure)
        # cannot push shutdown past ``timeout``.
        if to_persist:
            remaining = deadline - loop.time()
            if remaining <= 0:
                logger.warning("Run drain budget exhausted before persisting %d interrupted run(s) on shutdown", len(to_persist))
            else:
                try:
                    results = await asyncio.wait_for(
                        asyncio.gather(*(self._persist_status(record, RunStatus.interrupted) for record in to_persist), return_exceptions=True),
                        timeout=remaining,
                    )
                except TimeoutError:
                    logger.warning("Run drain status persistence exceeded the %.1fs budget; %d record(s) may not be persisted", timeout, len(to_persist))
                else:
                    # ``_persist_status`` is best-effort: it catches and logs its
                    # own failures, returning ``False``. Inspect the aggregate so a
                    # partial failure is surfaced at shutdown level (with the
                    # run_id) instead of being silently swallowed by the gather.
                    for record, result in zip(to_persist, results):
                        if isinstance(result, Exception):
                            logger.warning("Unexpected error persisting interrupted status for run %s during shutdown: %r", record.run_id, result)
                        elif result is False:
                            logger.warning("Could not persist interrupted status for run %s during shutdown", record.run_id)

        if pending:
            logger.warning("Run drain exceeded %.1fs on shutdown; %d run task(s) still active and may race checkpointer teardown", timeout, len(pending))
        logger.info("Drained %d in-flight run(s) on shutdown (%d settled within %.1fs)", len(inflight), len(inflight) - len(pending), timeout)


class ConflictError(Exception):
    """Raised when multitask_strategy=reject and thread has inflight runs."""


class UnsupportedStrategyError(Exception):
    """Raised when a multitask_strategy value is not yet implemented."""
