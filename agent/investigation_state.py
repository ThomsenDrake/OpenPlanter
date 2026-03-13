from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
ONTOLOGY_NAMESPACE = "openplanter.core"
ONTOLOGY_VERSION = "2026-03"
_LEGACY_KNOWN_KEYS = {
    "session_id",
    "saved_at",
    "external_observations",
    "observations",
    "turn_history",
    "loop_metrics",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state(session_id: str, now: str | None = None) -> dict[str, Any]:
    ts = now or utc_now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "created_at": ts,
        "updated_at": ts,
        "objective": "",
        "ontology": {
            "namespace": ONTOLOGY_NAMESPACE,
            "version": ONTOLOGY_VERSION,
        },
        "entities": {},
        "links": {},
        "claims": {},
        "evidence": {},
        "hypotheses": {},
        "questions": {},
        "tasks": {},
        "actions": {},
        "provenance_nodes": {},
        "confidence_profiles": {},
        "timeline": [],
        "indexes": {
            "by_external_ref": {},
            "by_tag": {},
        },
        "legacy": {
            "external_observations": [],
            "turn_history": [],
            "loop_metrics": {},
            "extra_fields": {},
        },
    }


def normalize_legacy_state(session_id: str, raw_state: dict[str, Any]) -> dict[str, Any]:
    state = raw_state if isinstance(raw_state, dict) else {}
    observations = state.get("external_observations")
    if not isinstance(observations, list):
        observations = _observations_from_rust_state(state)

    normalized = {
        "session_id": str(state.get("session_id") or session_id),
        "saved_at": str(state.get("saved_at") or utc_now_iso()),
        "external_observations": _string_list(observations),
        "turn_history": _json_list(state.get("turn_history")),
        "loop_metrics": _json_object(state.get("loop_metrics")),
    }
    normalized.update(_extra_fields_from_legacy_state(state))
    return normalized


