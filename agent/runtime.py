from __future__ import annotations

import json
import re
import secrets
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import AgentConfig
from .engine import ContentDeltaCallback, ExternalContext, RLMEngine, StepCallback, TurnSummary
from .investigation_state import (
    build_question_reasoning_packet,
    default_state,
    load_investigation_state,
    migrate_legacy_state,
    normalize_legacy_state,
    project_to_wiki_graph,
    save_investigation_state,
    state_to_legacy_projection,
    upsert_legacy_observations,
)
from .retrieval import build_retrieval_packet
from .replay_log import ReplayLogger

EventCallback = Callable[[str], None]


class SessionError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{secrets.token_hex(3)}"


def _safe_component(text: str) -> str:
    component = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")
    return component or "artifact"


def _has_reasoning_content(packet: dict[str, Any]) -> bool:
    findings = packet.get("findings", {})
    if packet.get("focus_question_ids"):
        return True
    if packet.get("contradictions"):
        return True
    if packet.get("candidate_actions"):
        return True
    if not isinstance(findings, dict):
        return False
    return any(findings.get(key) for key in ("supported", "contested", "unresolved"))


def _result_status(result: str, loop_metrics: dict[str, Any]) -> str:
    reason = str(loop_metrics.get("termination_reason", "") or "")
    if reason == "cancelled":
        return "cancelled"
    if reason in {"model_error", "time_limit"}:
        return "error"
    if reason in {"budget_no_progress", "budget_cap", "finalization_stall"}:
        return "partial"
    if result.startswith("Partial completion for objective:"):
        return "partial"
    return "final"


SESSION_SCHEMA_VERSION = 2
SESSION_FORMAT = "openplanter.session.v2"
TRACE_SCHEMA_VERSION = 2
TRACE_ENVELOPE = "openplanter.trace.event.v2"
TURN_RECORD_FORMAT = "openplanter.trace.turn.v2"


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _turn_id(turn_index: int) -> str:
    return f"turn-{turn_index:06d}"


def _metadata_session_id(metadata: dict[str, Any], fallback: str) -> str:
    session_id = metadata.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id.strip()
    legacy_id = metadata.get("id")
    if isinstance(legacy_id, str) and legacy_id.strip():
        return legacy_id.strip()
    return fallback


def _metadata_workspace_path(metadata: dict[str, Any], fallback: str) -> str:
    workspace_path = metadata.get("workspace_path")
    if isinstance(workspace_path, str) and workspace_path.strip():
        return workspace_path
    workspace = metadata.get("workspace")
    if isinstance(workspace, str) and workspace.strip():
        return workspace
    return fallback


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _turn_outcome_status(status: str) -> str:
    return {
        "final": "completed",
        "error": "failed",
        "partial": "partial",
        "cancelled": "cancelled",
    }.get(status, "completed")


def _failure_for_result(
    status: str,
    loop_metrics: dict[str, Any],
    result: str,
) -> dict[str, Any] | None:
    reason = str(loop_metrics.get("termination_reason", "") or "")
    details = {"termination_reason": reason}
    if status == "cancelled":
        return {
            "code": "cancelled",
            "category": "user_action",
            "phase": "model_completion",
            "retryable": False,
            "resumable": True,
            "user_visible": True,
            "message": "Task cancelled.",
            "details": details,
        }
    if status == "error":
        if reason == "time_limit":
            code = "timeout"
            category = "runtime"
            message = "Turn exceeded the configured time limit."
        elif reason == "model_error":
            code = "provider_error"
            category = "external"
            message = "Model completion failed."
        else:
            code = "unknown_error"
            category = "unknown"
            message = f"Turn failed ({reason or 'unknown'})."
        return {
            "code": code,
            "category": category,
            "phase": "model_completion",
            "retryable": False,
            "resumable": True,
            "user_visible": True,
            "message": message,
            "details": details,
        }
    if status == "partial":
        return {
            "code": "degraded",
            "category": "runtime",
            "phase": "model_completion",
            "retryable": False,
            "resumable": True,
            "user_visible": True,
            "message": result if result.startswith("Partial completion") else f"Turn ended partially ({reason or 'unknown'}).",
            "details": details,
        }
    return None


def _event_type_for_legacy(event_type: str, payload: dict[str, Any]) -> str:
    if "." in event_type:
        return event_type
    if event_type == "session_started":
        return "session.resumed" if payload.get("resume") else "session.started"
    if event_type == "objective":
        return "turn.objective"
    if event_type == "step":
        return "step.summary"
    if event_type == "trace":
        return "trace.note"
    if event_type == "artifact":
        return "artifact.created"
    if event_type == "result":
        status = str(payload.get("status") or "")
        if status == "cancelled":
            return "turn.cancelled"
        if status == "error":
            return "turn.failed"
        if status == "partial":
            return "result.summary"
        return "assistant.final"
    return f"legacy.{event_type}"


def _event_status(event_type: str, payload: dict[str, Any]) -> str:
    if event_type in {"session.started", "session.resumed"}:
        return "info"
    if event_type == "turn.objective":
        return "started"
    if event_type.startswith("trace."):
        return "info"
    if event_type == "turn.failed":
        return "failed"
    if event_type == "turn.cancelled":
        return "cancelled"
    if event_type == "result.summary" and str(payload.get("status") or "") == "partial":
        return "partial"
    return "completed"


