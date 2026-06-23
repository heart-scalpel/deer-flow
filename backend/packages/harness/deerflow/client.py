"""DeerFlowClient — Embedded Python client for DeerFlow agent system.

Provides direct programmatic access to DeerFlow's agent capabilities
without requiring LangGraph Server or Gateway API processes.

Usage:
    from deerflow.client import DeerFlowClient

    client = DeerFlowClient()
    response = client.chat("Analyze this paper for me", thread_id="my-thread")
    print(response)

    # Streaming
    for event in client.stream("hello"):
        print(event)
"""

import asyncio
import json
import logging
import mimetypes
import os
import shutil
import tempfile
import uuid
from collections.abc import Generator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from deerflow.agents.lead_agent.agent import build_middlewares
from deerflow.agents.lead_agent.prompt import apply_prompt_template
from deerflow.agents.thread_state import ThreadState
from deerflow.config.agents_config import AGENT_NAME_PATTERN
from deerflow.config.app_config import get_app_config, reload_app_config
from deerflow.config.extensions_config import ExtensionsConfig, SkillStateConfig, get_extensions_config, reload_extensions_config
from deerflow.config.paths import get_paths
from deerflow.models import create_chat_model
from deerflow.runtime.user_context import get_effective_user_id
from deerflow.skills.storage import get_or_new_skill_storage
from deerflow.tools.builtins.tool_search import assemble_deferred_tools
from deerflow.tracing import build_tracing_callbacks, inject_langfuse_metadata
from deerflow.uploads.manager import (
    claim_unique_filename,
    delete_file_safe,
    enrich_file_listing,
    ensure_uploads_dir,
    get_uploads_dir,
    list_files_in_dir,
    upload_artifact_url,
    upload_virtual_path,
)

logger = logging.getLogger(__name__)


StreamEventType = Literal["values", "messages-tuple", "custom", "end"]


@dataclass
class StreamEvent:
    """A single event from the streaming agent response.

    Event types align with the LangGraph SSE protocol:
        - ``"values"``: Full state snapshot (title, messages, artifacts).
        - ``"messages-tuple"``: Per-message update (AI text, tool calls, tool results).
        - ``"end"``: Stream finished.

    Attributes:
        type: Event type.
        data: Event payload. Contents vary by type.
    """

    type: StreamEventType
    data: dict[str, Any] = field(default_factory=dict)