def migrate_legacy_state(
    session_id: str,
    legacy_state: dict[str, Any],
    now: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_legacy_state(session_id, legacy_state)
    ts = now or str(normalized.get("saved_at") or utc_now_iso())
    migrated = default_state(session_id=session_id, now=ts)
    migrated["updated_at"] = ts
    migrated["legacy"] = {
        "external_observations": list(normalized.get("external_observations", [])),
        "turn_history": _json_list(normalized.get("turn_history")),
        "loop_metrics": _json_object(normalized.get("loop_metrics")),
        "extra_fields": {
            key: value
            for key, value in normalized.items()
            if key not in {"session_id", "saved_at", "external_observations", "turn_history", "loop_metrics"}
        },
    }
    return upsert_legacy_observations(migrated, migrated["legacy"]["external_observations"], now=ts)


def state_to_legacy_projection(state: dict[str, Any], session_id: str) -> dict[str, Any]:
    legacy = state.get("legacy", {})
    legacy_dict = legacy if isinstance(legacy, dict) else {}
    projected = {
        "session_id": str(state.get("session_id") or session_id),
        "saved_at": str(state.get("updated_at") or utc_now_iso()),
        "external_observations": _legacy_observations_from_state(state),
        "turn_history": _json_list(legacy_dict.get("turn_history")),
        "loop_metrics": _json_object(legacy_dict.get("loop_metrics")),
    }
    extras = legacy_dict.get("extra_fields")
    if isinstance(extras, dict):
        projected.update(copy.deepcopy(extras))
    return projected


def upsert_legacy_observations(
    state: dict[str, Any],
    observations: list[str],
    now: str | None = None,
) -> dict[str, Any]:
    ts = now or utc_now_iso()
    out = copy.deepcopy(state)
    out.setdefault("schema_version", SCHEMA_VERSION)
    out.setdefault("session_id", "")
    out.setdefault("created_at", ts)
    out["updated_at"] = ts
    out.setdefault(
        "ontology",
        {
            "namespace": ONTOLOGY_NAMESPACE,
            "version": ONTOLOGY_VERSION,
        },
    )
    out.setdefault("entities", {})
    out.setdefault("links", {})
    out.setdefault("claims", {})
    out.setdefault("hypotheses", {})
    out.setdefault("questions", {})
    out.setdefault("tasks", {})
    out.setdefault("actions", {})
    out.setdefault("provenance_nodes", {})
    out.setdefault("confidence_profiles", {})
    out.setdefault("timeline", [])

    indexes = out.setdefault("indexes", {})
    if not isinstance(indexes, dict):
        indexes = {}
        out["indexes"] = indexes
    by_external_ref = indexes.setdefault("by_external_ref", {})
    if not isinstance(by_external_ref, dict):
        by_external_ref = {}
        indexes["by_external_ref"] = by_external_ref
    indexes.setdefault("by_tag", {})

    legacy = out.setdefault("legacy", {})
    if not isinstance(legacy, dict):
        legacy = {}
        out["legacy"] = legacy
    legacy["external_observations"] = [str(item) for item in observations]
    legacy.setdefault("turn_history", [])
    legacy.setdefault("loop_metrics", {})
    legacy.setdefault("extra_fields", {})

    evidence = out.setdefault("evidence", {})
    if not isinstance(evidence, dict):
        evidence = {}
        out["evidence"] = evidence

    for index, observation in enumerate(observations):
        evidence_id = _legacy_evidence_id(index)
        source_uri = _legacy_source_uri(index)
        existing = evidence.get(evidence_id)
        record = existing if isinstance(existing, dict) else {}
        created_at = str(record.get("created_at") or ts)
        record.update(
            {
                "id": evidence_id,
                "evidence_type": "legacy_observation",
                "content": str(observation),
                "source_uri": source_uri,
                "normalization": {
                    "kind": "legacy_observation",
                    "normalization_version": "legacy-v1",
                },
                "provenance_ids": [],
                "confidence_id": None,
                "created_at": created_at,
                "updated_at": ts,
            }
        )
        evidence[evidence_id] = record
        by_external_ref[source_uri] = evidence_id

    keep_ids = {_legacy_evidence_id(index) for index in range(len(observations))}
    for evidence_id in list(evidence.keys()):
        record = evidence.get(evidence_id)
        if _is_legacy_evidence(evidence_id, record) and evidence_id not in keep_ids:
            del evidence[evidence_id]

    for key in list(by_external_ref.keys()):
        value = by_external_ref.get(key)
        if (
            isinstance(key, str)
            and key.startswith("state.json#external_observations[")
            and isinstance(value, str)
            and value.startswith("ev_legacy_")
            and value not in keep_ids
        ):
            del by_external_ref[key]

    return out


def load_investigation_state(path: Path) -> dict[str, Any]:
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise json.JSONDecodeError("Investigation state must be a JSON object", str(path), 0)
    return state


def save_investigation_state(path: Path, state: dict[str, Any]) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _json_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return copy.deepcopy(value)


def _json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return copy.deepcopy(value)


def _observations_from_rust_state(state: dict[str, Any]) -> list[str]:
    observations = state.get("observations")
    if not isinstance(observations, list):
        return []

    out: list[str] = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, str):
            out.append(content)
    return out


def _extra_fields_from_legacy_state(state: dict[str, Any]) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    for key, value in state.items():
        if key not in _LEGACY_KNOWN_KEYS:
            extras[key] = copy.deepcopy(value)
    return extras


def _legacy_observations_from_state(state: dict[str, Any]) -> list[str]:
    legacy = state.get("legacy", {})
    if isinstance(legacy, dict):
        persisted = legacy.get("external_observations")
        if isinstance(persisted, list):
            return [str(item) for item in persisted]

    evidence = state.get("evidence", {})
    if isinstance(evidence, dict):
        legacy_records: list[tuple[str, str]] = []
        for evidence_id, record in evidence.items():
            if not _is_legacy_evidence(str(evidence_id), record):
                continue
            content = record.get("content") if isinstance(record, dict) else None
            if isinstance(content, str):
                legacy_records.append((str(evidence_id), content))
        legacy_records.sort(key=lambda item: item[0])
        return [content for _, content in legacy_records]

    return []


def _legacy_evidence_id(index: int) -> str:
    return f"ev_legacy_{index + 1:06d}"


def _legacy_source_uri(index: int) -> str:
    return f"state.json#external_observations[{index}]"


def _is_legacy_evidence(evidence_id: str, record: Any) -> bool:
    if not evidence_id.startswith("ev_legacy_") or not isinstance(record, dict):
        return False
    normalization = record.get("normalization")
    return isinstance(normalization, dict) and normalization.get("kind") == "legacy_observation"