@dataclass
class SessionStore:
    workspace: Path
    session_root_dir: str = ".openplanter"
    _warnings: list[str] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        self.root = (self.workspace / self.session_root_dir).resolve()
        self.sessions = self.root / "sessions"
        self.sessions.mkdir(parents=True, exist_ok=True)

    def _session_dir(self, session_id: str) -> Path:
        return self.sessions / session_id

    def _metadata_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "metadata.json"

    def _state_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "state.json"

    def _investigation_state_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "investigation_state.json"

    def _graph_projection_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "graph_projection.json"

    def _events_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "events.jsonl"

    def _turns_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "turns.jsonl"

    def _artifacts_dir(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "artifacts"

    def _plan_dir(self, session_id: str) -> Path:
        """Directory where *.plan.md files live (same as session dir)."""
        return self._session_dir(session_id)

    def latest_session_id(self) -> str | None:
        session_dirs = [p for p in self.sessions.iterdir() if p.is_dir()]
        if not session_dirs:
            return None
        latest = max(session_dirs, key=lambda p: p.stat().st_mtime)
        return latest.name

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        session_dirs = sorted(
            (p for p in self.sessions.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        out: list[dict[str, Any]] = []
        for path in session_dirs[:limit]:
            meta_path = path / "metadata.json"
            meta: dict[str, Any] = {}
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    meta = {}
            session_id = _metadata_session_id(meta, path.name)
            out.append(
                {
                    "session_id": session_id,
                    "path": str(path),
                    "created_at": meta.get("created_at"),
                    "updated_at": meta.get("updated_at"),
                }
            )
        return out

    def open_session(
        self, session_id: str | None = None, resume: bool = False, investigation_id: str | None = None
    ) -> tuple[str, dict[str, Any], bool]:
        sid = session_id
        if resume and sid is None:
            sid = self.latest_session_id()
            if sid is None:
                raise SessionError("No previous sessions found to resume.")
        if sid is None:
            sid = _new_session_id()

        session_dir = self._session_dir(sid)
        created_new = False
        if resume:
            if not session_dir.exists():
                raise SessionError(f"Cannot resume missing session: {sid}")
        else:
            if session_dir.exists():
                sid = f"{sid}-{secrets.token_hex(2)}"
                session_dir = self._session_dir(sid)
            session_dir.mkdir(parents=True, exist_ok=True)
            created_new = True

        session_dir.mkdir(parents=True, exist_ok=True)
        self._artifacts_dir(sid).mkdir(parents=True, exist_ok=True)

        meta_path = self._metadata_path(sid)
        if not meta_path.exists():
            meta = self._canonicalize_metadata({}, sid, continuity_mode="resume" if resume else "new")
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        else:
            self._touch_metadata(sid, continuity_mode="resume" if resume else None)

        state = self.load_state(sid)

        # Store active_investigation_id in typed state if provided
        if investigation_id is not None and isinstance(investigation_id, str) and investigation_id.strip():
            typed_state = self.load_typed_state(sid)
            typed_state["active_investigation_id"] = investigation_id.strip()
            investigation_path = self._investigation_state_path(sid)
            save_investigation_state(investigation_path, typed_state)
            try:
                _write_investigation_homepage(
                    workspace=self.workspace,
                    session_root_dir=self.session_root_dir,
                    session_id=sid,
                    state=typed_state,
                )
            except (AttributeError, OSError, TypeError):
                pass

        return sid, state, created_new

    def _warn(self, message: str) -> None:
        self._warnings.append(message)

    def drain_warnings(self) -> list[str]:
        warnings = list(self._warnings)
        self._warnings.clear()
        return warnings

    def _try_load_investigation_state(
        self,
        investigation_path: Path,
        *,
        on_invalid: str,
    ) -> dict[str, Any] | None:
        try:
            return load_investigation_state(investigation_path)
        except json.JSONDecodeError:
            self._warn(
                f"Session investigation state is invalid JSON: {investigation_path}; {on_invalid}."
            )
            return None

    def load_state(self, session_id: str) -> dict[str, Any]:
        investigation_path = self._investigation_state_path(session_id)
        if investigation_path.exists():
            typed_state = self._try_load_investigation_state(
                investigation_path,
                on_invalid="falling back to legacy state",
            )
            if typed_state is not None:
                return state_to_legacy_projection(typed_state, session_id=session_id)

        state_path = self._state_path(session_id)
        if not state_path.exists():
            return {
                "session_id": session_id,
                "saved_at": _utc_now(),
                "external_observations": [],
            }
        try:
            raw_state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SessionError(f"Session state is invalid JSON: {state_path}") from exc
        if not isinstance(raw_state, dict):
            raise SessionError(f"Session state must be a JSON object: {state_path}")
        return normalize_legacy_state(session_id, raw_state)

    def load_typed_state(self, session_id: str) -> dict[str, Any]:
        investigation_path = self._investigation_state_path(session_id)
        if investigation_path.exists():
            typed_state = self._try_load_investigation_state(
                investigation_path,
                on_invalid="continuing without typed reasoning state",
            )
            if typed_state is not None:
                return typed_state

        state_path = self._state_path(session_id)
        if not state_path.exists():
            return default_state(session_id=session_id)
        try:
            raw_state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SessionError(f"Session state is invalid JSON: {state_path}") from exc
        if not isinstance(raw_state, dict):
            raise SessionError(f"Session state must be a JSON object: {state_path}")
        return migrate_legacy_state(session_id=session_id, legacy_state=raw_state)

    def save_state(self, session_id: str, state: dict[str, Any]) -> None:
        normalized_legacy = normalize_legacy_state(session_id, state)
        state_path = self._state_path(session_id)
        state_path.write_text(json.dumps(normalized_legacy, indent=2), encoding="utf-8")

        investigation_path = self._investigation_state_path(session_id)
        if investigation_path.exists():
            typed_state = self._try_load_investigation_state(
                investigation_path,
                on_invalid="preserving the corrupt typed state file and writing legacy state only",
            )
            if typed_state is None:
                self._touch_metadata(session_id)
                return
        else:
            typed_state = migrate_legacy_state(session_id=session_id, legacy_state=normalized_legacy)

        typed_state = upsert_legacy_observations(
            typed_state,
            normalized_legacy["external_observations"],
            now=normalized_legacy.get("saved_at"),
        )
        legacy = typed_state.setdefault("legacy", {})
        if not isinstance(legacy, dict):
            legacy = {}
            typed_state["legacy"] = legacy
        legacy["turn_history"] = normalized_legacy.get("turn_history", [])
        legacy["loop_metrics"] = normalized_legacy.get("loop_metrics", {})
        legacy["extra_fields"] = {
            key: value
            for key, value in normalized_legacy.items()
            if key not in {"session_id", "saved_at", "external_observations", "turn_history", "loop_metrics"}
        }

        typed_state["session_id"] = session_id
        typed_state["updated_at"] = normalized_legacy.get("saved_at", _utc_now())
        typed_state.setdefault("created_at", typed_state["updated_at"])
        save_investigation_state(investigation_path, typed_state)

        # Project investigation state to wiki graph format
        try:
            graph_projection = project_to_wiki_graph(typed_state)
            graph_projection_path = self._graph_projection_path(session_id)
            graph_projection_path.write_text(
                json.dumps(graph_projection, indent=2),
                encoding="utf-8",
            )
        except (OSError, TypeError):
            pass  # Non-fatal: projection is optional

        try:
            _write_investigation_homepage(
                workspace=self.workspace,
                session_root_dir=self.session_root_dir,
                session_id=session_id,
                state=typed_state,
            )
        except (AttributeError, OSError, TypeError):
            pass  # Non-fatal: homepage generation is optional

        self._touch_metadata(session_id)

    def append_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        turn_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        event_path = self._events_path(session_id)
        seq = self._next_seq(event_path)
        line = self._next_line_number(event_path)
        recorded_at = _utc_now()
        event_type_v2 = _event_type_for_legacy(event_type, payload)
        status = _event_status(event_type_v2, payload)
        resolved_turn_id = turn_id
        payload_turn_id = payload.get("turn_id")
        if resolved_turn_id is None and isinstance(payload_turn_id, str) and payload_turn_id:
            resolved_turn_id = payload_turn_id
        failure = None
        if event_type == "result":
            loop_metrics = payload.get("loop_metrics")
            failure = _failure_for_result(
                str(payload.get("status") or ""),
                loop_metrics if isinstance(loop_metrics, dict) else {},
                str(payload.get("text") or ""),
            )
        event = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "envelope": TRACE_ENVELOPE,
            "event_id": f"evt:event:{session_id}:{seq:06d}",
            "session_id": session_id,
            "turn_id": resolved_turn_id,
            "seq": seq,
            "recorded_at": recorded_at,
            "event_type": event_type_v2,
            "channel": "event",
            "status": status,
            "actor": {
                "kind": "runtime",
                "id": "python-runtime",
                "display": "OpenPlanter Python Runtime",
                "runtime_family": "python",
            },
            "failure": failure,
            "provenance": {
                "record_locator": {"file": event_path.name, "line": line},
                "parent_event_id": None,
                "caused_by": [],
                "source_refs": [],
                "evidence_refs": [],
                "ontology_refs": [],
                "generated_from": {
                    "provider": provider,
                    "model": model,
                    "request_id": None,
                    "conversation_id": None,
                },
            },
            "compat": {
                "legacy_role": None,
                "legacy_kind": event_type,
                "source_schema": "legacy-python-events-v1",
            },
            "ts": recorded_at,
            "type": event_type,
            "payload": payload,
        }
        with event_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=True) + "\n")
        self._touch_metadata(session_id)
        return event

    def append_turn_record(self, session_id: str, record: dict[str, Any]) -> None:
        turn_path = self._turns_path(session_id)
        with turn_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
        self._touch_metadata(session_id)

    def write_artifact(
        self, session_id: str, category: str, name: str, content: str
    ) -> str:
        category_safe = _safe_component(category)
        name_safe = _safe_component(name)
        artifact_rel = Path("artifacts") / category_safe / name_safe
        artifact_abs = self._session_dir(session_id) / artifact_rel
        artifact_abs.parent.mkdir(parents=True, exist_ok=True)
        artifact_abs.write_text(content, encoding="utf-8")
        self._touch_metadata(session_id)
        return artifact_rel.as_posix()

    def _touch_metadata(self, session_id: str, continuity_mode: str | None = None) -> None:
        meta_path = self._metadata_path(session_id)
        base = _read_json_object(meta_path)
        canonical = self._canonicalize_metadata(base, session_id, continuity_mode=continuity_mode)
        meta_path.write_text(json.dumps(canonical, indent=2), encoding="utf-8")

    def _next_line_number(self, path: Path) -> int:
        if not path.exists():
            return 1
        line_count = 0
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if raw_line.strip():
                line_count += 1
        return line_count + 1

    def _next_seq(self, path: Path) -> int:
        if not path.exists():
            return 0
        next_seq = 0
        for raw_line in path.read_text(encoding="utf-8").splitlines():
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

    def _canonicalize_metadata(
        self,
        base: dict[str, Any],
        session_id: str,
        *,
        continuity_mode: str | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        session_dir = self._session_dir(session_id)
        state_data = _read_json_object(self._state_path(session_id))
        turn_history = state_data.get("turn_history") if isinstance(state_data.get("turn_history"), list) else []
        state_turn_count = len(turn_history)
        last_history = turn_history[-1] if turn_history and isinstance(turn_history[-1], dict) else {}

        turns_path = self._turns_path(session_id)
        turn_record_count = 0
        last_turn_record: dict[str, Any] = {}
        if turns_path.exists():
            for raw_line in turns_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                turn_record_count += 1
                last_turn_record = record

        turn_count = max(_coerce_int(base.get("turn_count"), 0), state_turn_count, turn_record_count)
        status = base.get("status")
        if not isinstance(status, str) or not status:
            status = "active"
        outcome = last_turn_record.get("outcome")
        if isinstance(outcome, dict):
            outcome_status = outcome.get("status")
            if isinstance(outcome_status, str) and outcome_status:
                status = outcome_status

        source_compat = base.get("source_compat")
        if isinstance(source_compat, dict):
            compat = {
                "legacy_python_metadata": bool(source_compat.get("legacy_python_metadata")),
                "desktop_metadata": bool(source_compat.get("desktop_metadata")),
                "legacy_event_stream_present": bool(source_compat.get("legacy_event_stream_present")) or self._events_path(session_id).exists(),
                "legacy_replay_stream_present": bool(source_compat.get("legacy_replay_stream_present")) or (session_dir / "replay.jsonl").exists(),
            }
        else:
            compat = {
                "legacy_python_metadata": any(key in base for key in ("workspace", "session_id")),
                "desktop_metadata": "id" in base and "session_id" not in base,
                "legacy_event_stream_present": self._events_path(session_id).exists(),
                "legacy_replay_stream_present": (session_dir / "replay.jsonl").exists(),
            }

        capabilities = dict(base.get("capabilities")) if isinstance(base.get("capabilities"), dict) else {}
        capabilities.setdefault("supports_events_v2", True)
        capabilities.setdefault("supports_replay_v2", True)
        capabilities.setdefault("supports_turns_v2", True)
        capabilities.setdefault("supports_provenance_links", True)
        capabilities.setdefault("supports_failure_taxonomy_v2", True)

        durability = dict(base.get("durability")) if isinstance(base.get("durability"), dict) else {}
        durability["events_jsonl_present"] = self._events_path(session_id).exists()
        durability["replay_jsonl_present"] = (session_dir / "replay.jsonl").exists()
        durability["turns_jsonl_present"] = turns_path.exists()
        durability.setdefault("partial_records_possible", True)

        last_turn_id = base.get("last_turn_id")
        if not isinstance(last_turn_id, str) or not last_turn_id:
            candidate = last_turn_record.get("turn_id")
            if isinstance(candidate, str) and candidate:
                last_turn_id = candidate
            elif turn_count > 0:
                last_turn_id = _turn_id(turn_count)
            else:
                last_turn_id = None

        last_objective = base.get("last_objective")
        if not isinstance(last_objective, str) or not last_objective:
            candidate = last_turn_record.get("objective")
            if isinstance(candidate, str) and candidate:
                last_objective = candidate
            else:
                candidate = last_history.get("objective")
                last_objective = candidate if isinstance(candidate, str) and candidate else None

        canonical = dict(base)
        canonical["schema_version"] = SESSION_SCHEMA_VERSION
        canonical["session_format"] = SESSION_FORMAT
        canonical["session_id"] = _metadata_session_id(base, session_id)
        canonical["id"] = str(base.get("id") or canonical["session_id"])
        canonical["workspace"] = str(base.get("workspace") or self.workspace)
        canonical["workspace_path"] = _metadata_workspace_path(base, canonical["workspace"])
        canonical.setdefault("workspace_id", None)
        canonical["created_at"] = str(base.get("created_at") or now)
        canonical["updated_at"] = now
        canonical.setdefault("session_origin", "python")
        canonical.setdefault("session_kind", "investigation")
        canonical["status"] = status
        canonical["turn_count"] = turn_count
        canonical["last_turn_id"] = last_turn_id
        canonical["last_objective"] = last_objective
        if continuity_mode is not None:
            canonical["continuity_mode"] = continuity_mode
        else:
            existing_mode = base.get("continuity_mode")
            if isinstance(existing_mode, str) and existing_mode:
                canonical["continuity_mode"] = existing_mode
            else:
                canonical["continuity_mode"] = "resume" if turn_count else "new"
        canonical["source_compat"] = compat
        canonical["capabilities"] = capabilities
        canonical["durability"] = durability
        canonical.setdefault("migration", None)
        return canonical


def _seed_wiki(workspace: Path, session_root_dir: str) -> None:
    """Copy baseline wiki/ into the runtime .openplanter/wiki/ directory.

    On first run, copies the entire tree. On subsequent runs, copies only
    new baseline files — never overwrites agent-modified entries.
    """
    baseline = workspace / "wiki"
    if not baseline.is_dir():
        return
    runtime_wiki = workspace / session_root_dir / "wiki"
    if not runtime_wiki.exists():
        shutil.copytree(
            baseline,
            runtime_wiki,
            ignore=shutil.ignore_patterns(".*", "__pycache__"),
        )
        return
    # Incremental: copy only new baseline files
    for src in baseline.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(baseline)
        if any(p.startswith(".") or p == "__pycache__" for p in rel.parts):
            continue
        dst = runtime_wiki / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


_CLOSED_INVESTIGATION_STATUSES = {
    "cancelled",
    "canceled",
    "closed",
    "completed",
    "done",
    "resolved",
    "wont_fix",
    "won't_fix",
}


def _status_is_open(status: Any) -> bool:
    return str(status or "open").strip().lower() not in _CLOSED_INVESTIGATION_STATUSES


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_items(value: Any) -> list[str]:
    return [str(item).strip() for item in _list_value(value) if str(item).strip()]


def _markdown_inline_text(value: str) -> str:
    return re.sub(r"\s*[\r\n]+\s*", " ", value).strip()


def _markdown_link(label: str, target: str) -> str:
    safe_label = _markdown_inline_text(label).replace("[", "\\[").replace("]", "\\]")
    safe_target = (
        re.sub(r"\s+", "%20", _markdown_inline_text(target))
        .replace("(", "%28")
        .replace(")", "%29")
    )
    return f"[{safe_label}]({safe_target})"


def _markdown_table_cell(value: str) -> str:
    return _markdown_inline_text(value).replace("|", "\\|")


def _evidence_label(evidence_id: str, evidence_record: dict[str, Any]) -> str:
    for key in ("title", "name", "description", "content", "text", "source_uri", "url"):
        value = evidence_record.get(key)
        if isinstance(value, str) and value.strip():
            label = value.strip().splitlines()[0]
            return label[:120]
    return evidence_id


def _evidence_citation(evidence_id: str, evidence_record: dict[str, Any]) -> str:
    label = _evidence_label(evidence_id, evidence_record)
    for key in ("source_uri", "canonical_source_uri", "url", "artifact_path"):
        target = evidence_record.get(key)
        if isinstance(target, str) and target.strip():
            return _markdown_link(f"{evidence_id}: {label}", target.strip())
    return f"`{evidence_id}`: {label}"


def _evidence_record(evidence: dict[str, Any], evidence_id: str) -> dict[str, Any]:
    record = evidence.get(evidence_id)
    return record if isinstance(record, dict) else {}


def _evidence_citations(evidence_ids: list[str], evidence: dict[str, Any]) -> list[str]:
    return [
        _evidence_citation(evidence_id, _evidence_record(evidence, evidence_id))
        for evidence_id in evidence_ids
    ]


def _record_label(record: dict[str, Any], fallback: str, *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return _markdown_inline_text(value)
    return fallback


def _document_needs_from_question(question: dict[str, Any]) -> list[str]:
    docs: list[str] = []
    for key in (
        "needed_documents",
        "required_documents",
        "documents_needed",
        "missing_documents",
        "required_sources",
        "source_uris",
        "sources",
        "urls",
    ):
        for item in _list_value(question.get(key)):
            if isinstance(item, str) and item.strip():
                docs.append(item.strip())
            elif isinstance(item, dict):
                label = _record_label(
                    item,
                    "",
                    "name",
                    "document",
                    "title",
                    "description",
                    "source_uri",
                    "url",
                )
                if label:
                    docs.append(label)
    return _dedupe_preserve_order(docs)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _candidate_action_label(action: dict[str, Any]) -> str:
    label = _record_label(action, "", "title", "description", "label")
    if label:
        return label
    action_type = str(action.get("action_type") or "Investigate").replace("_", " ").strip()
    target_questions = _string_items(action.get("target_question_ids"))
    target_claims = _string_items(action.get("target_claim_ids"))
    if target_questions:
        return f"{action_type.title()} question {target_questions[0]}"
    if target_claims:
        return f"{action_type.title()} claim {target_claims[0]}"
    action_id = str(action.get("id") or action.get("action_id") or "").strip()
    return action_id or "Investigate evidence gap"


def _action_matches_question(action: dict[str, Any], question_id: str) -> bool:
    if str(action.get("opened_by_question_id") or "") == question_id:
        return True
    return question_id in _string_items(action.get("target_question_ids"))


def _question_documents(
    question_id: str,
    question: dict[str, Any],
    candidate_actions: list[dict[str, Any]],
) -> list[str]:
    docs = _document_needs_from_question(question)
    for action in candidate_actions:
        if not _action_matches_question(action, question_id):
            continue
        docs.extend(_string_items(action.get("required_sources")))
        for gap in _list_value(action.get("evidence_gap_refs")):
            if not isinstance(gap, dict):
                continue
            if str(gap.get("scope") or "") == "question":
                kind = str(gap.get("kind") or "evidence").replace("_", " ")
                docs.append(f"{kind} for question {question_id}")
    return _dedupe_preserve_order(docs)


def _todo_anchor(todo_id: str) -> str:
    return f"todo-{_safe_component(todo_id).lower()}"


def _render_investigation_homepage(state: dict[str, Any], session_id: str) -> str:
    packet = build_question_reasoning_packet(state)
    findings = packet.get("findings") if isinstance(packet.get("findings"), dict) else {}
    supported = findings.get("supported", []) if isinstance(findings, dict) else []
    contested = findings.get("contested", []) if isinstance(findings, dict) else []
    unresolved = findings.get("unresolved", []) if isinstance(findings, dict) else []
    unresolved_questions = packet.get("unresolved_questions")
    if not isinstance(unresolved_questions, list):
        unresolved_questions = []
    candidate_actions = packet.get("candidate_actions")
    if not isinstance(candidate_actions, list):
        candidate_actions = []

    questions = state.get("questions") if isinstance(state.get("questions"), dict) else {}
    evidence = state.get("evidence") if isinstance(state.get("evidence"), dict) else {}
    tasks = state.get("tasks") if isinstance(state.get("tasks"), dict) else {}
    investigation_id = str(state.get("active_investigation_id") or session_id).strip() or session_id
    objective = str(state.get("objective") or "").strip()
    updated_at = str(state.get("updated_at") or _utc_now())

    open_tasks: list[tuple[str, dict[str, Any]]] = []
    for task_id, raw_task in tasks.items():
        if isinstance(raw_task, dict) and _status_is_open(raw_task.get("status")):
            open_tasks.append((str(raw_task.get("id") or task_id), raw_task))

    lines = [
        f"# Investigation Home: {investigation_id}",
        "",
        "> Auto-generated from `investigation_state.json`.",
        "",
        "## Current Status",
        f"- **Session ID**: `{session_id}`",
        f"- **Investigation ID**: `{investigation_id}`",
        f"- **Last updated**: `{updated_at}`",
        f"- **Objective**: {objective or 'Not set'}",
        f"- **Open questions**: {len(unresolved_questions)}",
        f"- **Supported conclusions**: {len(supported)}",
        f"- **Contested conclusions**: {len(contested)}",
        f"- **Open to-dos**: {len(open_tasks) + len(candidate_actions)}",
        "",
        "## Current Conclusions and Citations to Proofs",
        "",
        "### Supported Conclusions",
    ]

    if not supported:
        lines.append("- _No supported conclusions yet._")
    for index, claim in enumerate(supported, start=1):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id") or f"supported-{index}")
        claim_text = _record_label(claim, "Unnamed supported conclusion", "claim", "claim_text", "text")
        confidence = claim.get("confidence")
        suffix = f" (confidence: {confidence})" if confidence is not None else ""
        lines.append(f"{index}. **{claim_id}**: {claim_text}{suffix}")
        proof_ids = _string_items(claim.get("support_evidence_ids"))
        if proof_ids:
            citations = _evidence_citations(proof_ids, evidence)
            lines.append(f"   - Proofs: {', '.join(citations) if citations else '_No supporting evidence linked yet._'}")
        else:
            lines.append("   - Proofs: _No supporting evidence linked yet._")

    lines.extend(["", "### Contested Conclusions"])
    if not contested:
        lines.append("- _No contested conclusions currently tracked._")
    for index, claim in enumerate(contested, start=1):
        if not isinstance(claim, dict):
            continue
        claim_id = str(claim.get("id") or f"contested-{index}")
        claim_text = _record_label(claim, "Unnamed contested conclusion", "claim", "claim_text", "text")
        lines.append(f"{index}. **{claim_id}**: {claim_text}")
        support_ids = _string_items(claim.get("support_evidence_ids"))
        contradiction_ids = _string_items(claim.get("contradiction_evidence_ids"))
        if support_ids:
            support_citations = _evidence_citations(support_ids, evidence)
            lines.append(f"   - Supporting citations: {', '.join(support_citations)}")
        if contradiction_ids:
            contradiction_citations = _evidence_citations(contradiction_ids, evidence)
            lines.append(f"   - Contradicting citations: {', '.join(contradiction_citations)}")

    if unresolved:
        lines.extend(["", "### Unresolved Conclusions"])
        for index, claim in enumerate(unresolved[:8], start=1):
            if isinstance(claim, dict):
                claim_id = str(claim.get("id") or f"unresolved-{index}")
                claim_text = _record_label(claim, "Unnamed unresolved conclusion", "claim", "claim_text", "text")
                lines.append(f"{index}. **{claim_id}**: {claim_text}")

    lines.extend(["", "## Open Questions and Needed Documents"])
    if not unresolved_questions:
        lines.append("- _No open questions recorded._")
    for index, question in enumerate(unresolved_questions, start=1):
        if not isinstance(question, dict):
            continue
        question_id = str(question.get("id") or f"q-{index}")
        text = _record_label(question, "Unspecified open question", "question", "question_text", "text")
        priority = str(question.get("priority") or "medium")
        raw_question = questions.get(question_id, {}) if isinstance(questions.get(question_id, {}), dict) else {}
        docs = _question_documents(question_id, raw_question, candidate_actions)
        lines.append(f"{index}. **{text}** (`{question_id}`, priority: {priority})")
        if docs:
            lines.append("   - Needed documents:")
            for doc in docs[:8]:
                lines.append(f"     - {doc}")
        else:
            lines.append("   - Needed documents: _Not captured yet._")

    lines.extend(["", "## Open To-Dos"])
    if not open_tasks and not candidate_actions:
        lines.append("- _No open to-dos._")
    for task_id, task in open_tasks:
        description = _record_label(task, task_id, "description", "label", "text", "title")
        status = str(task.get("status") or "open")
        priority = str(task.get("priority") or "unspecified")
        target = str(task.get("link") or task.get("url") or task.get("artifact_path") or "").strip()
        link_target = target or f"#{_todo_anchor(task_id)}"
        lines.append(f"- {_markdown_link(description, link_target)} (`{task_id}`, {status}, priority: {priority})")
    for action in candidate_actions:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("id") or action.get("action_id") or "").strip()
        if not action_id:
            continue
        label = _candidate_action_label(action)
        priority = str(action.get("priority") or "medium")
        lines.append(f"- {_markdown_link(label, '#' + _todo_anchor(action_id))} (`{action_id}`, candidate action, priority: {priority})")

    lines.extend(["", "## To-Do Details"])
    if not open_tasks and not candidate_actions:
        lines.append("- _No to-do details available._")
    for task_id, task in open_tasks:
        description = _record_label(task, task_id, "description", "label", "text", "title")
        lines.extend([
            f'<a id="{_todo_anchor(task_id)}"></a>',
            f"### TODO {task_id}",
            f"- **Status**: `{str(task.get('status') or 'open')}`",
            f"- **Description**: {description}",
            "",
        ])
    for action in candidate_actions:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("id") or action.get("action_id") or "").strip()
        if not action_id:
            continue
        lines.extend([
            f'<a id="{_todo_anchor(action_id)}"></a>',
            f"### TODO {action_id}",
            "- **Status**: `candidate_action`",
            f"- **Description**: {_candidate_action_label(action)}",
        ])
        required_sources = _string_items(action.get("required_sources"))
        if required_sources:
            lines.append(f"- **Needed sources**: {', '.join(required_sources[:8])}")
        rationale = action.get("rationale")
        if isinstance(rationale, dict):
            reason_codes = _string_items(rationale.get("reason_codes"))
            if reason_codes:
                lines.append(f"- **Rationale**: {', '.join(reason_codes)}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _upsert_investigation_index_link(index_path: Path, investigation_id: str, relative_path: str) -> None:
    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
    else:
        content = "# Data Sources Wiki\n\n## Sources by Category\n"
    link_target_pattern = re.compile(
        rf"\]\({re.escape(relative_path)}\)(?:\s*\||\s*$)"
    )
    if any(
        line.lstrip().startswith("|") and link_target_pattern.search(line)
        for line in content.splitlines()
    ):
        return

    investigation_label = _markdown_table_cell(investigation_id)
    row = f"| {investigation_label} | Active investigation | [{relative_path}]({relative_path}) |"
    section_header = "### Investigations"
    lines = content.splitlines()
    insert_at: int | None = None

    for index, line in enumerate(lines):
        if line.strip() == section_header:
            insert_at = index + 1
            break

    if insert_at is None:
        contributing_at = next(
            (index for index, line in enumerate(lines) if line.strip().lower() == "## contributing"),
            len(lines),
        )
        addition = [
            "",
            section_header,
            "",
            "| Source | Jurisdiction | Link |",
            "|--------|-------------|------|",
            row,
            "",
        ]
        lines[contributing_at:contributing_at] = addition
    else:
        while insert_at < len(lines) and lines[insert_at].strip() == "":
            insert_at += 1
        if insert_at >= len(lines) or not lines[insert_at].strip().startswith("| Source |"):
            lines.insert(insert_at, "| Source | Jurisdiction | Link |")
            lines.insert(insert_at + 1, "|--------|-------------|------|")
            insert_at += 2
        while insert_at < len(lines) and lines[insert_at].strip().startswith("|"):
            insert_at += 1
        lines.insert(insert_at, row)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_investigation_homepage(
    *,
    workspace: Path,
    session_root_dir: str,
    session_id: str,
    state: dict[str, Any],
) -> None:
    investigation_id = str(state.get("active_investigation_id") or "").strip()
    if not investigation_id:
        return

    wiki_root = workspace / session_root_dir / "wiki"
    relative_path = f"investigations/{_safe_component(investigation_id)}.md"
    homepage_path = wiki_root / relative_path
    homepage_path.parent.mkdir(parents=True, exist_ok=True)
    homepage_path.write_text(
        _render_investigation_homepage(state, session_id=session_id),
        encoding="utf-8",
    )
    _upsert_investigation_index_link(wiki_root / "index.md", investigation_id, relative_path)


@dataclass
class SessionRuntime:
    engine: RLMEngine
    store: SessionStore
    session_id: str
    context: ExternalContext
    max_persisted_observations: int = 400
    turn_history: list[TurnSummary] | None = None
    max_turn_summaries: int = 50
    loop_metrics: dict[str, Any] | None = None

    def _provider_name(self) -> str | None:
        return self.engine.config.provider if self.engine.config else None

    def _model_name(self) -> str | None:
        return self.engine.config.model if self.engine.config else None

    def _flush_store_warnings(self, emit: EventCallback | None = None) -> None:
        for message in self.store.drain_warnings():
            if emit is not None:
                emit(message)
                continue
            try:
                self.store.append_event(
                    self.session_id,
                    "trace",
                    {"message": message},
                    provider=self._provider_name(),
                    model=self._model_name(),
                )
            except OSError:
                pass

    @classmethod
    def bootstrap(
        cls,
        engine: RLMEngine,
        config: AgentConfig,
        session_id: str | None = None,
        resume: bool = False,
        investigation_id: str | None = None,
    ) -> "SessionRuntime":
        store = SessionStore(
            workspace=config.workspace,
            session_root_dir=config.session_root_dir,
        )
        try:
            _seed_wiki(config.workspace, config.session_root_dir)
        except OSError:
            pass
        sid, state, created_new = store.open_session(
            session_id=session_id, resume=resume, investigation_id=investigation_id
        )
        persisted = state.get("external_observations", [])
        obs = [str(x) for x in persisted] if isinstance(persisted, list) else []
        max_obs = max(1, config.max_persisted_observations)
        context = ExternalContext(observations=obs[-max_obs:])

        engine.session_dir = store._session_dir(sid)
        engine.session_id = sid

        # Load turn history from persisted state
        raw_history = state.get("turn_history", [])
        turn_history: list[TurnSummary] = []
        if isinstance(raw_history, list):
            for item in raw_history:
                if isinstance(item, dict):
                    try:
                        turn_history.append(TurnSummary.from_dict(item))
                    except (KeyError, TypeError):
                        pass
        max_turns = max(1, config.max_turn_summaries)
        raw_loop_metrics = state.get("loop_metrics", {})
        loop_metrics: dict[str, Any] = raw_loop_metrics if isinstance(raw_loop_metrics, dict) else {}
        loop_metrics.setdefault("turns", 0)
        loop_metrics.setdefault("steps", 0)
        loop_metrics.setdefault("model_turns", 0)
        loop_metrics.setdefault("tool_calls", 0)
        loop_metrics.setdefault("guardrail_warnings", 0)
        loop_metrics.setdefault("final_rejections", 0)
        loop_metrics.setdefault("rewrite_only_violations", 0)
        loop_metrics.setdefault("finalization_stalls", 0)
        loop_metrics.setdefault("extensions_granted", 0)
        loop_metrics.setdefault("extension_eligible_checks", 0)
        loop_metrics.setdefault("extension_denials_no_progress", 0)
        loop_metrics.setdefault("extension_denials_cap", 0)
        loop_metrics.setdefault("termination_reason", "")
        loop_metrics.setdefault("phase_counts", {})
        if not isinstance(loop_metrics["phase_counts"], dict):
            loop_metrics["phase_counts"] = {}
        for phase in ("investigate", "build", "iterate", "finalize"):
            loop_metrics["phase_counts"].setdefault(phase, 0)

        runtime = cls(
            engine=engine,
            store=store,
            session_id=sid,
            context=context,
            max_persisted_observations=max_obs,
            turn_history=turn_history[-max_turns:],
            max_turn_summaries=max_turns,
            loop_metrics=loop_metrics,
        )
        try:
            runtime.store.append_event(
                sid,
                "session_started",
                {"resume": resume, "created_new": created_new},
                provider=runtime._provider_name(),
                model=runtime._model_name(),
            )
        except OSError:
            pass
        runtime._flush_store_warnings()
        try:
            runtime._persist_state()
        except OSError:
            pass
        runtime._flush_store_warnings()
        return runtime

    def solve(
        self,
        objective: str,
        on_event: EventCallback | None = None,
        on_step: StepCallback | None = None,
        on_content_delta: ContentDeltaCallback | None = None,
    ) -> str:
        objective = objective.strip()
        if not objective:
            return "No objective provided."
        turn_number = (self.turn_history[-1].turn_number + 1) if self.turn_history else 1
        turn_id = _turn_id(turn_number)
        turn_started_at = _utc_now()
        event_seq_start = self.store._next_seq(self.store._events_path(self.session_id))
        artifact_refs: list[str] = []
        objective_event: dict[str, Any] | None = None

        try:
            objective_event = self.store.append_event(
                self.session_id,
                "objective",
                {"text": objective},
                turn_id=turn_id,
                provider=self._provider_name(),
                model=self._model_name(),
            )
        except OSError:
            pass
        patch_counter = 0

        def _on_event(msg: str) -> None:
            try:
                self.store.append_event(
                    self.session_id,
                    "trace",
                    {"message": msg},
                    turn_id=turn_id,
                    provider=self._provider_name(),
                    model=self._model_name(),
                )
            except OSError:
                pass
            if on_event:
                on_event(msg)

        def _combined_on_step(step_event: dict[str, Any]) -> None:
            nonlocal patch_counter
            try:
                self.store.append_event(
                    self.session_id, "step", step_event, turn_id=turn_id,
                    provider=self._provider_name(),
                    model=self._model_name(),
                )
            except OSError:
                pass
            action = step_event.get("action")
            if isinstance(action, dict) and action.get("name") == "apply_patch":
                patch_text = str(action.get("arguments", {}).get("patch", ""))
                if patch_text.strip():
                    patch_counter += 1
                    name = (
                        f"patch-d{step_event.get('depth', 0)}"
                        f"-s{step_event.get('step', 0)}-{patch_counter}.patch"
                    )
                    try:
                        artifact_rel = self.store.write_artifact(
                            self.session_id,
                            category="patches",
                            name=name,
                            content=patch_text,
                        )
                        artifact_refs.append(artifact_rel)
                        self.store.append_event(
                            self.session_id,
                            "artifact",
                            {"kind": "patch", "path": artifact_rel},
                            turn_id=turn_id,
                            provider=self._provider_name(),
                            model=self._model_name(),
                        )
                    except OSError:
                        pass
            # Forward to external on_step callback
            if on_step:
                try:
                    on_step(step_event)
                except Exception:
                    pass

        replay_path = self.store._session_dir(self.session_id) / "replay.jsonl"
        replay_logger = ReplayLogger(
            path=replay_path,
            force_snapshot_first_call=True,
            session_id=self.session_id,
            turn_id=turn_id,
        )
        replay_seq_start = replay_logger.current_seq

        typed_state = self.store.load_typed_state(self.session_id)
        self._flush_store_warnings(_on_event)
        ws_ontology_path = self.store.workspace / ".openplanter" / "ontology.json"
        ws_ontology = None
        if ws_ontology_path.exists():
            try:
                ws_ontology = json.loads(ws_ontology_path.read_text())
            except (OSError, ValueError):
                pass
        question_reasoning_packet = build_question_reasoning_packet(typed_state, workspace_ontology=ws_ontology)
        if not _has_reasoning_content(question_reasoning_packet):
            question_reasoning_packet = None
        retrieval_result = build_retrieval_packet(
            workspace=self.store.workspace,
            session_dir=self.store._session_dir(self.session_id),
            session_root_dir=self.store.session_root_dir,
            objective=objective,
            question_reasoning_packet=question_reasoning_packet,
            embeddings_provider=self.engine.config.embeddings_provider,
            voyage_api_key=self.engine.config.voyage_api_key,
            mistral_api_key=self.engine.config.mistral_api_key,
            on_event=_on_event,
        )
        _on_event(f"[retrieval] {retrieval_result.detail}")

        result, updated_context = self.engine.solve_with_context(
            objective=objective,
            context=self.context,
            on_event=_on_event,
            on_step=_combined_on_step,
            on_content_delta=on_content_delta,
            replay_logger=replay_logger,
            turn_history=self.turn_history,
            question_reasoning_packet=question_reasoning_packet,
            retrieval_packet=retrieval_result.packet,
        )
        self.context = updated_context

        latest_loop_metrics = self.engine.last_loop_metrics if isinstance(self.engine.last_loop_metrics, dict) else {}
        if self.loop_metrics is None:
            self.loop_metrics = {
                "turns": 0,
                "steps": 0,
                "model_turns": 0,
                "tool_calls": 0,
                "guardrail_warnings": 0,
                "final_rejections": 0,
                "rewrite_only_violations": 0,
                "finalization_stalls": 0,
                "extensions_granted": 0,
                "extension_eligible_checks": 0,
                "extension_denials_no_progress": 0,
                "extension_denials_cap": 0,
                "termination_reason": "",
                "phase_counts": {"investigate": 0, "build": 0, "iterate": 0, "finalize": 0},
            }
        self.loop_metrics["turns"] = int(self.loop_metrics.get("turns", 0)) + 1
        self.loop_metrics["steps"] = int(self.loop_metrics.get("steps", 0)) + int(latest_loop_metrics.get("steps", 0))
        self.loop_metrics["model_turns"] = int(self.loop_metrics.get("model_turns", 0)) + int(latest_loop_metrics.get("model_turns", 0))
        self.loop_metrics["tool_calls"] = int(self.loop_metrics.get("tool_calls", 0)) + int(latest_loop_metrics.get("tool_calls", 0))
        self.loop_metrics["guardrail_warnings"] = int(self.loop_metrics.get("guardrail_warnings", 0)) + int(latest_loop_metrics.get("guardrail_warnings", 0))
        self.loop_metrics["final_rejections"] = int(self.loop_metrics.get("final_rejections", 0)) + int(latest_loop_metrics.get("final_rejections", 0))
        self.loop_metrics["rewrite_only_violations"] = int(self.loop_metrics.get("rewrite_only_violations", 0)) + int(latest_loop_metrics.get("rewrite_only_violations", 0))
        self.loop_metrics["finalization_stalls"] = int(self.loop_metrics.get("finalization_stalls", 0)) + int(latest_loop_metrics.get("finalization_stalls", 0))
        self.loop_metrics["extensions_granted"] = int(self.loop_metrics.get("extensions_granted", 0)) + int(latest_loop_metrics.get("extensions_granted", 0))
        self.loop_metrics["extension_eligible_checks"] = int(self.loop_metrics.get("extension_eligible_checks", 0)) + int(latest_loop_metrics.get("extension_eligible_checks", 0))
        self.loop_metrics["extension_denials_no_progress"] = int(self.loop_metrics.get("extension_denials_no_progress", 0)) + int(latest_loop_metrics.get("extension_denials_no_progress", 0))
        self.loop_metrics["extension_denials_cap"] = int(self.loop_metrics.get("extension_denials_cap", 0)) + int(latest_loop_metrics.get("extension_denials_cap", 0))
        self.loop_metrics["termination_reason"] = str(latest_loop_metrics.get("termination_reason", ""))
        phase_counts = self.loop_metrics.setdefault("phase_counts", {})
        latest_phase_counts = latest_loop_metrics.get("phase_counts", {})
        if not isinstance(phase_counts, dict):
            phase_counts = {}
            self.loop_metrics["phase_counts"] = phase_counts
        if not isinstance(latest_phase_counts, dict):
            latest_phase_counts = {}
        for phase in ("investigate", "build", "iterate", "finalize"):
            phase_counts[phase] = int(phase_counts.get(phase, 0)) + int(latest_phase_counts.get(phase, 0))
        self.loop_metrics["last_turn"] = latest_loop_metrics

        # Generate turn summary
        if self.turn_history is None:
            self.turn_history = []
        result_preview = result[:200] + "..." if len(result) > 200 else result
        replay_seq_end = replay_logger.current_seq
        steps_used = max(0, replay_seq_end - replay_seq_start)
        summary = TurnSummary(
            turn_number=turn_number,
            objective=objective,
            result_preview=result_preview,
            timestamp=_utc_now(),
            steps_used=steps_used,
            replay_seq_start=replay_seq_start,
        )
        self.turn_history.append(summary)
        if len(self.turn_history) > self.max_turn_summaries:
            self.turn_history = self.turn_history[-self.max_turn_summaries:]
        status = _result_status(result, latest_loop_metrics)
        result_event: dict[str, Any] | None = None
        try:
            result_event = self.store.append_event(
                self.session_id,
                "result",
                {
                    "text": result,
                    "status": status,
                    "loop_metrics": latest_loop_metrics,
                },
                turn_id=turn_id,
                provider=self._provider_name(),
                model=self._model_name(),
            )
        except OSError:
            pass
        event_seq_end = max(event_seq_start, self.store._next_seq(self.store._events_path(self.session_id)) - 1)
        result_event_id = result_event.get("event_id") if isinstance(result_event, dict) else None
        objective_event_id = objective_event.get("event_id") if isinstance(objective_event, dict) else None
        failure = _failure_for_result(status, latest_loop_metrics, result)
        try:
            self.store.append_turn_record(
                self.session_id,
                {
                    "schema_version": SESSION_SCHEMA_VERSION,
                    "record": TURN_RECORD_FORMAT,
                    "session_id": self.session_id,
                    "turn_id": turn_id,
                    "turn_index": turn_number,
                    "started_at": turn_started_at,
                    "ended_at": _utc_now(),
                    "objective": objective,
                    "continuity": {
                        "mode": "resume" if turn_number > 1 else "new",
                        "resumed_from_turn_id": _turn_id(turn_number - 1) if turn_number > 1 else None,
                        "resumed_from_partial": False,
                        "checkpoint_ref": None,
                    },
                    "inputs": {
                        "user_message_ref": objective_event_id,
                        "attachments": [],
                        "context_refs": [],
                    },
                    "outputs": {
                        "assistant_final_ref": result_event_id,
                        "result_summary_ref": result_event_id,
                        "artifact_refs": artifact_refs,
                    },
                    "execution": {
                        "step_count": int(latest_loop_metrics.get("steps", 0)),
                        "tool_call_count": int(latest_loop_metrics.get("tool_calls", 0)),
                        "degraded": status == "partial",
                        "resumed": turn_number > 1,
                    },
                    "outcome": {
                        "status": _turn_outcome_status(status),
                        "failure_code": failure["code"] if failure is not None else None,
                        "failure": failure,
                        "summary": result_preview,
                    },
                    "provenance": {
                        "event_span": {
                            "start_seq": event_seq_start,
                            "end_seq": event_seq_end,
                        },
                        "replay_span": {
                            "start_seq": replay_seq_start,
                            "end_seq": replay_seq_end - 1 if replay_seq_end > replay_seq_start else replay_seq_start,
                        },
                        "evidence_refs": [
                            {
                                "kind": "artifact",
                                "id": path,
                                "label": path,
                                "locator": {"path": path},
                            }
                            for path in artifact_refs
                        ],
                        "ontology_refs": [],
                    },
                },
            )
        except OSError:
            pass
        try:
            self._persist_state()
            try:
                from .defrag import sync_session_to_workspace_ontology
                typed_state = self.store.load_typed_state(self.session_id)
                sync_session_to_workspace_ontology(
                    self.store.workspace, self.session_id, typed_state
                )
            except Exception:
                pass  # Never crash session finalization for ontology sync
        except OSError:
            pass
        self._flush_store_warnings(_on_event)
        return result

    def _persist_state(self) -> None:
        if len(self.context.observations) > self.max_persisted_observations:
            self.context.observations = self.context.observations[-self.max_persisted_observations :]
        state: dict[str, Any] = {
            "session_id": self.session_id,
            "saved_at": _utc_now(),
            "external_observations": self.context.observations,
        }
        if self.turn_history:
            state["turn_history"] = [t.to_dict() for t in self.turn_history]
        if self.loop_metrics:
            state["loop_metrics"] = self.loop_metrics
        self.store.save_state(self.session_id, state)