class DeerFlowClient:
    """Embedded Python client for DeerFlow agent system.

    Provides direct programmatic access to DeerFlow's agent capabilities
    without requiring LangGraph Server or Gateway API processes.

    Note:
        Multi-turn conversations require a ``checkpointer``. Without one,
        each ``stream()`` / ``chat()`` call is stateless — ``thread_id``
        is only used for file isolation (uploads / artifacts).

        The system prompt (including date, memory, and skills context) is
        generated when the internal agent is first created and cached until
        the configuration key changes. Call :meth:`reset_agent` to force
        a refresh in long-running processes.

    Example::

        from deerflow.client import DeerFlowClient

        client = DeerFlowClient()

        # Simple one-shot
        print(client.chat("hello"))

        # Streaming
        for event in client.stream("hello"):
            print(event.type, event.data)

        # Configuration queries
        print(client.list_models())
        print(client.list_skills())
    """

    def __init__(
        self,
        config_path: str | None = None,
        checkpointer=None,
        *,
        model_name: str | None = None,
        thinking_enabled: bool = True,
        subagent_enabled: bool = False,
        plan_mode: bool = False,
        agent_name: str | None = None,
        available_skills: set[str] | None = None,
        middlewares: Sequence[AgentMiddleware] | None = None,
        environment: str | None = None,
    ):
        """Initialize the client.

        Loads configuration but defers agent creation to first use.

        Args:
            config_path: Path to config.yaml. Uses default resolution if None.
            checkpointer: LangGraph checkpointer instance for state persistence.
                Required for multi-turn conversations on the same thread_id.
                Without a checkpointer, each call is stateless.
            model_name: Override the default model name from config.
            thinking_enabled: Enable model's extended thinking.
            subagent_enabled: Enable subagent delegation.
            plan_mode: Enable TodoList middleware for plan mode.
            agent_name: Name of the agent to use.
            available_skills: Optional set of skill names to make available. If None (default), all scanned skills are available.
            middlewares: Optional list of custom middlewares to inject into the agent.
            environment: Deployment environment label that ends up in
                ``langfuse_tags`` (e.g. ``"production"`` / ``"staging"``).
                When ``None`` the worker/client falls back to the
                ``DEER_FLOW_ENV`` or ``ENVIRONMENT`` env vars. Pass an
                explicit value for programmatic callers that do not want
                env-var coupling.
        """
        print("[DeerFlowClient] Initializing client")
        
        if config_path is not None:
            print(f"[DeerFlowClient] Loading custom config from: {config_path}")
            reload_app_config(config_path)
        self._app_config = get_app_config()

        if agent_name is not None and not AGENT_NAME_PATTERN.match(agent_name):
            print(f"[DeerFlowClient] Invalid agent name: {agent_name} (pattern: {AGENT_NAME_PATTERN.pattern})")
            raise ValueError(f"Invalid agent name '{agent_name}'. Must match pattern: {AGENT_NAME_PATTERN.pattern}")

        self._checkpointer = checkpointer
        self._model_name = model_name
        self._thinking_enabled = thinking_enabled
        self._subagent_enabled = subagent_enabled
        self._plan_mode = plan_mode
        self._agent_name = agent_name
        self._available_skills = set(available_skills) if available_skills is not None else None
        self._middlewares = list(middlewares) if middlewares else []
        self._environment = environment

        # Lazy agent — created on first call, recreated when config changes.
        self._agent = None
        self._agent_config_key: tuple | None = None

        print(
            f"[DeerFlowClient] Client initialized: agent_name={self._agent_name}, model={self._model_name}, "
            f"thinking={self._thinking_enabled}, subagent={self._subagent_enabled}, "
            f"plan_mode={self._plan_mode}, environment={self._environment}"
        )

    def reset_agent(self) -> None:
        """Force the internal agent to be recreated on the next call.

        Use this after external changes (e.g. memory updates, skill
        installations) that should be reflected in the system prompt
        or tool set.
        """
        print("[DeerFlowClient] Resetting agent instance")
        self._agent = None
        self._agent_config_key = None
        print("[DeerFlowClient] Agent reset complete, will recreate on next invocation")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        """Write JSON to *path* atomically (temp file + replace)."""
        print(f"[DeerFlowClient] Atomic write to: {path}")
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
        )
        try:
            json.dump(data, fd, indent=2)
            fd.close()
            Path(fd.name).replace(path)
            print(f"[DeerFlowClient] Atomic write completed successfully: {path}")
        except BaseException:
            fd.close()
            Path(fd.name).unlink(missing_ok=True)
            print(f"[DeerFlowClient] Atomic write failed: {path}")
            raise

    def _get_runnable_config(self, thread_id: str, **overrides) -> RunnableConfig:
        """Build a RunnableConfig for agent invocation."""
        configurable = {
            "thread_id": thread_id,
            "model_name": overrides.get("model_name", self._model_name),
            "thinking_enabled": overrides.get("thinking_enabled", self._thinking_enabled),
            "is_plan_mode": overrides.get("plan_mode", self._plan_mode),
            "subagent_enabled": overrides.get("subagent_enabled", self._subagent_enabled),
        }
        return RunnableConfig(
            configurable=configurable,
            recursion_limit=overrides.get("recursion_limit", 100),
        )

    def _ensure_agent(self, config: RunnableConfig):
        """Create (or recreate) the agent when config-dependent params change."""
        cfg = config.get("configurable", {})
        key = (
            cfg.get("model_name"),
            cfg.get("thinking_enabled"),
            cfg.get("is_plan_mode"),
            cfg.get("subagent_enabled"),
            self._agent_name,
            frozenset(self._available_skills) if self._available_skills is not None else None,
        )

        if self._agent is not None and self._agent_config_key == key:
            print("[DeerFlowClient] Reusing existing agent instance (config unchanged)")
            return

        print("[DeerFlowClient] Creating new agent instance")
        thinking_enabled = cfg.get("thinking_enabled", True)
        model_name = cfg.get("model_name")
        subagent_enabled = cfg.get("subagent_enabled", False)
        max_concurrent_subagents = cfg.get("max_concurrent_subagents", 3)

        tools = self._get_tools(model_name=model_name, subagent_enabled=subagent_enabled)
        final_tools, deferred_setup = assemble_deferred_tools(tools, enabled=self._app_config.tool_search.enabled)

        system_prompt = apply_prompt_template(
                subagent_enabled=subagent_enabled,
                max_concurrent_subagents=max_concurrent_subagents,
                agent_name=self._agent_name,
                available_skills=self._available_skills,
                deferred_names=deferred_setup.deferred_names,
            )
        # print(f"system_prompt: {system_prompt}")

        kwargs: dict[str, Any] = {
            # attach_tracing=False because ``stream()`` injects tracing
            # callbacks at the graph invocation root so a single embedded run
            # produces one trace with correct session_id / user_id propagation.
            # Attaching them again on the model would emit duplicate spans.
            "model": create_chat_model(name=model_name, thinking_enabled=thinking_enabled, attach_tracing=False),
            "tools": final_tools,
            "middleware": build_middlewares(
                config,
                model_name=model_name,
                agent_name=self._agent_name,
                available_skills=self._available_skills,
                custom_middlewares=self._middlewares,
                app_config=self._app_config,
                deferred_setup=deferred_setup,
            ),
            "system_prompt": system_prompt,
            "state_schema": ThreadState,
        }
        checkpointer = self._checkpointer
        if checkpointer is None:
            from deerflow.runtime.checkpointer import get_checkpointer

            checkpointer = get_checkpointer()
        if checkpointer is not None:
            kwargs["checkpointer"] = checkpointer
            print("[DeerFlowClient] Attached checkpointer to agent")

        self._agent = create_agent(**kwargs)
        self._agent_config_key = key
        print(
            f"[DeerFlowClient] Agent created successfully: agent_name={self._agent_name}, model={model_name}, "
            f"thinking={thinking_enabled}, subagent={subagent_enabled}, "
            f"tools_count={len(kwargs['tools'])}, middlewares_count={len(kwargs['middleware'])}"
        )

    @staticmethod
    def _get_tools(*, model_name: str | None, subagent_enabled: bool):
        """Lazy import to avoid circular dependency at module level."""
        from deerflow.tools import get_available_tools

        tools = get_available_tools(model_name=model_name, subagent_enabled=subagent_enabled)
        print(f"[DeerFlowClient] Loaded {len(tools)} available tools")
        return tools

    @staticmethod
    def _serialize_tool_calls(tool_calls) -> list[dict]:
        """Reshape LangChain tool_calls into the wire format used in events."""
        return [{"name": tc["name"], "args": tc["args"], "id": tc.get("id")} for tc in tool_calls]

    @staticmethod
    def _serialize_additional_kwargs(msg) -> dict[str, Any] | None:
        """Copy message additional_kwargs when present."""
        additional_kwargs = getattr(msg, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict) and additional_kwargs:
            return dict(additional_kwargs)
        return None

    @staticmethod
    def _ai_text_event(msg_id: str | None, text: str, usage: dict | None, additional_kwargs: dict[str, Any] | None = None) -> "StreamEvent":
        """Build a ``messages-tuple`` AI text event."""
        data: dict[str, Any] = {"type": "ai", "content": text, "id": msg_id}
        if usage:
            data["usage_metadata"] = usage
        if additional_kwargs:
            data["additional_kwargs"] = additional_kwargs
        return StreamEvent(type="messages-tuple", data=data)

    @staticmethod
    def _ai_tool_calls_event(msg_id: str | None, tool_calls, additional_kwargs: dict[str, Any] | None = None) -> "StreamEvent":
        """Build a ``messages-tuple`` AI tool-calls event."""
        data: dict[str, Any] = {
            "type": "ai",
            "content": "",
            "id": msg_id,
            "tool_calls": DeerFlowClient._serialize_tool_calls(tool_calls),
        }
        if additional_kwargs:
            data["additional_kwargs"] = additional_kwargs
        return StreamEvent(type="messages-tuple", data=data)

    @staticmethod
    def _tool_message_event(msg: ToolMessage) -> "StreamEvent":
        """Build a ``messages-tuple`` tool-result event from a ToolMessage."""
        return StreamEvent(
            type="messages-tuple",
            data={
                "type": "tool",
                "content": DeerFlowClient._extract_text(msg.content),
                "name": msg.name,
                "tool_call_id": msg.tool_call_id,
                "id": msg.id,
            },
        )

    @staticmethod
    def _serialize_message(msg) -> dict:
        """Serialize a LangChain message to a plain dict for values events."""
        if isinstance(msg, AIMessage):
            d: dict[str, Any] = {"type": "ai", "content": msg.content, "id": getattr(msg, "id", None)}
            if msg.tool_calls:
                d["tool_calls"] = DeerFlowClient._serialize_tool_calls(msg.tool_calls)
            if getattr(msg, "usage_metadata", None):
                d["usage_metadata"] = msg.usage_metadata
            if additional_kwargs := DeerFlowClient._serialize_additional_kwargs(msg):
                d["additional_kwargs"] = additional_kwargs
            return d
        if isinstance(msg, ToolMessage):
            d = {
                "type": "tool",
                "content": DeerFlowClient._extract_text(msg.content),
                "name": getattr(msg, "name", None),
                "tool_call_id": getattr(msg, "tool_call_id", None),
                "id": getattr(msg, "id", None),
            }
            if additional_kwargs := DeerFlowClient._serialize_additional_kwargs(msg):
                d["additional_kwargs"] = additional_kwargs
            return d
        if isinstance(msg, HumanMessage):
            d = {"type": "human", "content": msg.content, "id": getattr(msg, "id", None)}
            if additional_kwargs := DeerFlowClient._serialize_additional_kwargs(msg):
                d["additional_kwargs"] = additional_kwargs
            return d
        if isinstance(msg, SystemMessage):
            d = {"type": "system", "content": msg.content, "id": getattr(msg, "id", None)}
            if additional_kwargs := DeerFlowClient._serialize_additional_kwargs(msg):
                d["additional_kwargs"] = additional_kwargs
            return d
        return {"type": "unknown", "content": str(msg), "id": getattr(msg, "id", None)}

    @staticmethod
    def _extract_text(content) -> str:
        """Extract plain text from AIMessage content (str or list of blocks).

        String chunks are concatenated without separators to avoid corrupting
        token/character deltas or chunked JSON payloads. Dict-based text blocks
        are treated as full text blocks and joined with newlines to preserve
        readability.
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            if content and all(isinstance(block, str) for block in content):
                chunk_like = len(content) > 1 and all(isinstance(block, str) and len(block) <= 20 and any(ch in block for ch in '{}[]":,') for block in content)
                return "".join(content) if chunk_like else "\n".join(content)

            pieces: list[str] = []
            pending_str_parts: list[str] = []

            def flush_pending_str_parts() -> None:
                if pending_str_parts:
                    pieces.append("".join(pending_str_parts))
                    pending_str_parts.clear()

            for block in content:
                if isinstance(block, str):
                    pending_str_parts.append(block)
                elif isinstance(block, dict):
                    flush_pending_str_parts()
                    text_val = block.get("text")
                    if isinstance(text_val, str):
                        pieces.append(text_val)

            flush_pending_str_parts()
            return "\n".join(pieces) if pieces else ""
        return str(content)

    # ------------------------------------------------------------------
    # Public API — threads
    # ------------------------------------------------------------------

    def list_threads(self, limit: int = 10) -> dict:
        """List the recent N threads.

        Args:
            limit: Maximum number of threads to return. Default is 10.

        Returns:
            Dict with "thread_list" key containing list of thread info dicts,
            sorted by thread creation time descending.
        """
        print(f"[DeerFlowClient] Listing recent threads (limit={limit})", )
        checkpointer = self._checkpointer
        if checkpointer is None:
            from deerflow.runtime.checkpointer.provider import get_checkpointer

            checkpointer = get_checkpointer()

        thread_info_map = {}

        for cp in checkpointer.list(config=None, limit=limit):
            cfg = cp.config.get("configurable", {})
            thread_id = cfg.get("thread_id")
            if not thread_id:
                continue

            ts = cp.checkpoint.get("ts")
            checkpoint_id = cfg.get("checkpoint_id")

            if thread_id not in thread_info_map:
                channel_values = cp.checkpoint.get("channel_values", {})
                thread_info_map[thread_id] = {
                    "thread_id": thread_id,
                    "created_at": ts,
                    "updated_at": ts,
                    "latest_checkpoint_id": checkpoint_id,
                    "title": channel_values.get("title"),
                }
            else:
                # Explicitly compare timestamps to ensure accuracy when iterating over unordered namespaces.
                # Treat None as "missing" and only compare when existing values are non-None.
                if ts is not None:
                    current_created = thread_info_map[thread_id]["created_at"]
                    if current_created is None or ts < current_created:
                        thread_info_map[thread_id]["created_at"] = ts

                    current_updated = thread_info_map[thread_id]["updated_at"]
                    if current_updated is None or ts > current_updated:
                        thread_info_map[thread_id]["updated_at"] = ts
                        thread_info_map[thread_id]["latest_checkpoint_id"] = checkpoint_id
                        channel_values = cp.checkpoint.get("channel_values", {})
                        thread_info_map[thread_id]["title"] = channel_values.get("title")

        threads = list(thread_info_map.values())
        threads.sort(key=lambda x: x.get("created_at") or "", reverse=True)

        result = {"thread_list": threads[:limit]}
        print(f"[DeerFlowClient] Found {len(result['thread_list'])} threads")
        return result

    def get_thread(self, thread_id: str) -> dict:
        """Get the complete thread record, including all node execution records.

        Args:
            thread_id: Thread ID.

        Returns:
            Dict containing the thread's full checkpoint history.
        """
        print(f"[DeerFlowClient] Retrieving thread: {thread_id}")
        checkpointer = self._checkpointer
        if checkpointer is None:
            from deerflow.runtime.checkpointer.provider import get_checkpointer

            checkpointer = get_checkpointer()

        config = {"configurable": {"thread_id": thread_id}}
        checkpoints = []

        for cp in checkpointer.list(config):
            channel_values = dict(cp.checkpoint.get("channel_values", {}))
            if "messages" in channel_values:
                channel_values["messages"] = [self._serialize_message(m) if hasattr(m, "content") else m for m in channel_values["messages"]]

            cfg = cp.config.get("configurable", {})
            parent_cfg = cp.parent_config.get("configurable", {}) if cp.parent_config else {}

            checkpoints.append(
                {
                    "checkpoint_id": cfg.get("checkpoint_id"),
                    "parent_checkpoint_id": parent_cfg.get("checkpoint_id"),
                    "ts": cp.checkpoint.get("ts"),
                    "metadata": cp.metadata,
                    "values": channel_values,
                    "pending_writes": [{"task_id": w[0], "channel": w[1], "value": w[2]} for w in getattr(cp, "pending_writes", [])],
                }
            )

        # Sort globally by timestamp to prevent partial ordering issues caused by different namespaces (e.g., subgraphs)
        checkpoints.sort(key=lambda x: x["ts"] if x["ts"] else "")

        result = {"thread_id": thread_id, "checkpoints": checkpoints}
        print(f"[DeerFlowClient] Retrieved thread {thread_id} with {len(checkpoints)} checkpoints")
        return result

    # ------------------------------------------------------------------
    # Public API — conversation
    # ------------------------------------------------------------------

    def stream(
        self,
        message: str,
        *,
        thread_id: str | None = None,
        **kwargs,
    ) -> Generator[StreamEvent, None, None]:
        """Stream a conversation turn, yielding events incrementally.

        Each call sends one user message and yields events until the agent
        finishes its turn. A ``checkpointer`` must be provided at init time
        for multi-turn context to be preserved across calls.

        Event types align with the LangGraph SSE protocol so that
        consumers can switch between HTTP streaming and embedded mode
        without changing their event-handling logic.

        Token-level streaming
        ~~~~~~~~~~~~~~~~~~~~~
        This method subscribes to LangGraph's ``messages`` stream mode, so
        ``messages-tuple`` events for AI text are emitted as **deltas** as
        the model generates tokens, not as one cumulative dump at node
        completion.  Each delta carries a stable ``id`` — consumers that
        want the full text must accumulate ``content`` per ``id``.
        ``chat()`` already does this for you.

        Tool calls and tool results are still emitted once per logical
        message.  ``values`` events continue to carry full state snapshots
        after each graph node finishes; AI text already delivered via the
        ``messages`` stream is **not** re-synthesized from the snapshot to
        avoid duplicate deliveries.

        Why not reuse Gateway's ``run_agent``?
        ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        Gateway (``runtime/runs/worker.py``) has a complete streaming
        pipeline: ``run_agent`` → ``StreamBridge`` → ``sse_consumer``.  It
        looks like this client duplicates that work, but the two paths
        serve different audiences and **cannot** share execution:

        * ``run_agent`` is ``async def`` and uses ``agent.astream()``;
          this method is a sync generator using ``agent.stream()`` so
          callers can write ``for event in client.stream(...)`` without
          touching asyncio.  Bridging the two would require spinning up
          an event loop + thread per call.
        * Gateway events are JSON-serialized by ``serialize()`` for SSE
          wire transmission.  This client yields in-process stream event
          payloads directly as Python data structures (``StreamEvent``
          with ``data`` as a plain ``dict``), without the extra
          JSON/SSE serialization layer used for HTTP delivery.
        * ``StreamBridge`` is an asyncio-queue decoupling producers from
          consumers across an HTTP boundary (``Last-Event-ID`` replay,
          heartbeats, multi-subscriber fan-out).  A single in-process
          caller with a direct iterator needs none of that.

        So ``DeerFlowClient.stream()`` is a parallel, sync, in-process
        consumer of the same ``create_agent()`` factory — not a wrapper
        around Gateway.  The two paths **should** stay in sync on which
        LangGraph stream modes they subscribe to; that invariant is
        enforced by ``tests/test_client.py::test_messages_mode_emits_token_deltas``
        rather than by a shared constant, because the three layers
        (Graph, Platform SDK, HTTP) each use their own naming
        (``messages`` vs ``messages-tuple``) and cannot literally share
        a string.

        Args:
            message: User message text.
            thread_id: Thread ID for conversation context. Auto-generated if None.
            **kwargs: Override client defaults (model_name, thinking_enabled,
                plan_mode, subagent_enabled, recursion_limit).

        Yields:
            StreamEvent with one of:
            - type="values"          data={"title": str|None, "messages": [...], "artifacts": [...]}
            - type="custom"          data={...}
            - type="messages-tuple"  data={"type": "ai", "content": <delta>, "id": str}
            - type="messages-tuple"  data={"type": "ai", "content": <delta>, "id": str, "usage_metadata": {...}}
            - type="messages-tuple"  data={"type": "ai", "content": "", "id": str, "tool_calls": [...]}
            - type="messages-tuple"  data={"type": "ai", "content": "", "id": str, "additional_kwargs": {...}}
            - type="messages-tuple"  data={"type": "tool", "content": str, "name": str, "tool_call_id": str, "id": str}
            - type="end"             data={"usage": {"input_tokens": int, "output_tokens": int, "total_tokens": int}}
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())
            print(f"[DeerFlowClient] Auto-generated thread_id: {thread_id}")

        print(f"[DeerFlowClient] Starting stream: thread_id={thread_id}, message_length={len(message)}")
        
        config = self._get_runnable_config(thread_id, **kwargs)

        # Inject tracing callbacks and Langfuse trace metadata at the graph
        # invocation root so the embedded client matches the gateway worker's
        # behaviour: a single ``stream()`` produces one trace with all node /
        # LLM / tool calls nested under it, and the trace carries the reserved
        # ``langfuse_session_id`` / ``langfuse_user_id`` keys that the Langfuse
        # CallbackHandler lifts onto the root trace's ``sessionId`` / ``userId``.
        tracing_callbacks = build_tracing_callbacks()
        if tracing_callbacks:
            existing_callbacks = list(config.get("callbacks") or [])
            config["callbacks"] = [*existing_callbacks, *tracing_callbacks]
            print(f"[DeerFlowClient] Injected {len(tracing_callbacks)} tracing callbacks")

        configurable = config.get("configurable") or {}
        inject_langfuse_metadata(
            config,
            thread_id=thread_id,
            user_id=get_effective_user_id(),
            assistant_id=self._agent_name or "lead-agent",
            model_name=configurable.get("model_name") or self._model_name,
            environment=self._environment or os.environ.get("DEER_FLOW_ENV") or os.environ.get("ENVIRONMENT"),
        )

        self._ensure_agent(config)

        state: dict[str, Any] = {"messages": [HumanMessage(content=message)]}
        context = {"thread_id": thread_id}
        if self._agent_name:
            context["agent_name"] = self._agent_name

        seen_ids: set[str] = set()
        # Cross-mode handoff: ids already streamed via LangGraph ``messages``
        # mode so the ``values`` path skips re-synthesis of the same message.
        streamed_ids: set[str] = set()
        # The same message id carries identical cumulative ``usage_metadata``
        # in both the final ``messages`` chunk and the values snapshot —
        # count it only on whichever arrives first.
        counted_usage_ids: set[str] = set()
        sent_additional_kwargs_by_id: dict[str, dict[str, Any]] = {}
        cumulative_usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

        def _account_usage(msg_id: str | None, usage: Any) -> dict | None:
            """Add *usage* to cumulative totals if this id has not been counted.

            ``usage`` is a ``langchain_core.messages.UsageMetadata`` TypedDict
            or ``None``; typed as ``Any`` because TypedDicts are not
            structurally assignable to plain ``dict`` under strict type
            checking.  Returns the normalized usage dict (for attaching
            to an event) when we accepted it, otherwise ``None``.
            """
            if not usage:
                return None
            if msg_id and msg_id in counted_usage_ids:
                return None
            if msg_id:
                counted_usage_ids.add(msg_id)
            input_tokens = usage.get("input_tokens", 0) or 0
            output_tokens = usage.get("output_tokens", 0) or 0
            total_tokens = usage.get("total_tokens", 0) or 0
            cumulative_usage["input_tokens"] += input_tokens
            cumulative_usage["output_tokens"] += output_tokens
            cumulative_usage["total_tokens"] += total_tokens
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }

        def _unsent_additional_kwargs(msg_id: str | None, additional_kwargs: dict[str, Any] | None) -> dict[str, Any] | None:
            if not additional_kwargs:
                return None
            if not msg_id:
                return additional_kwargs

            sent = sent_additional_kwargs_by_id.setdefault(msg_id, {})
            delta = {key: value for key, value in additional_kwargs.items() if sent.get(key) != value}
            if not delta:
                return None

            sent.update(delta)
            return delta

        event_count = 0
        for item in self._agent.stream(
            state,
            config=config,
            context=context,
            stream_mode=["values", "messages", "custom"],
        ):
            if isinstance(item, tuple) and len(item) == 2:
                mode, chunk = item
                mode = str(mode)
            else:
                mode, chunk = "values", item

            if mode == "custom":
                event_count += 1
                yield StreamEvent(type="custom", data=chunk)
                continue

            if mode == "messages":
                # LangGraph ``messages`` mode emits ``(message_chunk, metadata)``.
                if isinstance(chunk, tuple) and len(chunk) == 2:
                    msg_chunk, _metadata = chunk
                else:
                    msg_chunk = chunk

                msg_id = getattr(msg_chunk, "id", None)

                if isinstance(msg_chunk, AIMessage):
                    text = self._extract_text(msg_chunk.content)
                    additional_kwargs = self._serialize_additional_kwargs(msg_chunk)
                    counted_usage = _account_usage(msg_id, msg_chunk.usage_metadata)
                    sent_additional_kwargs = False

                    if text:
                        if msg_id:
                            streamed_ids.add(msg_id)
                        additional_kwargs_delta = _unsent_additional_kwargs(msg_id, additional_kwargs)
                        event_count += 1
                        yield self._ai_text_event(
                            msg_id,
                            text,
                            counted_usage,
                            additional_kwargs_delta,
                        )
                        sent_additional_kwargs = bool(additional_kwargs_delta)

                    if msg_chunk.tool_calls:
                        if msg_id:
                            streamed_ids.add(msg_id)
                        additional_kwargs_delta = None if sent_additional_kwargs else _unsent_additional_kwargs(msg_id, additional_kwargs)
                        print(f"[DeerFlowClient] Agent calling tools: {[tc['name'] for tc in msg_chunk.tool_calls]}")
                        event_count += 1
                        yield self._ai_tool_calls_event(
                            msg_id,
                            msg_chunk.tool_calls,
                            additional_kwargs_delta,
                        )

                elif isinstance(msg_chunk, ToolMessage):
                    if msg_id:
                        streamed_ids.add(msg_id)
                    print(f"[DeerFlowClient] Received tool result: name={msg_chunk.name}, tool_call_id={msg_chunk.tool_call_id}")
                    event_count += 1
                    yield self._tool_message_event(msg_chunk)
                continue

            # mode == "values"
            messages = chunk.get("messages", [])

            for msg in messages:
                msg_id = getattr(msg, "id", None)
                if msg_id and msg_id in seen_ids:
                    continue
                if msg_id:
                    seen_ids.add(msg_id)

                # Already streamed via ``messages`` mode; only (defensively)
                # capture usage here and skip re-synthesizing the event.
                if msg_id and msg_id in streamed_ids:
                    if isinstance(msg, AIMessage):
                        _account_usage(msg_id, getattr(msg, "usage_metadata", None))
                        additional_kwargs = self._serialize_additional_kwargs(msg)
                        additional_kwargs_delta = _unsent_additional_kwargs(msg_id, additional_kwargs)
                        if additional_kwargs_delta:
                            # Metadata-only follow-up: ``messages-tuple`` has no
                            # dedicated attribution event, so clients should
                            # merge this empty-content AI event by message id
                            # and ignore it for text rendering.
                            event_count += 1
                            yield self._ai_text_event(msg_id, "", None, additional_kwargs_delta)
                    continue

                if isinstance(msg, AIMessage):
                    counted_usage = _account_usage(msg_id, msg.usage_metadata)
                    additional_kwargs = self._serialize_additional_kwargs(msg)
                    sent_additional_kwargs = False

                    if msg.tool_calls:
                        additional_kwargs_delta = _unsent_additional_kwargs(msg_id, additional_kwargs)
                        tool_names = [tc["name"] for tc in msg.tool_calls] if msg.tool_calls else []
                        print(f"[DeerFlowClient] Agent calling tools (values mode): {tool_names}")
                        event_count += 1
                        yield self._ai_tool_calls_event(
                            msg_id,
                            msg.tool_calls,
                            additional_kwargs_delta,
                        )
                        sent_additional_kwargs = bool(additional_kwargs_delta)

                    text = self._extract_text(msg.content)
                    if text:
                        additional_kwargs_delta = None if sent_additional_kwargs else _unsent_additional_kwargs(msg_id, additional_kwargs)
                        event_count += 1
                        yield self._ai_text_event(
                            msg_id,
                            text,
                            counted_usage,
                            additional_kwargs_delta,
                        )
                    elif msg_id:
                        additional_kwargs_delta = None if sent_additional_kwargs else _unsent_additional_kwargs(msg_id, additional_kwargs)
                        if not additional_kwargs_delta:
                            continue
                        # See the metadata-only follow-up convention above.
                        event_count += 1
                        yield self._ai_text_event(msg_id, "", None, additional_kwargs_delta)

                elif isinstance(msg, ToolMessage):
                    print(f"[DeerFlowClient] Received tool result (values mode): name={msg.name}, tool_call_id={msg.tool_call_id}")
                    event_count += 1
                    yield self._tool_message_event(msg)

            # Emit a values event for each state snapshot
            event_count += 1
            yield StreamEvent(
                type="values",
                data={
                    "title": chunk.get("title"),
                    "messages": [self._serialize_message(m) for m in messages],
                    "artifacts": chunk.get("artifacts", []),
                },
            )

        event_count += 1
        yield StreamEvent(type="end", data={"usage": cumulative_usage})

        print(
            f"[DeerFlowClient] Stream completed: thread_id={thread_id}, events={event_count}, "
            f"input_tokens={cumulative_usage['input_tokens']}, "
            f"output_tokens={cumulative_usage['output_tokens']}, "
            f"total_tokens={cumulative_usage['total_tokens']}"
        )

    def chat(self, message: str, *, thread_id: str | None = None, **kwargs) -> str:
        """Send a message and return the final text response.

        Convenience wrapper around :meth:`stream` that accumulates delta
        ``messages-tuple`` events per ``id`` and returns the text of the
        **last** AI message to complete.  Intermediate AI messages (e.g.
        planner drafts) are discarded — only the final id's accumulated
        text is returned.  Use :meth:`stream` directly if you need every
        delta as it arrives.

        Args:
            message: User message text.
            thread_id: Thread ID for conversation context. Auto-generated if None.
            **kwargs: Override client defaults (same as stream()).

        Returns:
            The accumulated text of the last AI message, or empty string
            if no AI text was produced.
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())
            print(f"[DeerFlowClient] Auto-generated thread_id for chat: {thread_id}")

        print(f"[DeerFlowClient] Starting chat: thread_id={thread_id}, message_length={len(message)}")
        
        # Per-id delta lists joined once at the end — avoids the O(n²) cost
        # of repeated ``str + str`` on a growing buffer for long responses.
        chunks: dict[str, list[str]] = {}
        last_id: str = ""
        for event in self.stream(message, thread_id=thread_id, **kwargs):
            if event.type == "messages-tuple" and event.data.get("type") == "ai":
                msg_id = event.data.get("id") or ""
                delta = event.data.get("content", "")
                if delta:
                    chunks.setdefault(msg_id, []).append(delta)
                    last_id = msg_id

        response = "".join(chunks.get(last_id, ()))
        print(
            f"[DeerFlowClient] Chat completed: thread_id={thread_id}, response_length={len(response)}, messages_count={len(chunks)}"
        )
        return response

    # ------------------------------------------------------------------
    # Public API — configuration queries
    # ------------------------------------------------------------------

    def list_models(self) -> dict:
        """List available models from configuration.

        Returns:
            Dict with "models" key containing list of model info dicts,
            matching the Gateway API ``ModelsListResponse`` schema.
        """
        print("[DeerFlowClient] Listing available models")
        token_usage_enabled = getattr(getattr(self._app_config, "token_usage", None), "enabled", False)
        if not isinstance(token_usage_enabled, bool):
            token_usage_enabled = False

        models = [
            {
                "name": model.name,
                "model": getattr(model, "model", None),
                "display_name": getattr(model, "display_name", None),
                "description": getattr(model, "description", None),
                "supports_thinking": getattr(model, "supports_thinking", False),
                "supports_reasoning_effort": getattr(model, "supports_reasoning_effort", False),
            }
            for model in self._app_config.models
        ]

        result = {
            "models": models,
            "token_usage": {"enabled": token_usage_enabled},
        }

        print(f"[DeerFlowClient] Found {len(models)} available models")
        return result

    def list_skills(self, enabled_only: bool = False) -> dict:
        """List available skills.

        Args:
            enabled_only: If True, only return enabled skills.

        Returns:
            Dict with "skills" key containing list of skill info dicts,
            matching the Gateway API ``SkillsListResponse`` schema.
        """
        print(f"[DeerFlowClient] Listing skills (enabled_only={enabled_only})", )
        skills = [
            {
                "name": s.name,
                "description": s.description,
                "license": s.license,
                "category": s.category,
                "enabled": s.enabled,
            }
            for s in get_or_new_skill_storage().load_skills(enabled_only=enabled_only)
        ]

        result = {"skills": skills}
        print(f"[DeerFlowClient] Found {len(skills)} skills")
        return result

    def get_memory(self) -> dict:
        """Get current memory data.

        Returns:
            Memory data dict (see src/agents/memory/updater.py for structure).
        """
        print("[DeerFlowClient] Retrieving memory data")
        from deerflow.agents.memory.updater import get_memory_data

        memory_data = get_memory_data(user_id=get_effective_user_id())
        print(f"[DeerFlowClient] Retrieved memory data with {len(memory_data.get('facts', []))} facts")
        return memory_data

    def export_memory(self) -> dict:
        """Export current memory data for backup or transfer."""
        print("[DeerFlowClient] Exporting memory data")
        from deerflow.agents.memory.updater import get_memory_data

        memory_data = get_memory_data(user_id=get_effective_user_id())
        print(f"[DeerFlowClient] Exported memory data: {len(memory_data.get('facts', []))} facts")
        return memory_data

    def import_memory(self, memory_data: dict) -> dict:
        """Import and persist full memory data."""
        print(f"[DeerFlowClient] Importing memory data: {len(memory_data.get('facts', []))} facts")
        from deerflow.agents.memory.updater import import_memory_data

        result = import_memory_data(memory_data, user_id=get_effective_user_id())
        print("[DeerFlowClient] Memory import completed successfully")
        return result

    def get_model(self, name: str) -> dict | None:
        """Get a specific model's configuration by name.

        Args:
            name: Model name.

        Returns:
            Model info dict matching the Gateway API ``ModelResponse``
            schema, or None if not found.
        """
        print(f"[DeerFlowClient] Retrieving model config: {name}")
        model = self._app_config.get_model_config(name)
        if model is None:
            logger.warning("[DeerFlowClient] Model not found: %s", name)
            return None

        result = {
            "name": model.name,
            "model": getattr(model, "model", None),
            "display_name": getattr(model, "display_name", None),
            "description": getattr(model, "description", None),
            "supports_thinking": getattr(model, "supports_thinking", False),
            "supports_reasoning_effort": getattr(model, "supports_reasoning_effort", False),
        }

        print(f"[DeerFlowClient] Retrieved model config: {name}")
        return result

    # ------------------------------------------------------------------
    # Public API — MCP configuration
    # ------------------------------------------------------------------

    def get_mcp_config(self) -> dict:
        """Get MCP server configurations.

        Returns:
            Dict with "mcp_servers" key mapping server name to config,
            matching the Gateway API ``McpConfigResponse`` schema.
        """
        print("[DeerFlowClient] Retrieving MCP configuration")
        config = get_extensions_config()
        result = {"mcp_servers": {name: server.model_dump() for name, server in config.mcp_servers.items()}}
        print(f"[DeerFlowClient] Found {len(result['mcp_servers'])} MCP servers")
        return result

    def update_mcp_config(self, mcp_servers: dict[str, dict]) -> dict:
        """Update MCP server configurations.

        Writes to extensions_config.json and reloads the cache.

        Args:
            mcp_servers: Dict mapping server name to config dict.
                Each value should contain keys like enabled, type, command, args, env, url, etc.

        Returns:
            Dict with "mcp_servers" key, matching the Gateway API
            ``McpConfigResponse`` schema.

        Raises:
            OSError: If the config file cannot be written.
        """
        print(f"[DeerFlowClient] Updating MCP configuration: {len(mcp_servers)} servers")
        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            print("[DeerFlowClient] Cannot locate extensions_config.json")
            raise FileNotFoundError("Cannot locate extensions_config.json. Set DEER_FLOW_EXTENSIONS_CONFIG_PATH or ensure it exists in the project root.")

        current_config = get_extensions_config()

        config_data = {
            "mcpServers": mcp_servers,
            "skills": {name: {"enabled": skill.enabled} for name, skill in current_config.skills.items()},
        }

        self._atomic_write_json(config_path, config_data)

        self._agent = None
        self._agent_config_key = None
        reloaded = reload_extensions_config()
        
        result = {"mcp_servers": {name: server.model_dump() for name, server in reloaded.mcp_servers.items()}}
        print("[DeerFlowClient] MCP configuration updated successfully")
        return result

    # ------------------------------------------------------------------
    # Public API — skills management
    # ------------------------------------------------------------------

    def get_skill(self, name: str) -> dict | None:
        """Get a specific skill by name.

        Args:
            name: Skill name.

        Returns:
            Skill info dict, or None if not found.
        """
        print(f"[DeerFlowClient] Retrieving skill: {name}")
        from deerflow.skills.storage import get_or_new_skill_storage

        skill = next((s for s in get_or_new_skill_storage().load_skills(enabled_only=False) if s.name == name), None)
        if skill is None:
            logger.warning("[DeerFlowClient] Skill not found: %s", name)
            return None

        result = {
            "name": skill.name,
            "description": skill.description,
            "license": skill.license,
            "category": skill.category,
            "enabled": skill.enabled,
        }

        print(f"[DeerFlowClient] Retrieved skill: {name} (enabled={skill.enabled})")
        return result

    def update_skill(self, name: str, *, enabled: bool) -> dict:
        """Update a skill's enabled status.

        Args:
            name: Skill name.
            enabled: New enabled status.

        Returns:
            Updated skill info dict.

        Raises:
            ValueError: If the skill is not found.
            OSError: If the config file cannot be written.
        """
        print(f"[DeerFlowClient] Updating skill: {name}, enabled={enabled}")
        from deerflow.skills.storage import get_or_new_skill_storage

        skills = get_or_new_skill_storage().load_skills(enabled_only=False)
        skill = next((s for s in skills if s.name == name), None)
        if skill is None:
            print(f"[DeerFlowClient] Skill not found: {name}")
            raise ValueError(f"Skill '{name}' not found")

        config_path = ExtensionsConfig.resolve_config_path()
        if config_path is None:
            print("[DeerFlowClient] Cannot locate extensions_config.json")
            raise FileNotFoundError("Cannot locate extensions_config.json. Set DEER_FLOW_EXTENSIONS_CONFIG_PATH or ensure it exists in the project root.")

        extensions_config = get_extensions_config()
        extensions_config.skills[name] = SkillStateConfig(enabled=enabled)

        config_data = {
            "mcpServers": {n: s.model_dump() for n, s in extensions_config.mcp_servers.items()},
            "skills": {n: {"enabled": sc.enabled} for n, sc in extensions_config.skills.items()},
        }

        self._atomic_write_json(config_path, config_data)

        self._agent = None
        self._agent_config_key = None
        reload_extensions_config()

        updated = next((s for s in get_or_new_skill_storage().load_skills(enabled_only=False) if s.name == name), None)
        if updated is None:
            print(f"[DeerFlowClient] Skill '{name}' disappeared after update")
            raise RuntimeError(f"Skill '{name}' disappeared after update")

        result = {
            "name": updated.name,
            "description": updated.description,
            "license": updated.license,
            "category": updated.category,
            "enabled": updated.enabled,
        }

        print(f"[DeerFlowClient] Skill updated successfully: {name}, enabled={enabled}")
        return result

    def install_skill(self, skill_path: str | Path) -> dict:
        """Install a skill from a .skill archive (ZIP).

        Args:
            skill_path: Path to the .skill file.

        Returns:
            Dict with success, skill_name, message.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is invalid.
        """
        print(f"[DeerFlowClient] Installing skill from: {skill_path}")
        result = get_or_new_skill_storage().install_skill_from_archive(skill_path)

        if result.get("success"):
            print(f"[DeerFlowClient] Skill installed successfully: {result.get('skill_name')}")
            # Reset agent to pick up new skill
            self.reset_agent()
        else:
            print(f"[DeerFlowClient] Skill installation failed: {result.get('message')}")

        return result

    # ------------------------------------------------------------------
    # Public API — memory management
    # ------------------------------------------------------------------

    def reload_memory(self) -> dict:
        """Reload memory data from file, forcing cache invalidation.

        Returns:
            The reloaded memory data dict.
        """
        print("[DeerFlowClient] Reloading memory data")
        from deerflow.agents.memory.updater import reload_memory_data

        memory_data = reload_memory_data(user_id=get_effective_user_id())
        print(f"[DeerFlowClient] Memory reloaded: {len(memory_data.get('facts', []))} facts")
        return memory_data

    def clear_memory(self) -> dict:
        """Clear all persisted memory data."""
        logger.warning("[DeerFlowClient] Clearing all memory data")
        from deerflow.agents.memory.updater import clear_memory_data

        result = clear_memory_data(user_id=get_effective_user_id())
        print("[DeerFlowClient] Memory cleared successfully")
        return result

    def create_memory_fact(self, content: str, category: str = "context", confidence: float = 0.5) -> dict:
        """Create a single fact manually."""
        print(f"[DeerFlowClient] Creating memory fact: category={category}, confidence={confidence:.2f}")
        from deerflow.agents.memory.updater import create_memory_fact

        result = create_memory_fact(content=content, category=category, confidence=confidence)
        print(f"[DeerFlowClient] Memory fact created: id={result.get('id')}")
        return result

    def delete_memory_fact(self, fact_id: str) -> dict:
        """Delete a single fact from memory by fact id."""
        print(f"[DeerFlowClient] Deleting memory fact: {fact_id}")
        from deerflow.agents.memory.updater import delete_memory_fact

        result = delete_memory_fact(fact_id)
        print(f"[DeerFlowClient] Memory fact deleted: {fact_id}")
        return result

    def update_memory_fact(
        self,
        fact_id: str,
        content: str | None = None,
        category: str | None = None,
        confidence: float | None = None,
    ) -> dict:
        """Update a single fact manually, preserving omitted fields."""
        print(f"[DeerFlowClient] Updating memory fact: {fact_id}")
        from deerflow.agents.memory.updater import update_memory_fact

        result = update_memory_fact(
            fact_id=fact_id,
            content=content,
            category=category,
            confidence=confidence,
        )
        print(f"[DeerFlowClient] Memory fact updated: {fact_id}")
        return result

    def get_memory_config(self) -> dict:
        """Get memory system configuration.

        Returns:
            Memory config dict.
        """
        print("[DeerFlowClient] Retrieving memory configuration")
        from deerflow.config.memory_config import get_memory_config

        config = get_memory_config()
        result = {
            "enabled": config.enabled,
            "storage_path": config.storage_path,
            "debounce_seconds": config.debounce_seconds,
            "max_facts": config.max_facts,
            "fact_confidence_threshold": config.fact_confidence_threshold,
            "injection_enabled": config.injection_enabled,
            "max_injection_tokens": config.max_injection_tokens,
            "token_counting": config.token_counting,
            "guaranteed_categories": config.guaranteed_categories,
            "guaranteed_token_budget": config.guaranteed_token_budget,
        }
        
        print("[DeerFlowClient] Retrieved memory configuration")
        return result

    def get_memory_status(self) -> dict:
        """Get memory status: config + current data.

        Returns:
            Dict with "config" and "data" keys.
        """
        print("[DeerFlowClient] Retrieving memory status")
        return {
            "config": self.get_memory_config(),
            "data": self.get_memory(),
        }

    # ------------------------------------------------------------------
    # Public API — file uploads
    # ------------------------------------------------------------------

    def upload_files(self, thread_id: str, files: list[str | Path]) -> dict:
        """Upload local files into a thread's uploads directory.

        For PDF, PPT, Excel, and Word files, they are also converted to Markdown.

        Args:
            thread_id: Target thread ID.
            files: List of local file paths to upload.

        Returns:
            Dict with success, files, message — matching the Gateway API
            ``UploadResponse`` schema.

        Raises:
            FileNotFoundError: If any file does not exist.
            ValueError: If any supplied path exists but is not a regular file.
        """
        print(f"[DeerFlowClient] Uploading files: thread_id={thread_id}, files_count={len(files)}")
        from deerflow.utils.file_conversion import CONVERTIBLE_EXTENSIONS, convert_file_to_markdown

        # Validate all files upfront to avoid partial uploads.
        resolved_files = []
        seen_names: set[str] = set()
        has_convertible_file = False
        for f in files:
            p = Path(f)
            if not p.exists():
                print(f"[DeerFlowClient] File not found: {f}")
                raise FileNotFoundError(f"File not found: {f}")
            if not p.is_file():
                print(f"[DeerFlowClient] Path is not a file: {f}")
                raise ValueError(f"Path is not a file: {f}")
            dest_name = claim_unique_filename(p.name, seen_names)
            resolved_files.append((p, dest_name))
            if not has_convertible_file and p.suffix.lower() in CONVERTIBLE_EXTENSIONS:
                has_convertible_file = True

        uploads_dir = ensure_uploads_dir(thread_id)
        uploaded_files: list[dict] = []

        conversion_pool = None
        if has_convertible_file:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                conversion_pool = None
            else:
                import concurrent.futures

                # Reuse one worker when already inside an event loop to avoid
                # creating a new ThreadPoolExecutor per converted file.
                conversion_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        def _convert_in_thread(path: Path):
            return asyncio.run(convert_file_to_markdown(path))

        try:
            for src_path, dest_name in resolved_files:
                dest = uploads_dir / dest_name
                shutil.copy2(src_path, dest)

                info: dict[str, Any] = {
                    "filename": dest_name,
                    "size": dest.stat().st_size,
                    "path": str(dest),
                    "virtual_path": upload_virtual_path(dest_name),
                    "artifact_url": upload_artifact_url(thread_id, dest_name),
                }
                if dest_name != src_path.name:
                    info["original_filename"] = src_path.name

                if src_path.suffix.lower() in CONVERTIBLE_EXTENSIONS:
                    try:
                        if conversion_pool is not None:
                            md_path = conversion_pool.submit(_convert_in_thread, dest).result()
                        else:
                            md_path = asyncio.run(convert_file_to_markdown(dest))
                    except Exception:
                        logger.warning(
                            "[DeerFlowClient] Failed to convert %s to markdown",
                            src_path.name,
                            exc_info=True,
                        )
                        md_path = None

                    if md_path is not None:
                        info["markdown_file"] = md_path.name
                        info["markdown_path"] = str(uploads_dir / md_path.name)
                        info["markdown_virtual_path"] = upload_virtual_path(md_path.name)
                        info["markdown_artifact_url"] = upload_artifact_url(thread_id, md_path.name)

                uploaded_files.append(info)
        finally:
            if conversion_pool is not None:
                conversion_pool.shutdown(wait=True)

        print(f"[DeerFlowClient] Files uploaded successfully: thread_id={thread_id}, uploaded={len(uploaded_files)}")
        return {
            "success": True,
            "files": uploaded_files,
            "message": f"Successfully uploaded {len(uploaded_files)} file(s)",
        }

    def list_uploads(self, thread_id: str) -> dict:
        """List files in a thread's uploads directory.

        Args:
            thread_id: Thread ID.

        Returns:
            Dict with "files" and "count" keys, matching the Gateway API
            ``list_uploaded_files`` response.
        """
        print(f"[DeerFlowClient] Listing uploads: thread_id={thread_id}")
        uploads_dir = get_uploads_dir(thread_id)
        result = list_files_in_dir(uploads_dir)
        enriched = enrich_file_listing(result, thread_id)
        print(f"[DeerFlowClient] Found {enriched['count']} uploads")
        return enriched

    def delete_upload(self, thread_id: str, filename: str) -> dict:
        """Delete a file from a thread's uploads directory.

        Args:
            thread_id: Thread ID.
            filename: Filename to delete.

        Returns:
            Dict with success and message, matching the Gateway API
            ``delete_uploaded_file`` response.

        Raises:
            FileNotFoundError: If the file does not exist.
            PermissionError: If path traversal is detected.
        """
        print(f"[DeerFlowClient] Deleting upload: thread_id={thread_id}, filename={filename}")
        from deerflow.utils.file_conversion import CONVERTIBLE_EXTENSIONS

        uploads_dir = get_uploads_dir(thread_id)
        result = delete_file_safe(uploads_dir, filename, convertible_extensions=CONVERTIBLE_EXTENSIONS)
        print(f"[DeerFlowClient] Upload deleted: thread_id={thread_id}, filename={filename}")
        return result

    # ------------------------------------------------------------------
    # Public API — artifacts
    # ------------------------------------------------------------------

    def get_artifact(self, thread_id: str, path: str) -> tuple[bytes, str]:
        """Read an artifact file produced by the agent.

        Args:
            thread_id: Thread ID.
            path: Virtual path (e.g. "mnt/user-data/outputs/file.txt").

        Returns:
            Tuple of (file_bytes, mime_type).

        Raises:
            FileNotFoundError: If the artifact does not exist.
            ValueError: If the path is invalid.
        """
        print(f"[DeerFlowClient] Retrieving artifact: thread_id={thread_id}, path={path}")
        try:
            actual = get_paths().resolve_virtual_path(thread_id, path, user_id=get_effective_user_id())
        except ValueError as exc:
            if "traversal" in str(exc):
                from deerflow.uploads.manager import PathTraversalError

                raise PathTraversalError("Path traversal detected") from exc
            raise
        if not actual.exists():
            print(f"[DeerFlowClient] Artifact not found: {path}")
            raise FileNotFoundError(f"Artifact not found: {path}")
        if not actual.is_file():
            print(f"[DeerFlowClient] Path is not a file: {path}")
            raise ValueError(f"Path is not a file: {path}")

        mime_type, _ = mimetypes.guess_type(actual)
        print(f"[DeerFlowClient] Retrieved artifact: {path}, size={actual.stat().st_size} bytes")
        return actual.read_bytes(), mime_type or "application/octet-stream"
