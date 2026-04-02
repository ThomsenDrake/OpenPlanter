from __future__ import annotations

import json
import random
import re
import time
import threading
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .config import AgentConfig
from .investigation_state import build_question_reasoning_packet, load_investigation_state
from .model import BaseModel, ImageData, ModelError, ModelTurn, RateLimitError, ToolCall, ToolResult
from .prompts import build_system_prompt
from .replay_log import ReplayLogger
from .retrieval import build_retrieval_packet
from .tool_defs import get_tool_definitions
from .tools import WorkspaceTools

EventCallback = Callable[[str], None]
StepCallback = Callable[[dict[str, Any]], None]
ContentDeltaCallback = Callable[[str, str], None]


_RECON_TOOL_NAMES = {
    "list_files",
    "search_files",
    "repo_map",
    "web_search",
    "fetch_url",
    "read_file",
    "read_image",
    "audio_transcribe",
    "document_ocr",
    "document_annotations",
    "document_qa",
    "list_artifacts",
    "read_artifact",
}
_ARTIFACT_TOOL_NAMES = {
    "document_ocr",
    "write_file",
    "apply_patch",
    "edit_file",
    "hashline_edit",
}
_WEAK_STRUCTURAL_META_PATTERNS = (
    re.compile(r"^\s*(here(?:'s| is)\s+(?:my|the)\s+(?:plan|approach|analysis))\b", re.I),
)
_STRONG_PROCESS_META_PATTERNS = (
    re.compile(r"\b(i\s+(?:will|can|should|need to|want to|am going to|plan to))\b", re.I),
    re.compile(r"\b(let me|next,?\s+i\s+will|i\s+should\s+start\s+by)\b", re.I),
)
_META_DELIVERABLE_OBJECTIVE_PATTERN = re.compile(
    r"\b(plan(?:ning)?|approach|strategy|outline|spec(?:ification)?|design|roadmap|proposal|review|audit|analysis|analyze|brainstorm)\b",
    re.I,
)
_INVESTIGATION_STRATEGY_CUE_PATTERN = re.compile(
    r"\b(weakness|capitalize|opposition|vulnerability|pressure point|risk|contrast|recommendation|line of attack)\b",
    re.I,
)
_MULTI_PHASE_PATTERNS = (
    re.compile(r"\b(and then|after|before|first|then|finally)\b", re.I),
    re.compile(r"\b(compare|cross-reference|cross reference|end-to-end|end to end)\b", re.I),
)
_INVESTIGATE_INTENT_PATTERN = re.compile(
    r"\b(analyze|analysis|inspect|trace|understand|find|investigate|survey|read|search|compare)\b",
    re.I,
)
_MUTATION_INTENT_PATTERN = re.compile(
    r"\b(write|edit|fix|update|create|implement|verify|patch|modify|build)\b",
    re.I,
)
_MULTI_SURFACE_PATTERNS = (
    re.compile(r"\b(across|between|multiple files|frontend and backend|backend and frontend)\b", re.I),
    re.compile(r"\bdataset\s+\w+\s+and\s+\w+\b", re.I),
)
_PATHLIKE_TOKEN_PATTERN = re.compile(r"(?:[\w./-]+\.[A-Za-z0-9]+|[/\\][\w./-]+)")


def _summarize_args(args: dict[str, Any], max_len: int = 120) -> str:
    """One-line summary of tool call arguments."""
    parts: list[str] = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 60:
            s = s[:57] + "..."
        parts.append(f"{k}={s}")
    joined = ", ".join(parts)
    if len(joined) > max_len:
        joined = joined[:max_len - 3] + "..."
    return joined


def _summarize_observation(text: str, max_len: int = 200) -> str:
    """First line or truncated preview of an observation."""
    first = text.split("\n", 1)[0].strip()
    if len(first) > max_len:
        first = first[:max_len - 3] + "..."
    lines = text.count("\n") + 1
    chars = len(text)
    if lines > 1:
        return f"{first} ({lines} lines, {chars} chars)"
    return first


# Legacy alias for tests and external code that reference SYSTEM_PROMPT directly.
SYSTEM_PROMPT = build_system_prompt(recursive=True)

# Context window sizes (tokens) for condensation heuristic.
_MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "gpt-4o": 128_000,
    "gpt-4.1": 1_000_000,
    "gpt-5-turbo-16k": 16_000,
}
_DEFAULT_CONTEXT_WINDOW = 128_000
_CONDENSATION_THRESHOLD = 0.75
_BUDGET_EXTENSION_WINDOW = 12
_MIN_EXTENSION_PROGRESS_SIGNALS = 2
_MIN_MEANINGFUL_RESULT_CHARS = 24
_NON_PROGRESS_TOOL_NAMES = _RECON_TOOL_NAMES | {"think"}
_INVESTIGATION_REQUIRED_JSON_KEYS = (
    "key_judgments",
    "supported_findings",
    "contested_findings",
    "unresolved_findings",
)
_FINALIZER_RESCUE_SYSTEM_PROMPT = (
    "You are finishing already-completed work.\n"
    "Return only the direct final deliverable as plain text.\n"
    "Use only the supplied objective, reasoning packet, retrieval summary, rejected candidate, and completed-work notes.\n"
    "Prefer minimally editing the rejected candidate when it already contains the deliverable.\n"
    "When the objective is an investigation, preserve the required report sections or JSON keys.\n"
    "Remove process commentary, future-tense promises, and next-step language.\n"
    "Do not call tools, create or verify files, claim new verification, or invent new work."
)


def _has_reasoning_packet_content(packet: dict[str, Any] | None) -> bool:
    if not isinstance(packet, dict):
        return False
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


def _objective_requires_strategic_implications(objective: str) -> bool:
    return bool(_INVESTIGATION_STRATEGY_CUE_PATTERN.search(objective))


def _find_markdown_section(text: str, heading: str) -> re.Match[str] | None:
    return re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", text)


def _markdown_section_body(text: str, heading: str) -> str:
    match = re.search(
        rf"(?ims)^##\s+{re.escape(heading)}\s*$\n?(.*?)(?=^##\s+|\Z)",
        text,
    )
    if match is None:
        return ""
    return match.group(1).strip()


def _json_sequence_has_content(value: Any) -> bool:
    if isinstance(value, list):
        return any(bool(item) for item in value)
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return bool(value)
    return value is not None


def _parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _model_tier(model_name: str, reasoning_effort: str | None = None) -> int:
    """Determine capability tier for a model.  Lower number = higher capability.

    Anthropic chain (by model name):
      opus → 1, sonnet → 2, haiku → 3
    OpenAI codex chain (by reasoning effort):
      xhigh → 1, high → 2, medium → 3, low → 4
    Unknown → 2
    """
    lower = model_name.lower()
    if "opus" in lower:
        return 1
    if "sonnet" in lower:
        return 2
    if "haiku" in lower:
        return 3
    if lower.startswith("gpt-5") and "codex" in lower:
        effort = (reasoning_effort or "").lower()
        return {"xhigh": 1, "high": 2, "medium": 3, "low": 4}.get(effort, 2)
    return 2


def _lowest_tier_model(model_name: str) -> tuple[str, str | None]:
    """Return (model_name, reasoning_effort) for the lowest-tier executor.

    Anthropic models → haiku.  Unknown → no downgrade (return same name).
    """
    lower = model_name.lower()
    if "claude" in lower:
        return ("claude-haiku-4-5-20251001", None)
    return (model_name, None)


def _objective_requires_auto_recursion(objective: str) -> bool:
    score = 0
    lower = objective.lower()
    if any(pattern.search(lower) for pattern in _MULTI_PHASE_PATTERNS):
        score += 1
    if _INVESTIGATE_INTENT_PATTERN.search(lower) and _MUTATION_INTENT_PATTERN.search(lower):
        score += 1
    multi_surface = any(pattern.search(lower) for pattern in _MULTI_SURFACE_PATTERNS)
    if not multi_surface and len(_PATHLIKE_TOKEN_PATTERN.findall(objective)) >= 2:
        multi_surface = True
    if multi_surface:
        score += 1
    return score >= 2


ModelFactory = Callable[[str, str | None], "BaseModel"]


