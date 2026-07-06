"""Abstract interface for run metadata storage.

RunManager depends on this interface. Implementations:
- MemoryRunStore: in-memory dict (development, tests)
- RunRepository: SQLAlchemy ORM backed by SQLite or Postgres

All methods accept an optional user_id for user isolation.
When user_id is None, no user filtering is applied (single-user mode).

Multi-worker note: ``insert_active_run_atomic`` / ``claim_inflight_for_thread``
/ ``renew_lease`` / ``takeover_expired_active_run`` form the lease-based atomic
surface that ``RunManager.create_or_reject`` uses when
``run_ownership.heartbeat_enabled=True``. The legacy in-process path goes
through ``put`` and the secondary ``asyncio.Lock`` instead, so single-worker
deployments are unchanged.
"""

from __future__ import annotations

import abc
from datetime import datetime
from typing import Any


class RunStore(abc.ABC):
    @abc.abstractmethod
    async def put(
        self,
        run_id: str,
        *,
        thread_id: str,
        assistant_id: str | None = None,
        user_id: str | None = None,
        model_name: str | None = None,
        status: str = "pending",
        multitask_strategy: str = "reject",
        metadata: dict[str, Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        error: str | None = None,
        created_at: str | None = None,
        owner_worker_id: str | None = None,
        lease_expires_at: datetime | None = None,
    ) -> None:
        pass

    @abc.abstractmethod
    async def get(
        self,
        run_id: str,
        *,
        user_id: str | None = None,
    ) -> dict[str, Any] | None:
        pass

    @abc.abstractmethod
    async def list_by_thread(
        self,
        thread_id: str,
        *,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        pass

    @abc.abstractmethod
    async def update_status(
        self,
        run_id: str,
        status: str,
        *,
        error: str | None = None,
    ) -> bool | None:
        """Update a run status.

        Returns ``False`` when the store can prove no row was updated. Older or
        lightweight stores may return ``None`` when they cannot report rowcount.
        """
        pass

    @abc.abstractmethod
    async def delete(self, run_id: str) -> None:
        pass

    @abc.abstractmethod
    async def update_model_name(
        self,
        run_id: str,
        model_name: str | None,
    ) -> None:
        """Update the model_name field for an existing run."""
        pass

    @abc.abstractmethod
    async def update_run_completion(
        self,
        run_id: str,
        *,
        status: str,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
        total_tokens: int = 0,
        llm_call_count: int = 0,
        lead_agent_tokens: int = 0,
        subagent_tokens: int = 0,
        middleware_tokens: int = 0,
        token_usage_by_model: dict[str, dict[str, int]] | None = None,
        message_count: int = 0,
        last_ai_message: str | None = None,
        first_human_message: str | None = None,
        error: str | None = None,
    ) -> bool | None:
        """Persist final completion fields.

        Returns ``False`` when the store can prove no row was updated.
        """
        pass

    async def update_run_progress(
        self,
        run_id: str,
        *,
        total_input_tokens: int | None = None,
        total_output_tokens: int | None = None,
        total_tokens: int | None = None,
        llm_call_count: int | None = None,
        lead_agent_tokens: int | None = None,
        subagent_tokens: int | None = None,
        middleware_tokens: int | None = None,
        token_usage_by_model: dict[str, dict[str, int]] | None = None,
        message_count: int | None = None,
        last_ai_message: str | None = None,
        first_human_message: str | None = None,
    ) -> None:
        """Persist a best-effort running snapshot without changing run status."""
        return None

    @abc.abstractmethod
    async def list_pending(self, *, before: str | None = None) -> list[dict[str, Any]]:
        pass

    @abc.abstractmethod
    async def list_inflight(self, *, before: str | None = None) -> list[dict[str, Any]]:
        """Return persisted runs that are still ``pending`` or ``running``."""
        pass

    @abc.abstractmethod
    async def aggregate_tokens_by_thread(self, thread_id: str, *, include_active: bool = False) -> dict[str, Any]:
        """Aggregate token usage for completed runs in a thread.

        Returns a dict with keys: total_tokens, total_input_tokens,
        total_output_tokens, total_runs, by_model (model_name → {tokens, runs}),
        by_caller ({lead_agent, subagent, middleware}).
        """
        pass

    # ------------------------------------------------------------------
    # Lease-based atomic primitives (multi-worker only)
    # ------------------------------------------------------------------
    #
    # MemoryRunStore no-ops these because the in-process ``RunManager._lock``
    # already serialises callers; only the SQL-backed ``RunRepository``
    # implements them. ``RunManager`` probes ``supports_lease_takeover`` to
    # decide which code path to take.

    @property
    def supports_lease_takeover(self) -> bool:
        """Return ``True`` when this store can do lease-based takeover.

        ``RunManager`` uses this to pick between the legacy in-process path
        (single worker / memory store) and the lease-aware path (multi-worker
        SQL store). The default keeps MemoryRunStore and any future read-only
        store on the original path without each caller needing a special case.
        """
        return False

    async def insert_active_run_atomic(
        self,
        run_id: str,
        *,
        thread_id: str,
        assistant_id: str | None,
        user_id: str | None,
        model_name: str | None,
        multitask_strategy: str,
        metadata: dict[str, Any] | None,
        kwargs: dict[str, Any] | None,
        created_at: datetime,
        owner_worker_id: str,
        lease_expires_at: datetime,
    ) -> None:
        """Atomically INSERT a new active run relying on the partial unique index.

        Raises:
            ActiveRunConflict: when the partial unique index
                ``uq_runs_thread_active`` rejects the INSERT because another
                active row already exists for ``thread_id``.
            NotImplementedError: when the store does not support lease takeover
                (memory store / single-worker).
        """
        raise NotImplementedError

    async def claim_inflight_for_thread(
        self,
        thread_id: str,
        *,
        now: datetime,
        grace_seconds: int,
    ) -> list[dict[str, Any]]:
        """Return inflight runs for *thread_id* with their lease liveness flag.

        Each row carries an extra ``lease_live`` boolean — ``True`` when the
        owning worker's heartbeat is still within ``grace_seconds`` of
        ``now``. Callers use it to decide whether an interrupt/rollback
        strategy can dispatch the in-process cancel signal (own lease) or
        must mark the row ``error`` to drop out of the partial unique index
        before retrying the INSERT.
        """
        raise NotImplementedError

    async def renew_lease(
        self,
        run_id: str,
        *,
        owner_worker_id: str,
        lease_expires_at: datetime,
    ) -> bool:
        """Refresh ``lease_expires_at`` on a run this worker still owns.

        Returns ``False`` when the row is missing, no longer active, or owned
        by a different worker — the heartbeat task treats that as "stop
        renewing this run".
        """
        raise NotImplementedError

    async def takeover_expired_active_run(
        self,
        run_id: str,
        *,
        caller_worker_id: str,
        error: str,
        new_status: str,
    ) -> bool:
        """Mark an orphaned active run as terminal so this worker can INSERT.

        Returns ``False`` when the row is missing, already terminal, or still
        has an unexpired lease owned by another worker.
        """
        raise NotImplementedError


class ActiveRunConflict(Exception):
    """Raised by ``insert_active_run_atomic`` when the partial unique index bites.

    ``RunManager.create_or_reject`` translates this into ``ConflictError`` for
    the ``reject`` strategy. The exception carries the ``thread_id`` so the
    caller does not have to re-derive it from the request.
    """

    def __init__(self, thread_id: str, message: str | None = None) -> None:
        super().__init__(message or f"Thread {thread_id} already has an active run")
        self.thread_id = thread_id
