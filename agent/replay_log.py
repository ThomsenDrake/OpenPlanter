"""Replay-capable LLM interaction logging with delta encoding."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

_OWNER_SLUG_MAX_CHARS = 24
TRACE_SCHEMA_VERSION = 2
TRACE_ENVELOPE = "openplanter.trace.event.v2"


def _normalize_owner_slug(owner: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", owner.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("._-")
    if not normalized:
        return "anon"
    return normalized[:_OWNER_SLUG_MAX_CHARS]


def _owner_hash(owner: str) -> str:
    return hashlib.sha1(owner.encode("utf-8")).hexdigest()[:8]


def _trace_event_id(*parts: object) -> str:
    digest = hashlib.sha1(":".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:12]
    return f"evt-{digest}"


@dataclass
class _ReplayFileState:
    """Shared sequencing state for a single replay log file."""

    lock: threading.RLock = field(default_factory=threading.RLock)
    next_seq: int | None = None


@dataclass
class ReplayLogger:
    """Logs every LLM API call so any individual call can be replayed exactly.

    Uses delta encoding: seq 0 stores a full messages snapshot, seq 1+
    store only messages appended since the previous call.

    Each conversation (root + subtasks) gets its own conversation_id.
    All records append to the same JSONL file in chronological order.
    """

    path: Path
    conversation_id: str = "root"
    force_snapshot_first_call: bool = False
    session_id: str | None = None
    turn_id: str | None = None
    _seq: int = field(default=0, init=False)
    _last_msg_count: int = field(default=0, init=False)
    _has_call: bool = field(default=False, init=False)
    _has_header: bool = field(default=False, init=False)
    _registry_path: Path = field(init=False, repr=False)
    _file_state: _ReplayFileState = field(init=False, repr=False)
    _provider: str | None = field(default=None, init=False)
    _model: str | None = field(default=None, init=False)

    _registry_lock: ClassVar[threading.Lock] = threading.Lock()
    _file_states: ClassVar[dict[Path, _ReplayFileState]] = {}

    def __post_init__(self) -> None:
        self._registry_path = self.path.resolve()
        self._file_state = self._get_file_state(self._registry_path)
        self._seq = self.current_seq
        self._hydrate_conversation_state()
        if self.force_snapshot_first_call:
            self._has_call = False
            self._last_msg_count = 0

    @property
    def needs_header(self) -> bool:
        return not self._has_header

    @property
    def current_seq(self) -> int:
        with self._file_state.lock:
            return self._ensure_next_seq_locked()

    def child(self, depth: int, step: int, owner: str | None = None) -> "ReplayLogger":
        """Create a child logger for a subtask conversation."""
        child_id = f"{self.conversation_id}/d{depth}s{step}"
        if owner is not None:
            child_id = f"{child_id}/o{_normalize_owner_slug(owner)}_{_owner_hash(owner)}"
        child_logger = ReplayLogger(
            path=self.path,
            conversation_id=child_id,
            force_snapshot_first_call=self.force_snapshot_first_call,
            session_id=self.session_id,
            turn_id=self.turn_id,
        )
        child_logger._provider = self._provider
        child_logger._model = self._model
        return child_logger

    def write_header(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        system_prompt: str,
        tool_defs: list[Any],
        reasoning_effort: str | None = None,
        temperature: float | None = None,
    ) -> None:
        recorded_at = datetime.now(timezone.utc).isoformat()
        line = self._next_line_number_locked()
        payload: dict[str, Any] = {
            "base_url": base_url,
            "system_prompt": system_prompt,
            "tool_defs": tool_defs,
        }
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort
        if temperature is not None:
            payload["temperature"] = temperature
        record: dict[str, Any] = {
            "type": "header",
            "conversation_id": self.conversation_id,
            "provider": provider,
            "model": model,
            "base_url": base_url,
            "system_prompt": system_prompt,
            "tool_defs": tool_defs,
            "schema_version": TRACE_SCHEMA_VERSION,
            "envelope": TRACE_ENVELOPE,
            "event_id": _trace_event_id(self._resolved_session_id(), self.conversation_id, "header"),
            "session_id": self._resolved_session_id(),
            "turn_id": self.turn_id,
            "recorded_at": recorded_at,
            "event_type": "session.started",
            "channel": "replay",
            "status": "info",
            "actor": {
                "kind": "runtime",
                "id": self.conversation_id,
                "display": "OpenPlanter",
                "runtime_family": "python",
                "provider": provider,
                "model": model,
            },
            "payload": payload,
            "failure": None,
            "provenance": {
                "record_locator": {"file": self.path.name, "line": line},
                "parent_event_id": None,
                "caused_by": [],
                "source_refs": [],
                "evidence_refs": [],
                "ontology_refs": [],
                "generated_from": {
                    "provider": provider,
                    "model": model,
                    "conversation_id": self.conversation_id,
                },
            },
            "compat": {
                "legacy_role": None,
                "legacy_kind": "header",
                "source_schema": "legacy-python-replay-v1",
            },
        }
        if reasoning_effort is not None:
            record["reasoning_effort"] = reasoning_effort
        if temperature is not None:
            record["temperature"] = temperature
        with self._file_state.lock:
            self._append_locked(record)
        self._provider = provider
        self._model = model
        self._has_header = True

    def log_call(
        self,
        *,
        depth: int,
        step: int,
        messages: list[Any],
        response: Any,
        input_tokens: int = 0,
        output_tokens: int = 0,
        elapsed_sec: float = 0.0,
    ) -> None:
        with self._file_state.lock:
            seq = self._ensure_next_seq_locked()
            ts = datetime.now(timezone.utc).isoformat()
            line = self._next_line_number_locked()
            record: dict[str, Any] = {
                "type": "call",
                "conversation_id": self.conversation_id,
                "seq": seq,
                "depth": depth,
                "step": step,
                "ts": ts,
                "schema_version": TRACE_SCHEMA_VERSION,
                "envelope": TRACE_ENVELOPE,
                "event_id": _trace_event_id(self._resolved_session_id(), self.conversation_id, seq),
                "session_id": self._resolved_session_id(),
                "turn_id": self.turn_id,
                "recorded_at": ts,
                "event_type": "assistant.message",
                "channel": "replay",
                "status": "completed",
                "actor": {
                    "kind": "assistant",
                    "id": self.conversation_id,
                    "display": "OpenPlanter",
                    "runtime_family": "python",
                    "provider": self._provider,
                    "model": self._model,
                },
            }
            if not self._has_call:
                record["messages_snapshot"] = messages
            else:
                record["messages_delta"] = messages[self._last_msg_count:]
            record["response"] = response
            record["input_tokens"] = input_tokens
            record["output_tokens"] = output_tokens
            record["elapsed_sec"] = round(elapsed_sec, 3)
            record["payload"] = {
                "conversation_id": self.conversation_id,
                "depth": depth,
                "step": step,
                "messages_snapshot": record.get("messages_snapshot"),
                "messages_delta": record.get("messages_delta"),
                "response": response,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "elapsed_sec": round(elapsed_sec, 3),
            }
            record["failure"] = None
            record["provenance"] = {
                "record_locator": {"file": self.path.name, "line": line},
                "parent_event_id": None,
                "caused_by": [],
                "source_refs": [
                    {
                        "kind": "jsonl_record",
                        "file": self.path.name,
                        "line": line,
                        "event_id": record["event_id"],
                    }
                ],
                "evidence_refs": [],
                "ontology_refs": [],
                "generated_from": {
                    "provider": self._provider,
                    "model": self._model,
                    "conversation_id": self.conversation_id,
                },
            }
            record["compat"] = {
                "legacy_role": None,
                "legacy_kind": "call",
                "source_schema": "legacy-python-replay-v1",
            }

            self._append_locked(record)
            self._file_state.next_seq = seq + 1
            self._seq = self._file_state.next_seq
            self._last_msg_count = len(messages)
            self._has_call = True

    @classmethod
    def _get_file_state(cls, path: Path) -> _ReplayFileState:
        with cls._registry_lock:
            state = cls._file_states.get(path)
            if state is None:
                state = _ReplayFileState()
                cls._file_states[path] = state
            return state

    def _ensure_next_seq_locked(self) -> int:
        if self._file_state.next_seq is None:
            self._file_state.next_seq = self._scan_next_seq()
        return self._file_state.next_seq

    def _scan_next_seq(self) -> int:
        if not self.path.exists():
            return 0
        next_seq = 0
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            seq = record.get("seq")
            if isinstance(seq, int) and seq >= next_seq:
                next_seq = seq + 1
        return next_seq

    def _hydrate_conversation_state(self) -> None:
        with self._file_state.lock:
            if not self.path.exists():
                return
            msg_count = 0
            has_call = False
            has_header = False
            for raw_line in self.path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("conversation_id") != self.conversation_id:
                    continue
                record_type = self._record_kind(record)
                if record_type == "header":
                    has_header = True
                    continue
                if record_type != "call":
                    continue
                has_call = True
                snapshot = record.get("messages_snapshot")
                if not isinstance(snapshot, list):
                    payload = record.get("payload")
                    if isinstance(payload, dict):
                        snapshot = payload.get("messages_snapshot")
                if isinstance(snapshot, list):
                    msg_count = len(snapshot)
                    continue
                delta = record.get("messages_delta")
                if not isinstance(delta, list):
                    payload = record.get("payload")
                    if isinstance(payload, dict):
                        delta = payload.get("messages_delta")
                if isinstance(delta, list):
                    msg_count += len(delta)
        self._has_call = has_call
        self._has_header = has_header
        self._last_msg_count = msg_count

    def _resolved_session_id(self) -> str | None:
        if self.session_id is not None:
            return self.session_id
        parent_name = self.path.parent.name.strip()
        return parent_name or None

    def _next_line_number_locked(self) -> int:
        if not self.path.exists():
            return 1
        line_count = 0
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            if raw_line.strip():
                line_count += 1
        return line_count + 1

    @staticmethod
    def _record_kind(record: dict[str, Any]) -> str | None:
        record_type = record.get("type")
        if record_type in {"header", "call"}:
            return record_type
        compat = record.get("compat")
        if isinstance(compat, dict):
            legacy_kind = compat.get("legacy_kind")
            if legacy_kind in {"header", "call"}:
                return legacy_kind
        if record.get("envelope") != TRACE_ENVELOPE:
            return None
        if record.get("event_type") == "session.started":
            return "header"
        payload = record.get("payload")
        if isinstance(payload, dict):
            if isinstance(payload.get("messages_snapshot"), list) or isinstance(payload.get("messages_delta"), list):
                return "call"
        return None

    def _append_locked(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")