@dataclass
class ExternalContext:
    observations: list[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        self.observations.append(text)

    def summary(self, max_items: int = 12, max_chars: int = 8000) -> str:
        if not self.observations:
            return "(empty)"
        if max_items <= 0:
            return "(empty)"
        recent = self.observations[-max_items:]
        joined = "\n\n".join(recent)
        if len(joined) <= max_chars:
            return joined
        return f"{joined[:max_chars]}\n...[truncated external context]..."


@dataclass
class TurnSummary:
    """Compact, serializable summary for a completed top-level turn."""

    turn_number: int
    objective: str
    result_preview: str
    timestamp: str
    steps_used: int = 0
    replay_seq_start: int = 0

    def to_dict(self) -> dict[str, int | str]:
        return {
            "turn_number": self.turn_number,
            "objective": self.objective,
            "result_preview": self.result_preview,
            "timestamp": self.timestamp,
            "steps_used": self.steps_used,
            "replay_seq_start": self.replay_seq_start,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "TurnSummary":
        return cls(
            turn_number=int(payload["turn_number"]),
            objective=str(payload.get("objective", "")),
            result_preview=str(payload.get("result_preview", "")),
            timestamp=str(payload.get("timestamp", "")),
            steps_used=int(payload.get("steps_used", 0) or 0),
            replay_seq_start=int(payload.get("replay_seq_start", 0) or 0),
        )


@dataclass
class StepProgressRecord:
    step: int
    phase: str
    step_signature: str
    tool_count: int
    failed_tool_step: bool
    final_rejection: bool = False
    rewrite_only_violation: bool = False
    post_finalization_artifact_churn: bool = False
    successful_action_signatures: set[str] = field(default_factory=set)
    state_delta_signatures: set[str] = field(default_factory=set)
    completed_previews: list[str] = field(default_factory=list)


def _normalize_progress_fragment(text: str, max_len: int = 120) -> str:
    collapsed = re.sub(r"\s+", " ", text.strip().lower())
    collapsed = re.sub(r"^(?:\[[^\]]+\]\s*)+", "", collapsed)
    if len(collapsed) > max_len:
        collapsed = collapsed[: max_len - 3] + "..."
    return collapsed


def _action_signature(name: str, args: dict[str, Any]) -> str:
    payload = json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    payload = payload[:160]
    return f"{name}|{payload}"


def _looks_like_failed_tool_result(name: str, result: ToolResult) -> bool:
    if result.is_error:
        return True
    content = result.content.strip()
    normalized = _normalize_progress_fragment(content, max_len=200)
    exit_match = re.search(r"\[exit_code=(-?\d+)\]", content)
    if exit_match:
        try:
            if int(exit_match.group(1)) != 0:
                return True
        except ValueError:
            pass
    failure_prefixes = (
        "file not found:",
        "path is a directory, not a file:",
        "failed to ",
        "blocked:",
        "blocked by policy:",
        "unsupported image format:",
        "image too large:",
        "max recursion depth reached;",
        "cannot delegate to higher-tier model",
        "task cancelled.",
        "tool ",
    )
    if normalized.startswith(failure_prefixes):
        return True
    if normalized.startswith("search_files requires ") or normalized.startswith("read_file requires "):
        return True
    if normalized.startswith("run_shell requires ") or normalized.startswith("apply_patch requires "):
        return True
    return " crashed:" in normalized


def _build_step_progress_record(
    step: int,
    phase: str,
    tool_calls: list[ToolCall],
    results: list[ToolResult],
) -> StepProgressRecord:
    tool_names = [tc.name for tc in tool_calls]
    has_artifact = any(name in _ARTIFACT_TOOL_NAMES for name in tool_names)
    failed_results = [
        _looks_like_failed_tool_result(tool_call.name, result)
        for tool_call, result in zip(tool_calls, results)
    ]
    has_error = any(failed_results)
    record = StepProgressRecord(
        step=step,
        phase=phase,
        step_signature=f"{','.join(sorted(tool_names))}|artifact={int(has_artifact)}|error={int(has_error)}",
        tool_count=len(tool_calls),
        failed_tool_step=has_error,
    )
    for tool_call, result, failed_result in zip(tool_calls, results, failed_results):
        if failed_result or tool_call.name in _NON_PROGRESS_TOOL_NAMES:
            continue
        normalized_result = _normalize_progress_fragment(result.content)
        if len(normalized_result) < _MIN_MEANINGFUL_RESULT_CHARS:
            continue
        record.successful_action_signatures.add(_action_signature(tool_call.name, tool_call.arguments))
        record.state_delta_signatures.add(f"{tool_call.name}|{normalized_result}")
        preview = _summarize_observation(result.content)
        if preview not in record.completed_previews:
            record.completed_previews.append(preview)
    return record


def _special_step_progress_record(
    step: int,
    phase: str,
    *,
    final_rejection: bool = False,
    rewrite_only_violation: bool = False,
    post_finalization_artifact_churn: bool = False,
) -> StepProgressRecord:
    return StepProgressRecord(
        step=step,
        phase=phase,
        step_signature=(
            f"special|final_rejection={int(final_rejection)}"
            f"|rewrite_only_violation={int(rewrite_only_violation)}"
            f"|artifact_churn={int(post_finalization_artifact_churn)}"
        ),
        tool_count=0,
        failed_tool_step=False,
        final_rejection=final_rejection,
        rewrite_only_violation=rewrite_only_violation,
        post_finalization_artifact_churn=post_finalization_artifact_churn,
    )


def _evaluate_budget_extension(
    records: list[StepProgressRecord],
    *,
    recon_streak: int,
) -> dict[str, Any]:
    window = records[-_BUDGET_EXTENSION_WINDOW:]
    tool_steps = sum(1 for record in window if record.tool_count > 0)
    failed_steps = sum(1 for record in window if record.failed_tool_step)
    failure_ratio = (failed_steps / tool_steps) if tool_steps else 0.0

    repeated_signature_streak = 1
    current_streak = 1
    previous_signature: str | None = None
    for record in window:
        if previous_signature is not None and record.step_signature == previous_signature:
            current_streak += 1
        else:
            current_streak = 1
            previous_signature = record.step_signature
        repeated_signature_streak = max(repeated_signature_streak, current_streak)

    prior_action_signatures: set[str] = set()
    for record in records[: max(0, len(records) - len(window))]:
        prior_action_signatures.update(record.successful_action_signatures)

    recent_action_signatures: set[str] = set()
    recent_state_delta_signatures: set[str] = set()
    has_build_or_finalize = False
    has_finalization_churn = False
    for record in window:
        recent_action_signatures.update(record.successful_action_signatures)
        recent_state_delta_signatures.update(record.state_delta_signatures)
        has_build_or_finalize = has_build_or_finalize or record.phase in {"build", "finalize"}
        has_finalization_churn = has_finalization_churn or any(
            (
                record.final_rejection,
                record.rewrite_only_violation,
                record.post_finalization_artifact_churn,
            )
        )

    novel_action_signatures = recent_action_signatures - prior_action_signatures
    positive_signals = 0
    if len(novel_action_signatures) >= 2:
        positive_signals += 1
    if len(recent_state_delta_signatures) >= 2:
        positive_signals += 1
    if has_build_or_finalize:
        positive_signals += 1

    blockers: list[str] = []
    if repeated_signature_streak >= 3:
        blockers.append("repeated_signatures")
    if failure_ratio > 0.6:
        blockers.append("high_failure_ratio")
    if recon_streak >= 4:
        blockers.append("recon_streak")
    if has_finalization_churn:
        blockers.append("finalization_churn")

    return {
        "eligible": not blockers and positive_signals >= _MIN_EXTENSION_PROGRESS_SIGNALS,
        "window_size": len(window),
        "repeated_signature_streak": repeated_signature_streak,
        "failure_ratio": failure_ratio,
        "novel_action_count": len(novel_action_signatures),
        "state_delta_count": len(recent_state_delta_signatures),
        "has_build_or_finalize": has_build_or_finalize,
        "has_finalization_churn": has_finalization_churn,
        "positive_signals": positive_signals,
        "blockers": blockers,
    }


def _suggest_next_actions(
    objective: str,
    evaluation: dict[str, Any],
    recent_previews: list[str],
) -> list[str]:
    actions: list[str] = []
    blockers = set(evaluation.get("blockers", []))
    if "repeated_signatures" in blockers:
        actions.append("Stop retrying the same command pattern and switch to a different source or tactic.")
    if "high_failure_ratio" in blockers:
        actions.append("Triage the failing tool calls first so the next run is not dominated by avoidable errors.")
    if "recon_streak" in blockers:
        actions.append("Move from exploration into artifact-building or synthesis before doing more reconnaissance.")
    if "finalization_churn" in blockers:
        actions.append("Rewrite the answer from completed work only instead of calling more tools or creating more files.")
    if recent_previews:
        actions.append("Turn the completed findings below into a concrete artifact or summary before resuming deeper work.")
    actions.append(f"Resume the objective with a narrower next slice: {objective}")
    return actions[:4]


def _collect_recent_completed_previews(
    records: list[StepProgressRecord],
    limit: int = 3,
) -> list[str]:
    recent_previews: list[str] = []
    for record in reversed(records[-_BUDGET_EXTENSION_WINDOW:]):
        for preview in record.completed_previews:
            if preview not in recent_previews:
                recent_previews.append(preview)
            if len(recent_previews) >= limit:
                return recent_previews
    return recent_previews


def _render_partial_completion(
    objective: str,
    loop_metrics: dict[str, Any],
    evaluation: dict[str, Any],
    records: list[StepProgressRecord],
) -> str:
    recent_previews = _collect_recent_completed_previews(records)
    next_actions = _suggest_next_actions(objective, evaluation, recent_previews)
    completed = recent_previews or ["The run gathered additional context but did not converge on a final artifact before the bounded limit."]
    reason = str(loop_metrics.get("termination_reason", "budget_no_progress"))
    if reason == "finalization_stall":
        remaining = "Rewrite the final answer from the completed work below only. Do not call more tools or create more files."
    else:
        remaining = (
            "Finish the deliverable using the completed work below and avoid repeating the stalled loop."
            if recent_previews
            else "Finish the deliverable with a narrower plan or a different tactic."
        )
    header = (
        f"Partial completion for objective: {objective}\n"
        f"Stopped after {int(loop_metrics.get('steps', 0))} steps "
        f"with {int(loop_metrics.get('extensions_granted', 0))} budget extension(s). "
        f"Termination reason: {reason}."
    )
    completed_block = "\n".join(f"- {item}" for item in completed)
    next_actions_block = "\n".join(f"- {item}" for item in next_actions)
    return (
        f"{header}\n\n"
        "Completed work:\n"
        f"{completed_block}\n\n"
        "Remaining work:\n"
        f"- {remaining}\n\n"
        "Suggested next actions:\n"
        f"{next_actions_block}"
    )


@dataclass
class RLMEngine:
    model: BaseModel
    tools: WorkspaceTools
    config: AgentConfig
    system_prompt: str = ""
    session_tokens: dict[str, dict[str, int]] = field(default_factory=dict)
    model_factory: ModelFactory | None = None
    _model_cache: dict[tuple[str, str | None], BaseModel] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    session_dir: Path | None = None
    session_id: str | None = None
    _shell_command_counts: dict[tuple[int, str], int] = field(default_factory=dict)
    _cancel: threading.Event = field(default_factory=threading.Event)
    _pending_image: threading.local = field(default_factory=threading.local)
    last_loop_metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.system_prompt:
            self.system_prompt = build_system_prompt(
                self.config.recursive,
                acceptance_criteria=self.config.acceptance_criteria,
                demo=self.config.demo,
            )
        self._set_model_tool_defs(self.model, include_subtask=self.config.recursive)

    def _build_tool_defs(
        self,
        *,
        include_subtask: bool,
        delegation_only: bool = False,
    ) -> list[dict[str, Any]]:
        ac = self.config.acceptance_criteria
        dynamic_defs = self.tools.get_chrome_mcp_tool_defs()
        return get_tool_definitions(
            include_subtask=include_subtask,
            delegation_only=delegation_only,
            include_acceptance_criteria=ac,
            dynamic_defs=dynamic_defs,
        )

    def _set_model_tool_defs(
        self,
        model: BaseModel,
        *,
        include_subtask: bool,
        delegation_only: bool = False,
    ) -> list[dict[str, Any]]:
        tool_defs = self._build_tool_defs(
            include_subtask=include_subtask,
            delegation_only=delegation_only,
        )
        if hasattr(model, "tool_defs"):
            model.tool_defs = tool_defs
        return tool_defs

    def _required_subtask_depth(self, objective: str) -> int:
        if not self.config.recursive or self.config.max_depth <= 0:
            return 0
        min_depth = min(self.config.min_subtask_depth, self.config.max_depth)
        if self.config.recursion_policy == "force_max":
            return self.config.max_depth
        auto_depth = 0
        if self.config.max_steps_per_call >= 2 and _objective_requires_auto_recursion(objective):
            auto_depth = 1
        return min(self.config.max_depth, max(min_depth, auto_depth))

    def _delegation_policy_message(self, depth: int, required_depth: int) -> str:
        requirement = (
            f"Delegation required: recursion policy requires depth {required_depth} "
            f"before direct work or finalization. Current depth is {depth}. "
            "Your next action must be exactly one subtask(objective=..., "
        )
        if self.config.acceptance_criteria:
            requirement += 'acceptance_criteria="...").'
        else:
            requirement += "...)."
        return requirement

    def cancel(self) -> None:
        """Signal the engine to stop after the current model call or tool."""
        self._cancel.set()

    def solve(self, objective: str, on_event: EventCallback | None = None) -> str:
        result, _ = self.solve_with_context(objective=objective, on_event=on_event)
        return result

    def solve_with_context(
        self,
        objective: str,
        context: ExternalContext | None = None,
        on_event: EventCallback | None = None,
        on_step: StepCallback | None = None,
        on_content_delta: ContentDeltaCallback | None = None,
        replay_logger: ReplayLogger | None = None,
        turn_history: list[TurnSummary] | None = None,
        question_reasoning_packet: dict[str, Any] | None = None,
        retrieval_packet: dict[str, Any] | None = None,
    ) -> tuple[str, ExternalContext]:
        if not objective.strip():
            return "No objective provided.", context or ExternalContext()
        self._cancel.clear()
        with self._lock:
            self._shell_command_counts.clear()
        active_context = context if context is not None else ExternalContext()
        deadline = (time.monotonic() + self.config.max_solve_seconds) if self.config.max_solve_seconds > 0 else 0
        self._set_model_tool_defs(self.model, include_subtask=self.config.recursive)
        try:
            result = self._solve_recursive(
                objective=objective.strip(),
                depth=0,
                context=active_context,
                on_event=on_event,
                on_step=on_step,
                on_content_delta=on_content_delta,
                deadline=deadline,
                replay_logger=replay_logger,
                turn_history=turn_history,
                question_reasoning_packet=question_reasoning_packet,
                retrieval_packet=retrieval_packet,
            )
        finally:
            cleanup = getattr(self.tools, "cleanup_bg_jobs", None)
            if cleanup:
                cleanup()
        return result, active_context

    def _emit(self, msg: str, on_event: EventCallback | None) -> None:
        if on_event:
            try:
                on_event(msg)
            except Exception:
                pass

    def _clip_observation(self, text: str) -> str:
        return text if len(text) <= self.config.max_observation_chars else (
            f"{text[:self.config.max_observation_chars]}"
            f"\n...[truncated {len(text) - self.config.max_observation_chars} chars]..."
        )

    def _runtime_policy_check(self, name: str, args: dict[str, Any], depth: int) -> str | None:
        if name != "run_shell":
            return None
        command = str(args.get("command", "")).strip()
        if not command:
            return None
        key = (depth, command)
        with self._lock:
            count = self._shell_command_counts.get(key, 0) + 1
            self._shell_command_counts[key] = count
        if count <= 2:
            return None
        return (
            "Blocked by runtime policy: identical run_shell command repeated more than twice "
            "at the same depth. Change strategy instead of retrying the same command."
        )

    def _judge_result(
        self,
        objective: str,
        acceptance_criteria: str,
        result: str,
        current_model: BaseModel | None = None,
    ) -> str:
        """Evaluate a subtask/execute result against acceptance criteria using a cheap judge model."""
        if not self.model_factory:
            return "PASS\n(no judge available)"

        cur = current_model or self.model
        cur_name = getattr(cur, "model", "")
        judge_name, judge_effort = _lowest_tier_model(cur_name)

        cache_key = ("_judge_" + judge_name, judge_effort)
        with self._lock:
            if cache_key not in self._model_cache:
                try:
                    self._model_cache[cache_key] = self.model_factory(judge_name, judge_effort)
                except Exception:
                    return "PASS\n(no judge available)"
            judge_model = self._model_cache[cache_key]
        if hasattr(judge_model, "tool_defs"):
            judge_model.tool_defs = []

        truncated = result[:4000] if len(result) > 4000 else result
        prompt = (
            "You are a judge evaluating whether a task result meets acceptance criteria.\n\n"
            f"Objective: {objective}\n\n"
            f"Acceptance criteria: {acceptance_criteria}\n\n"
            f"Result:\n{truncated}\n\n"
            "Respond with exactly one line starting with PASS: or FAIL: followed by a brief explanation."
        )

        try:
            conversation = judge_model.create_conversation("You are a concise evaluator.", prompt)
            turn = judge_model.complete(conversation)
            verdict = (turn.text or "").strip()
            if not verdict:
                return "PASS\n(judge returned empty response)"
            return verdict
        except Exception as exc:
            return f"PASS\n(judge error: {exc})"

    def _objective_allows_meta_final(self, objective: str) -> bool:
        return bool(_META_DELIVERABLE_OBJECTIVE_PATTERN.search(objective))

    def _weak_structural_meta_prefix(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in _WEAK_STRUCTURAL_META_PATTERNS)

    def _has_strong_process_meta(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in _STRONG_PROCESS_META_PATTERNS)

    def _substantive_completion_block(self, text: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if self._has_strong_process_meta(stripped):
            return False
        lower = stripped.lower()
        if (
            stripped.startswith("#")
            or stripped.startswith("- ")
            or stripped.startswith("* ")
            or stripped.startswith("1. ")
            or lower.startswith("subject:")
        ):
            return True
        return len(stripped) >= 80

    def _split_nonempty_paragraphs(self, text: str) -> list[str]:
        return [paragraph.strip() for paragraph in text.split("\n\n") if paragraph.strip()]

    def _classify_final_answer_text(self, text: str, objective: str = "") -> str:
        stripped = text.strip()
        if not stripped:
            return "reject_meta"
        allows_structural_meta = self._objective_allows_meta_final(objective)
        has_weak_structural_meta = self._weak_structural_meta_prefix(stripped)
        has_strong_meta = self._has_strong_process_meta(stripped)

        if has_weak_structural_meta and allows_structural_meta and not has_strong_meta:
            return "accept"

        paragraphs = self._split_nonempty_paragraphs(stripped)
        if paragraphs:
            first = paragraphs[0]
            leading_meta = len(first) <= 200 and (
                self._has_strong_process_meta(first) or self._weak_structural_meta_prefix(first)
            )
            if leading_meta and any(
                self._substantive_completion_block(paragraph)
                for paragraph in paragraphs[1:]
            ):
                return "accept"

        for delimiter in ("\n\n", "\n", ":"):
            idx = stripped.find(delimiter)
            if idx == -1:
                continue
            leading = stripped[: idx + len(delimiter)]
            rest = stripped[idx + len(delimiter) :].strip()
            if len(leading) <= 200 and self._has_strong_process_meta(leading):
                if self._substantive_completion_block(rest) or any(
                    self._substantive_completion_block(paragraph)
                    for paragraph in self._split_nonempty_paragraphs(rest)
                ):
                    return "accept"

        if has_strong_meta or (has_weak_structural_meta and not allows_structural_meta):
            return "reject_meta"
        return "accept"

    def _is_meta_final_text(self, text: str, objective: str = "") -> bool:
        return self._classify_final_answer_text(text, objective) == "reject_meta"

    def _append_user_message(self, conversation: Any, content: str) -> None:
        conversation._provider_messages.append({"role": "user", "content": content})

    def _investigation_required_sections(self, objective: str) -> list[str]:
        sections = ["Key Judgments"]
        if _objective_requires_strategic_implications(objective):
            sections.append("Strategic Implications")
        sections.extend(["Supported Findings", "Contested Findings", "Unresolved Findings"])
        return sections

    def _investigation_deliverable_issue(self, text: str, objective: str) -> str | None:
        stripped = text.strip()
        if not stripped:
            return "deliverable is empty"

        parsed_json = _parse_json_object(stripped) if stripped.startswith("{") else None
        if isinstance(parsed_json, dict):
            for key in _INVESTIGATION_REQUIRED_JSON_KEYS:
                if key not in parsed_json:
                    return f"JSON deliverable is missing `{key}`"
            if not _json_sequence_has_content(parsed_json.get("key_judgments")):
                return "JSON deliverable has an empty `key_judgments` field"
            if _objective_requires_strategic_implications(objective):
                if "strategic_implications" not in parsed_json:
                    return "JSON deliverable is missing `strategic_implications`"
                if not _json_sequence_has_content(parsed_json.get("strategic_implications")):
                    return "JSON deliverable has an empty `strategic_implications` field"
            return None

        section_positions: dict[str, int] = {}
        for heading in self._investigation_required_sections(objective):
            match = _find_markdown_section(stripped, heading)
            if match is None:
                return f"Markdown deliverable is missing `## {heading}`"
            section_positions[heading] = match.start()
            if not _markdown_section_body(stripped, heading):
                return f"Markdown deliverable has an empty `## {heading}` section"

        ordered_sections = self._investigation_required_sections(objective)
        for left, right in zip(ordered_sections, ordered_sections[1:]):
            if section_positions[left] >= section_positions[right]:
                return (
                    "Markdown deliverable sections are out of order: "
                    f"`## {left}` must appear before `## {right}`"
                )
        return None

    def _summarize_question_reasoning_packet(
        self,
        packet: dict[str, Any] | None,
    ) -> str:
        if not isinstance(packet, dict):
            return "(none)"
        summary = {
            "focus_question_ids": packet.get("focus_question_ids", [])[:3],
            "unresolved_questions": [
                {
                    "id": item.get("id"),
                    "question": item.get("question") or item.get("question_text"),
                    "priority": item.get("priority"),
                }
                for item in packet.get("unresolved_questions", [])[:3]
                if isinstance(item, dict)
            ],
            "findings": {
                "supported": [
                    item.get("id")
                    for item in packet.get("findings", {}).get("supported", [])[:3]
                    if isinstance(item, dict)
                ],
                "contested": [
                    item.get("id")
                    for item in packet.get("findings", {}).get("contested", [])[:3]
                    if isinstance(item, dict)
                ],
                "unresolved": [
                    item.get("id")
                    for item in packet.get("findings", {}).get("unresolved", [])[:3]
                    if isinstance(item, dict)
                ],
            },
            "candidate_actions": [
                {
                    "id": item.get("id"),
                    "priority": item.get("priority"),
                    "title": item.get("title"),
                    "reason_codes": item.get("reason_codes", [])[:3],
                }
                for item in packet.get("candidate_actions", [])[:3]
                if isinstance(item, dict)
            ],
        }
        return json.dumps(summary, indent=2, ensure_ascii=True)

    def _summarize_retrieval_packet(self, packet: dict[str, Any] | None) -> str:
        if not isinstance(packet, dict):
            return "(none)"

        def _hit_label(item: Any) -> str | None:
            if not isinstance(item, dict):
                return None
            for key in ("title", "label", "path", "source_path", "object_id"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            return None

        hits = packet.get("hits", {}) if isinstance(packet.get("hits"), dict) else {}
        summary = {
            "status": packet.get("status"),
            "provider": packet.get("provider"),
            "model": packet.get("model"),
            "query": packet.get("query", {}),
            "coverage": packet.get("coverage", {}),
            "top_document_hits": [
                label
                for label in (_hit_label(item) for item in hits.get("documents", [])[:3])
                if label
            ],
            "top_ontology_hits": [
                label
                for label in (_hit_label(item) for item in hits.get("ontology_objects", [])[:3])
                if label
            ],
            "top_graph_expansions": [
                label
                for label in (_hit_label(item) for item in hits.get("graph_expansions", [])[:3])
                if label
            ],
        }
        return json.dumps(summary, indent=2, ensure_ascii=True)

    def _build_synthesis_checkpoint_message(
        self,
        objective: str,
        question_reasoning_packet: dict[str, Any],
    ) -> str:
        questions = []
        for item in question_reasoning_packet.get("unresolved_questions", [])[:3]:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question") or item.get("question_text") or "").strip()
            if question:
                questions.append(f"- {question}")
        if not questions:
            questions.append("- Use the highest-priority unresolved question from the reasoning packet.")
        sections = [f"- ## {heading}" for heading in self._investigation_required_sections(objective)]
        return (
            "Mandatory synthesis checkpoint: stop broadening the search unless a missing source is decisive. "
            "Use the evidence already gathered to answer the objective directly.\n\n"
            "Resolve these focus questions now:\n"
            f"{chr(10).join(questions)}\n\n"
            "Required deliverable structure:\n"
            f"{chr(10).join(sections)}\n\n"
            "Translate major connections into objective-facing judgments. "
            "If the evidence is still insufficient, say that explicitly inside Key Judgments or Strategic Implications."
        )

    def _build_refreshed_reasoning_user_message(
        self,
        reason: str,
        question_reasoning_packet: dict[str, Any] | None,
        retrieval_packet: dict[str, Any] | None,
    ) -> str | None:
        payload: dict[str, Any] = {"reasoning_context_refresh": {"reason": reason}}
        if isinstance(question_reasoning_packet, dict):
            payload["question_reasoning_packet"] = question_reasoning_packet
        if isinstance(retrieval_packet, dict):
            payload["retrieval_packet"] = retrieval_packet
        if len(payload) == 1:
            return None
        return json.dumps(payload, ensure_ascii=True)

    def _load_workspace_ontology(self) -> dict[str, Any] | None:
        ontology_path = self.config.workspace / ".openplanter" / "ontology.json"
        if not ontology_path.exists():
            return None
        try:
            raw = json.loads(ontology_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return raw if isinstance(raw, dict) else None

    def _maybe_refresh_reasoning_context_if_needed(
        self,
        *,
        conversation: Any,
        objective: str,
        question_reasoning_packet: dict[str, Any] | None,
        retrieval_packet: dict[str, Any] | None,
        last_state_mtime_ns: int | None,
        on_event: EventCallback | None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int | None, bool]:
        if self.session_dir is None:
            return question_reasoning_packet, retrieval_packet, last_state_mtime_ns, False

        investigation_state_path = self.session_dir / "investigation_state.json"
        if not investigation_state_path.exists():
            return question_reasoning_packet, retrieval_packet, last_state_mtime_ns, False

        try:
            current_mtime_ns = investigation_state_path.stat().st_mtime_ns
        except OSError:
            return question_reasoning_packet, retrieval_packet, last_state_mtime_ns, False

        if last_state_mtime_ns is not None and current_mtime_ns == last_state_mtime_ns:
            return question_reasoning_packet, retrieval_packet, last_state_mtime_ns, False

        try:
            typed_state = load_investigation_state(investigation_state_path)
        except json.JSONDecodeError as exc:
            self._emit(
                f"[reasoning-refresh] skipped typed-state refresh after state change: {exc}",
                on_event,
            )
            return question_reasoning_packet, retrieval_packet, current_mtime_ns, False

        refreshed_packet = build_question_reasoning_packet(
            typed_state,
            workspace_ontology=self._load_workspace_ontology(),
        )
        if not _has_reasoning_packet_content(refreshed_packet):
            refreshed_packet = None

        retrieval_result = build_retrieval_packet(
            workspace=self.config.workspace,
            session_dir=self.session_dir,
            session_root_dir=self.config.session_root_dir,
            objective=objective,
            question_reasoning_packet=refreshed_packet,
            embeddings_provider=self.config.embeddings_provider,
            voyage_api_key=self.config.voyage_api_key,
            mistral_api_key=self.config.mistral_api_key,
            on_event=on_event,
        )
        self._emit(f"[retrieval] {retrieval_result.detail}", on_event)

        refresh_message = self._build_refreshed_reasoning_user_message(
            "investigation_state_changed",
            refreshed_packet,
            retrieval_result.packet,
        )
        if refresh_message is not None:
            self._append_user_message(conversation, refresh_message)
            self._emit("[reasoning-refresh] appended updated reasoning context", on_event)
            return refreshed_packet, retrieval_result.packet, current_mtime_ns, True

        return refreshed_packet, retrieval_result.packet, current_mtime_ns, False

    def _build_finalizer_rescue_payload(
        self,
        objective: str,
        failure_label: str,
        rejected_candidate: str,
        previews: list[str],
        question_reasoning_packet: dict[str, Any] | None,
        retrieval_packet: dict[str, Any] | None,
    ) -> str:
        completed_work = (
            "\n".join(f"- {item}" for item in previews)
            if previews
            else "- (no completed-work notes recorded)"
        )
        if _objective_requires_strategic_implications(objective):
            deliverable_contract = (
                "Return an investigation deliverable with these Markdown sections in order:\n"
                "- ## Key Judgments\n"
                "- ## Strategic Implications\n"
                "- ## Supported Findings\n"
                "- ## Contested Findings\n"
                "- ## Unresolved Findings\n"
                "If you return JSON instead, include non-empty `key_judgments` and `strategic_implications` fields plus supported/contested/unresolved finding arrays."
            )
        else:
            deliverable_contract = (
                "Return an investigation deliverable with these Markdown sections in order:\n"
                "- ## Key Judgments\n"
                "- ## Supported Findings\n"
                "- ## Contested Findings\n"
                "- ## Unresolved Findings\n"
                "If you return JSON instead, include a non-empty `key_judgments` field plus supported/contested/unresolved finding arrays."
            )
        return (
            f"Objective:\n{objective}\n\n"
            f"Failure label: {failure_label}\n\n"
            "Latest question reasoning packet:\n"
            f"{self._summarize_question_reasoning_packet(question_reasoning_packet)}\n\n"
            "Latest retrieval summary:\n"
            f"{self._summarize_retrieval_packet(retrieval_packet)}\n\n"
            "Rejected final-answer candidate:\n"
            f"{(rejected_candidate.strip() or '(none captured)')}\n\n"
            "Completed-work notes:\n"
            f"{completed_work}\n\n"
            f"Deliverable contract:\n{deliverable_contract}\n\n"
            "Rewrite the rejected candidate into the final deliverable only. "
            "Keep required substantive content and formatting, including signatures when they belong in the deliverable. "
            "Remove meta/process/future-tense language. "
            "Do not add new claims, new verification, or new work."
        )

    def _attempt_finalizer_rescue(
        self,
        *,
        model: BaseModel,
        objective: str,
        failure_label: str,
        rejected_candidate: str,
        step_records: list[StepProgressRecord],
        loop_metrics: dict[str, Any],
        on_event: EventCallback | None,
        deadline: float = 0,
        question_reasoning_packet: dict[str, Any] | None = None,
        retrieval_packet: dict[str, Any] | None = None,
    ) -> str | None:
        if self._cancel.is_set():
            self._emit("[finalizer-rescue] skipped: solve already cancelled", on_event)
            return None
        if deadline and time.monotonic() > deadline:
            self._emit("[finalizer-rescue] skipped: deadline already exceeded", on_event)
            return None

        previews = _collect_recent_completed_previews(step_records)
        payload = self._build_finalizer_rescue_payload(
            objective,
            failure_label,
            rejected_candidate,
            previews,
            question_reasoning_packet,
            retrieval_packet,
        )
        self._emit(f"[finalizer-rescue] starting separate-context finalizer rescue ({failure_label})", on_event)

        had_tool_defs = hasattr(model, "tool_defs")
        original_tool_defs = model.tool_defs if had_tool_defs else None
        try:
            if had_tool_defs:
                model.tool_defs = []
            conversation = model.create_conversation(_FINALIZER_RESCUE_SYSTEM_PROMPT, payload)
            turn = model.complete(conversation)
            loop_metrics["model_turns"] += 1
        except Exception as exc:
            self._emit(f"[finalizer-rescue] failed; falling back to stall handling: {exc}", on_event)
            return None
        finally:
            if had_tool_defs:
                model.tool_defs = original_tool_defs

        if turn.tool_calls:
            self._emit("[finalizer-rescue] rejected: rescue returned tool calls", on_event)
            return None

        rescue_text = (turn.text or "").strip()
        if not rescue_text:
            self._emit("[finalizer-rescue] rejected: rescue returned empty text", on_event)
            return None

        if self._classify_final_answer_text(rescue_text, objective) == "reject_meta":
            self._emit("[finalizer-rescue] rejected: rescue output still looked meta", on_event)
            return None
        if _has_reasoning_packet_content(question_reasoning_packet):
            issue = self._investigation_deliverable_issue(rescue_text, objective)
            if issue is not None:
                self._emit(
                    f"[finalizer-rescue] rejected: rescue output still missed the investigation deliverable contract ({issue})",
                    on_event,
                )
                return None

        self._emit("[finalizer-rescue] accepted concrete final answer", on_event)
        return rescue_text

    def _return_final_answer(
        self,
        *,
        depth: int,
        step: int,
        objective: str,
        final_text: str,
        loop_metrics: dict[str, Any],
        on_event: EventCallback | None,
        on_step: StepCallback | None,
        started_at: float,
    ) -> str:
        loop_metrics["phase_counts"]["finalize"] += 1
        loop_metrics["termination_reason"] = "success"
        elapsed = time.monotonic() - started_at
        preview = final_text[:200] + "..." if len(final_text) > 200 else final_text
        self._emit(
            f"[d{depth}/s{step}] final answer ({len(final_text)} chars, {elapsed:.1f}s): {preview}",
            on_event,
        )
        self.last_loop_metrics = loop_metrics
        if on_step:
            try:
                on_step(
                    {
                        "depth": depth,
                        "step": step,
                        "objective": objective,
                        "action": {"name": "final", "arguments": {"text": final_text}},
                        "observation": final_text,
                        "is_final": True,
                        "phase": "finalize",
                        "loop_metrics": dict(loop_metrics),
                    }
                )
            except Exception:
                pass
        return final_text

    def _solve_recursive(
        self,
        objective: str,
        depth: int,
        context: ExternalContext,
        on_event: EventCallback | None = None,
        on_step: StepCallback | None = None,
        on_content_delta: ContentDeltaCallback | None = None,
        deadline: float = 0,
        model_override: BaseModel | None = None,
        replay_logger: ReplayLogger | None = None,
        turn_history: list[TurnSummary] | None = None,
        question_reasoning_packet: dict[str, Any] | None = None,
        retrieval_packet: dict[str, Any] | None = None,
    ) -> str:
        model = model_override or self.model

        self._emit(f"[depth {depth}] objective: {objective}", on_event)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if depth == 0 and not self.config.recursive:
            initial_msg_dict = {
                "timestamp": now_iso,
                "objective": objective,
                "max_steps_per_call": self.config.max_steps_per_call,
                "workspace": str(self.config.workspace),
                "external_context_summary": context.summary(),
            }
        else:
            if depth == 0:
                repl_hint = "Begin REPL cycle 1: start with a broad READ of the workspace."
            else:
                repl_hint = "Begin REPL cycle 1: parent has surveyed — READ only what this objective requires, then act."
            initial_msg_dict = {
                "timestamp": now_iso,
                "objective": objective,
                "depth": depth,
                "max_depth": self.config.max_depth,
                "recursion_policy": self.config.recursion_policy,
                "min_subtask_depth": self.config.min_subtask_depth,
                "required_subtask_depth": self._required_subtask_depth(objective),
                "max_steps_per_call": self.config.max_steps_per_call,
                "workspace": str(self.config.workspace),
                "external_context_summary": context.summary(),
                "repl_hint": repl_hint,
            }
        if self.session_dir is not None:
            initial_msg_dict["session_dir"] = str(self.session_dir)
        if self.session_id is not None:
            initial_msg_dict["session_id"] = self.session_id
        if depth == 0 and turn_history:
            initial_msg_dict["turn_history"] = [t.to_dict() for t in turn_history]
            initial_msg_dict["turn_history_note"] = (
                f"{len(turn_history)} prior turn(s). "
                f"Read replay.jsonl/events.jsonl in session_dir for full details."
            )
        if depth == 0 and question_reasoning_packet is not None:
            initial_msg_dict["question_reasoning_packet"] = question_reasoning_packet
        if depth == 0 and retrieval_packet is not None:
            initial_msg_dict["retrieval_packet"] = retrieval_packet
        initial_message = json.dumps(initial_msg_dict, ensure_ascii=True)

        conversation = model.create_conversation(self.system_prompt, initial_message)
        current_question_reasoning_packet = (
            question_reasoning_packet if _has_reasoning_packet_content(question_reasoning_packet) else None
        )
        current_retrieval_packet = retrieval_packet if isinstance(retrieval_packet, dict) else None
        investigation_state_path = (
            self.session_dir / "investigation_state.json"
            if depth == 0 and self.session_dir is not None
            else None
        )
        last_reasoning_state_mtime_ns: int | None = None
        if investigation_state_path is not None and investigation_state_path.exists():
            try:
                last_reasoning_state_mtime_ns = investigation_state_path.stat().st_mtime_ns
            except OSError:
                last_reasoning_state_mtime_ns = None

        loop_metrics: dict[str, Any] = {
            "steps": 0,
            "model_turns": 0,
            "tool_calls": 0,
            "phase_counts": {"investigate": 0, "build": 0, "iterate": 0, "finalize": 0},
            "recon_streak": 0,
            "max_recon_streak": 0,
            "guardrail_warnings": 0,
            "final_rejections": 0,
            "rewrite_only_violations": 0,
            "finalization_stalls": 0,
            "last_guardrail_streak": 0,
            "budget_extension_enabled": bool(self.config.budget_extension_enabled),
            "budget_extension_block_steps": int(self.config.budget_extension_block_steps),
            "budget_extension_max_blocks": int(self.config.budget_extension_max_blocks),
            "extensions_granted": 0,
            "extension_eligible_checks": 0,
            "extension_denials_no_progress": 0,
            "extension_denials_cap": 0,
            "termination_reason": "",
        }
        step_records: list[StepProgressRecord] = []
        pending_final_rewrite = False
        final_rejection_streak = 0
        rewrite_only_violations = 0
        finalizer_rescue_used = False
        last_rejected_final_candidate = ""
        synthesis_checkpoint_sent = False
        active_step_budget = self.config.max_steps_per_call
        max_total_steps = self.config.max_steps_per_call + (
            self.config.budget_extension_block_steps * self.config.budget_extension_max_blocks
            if self.config.budget_extension_enabled
            else 0
        )
        required_depth = self._required_subtask_depth(objective)
        delegation_requirement_satisfied = depth >= required_depth

        self.last_loop_metrics = loop_metrics

        if replay_logger and replay_logger.needs_header:
            replay_logger.write_header(
                provider=type(model).__name__,
                model=getattr(model, "model", "(unknown)"),
                base_url=getattr(model, "base_url", ""),
                system_prompt=self.system_prompt,
                tool_defs=getattr(model, "tool_defs", None) or [],
                reasoning_effort=getattr(model, "reasoning_effort", None),
                temperature=getattr(model, "temperature", None),
            )

        for step in range(1, max_total_steps + 1):
            force_subtask = self.config.recursive and not delegation_requirement_satisfied
            self._set_model_tool_defs(
                model,
                include_subtask=self.config.recursive,
                delegation_only=force_subtask,
            )
            if self._cancel.is_set():
                self._emit(f"[d{depth}] cancelled by user", on_event)
                loop_metrics["termination_reason"] = "cancelled"
                self.last_loop_metrics = loop_metrics
                return "Task cancelled."
            if deadline and time.monotonic() > deadline:
                self._emit(f"[d{depth}] wall-clock limit reached", on_event)
                loop_metrics["termination_reason"] = "time_limit"
                self.last_loop_metrics = loop_metrics
                return "Time limit exceeded. Try a more focused objective."
            self._emit(f"[d{depth}/s{step}] calling model...", on_event)
            t0 = time.monotonic()
            # Stream thinking/text deltas only for top-level calls
            if on_content_delta and depth == 0 and hasattr(model, "on_content_delta"):
                model.on_content_delta = on_content_delta
            try:
                rate_limit_retries = 0
                while True:
                    if self._cancel.is_set():
                        self._emit(f"[d{depth}] cancelled by user", on_event)
                        loop_metrics["termination_reason"] = "cancelled"
                        self.last_loop_metrics = loop_metrics
                        return "Task cancelled."
                    try:
                        turn = model.complete(conversation)
                        break
                    except RateLimitError as exc:
                        if rate_limit_retries >= self.config.rate_limit_max_retries:
                            self._emit(f"[d{depth}/s{step}] model error: {exc}", on_event)
                            loop_metrics["termination_reason"] = "model_error"
                            self.last_loop_metrics = loop_metrics
                            return f"Model error at depth {depth}, step {step}: {exc}"
                        rate_limit_retries += 1
                        delay: float | None = None
                        if exc.retry_after_sec is not None:
                            delay = min(
                                max(exc.retry_after_sec, 0.0),
                                self.config.rate_limit_retry_after_cap_sec,
                            )
                        if delay is None:
                            delay = self.config.rate_limit_backoff_base_sec * (2 ** (rate_limit_retries - 1))
                        delay += random.uniform(0.0, 0.25)
                        delay = min(delay, self.config.rate_limit_backoff_max_sec)
                        if deadline and (time.monotonic() + delay) > deadline:
                            self._emit(f"[d{depth}] wall-clock limit reached", on_event)
                            loop_metrics["termination_reason"] = "time_limit"
                            self.last_loop_metrics = loop_metrics
                            return "Time limit exceeded. Try a more focused objective."
                        provider_code = f" ({exc.provider_code})" if exc.provider_code is not None else ""
                        self._emit(
                            f"[d{depth}/s{step}] rate limited{provider_code}. "
                            f"Sleeping {delay:.1f}s before retry {rate_limit_retries}/{self.config.rate_limit_max_retries}...",
                            on_event,
                        )
                        if delay > 0:
                            time.sleep(delay)
            except ModelError as exc:
                self._emit(f"[d{depth}/s{step}] model error: {exc}", on_event)
                loop_metrics["termination_reason"] = "model_error"
                self.last_loop_metrics = loop_metrics
                return f"Model error at depth {depth}, step {step}: {exc}"
            finally:
                if hasattr(model, "on_content_delta"):
                    model.on_content_delta = None
            elapsed = time.monotonic() - t0
            loop_metrics["steps"] = step
            loop_metrics["model_turns"] += 1

            if replay_logger:
                try:
                    replay_logger.log_call(
                        depth=depth,
                        step=step,
                        messages=conversation.get_messages(),
                        response=turn.raw_response,
                        input_tokens=turn.input_tokens,
                        output_tokens=turn.output_tokens,
                        elapsed_sec=elapsed,
                    )
                except OSError:
                    pass

            # Accumulate token usage per model
            if turn.input_tokens or turn.output_tokens:
                model_name = getattr(model, "model", "(unknown)")
                with self._lock:
                    bucket = self.session_tokens.setdefault(model_name, {"input": 0, "output": 0})
                    bucket["input"] += turn.input_tokens
                    bucket["output"] += turn.output_tokens

            model.append_assistant_turn(conversation, turn)

            # Context condensation
            if turn.input_tokens:
                model_name = getattr(model, "model", "(unknown)")
                context_window = _MODEL_CONTEXT_WINDOWS.get(model_name, _DEFAULT_CONTEXT_WINDOW)
                if turn.input_tokens > _CONDENSATION_THRESHOLD * context_window:
                    condense_fn = getattr(model, "condense_conversation", None)
                    if condense_fn:
                        condense_fn(conversation)

            if on_step:
                try:
                    on_step(
                        {
                            "depth": depth,
                            "step": step,
                            "objective": objective,
                            "action": {"name": "_model_turn"},
                            "observation": "",
                            "model_text": turn.text or "",
                            "tool_call_names": [tc.name for tc in turn.tool_calls],
                            "input_tokens": turn.input_tokens,
                            "output_tokens": turn.output_tokens,
                            "elapsed_sec": round(elapsed, 2),
                            "is_final": False,
                            "phase": "model",
                        }
                    )
                except Exception:
                    pass

            # No tool calls + text present = final answer
            if not turn.tool_calls and turn.text:
                if force_subtask:
                    self._emit(
                        f"[d{depth}/s{step}] recursion policy blocked shallow final answer; requesting subtask",
                        on_event,
                    )
                    model.append_tool_results(
                        conversation,
                        [
                            ToolResult(
                                tool_call_id="delegation-floor",
                                name="system",
                                content=self._delegation_policy_message(depth, required_depth),
                                is_error=True,
                            )
                        ],
                    )
                    continue
                rejection_message: str | None = None
                rescue_failure_label: str | None = None
                if self._classify_final_answer_text(turn.text, objective) == "reject_meta":
                    rejection_message = (
                        "Final-answer candidate rejected: response is meta/process text. "
                        "Provide a concrete completion summary instead of describing what you will do next."
                    )
                    rescue_failure_label = "meta_rejection_stall"
                elif depth == 0 and _has_reasoning_packet_content(current_question_reasoning_packet):
                    investigation_issue = self._investigation_deliverable_issue(turn.text, objective)
                    if investigation_issue is not None:
                        rejection_message = (
                            "Final-answer candidate rejected: investigation deliverable is missing required conclusion-driven "
                            f"structure ({investigation_issue}). Rewrite it as the final deliverable with the required "
                            "report sections or JSON keys, grounded only in the evidence already gathered."
                        )
                        rescue_failure_label = "insufficient_synthesis_stall"
                if rejection_message is not None:
                    loop_metrics["final_rejections"] += 1
                    final_rejection_streak += 1
                    pending_final_rewrite = True
                    last_rejected_final_candidate = turn.text or ""
                    step_records.append(
                        _special_step_progress_record(
                            step=step,
                            phase="finalize",
                            final_rejection=True,
                        )
                    )
                    self._emit(
                        f"[d{depth}/s{step}] rejected final-answer candidate; requesting concrete completion",
                        on_event,
                    )
                    rejection_result = ToolResult(
                        tool_call_id="meta-final-reject",
                        name="system",
                        content=rejection_message,
                    )
                    model.append_tool_results(conversation, [rejection_result])
                    if final_rejection_streak >= 2:
                        if not finalizer_rescue_used:
                            finalizer_rescue_used = True
                            rescue_text = self._attempt_finalizer_rescue(
                                model=model,
                                objective=objective,
                                failure_label=rescue_failure_label or "final_rejection_stall",
                                rejected_candidate=last_rejected_final_candidate,
                                step_records=step_records,
                                loop_metrics=loop_metrics,
                                on_event=on_event,
                                deadline=deadline,
                                question_reasoning_packet=current_question_reasoning_packet,
                                retrieval_packet=current_retrieval_packet,
                            )
                            if rescue_text is not None:
                                pending_final_rewrite = False
                                final_rejection_streak = 0
                                rewrite_only_violations = 0
                                return self._return_final_answer(
                                    depth=depth,
                                    step=step,
                                    objective=objective,
                                    final_text=rescue_text,
                                    loop_metrics=loop_metrics,
                                    on_event=on_event,
                                    on_step=on_step,
                                    started_at=t0,
                                )
                        loop_metrics["finalization_stalls"] += 1
                        loop_metrics["termination_reason"] = "finalization_stall"
                        self.last_loop_metrics = loop_metrics
                        return _render_partial_completion(
                            objective,
                            loop_metrics,
                            {
                                "eligible": False,
                                "window_size": min(len(step_records), _BUDGET_EXTENSION_WINDOW),
                                "repeated_signature_streak": 0,
                                "failure_ratio": 0.0,
                                "novel_action_count": 0,
                                "state_delta_count": 0,
                                "has_build_or_finalize": True,
                                "has_finalization_churn": True,
                                "positive_signals": 0,
                                "blockers": ["finalization_churn"],
                            },
                            step_records,
                        )
                    continue
                pending_final_rewrite = False
                final_rejection_streak = 0
                rewrite_only_violations = 0
                return self._return_final_answer(
                    depth=depth,
                    step=step,
                    objective=objective,
                    final_text=turn.text,
                    loop_metrics=loop_metrics,
                    on_event=on_event,
                    on_step=on_step,
                    started_at=t0,
                )

            # No tool calls and no text = unexpected empty response
            if not turn.tool_calls:
                self._emit(f"[d{depth}/s{step}] empty model response ({elapsed:.1f}s), nudging...", on_event)
                empty_result = ToolResult(
                    tool_call_id="empty",
                    name="system",
                    content="No tool calls and no text in response. Please use a tool or provide a final answer.",
                )
                model.append_tool_results(conversation, [empty_result])
                continue

            if pending_final_rewrite and turn.tool_calls:
                rewrite_only_violations += 1
                loop_metrics["rewrite_only_violations"] += 1
                artifact_churn = any(tc.name in _ARTIFACT_TOOL_NAMES for tc in turn.tool_calls)
                step_records.append(
                    _special_step_progress_record(
                        step=step,
                        phase="finalize",
                        rewrite_only_violation=True,
                        post_finalization_artifact_churn=artifact_churn,
                    )
                )
                self._emit(
                    f"[d{depth}/s{step}] rewrite-only finalization retry blocked tool calls; requesting plain-text rewrite",
                    on_event,
                )
                model.append_tool_results(
                    conversation,
                    [
                        ToolResult(
                            tool_call_id="rewrite-only-final",
                            name="system",
                            content=(
                                "Your previous response was process/meta commentary rather than a concrete final answer. "
                                "Rewrite it from the completed work only: do not call tools, do not create or verify files, "
                                "and return the direct final deliverable as plain text."
                            ),
                            is_error=True,
                        )
                    ],
                )
                if final_rejection_streak >= 1 and rewrite_only_violations >= 2:
                    if not finalizer_rescue_used:
                        finalizer_rescue_used = True
                        rescue_text = self._attempt_finalizer_rescue(
                            model=model,
                            objective=objective,
                            failure_label="rewrite_only_violation_stall",
                            rejected_candidate=last_rejected_final_candidate,
                            step_records=step_records,
                            loop_metrics=loop_metrics,
                            on_event=on_event,
                            deadline=deadline,
                            question_reasoning_packet=current_question_reasoning_packet,
                            retrieval_packet=current_retrieval_packet,
                        )
                        if rescue_text is not None:
                            pending_final_rewrite = False
                            final_rejection_streak = 0
                            rewrite_only_violations = 0
                            return self._return_final_answer(
                                depth=depth,
                                step=step,
                                objective=objective,
                                final_text=rescue_text,
                                loop_metrics=loop_metrics,
                                on_event=on_event,
                                on_step=on_step,
                                started_at=t0,
                            )
                    loop_metrics["finalization_stalls"] += 1
                    loop_metrics["termination_reason"] = "finalization_stall"
                    self.last_loop_metrics = loop_metrics
                    return _render_partial_completion(
                        objective,
                        loop_metrics,
                        {
                            "eligible": False,
                            "window_size": min(len(step_records), _BUDGET_EXTENSION_WINDOW),
                            "repeated_signature_streak": 0,
                            "failure_ratio": 0.0,
                            "novel_action_count": 0,
                            "state_delta_count": 0,
                            "has_build_or_finalize": True,
                            "has_finalization_churn": True,
                            "positive_signals": 0,
                            "blockers": ["finalization_churn"],
                        },
                        step_records,
                    )
                continue

            if force_subtask and (
                len(turn.tool_calls) != 1 or turn.tool_calls[0].name != "subtask"
            ):
                self._emit(
                    f"[d{depth}/s{step}] recursion policy blocked non-subtask action below required depth {required_depth}",
                    on_event,
                )
                model.append_tool_results(
                    conversation,
                    [
                        ToolResult(
                            tool_call_id="delegation-floor",
                            name="system",
                            content=self._delegation_policy_message(depth, required_depth),
                            is_error=True,
                        )
                    ],
                )
                continue

            # Log tool calls from model
            tc_names = [tc.name for tc in turn.tool_calls]
            loop_metrics["tool_calls"] += len(tc_names)
            has_recon = any(name in _RECON_TOOL_NAMES for name in tc_names)
            has_artifact = any(name in _ARTIFACT_TOOL_NAMES for name in tc_names)
            if has_recon and not has_artifact and all(name in _RECON_TOOL_NAMES for name in tc_names):
                loop_metrics["recon_streak"] += 1
                loop_metrics["phase_counts"]["investigate"] += 1
            elif has_artifact:
                loop_metrics["recon_streak"] = 0
                loop_metrics["last_guardrail_streak"] = 0
                loop_metrics["phase_counts"]["build"] += 1
            else:
                loop_metrics["recon_streak"] = 0
                loop_metrics["last_guardrail_streak"] = 0
                loop_metrics["phase_counts"]["iterate"] += 1
            loop_metrics["max_recon_streak"] = max(
                int(loop_metrics["max_recon_streak"]), int(loop_metrics["recon_streak"])
            )
            self._emit(
                f"[d{depth}/s{step}] model returned {len(turn.tool_calls)} tool call(s) ({elapsed:.1f}s): {', '.join(tc_names)}",
                on_event,
            )
            if turn.text:
                self._emit(f"[d{depth}/s{step}] model text: {turn.text[:200]}", on_event)

            # Execute all tool calls — parallel for subtask/execute, sequential for others.
            results: list[ToolResult] = []
            final_answer: str | None = None

            _PARALLEL_TOOLS = {"subtask", "execute"}

            sequential = [(i, tc) for i, tc in enumerate(turn.tool_calls) if tc.name not in _PARALLEL_TOOLS]
            parallel = [(i, tc) for i, tc in enumerate(turn.tool_calls) if tc.name in _PARALLEL_TOOLS]

            # If no factory and we have execute calls, fall back to sequential.
            if not self.model_factory and any(tc.name == "execute" for _, tc in parallel):
                sequential = list(enumerate(turn.tool_calls))
                parallel = []

            indexed_results: dict[int, tuple[ToolResult, bool]] = {}

            for idx, tc in sequential:
                result_entry, is_final_entry = self._run_one_tool(
                    tc=tc, depth=depth, step=step, objective=objective,
                    context=context, on_event=on_event, on_step=on_step,
                    deadline=deadline, current_model=model,
                    replay_logger=replay_logger,
                )
                indexed_results[idx] = (result_entry, is_final_entry)
                if is_final_entry:
                    final_answer = result_entry.content
                    break

            if parallel and final_answer is None:
                group_id = f"d{depth}-s{step}-{time.monotonic_ns()}"
                use_parallel_owner = len(parallel) > 1
                begin_group = getattr(self.tools, "begin_parallel_write_group", None)
                end_group = getattr(self.tools, "end_parallel_write_group", None)
                if callable(begin_group):
                    begin_group(group_id)
                try:
                    with ThreadPoolExecutor(max_workers=len(parallel)) as pool:
                        futures = {
                            pool.submit(
                                self._run_one_tool,
                                tc=tc, depth=depth, step=step, objective=objective,
                                context=context, on_event=on_event, on_step=on_step,
                                deadline=deadline, current_model=model,
                                replay_logger=replay_logger,
                                parallel_group_id=group_id,
                                parallel_owner=(f"{tc.id or 'tc'}:{idx}" if use_parallel_owner else None),
                            ): idx
                            for idx, tc in parallel
                        }
                        for future in futures:
                            idx = futures[future]
                            result_entry, is_final_entry = future.result()
                            indexed_results[idx] = (result_entry, is_final_entry)
                finally:
                    if callable(end_group):
                        end_group(group_id)

            for i in sorted(indexed_results):
                r, is_final_entry = indexed_results[i]
                results.append(r)
                if is_final_entry and final_answer is None:
                    final_answer = r.content

            if (
                not delegation_requirement_satisfied
                and len(turn.tool_calls) == 1
                and turn.tool_calls[0].name == "subtask"
                and results
                and "Subtask result for" in results[0].content
            ):
                delegation_requirement_satisfied = True

            # Timestamp + step budget + context usage awareness
            if final_answer is None and results:
                budget_total = active_step_budget
                remaining = budget_total - step
                ts_tag = f"[{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}]"
                budget_tag = f"[Step {step}/{budget_total}]"
                _mname = getattr(model, "model", "(unknown)")
                _ctx_window = _MODEL_CONTEXT_WINDOWS.get(_mname, _DEFAULT_CONTEXT_WINDOW)
                ctx_tag = f"[Context {turn.input_tokens}/{_ctx_window} tokens]"
                r0 = results[0]
                results[0] = ToolResult(
                    r0.tool_call_id, r0.name,
                    f"{ts_tag} {budget_tag} {ctx_tag} {r0.content}", r0.is_error,
                    image=r0.image,
                )
                if 0 < remaining <= budget_total // 4:
                    warning = (
                        f"\n\n** BUDGET CRITICAL: {remaining} of {budget_total} steps remain. "
                        "Stop exploring/surveying. Write your output files NOW with your best answer. "
                        "A partial result beats no result."
                    )
                    rl = results[-1]
                    results[-1] = ToolResult(
                        rl.tool_call_id, rl.name,
                        rl.content + warning, rl.is_error,
                        image=rl.image,
                    )
                elif remaining <= budget_total // 2:
                    warning = (
                        f"\n\n** BUDGET WARNING: {remaining} of {budget_total} steps remain. "
                        "Focus on completing the task directly. Do not write exploration scripts."
                    )
                    rl = results[-1]
                    results[-1] = ToolResult(
                        rl.tool_call_id, rl.name,
                        rl.content + warning, rl.is_error,
                        image=rl.image,
                    )

            phase_name = (
                "build"
                if has_artifact
                else "investigate"
                if has_recon and all(name in _RECON_TOOL_NAMES for name in tc_names)
                else "iterate"
            )
            step_records.append(
                _build_step_progress_record(
                    step=step,
                    phase=phase_name,
                    tool_calls=turn.tool_calls,
                    results=results,
                )
            )

            if (
                final_answer is None
                and results
                and int(loop_metrics["recon_streak"]) >= 3
                and not has_artifact
                and int(loop_metrics.get("last_guardrail_streak", 0)) == 0
            ):
                loop_metrics["guardrail_warnings"] += 1
                loop_metrics["last_guardrail_streak"] = int(loop_metrics["recon_streak"])
                soft_warning = ToolResult(
                    "recon-guardrail",
                    "system",
                    (
                        "Soft guardrail: you've spent multiple consecutive steps in read/list/search mode "
                        "without producing artifacts. Move to implementation now (edit files, run targeted "
                        "validation, and return concrete outputs). If recent OCR/transcription/API results "
                        "may be needed again, persist them to workspace files now instead of relying on "
                        "scrollback."
                    ),
                )
                results.append(soft_warning)

            # Plan injection — find newest *.plan.md in session dir, append to last result
            if self.session_dir is not None and results and final_answer is None:
                try:
                    plan_files = sorted(
                        self.session_dir.glob("*.plan.md"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    if plan_files:
                        plan_path = plan_files[0]
                        plan_text = plan_path.read_text(encoding="utf-8")
                        if plan_text.strip():
                            max_pc = self.config.max_plan_chars
                            if len(plan_text) > max_pc:
                                plan_text = plan_text[:max_pc] + "\n...[plan truncated]..."
                            plan_block = (
                                f"\n[SESSION PLAN file={plan_path.name}]\n"
                                f"{plan_text}\n[/SESSION PLAN]\n"
                            )
                            rl = results[-1]
                            results[-1] = ToolResult(
                                rl.tool_call_id, rl.name,
                                rl.content + plan_block, rl.is_error,
                                image=rl.image,
                            )
                except OSError:
                    pass

            model.append_tool_results(conversation, results)

            has_successful_artifact = any(
                tc.name in _ARTIFACT_TOOL_NAMES and not _looks_like_failed_tool_result(tc.name, result)
                for tc, result in zip(turn.tool_calls, results)
            )
            if (
                depth == 0
                and has_successful_artifact
            ):
                (
                    current_question_reasoning_packet,
                    current_retrieval_packet,
                    last_reasoning_state_mtime_ns,
                    _,
                ) = self._maybe_refresh_reasoning_context_if_needed(
                    conversation=conversation,
                    objective=objective,
                    question_reasoning_packet=current_question_reasoning_packet,
                    retrieval_packet=current_retrieval_packet,
                    last_state_mtime_ns=last_reasoning_state_mtime_ns,
                    on_event=on_event,
                )

            should_trigger_synthesis_checkpoint = (
                depth == 0
                and not synthesis_checkpoint_sent
                and _has_reasoning_packet_content(current_question_reasoning_packet)
                and (
                    int(loop_metrics.get("recon_streak", 0)) >= 3
                    or step >= max(1, active_step_budget // 2)
                    or (active_step_budget > 1 and step == active_step_budget - 1)
                )
            )
            if should_trigger_synthesis_checkpoint:
                synthesis_checkpoint_sent = True
                self._append_user_message(
                    conversation,
                    self._build_synthesis_checkpoint_message(
                        objective,
                        current_question_reasoning_packet or {},
                    ),
                )
                self._emit(
                    f"[d{depth}/s{step}] injected mandatory synthesis checkpoint",
                    on_event,
                )

            if final_answer is not None:
                self._emit(f"[d{depth}] completed in {step} step(s)", on_event)
                loop_metrics["termination_reason"] = "success"
                self.last_loop_metrics = loop_metrics
                return final_answer

            for r in results:
                context.add(f"[depth {depth} step {step}]\n{r.content}")

            if step >= active_step_budget:
                evaluation = _evaluate_budget_extension(
                    step_records,
                    recon_streak=int(loop_metrics.get("recon_streak", 0)),
                )
                loop_metrics["extension_eligible_checks"] = int(
                    loop_metrics.get("extension_eligible_checks", 0)
                ) + 1
                loop_metrics["last_budget_extension_eval"] = evaluation
                can_extend = (
                    self.config.budget_extension_enabled
                    and int(loop_metrics.get("extensions_granted", 0)) < self.config.budget_extension_max_blocks
                    and bool(evaluation.get("eligible"))
                )
                if can_extend:
                    loop_metrics["extensions_granted"] = int(loop_metrics.get("extensions_granted", 0)) + 1
                    active_step_budget += self.config.budget_extension_block_steps
                    extension_notice = ToolResult(
                        tool_call_id="budget-extension",
                        name="system",
                        content=(
                            "Progress-based budget extension granted. You have a small number of extra steps. "
                            "Finish the deliverable now and avoid repeating the same loop."
                        ),
                    )
                    model.append_tool_results(conversation, [extension_notice])
                    continue

                if int(loop_metrics.get("extensions_granted", 0)) >= self.config.budget_extension_max_blocks:
                    loop_metrics["extension_denials_cap"] = int(loop_metrics.get("extension_denials_cap", 0)) + 1
                    loop_metrics["termination_reason"] = "budget_cap"
                else:
                    loop_metrics["extension_denials_no_progress"] = int(
                        loop_metrics.get("extension_denials_no_progress", 0)
                    ) + 1
                    loop_metrics["termination_reason"] = "budget_no_progress"
                if depth == 0 and _has_reasoning_packet_content(current_question_reasoning_packet):
                    rescue_text = self._attempt_finalizer_rescue(
                        model=model,
                        objective=objective,
                        failure_label=f"{loop_metrics['termination_reason']}_synthesis_rescue",
                        rejected_candidate=last_rejected_final_candidate,
                        step_records=step_records,
                        loop_metrics=loop_metrics,
                        on_event=on_event,
                        deadline=deadline,
                        question_reasoning_packet=current_question_reasoning_packet,
                        retrieval_packet=current_retrieval_packet,
                    )
                    if rescue_text is not None:
                        pending_final_rewrite = False
                        final_rejection_streak = 0
                        rewrite_only_violations = 0
                        return self._return_final_answer(
                            depth=depth,
                            step=step,
                            objective=objective,
                            final_text=rescue_text,
                            loop_metrics=loop_metrics,
                            on_event=on_event,
                            on_step=on_step,
                            started_at=t0,
                        )
                self.last_loop_metrics = loop_metrics
                return _render_partial_completion(objective, loop_metrics, evaluation, step_records)

        loop_metrics["termination_reason"] = "budget_cap"
        self.last_loop_metrics = loop_metrics
        return _render_partial_completion(
            objective,
            loop_metrics,
            {
                "eligible": False,
                "window_size": 0,
                "repeated_signature_streak": 0,
                "failure_ratio": 0.0,
                "novel_action_count": 0,
                "state_delta_count": 0,
                "has_build_or_finalize": False,
                "positive_signals": 0,
                "blockers": ["max_total_steps"],
            },
            step_records,
        )

    def _run_one_tool(
        self,
        tc: ToolCall,
        depth: int,
        step: int,
        objective: str,
        context: ExternalContext,
        on_event: EventCallback | None,
        on_step: StepCallback | None,
        deadline: float,
        current_model: BaseModel,
        replay_logger: ReplayLogger | None,
        parallel_group_id: str | None = None,
        parallel_owner: str | None = None,
    ) -> tuple[ToolResult, bool]:
        """Run a single tool call. Returns (ToolResult, is_final)."""
        if self._cancel.is_set():
            return ToolResult(tc.id, tc.name, "Task cancelled.", is_error=False), False
        arg_summary = _summarize_args(tc.arguments)
        self._emit(f"[d{depth}/s{step}] {tc.name}({arg_summary})", on_event)

        t1 = time.monotonic()
        scope_fn = getattr(self.tools, "execution_scope", None)
        scope_cm = (
            scope_fn(parallel_group_id, parallel_owner)
            if callable(scope_fn) and parallel_group_id and parallel_owner
            else nullcontext()
        )
        with scope_cm:
            # Clear any pending image data from a previous call.
            self._pending_image.data = None
            try:
                is_final, observation = self._apply_tool_call(
                    tool_call=tc,
                    depth=depth,
                    context=context,
                    on_event=on_event,
                    on_step=on_step,
                    deadline=deadline,
                    current_model=current_model,
                    replay_logger=replay_logger,
                    step=step,
                    child_conversation_owner=parallel_owner,
                )
            except Exception as exc:
                observation = f"Tool {tc.name} crashed: {type(exc).__name__}: {exc}"
                is_final = False
        observation = self._clip_observation(observation)
        tool_elapsed = time.monotonic() - t1

        # Check for pending image data from read_image.
        image: ImageData | None = None
        pending = getattr(self._pending_image, "data", None)
        if pending is not None:
            b64, media_type = pending
            image = ImageData(base64_data=b64, media_type=media_type)
            self._pending_image.data = None

        obs_summary = _summarize_observation(observation)
        self._emit(f"[d{depth}/s{step}]   -> {obs_summary} ({tool_elapsed:.1f}s)", on_event)

        if on_step:
            try:
                on_step(
                    {
                        "depth": depth,
                        "step": step,
                        "objective": objective,
                        "action": {"name": tc.name, "arguments": tc.arguments},
                        "observation": observation,
                        "elapsed_sec": round(tool_elapsed, 2),
                        "is_final": is_final,
                    }
                )
            except Exception:
                pass

        return ToolResult(tc.id, tc.name, observation, is_error=False, image=image), is_final

    def _apply_tool_call(
        self,
        tool_call: ToolCall,
        depth: int,
        context: ExternalContext,
        on_event: EventCallback | None,
        on_step: StepCallback | None,
        deadline: float = 0,
        current_model: BaseModel | None = None,
        replay_logger: ReplayLogger | None = None,
        step: int = 0,
        child_conversation_owner: str | None = None,
    ) -> tuple[bool, str]:
        name = tool_call.name
        args = tool_call.arguments
        policy_error = self._runtime_policy_check(name=name, args=args, depth=depth)
        if policy_error:
            return False, policy_error

        if name == "think":
            note = str(args.get("note", ""))
            return False, f"Thought noted: {note}"

        if name == "list_files":
            glob = args.get("glob")
            return False, self.tools.list_files(glob=str(glob) if glob else None)

        if name == "search_files":
            query = str(args.get("query", "")).strip()
            glob = args.get("glob")
            if not query:
                return False, "search_files requires non-empty query"
            return False, self.tools.search_files(query=query, glob=str(glob) if glob else None)

        if name == "repo_map":
            glob = args.get("glob")
            raw_max_files = args.get("max_files", 200)
            max_files = raw_max_files if isinstance(raw_max_files, int) else 200
            return False, self.tools.repo_map(glob=str(glob) if glob else None, max_files=max_files)

        if name == "web_search":
            query = str(args.get("query", "")).strip()
            if not query:
                return False, "web_search requires non-empty query"
            raw_num_results = args.get("num_results", 10)
            num_results = raw_num_results if isinstance(raw_num_results, int) else 10
            raw_include_text = args.get("include_text", False)
            include_text = bool(raw_include_text) if isinstance(raw_include_text, bool) else False
            return False, self.tools.web_search(
                query=query,
                num_results=num_results,
                include_text=include_text,
            )

        if name == "fetch_url":
            urls = args.get("urls")
            if not isinstance(urls, list):
                return False, "fetch_url requires a list of URL strings"
            return False, self.tools.fetch_url([str(u) for u in urls if isinstance(u, str)])

        if name == "read_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "read_file requires path"
            hashline = args.get("hashline")
            hashline = hashline if hashline is not None else True
            return False, self.tools.read_file(path, hashline=hashline)

        if name == "read_image":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "read_image requires path"
            text, b64, media_type = self.tools.read_image(path)
            if b64 is not None and media_type is not None:
                self._pending_image.data = (b64, media_type)
            return False, text

        if name == "audio_transcribe":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "audio_transcribe requires path"
            diarize = args.get("diarize")
            diarize = diarize if isinstance(diarize, bool) else None
            raw_timestamps = args.get("timestamp_granularities")
            if isinstance(raw_timestamps, list):
                timestamp_granularities = [
                    str(v).strip() for v in raw_timestamps if str(v).strip()
                ]
            elif isinstance(raw_timestamps, str) and raw_timestamps.strip():
                timestamp_granularities = [raw_timestamps.strip()]
            else:
                timestamp_granularities = None
            raw_context_bias = args.get("context_bias")
            if isinstance(raw_context_bias, list):
                context_bias = [
                    str(v).strip() for v in raw_context_bias if str(v).strip()
                ]
            elif isinstance(raw_context_bias, str) and raw_context_bias.strip():
                context_bias = [
                    part.strip()
                    for part in raw_context_bias.split(",")
                    if part.strip()
                ]
            else:
                context_bias = None
            language = str(args.get("language", "")).strip() or None
            model = str(args.get("model", "")).strip() or None
            raw_temperature = args.get("temperature")
            temperature = None
            if isinstance(raw_temperature, (int, float)) and not isinstance(
                raw_temperature, bool
            ):
                temperature = float(raw_temperature)
            chunking = str(args.get("chunking", "")).strip().lower() or None
            raw_chunk_max_seconds = args.get("chunk_max_seconds")
            chunk_max_seconds = None
            if isinstance(raw_chunk_max_seconds, int) and not isinstance(
                raw_chunk_max_seconds, bool
            ):
                chunk_max_seconds = raw_chunk_max_seconds
            raw_chunk_overlap_seconds = args.get("chunk_overlap_seconds")
            chunk_overlap_seconds = None
            if isinstance(raw_chunk_overlap_seconds, (int, float)) and not isinstance(
                raw_chunk_overlap_seconds, bool
            ):
                chunk_overlap_seconds = float(raw_chunk_overlap_seconds)
            raw_max_chunks = args.get("max_chunks")
            max_chunks = None
            if isinstance(raw_max_chunks, int) and not isinstance(raw_max_chunks, bool):
                max_chunks = raw_max_chunks
            raw_continue_on_chunk_error = args.get("continue_on_chunk_error")
            continue_on_chunk_error = (
                raw_continue_on_chunk_error
                if isinstance(raw_continue_on_chunk_error, bool)
                else None
            )
            return False, self.tools.audio_transcribe(
                path=path,
                diarize=diarize,
                timestamp_granularities=timestamp_granularities,
                context_bias=context_bias,
                language=language,
                model=model,
                temperature=temperature,
                chunking=chunking,
                chunk_max_seconds=chunk_max_seconds,
                chunk_overlap_seconds=chunk_overlap_seconds,
                max_chunks=max_chunks,
                continue_on_chunk_error=continue_on_chunk_error,
            )

        if name == "document_ocr":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "document_ocr requires path"
            include_images = (
                args.get("include_images")
                if isinstance(args.get("include_images"), bool)
                else None
            )
            raw_pages = args.get("pages")
            pages: list[int] | None = None
            if isinstance(raw_pages, list):
                pages = []
                for value in raw_pages:
                    if isinstance(value, int) and not isinstance(value, bool):
                        pages.append(value)
            model = str(args.get("model", "")).strip() or None
            return False, self.tools.document_ocr(
                path=path,
                include_images=include_images,
                pages=pages,
                model=model,
            )

        if name == "document_annotations":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "document_annotations requires path"

            def _coerce_schema(value: Any) -> dict[str, Any] | None:
                if isinstance(value, dict):
                    return value
                if isinstance(value, str) and value.strip():
                    try:
                        parsed = json.loads(value)
                    except json.JSONDecodeError:
                        return None
                    if isinstance(parsed, dict):
                        return parsed
                return None

            document_schema = _coerce_schema(args.get("document_schema"))
            bbox_schema = _coerce_schema(args.get("bbox_schema"))
            instruction = str(args.get("instruction", "")).strip() or None
            raw_pages = args.get("pages")
            pages: list[int] | None = None
            if isinstance(raw_pages, list):
                pages = []
                for value in raw_pages:
                    if isinstance(value, int) and not isinstance(value, bool):
                        pages.append(value)
            include_images = (
                args.get("include_images")
                if isinstance(args.get("include_images"), bool)
                else None
            )
            model = str(args.get("model", "")).strip() or None
            return False, self.tools.document_annotations(
                path=path,
                document_schema=document_schema,
                bbox_schema=bbox_schema,
                instruction=instruction,
                pages=pages,
                include_images=include_images,
                model=model,
            )

        if name == "document_qa":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "document_qa requires path"
            question = str(args.get("question", "")).strip()
            if not question:
                return False, "document_qa requires question"
            model = str(args.get("model", "")).strip() or None
            return False, self.tools.document_qa(
                path=path,
                question=question,
                model=model,
            )

        if name == "write_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "write_file requires path"
            content = str(args.get("content", ""))
            return False, self.tools.write_file(path, content)

        if name == "apply_patch":
            patch = str(args.get("patch", ""))
            if not patch.strip():
                return False, "apply_patch requires non-empty patch"
            return False, self.tools.apply_patch(patch)

        if name == "edit_file":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "edit_file requires path"
            old_text = str(args.get("old_text", ""))
            new_text = str(args.get("new_text", ""))
            if not old_text:
                return False, "edit_file requires old_text"
            return False, self.tools.edit_file(path, old_text, new_text)

        if name == "hashline_edit":
            path = str(args.get("path", "")).strip()
            if not path:
                return False, "hashline_edit requires path"
            edits = args.get("edits")
            if not isinstance(edits, list):
                return False, "hashline_edit requires edits array"
            return False, self.tools.hashline_edit(path, edits)

        if name == "run_shell":
            command = str(args.get("command", "")).strip()
            if not command:
                return False, "run_shell requires command"
            raw_timeout = args.get("timeout")
            timeout = int(raw_timeout) if raw_timeout is not None else None
            return False, self.tools.run_shell(command, timeout=timeout)

        if name == "run_shell_bg":
            command = str(args.get("command", "")).strip()
            if not command:
                return False, "run_shell_bg requires command"
            return False, self.tools.run_shell_bg(command)

        if name == "check_shell_bg":
            raw_id = args.get("job_id")
            if raw_id is None:
                return False, "check_shell_bg requires job_id"
            return False, self.tools.check_shell_bg(int(raw_id))

        if name == "kill_shell_bg":
            raw_id = args.get("job_id")
            if raw_id is None:
                return False, "kill_shell_bg requires job_id"
            return False, self.tools.kill_shell_bg(int(raw_id))

        if name == "defrag_workspace":
            obs = self.tools.defrag_workspace(**args)
            return False, obs

        if name == "subtask":
            if not self.config.recursive:
                return False, "Subtask tool not available in flat mode."
            if depth >= self.config.max_depth:
                return False, "Max recursion depth reached; cannot run subtask."
            objective = str(args.get("objective", "")).strip()
            if not objective:
                return False, "subtask requires objective"
            criteria = str(args.get("acceptance_criteria", "") or "").strip()
            if self.config.acceptance_criteria and not criteria:
                return False, (
                    "subtask requires acceptance_criteria when acceptance criteria mode is enabled. "
                    "Provide specific, verifiable criteria for judging the result."
                )

            # Sub-model routing
            requested_model_name = args.get("model")
            requested_effort = args.get("reasoning_effort")
            subtask_model: BaseModel | None = None

            if (requested_model_name or requested_effort) and self.model_factory:
                cur = current_model or self.model
                cur_name = getattr(cur, "model", "")
                cur_effort = getattr(cur, "reasoning_effort", None)
                cur_tier = _model_tier(cur_name, cur_effort)

                req_name = requested_model_name or cur_name
                req_effort = requested_effort
                req_tier = _model_tier(req_name, req_effort or cur_effort)

                if req_tier < cur_tier:
                    return False, (
                        f"Cannot delegate to higher-tier model "
                        f"(current tier {cur_tier}, requested tier {req_tier}). "
                        f"Use an equal or lower-tier model."
                    )

                cache_key = (req_name, requested_effort)
                with self._lock:
                    if cache_key not in self._model_cache:
                        self._model_cache[cache_key] = self.model_factory(req_name, requested_effort)
                    subtask_model = self._model_cache[cache_key]

            self._emit(f"[d{depth}] >> entering subtask: {objective}", on_event)
            child_logger = (
                replay_logger.child(depth, step, owner=child_conversation_owner)
                if replay_logger else None
            )
            subtask_result = self._solve_recursive(
                objective=objective,
                depth=depth + 1,
                context=context,
                on_event=on_event,
                on_step=on_step,
                on_content_delta=None,
                deadline=deadline,
                model_override=subtask_model,
                replay_logger=child_logger,
            )
            observation = f"Subtask result for '{objective}':\n{subtask_result}"

            if criteria and self.config.acceptance_criteria:
                verdict = self._judge_result(objective, criteria, subtask_result, current_model)
                tag = "PASS" if verdict.startswith("PASS") else "FAIL"
                observation += f"\n\n[ACCEPTANCE CRITERIA: {tag}]\n{verdict}"

            return False, observation

        if name == "execute":
            objective = str(args.get("objective", "")).strip()
            if not objective:
                return False, "execute requires objective"
            criteria = str(args.get("acceptance_criteria", "") or "").strip()
            if self.config.acceptance_criteria and not criteria:
                return False, (
                    "execute requires acceptance_criteria when acceptance criteria mode is enabled. "
                    "Provide specific, verifiable criteria for judging the result."
                )
            if depth >= self.config.max_depth:
                return False, "Max recursion depth reached; cannot run execute."

            # Resolve lowest-tier model for the executor.
            cur = current_model or self.model
            cur_name = getattr(cur, "model", "")
            exec_name, exec_effort = _lowest_tier_model(cur_name)

            exec_model: BaseModel | None = None
            if self.model_factory:
                cache_key = (exec_name, exec_effort)
                with self._lock:
                    if cache_key not in self._model_cache:
                        self._model_cache[cache_key] = self.model_factory(exec_name, exec_effort)
                    exec_model = self._model_cache[cache_key]

            # Give executor full tools (no subtask, no execute).
            _saved_defs = None
            if exec_model and hasattr(exec_model, "tool_defs"):
                exec_model.tool_defs = self._build_tool_defs(include_subtask=False)
            elif exec_model is None and hasattr(cur, "tool_defs"):
                _saved_defs = cur.tool_defs
                cur.tool_defs = self._build_tool_defs(include_subtask=False)

            self._emit(f"[d{depth}] >> executing leaf: {objective}", on_event)
            child_logger = (
                replay_logger.child(depth, step, owner=child_conversation_owner)
                if replay_logger else None
            )
            exec_result = self._solve_recursive(
                objective=objective,
                depth=depth + 1,
                context=context,
                on_event=on_event,
                on_step=on_step,
                on_content_delta=None,
                deadline=deadline,
                model_override=exec_model,
                replay_logger=child_logger,
            )
            if _saved_defs is not None:
                cur.tool_defs = _saved_defs
            observation = f"Execute result for '{objective}':\n{exec_result}"

            if criteria and self.config.acceptance_criteria:
                verdict = self._judge_result(objective, criteria, exec_result, current_model)
                tag = "PASS" if verdict.startswith("PASS") else "FAIL"
                observation += f"\n\n[ACCEPTANCE CRITERIA: {tag}]\n{verdict}"

            return False, observation

        if name == "list_artifacts":
            return False, self._list_artifacts()

        if name == "read_artifact":
            aid = str(args.get("artifact_id", "")).strip()
            if not aid:
                return False, "read_artifact requires artifact_id"
            offset = int(args.get("offset", 0) or 0)
            limit = int(args.get("limit", 100) or 100)
            return False, self._read_artifact(aid, offset, limit)

        dynamic_result = self.tools.try_execute_dynamic_tool(name, args)
        if dynamic_result is not None:
            if dynamic_result.image is not None:
                self._pending_image.data = (
                    dynamic_result.image.base64_data,
                    dynamic_result.image.media_type,
                )
            return False, dynamic_result.content

        return False, f"Unknown action type: {name}"

    # ------------------------------------------------------------------
    # Artifact helpers
    # ------------------------------------------------------------------

    def _list_artifacts(self) -> str:
        """List available artifacts."""
        artifacts_dir = self.config.workspace / ".openplanter_artifacts"
        if not artifacts_dir.exists():
            return "No artifacts found."
        entries = sorted(artifacts_dir.glob("*.jsonl"))
        if not entries:
            return "No artifacts found."
        lines = []
        for p in entries:
            try:
                with open(p) as f:
                    first = json.loads(f.readline())
                lines.append(
                    f"- {first.get('artifact_id', p.stem)}: "
                    f"{first.get('objective', '(no objective)')[:120]}"
                )
            except (json.JSONDecodeError, OSError):
                lines.append(f"- {p.stem}: (unreadable)")
        return f"Artifacts ({len(lines)}):\n" + "\n".join(lines)

    def _read_artifact(self, artifact_id: str, offset: int = 0, limit: int = 100) -> str:
        """Read an artifact's conversation log."""
        artifacts_dir = self.config.workspace / ".openplanter_artifacts"
        path = artifacts_dir / f"{artifact_id}.jsonl"
        if not path.exists():
            return f"Artifact '{artifact_id}' not found."
        lines = path.read_text().splitlines()
        total = len(lines)
        selected = lines[offset:offset + limit]
        header = f"Artifact {artifact_id} (lines {offset}-{offset + len(selected)} of {total}):\n"
        return header + "\n".join(selected)
