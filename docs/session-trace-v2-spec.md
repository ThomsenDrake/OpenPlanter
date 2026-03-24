# OpenPlanter Session Trace v2 Spec

**Status:** Draft v2 implementation spec  
**Last updated:** 2026-03-23  
**Applies to:** Python agent sessions, Rust desktop sessions, and frontend replay/history consumers

## 1. Purpose

This document defines the additive, backwards-compatible v2 session trace contract for OpenPlanter.

The goal is to give Python, Rust, and frontend implementations one concrete session model for:

- durable session metadata,
- replay and event recording,
- minimum per-turn resumability,
- provenance and evidence drill-down,
- reliability and failure reporting,
- compatibility with both legacy Python sessions and newer desktop sessions,
- and future ontology-linked session views promised by `VISION.md`.

This spec does not require destructive migration. Existing sessions must remain readable as-is. v2 writers may emit new fields and new files, but v1-era `metadata.json`, `events.jsonl`, and `replay.jsonl` remain valid inputs.

## 2. Design Goals

1. Additive only. No destructive rewrite of historical sessions is required.
2. One logical model. Python and desktop may persist different subsets, but they must map to the same canonical schema.
3. Durable per-turn continuity. Every turn must be recoverable enough to explain what was asked, what happened, what evidence was produced, and how the turn ended.
4. Curated-first, drill-down always. High-level replay should stay easy to render, but every user-visible claim must be traceable to events, artifacts, or ontology objects.
5. Append-friendly. Writers should append records rather than rewrite long logs.
6. Failure-explicit. Reliability state must be represented directly rather than inferred from missing output.
7. Frontend-safe. The canonical envelope must be easy to stream, diff, filter, and render in the desktop UI.
8. Ontology-ready. Provenance fields must support later graph, map, timeline, and audit views without another trace redesign.

## 3. Non-goals

This spec does not yet require:

- tamper-evident cryptographic chaining,
- destructive migration or one-shot backfill jobs,
- ontology-native storage of every reasoning object,
- multi-user merge semantics,
- replacement of existing legacy readers on day one.

Those can be layered on top of this contract later.

## 4. On-disk Contract

A session directory may contain legacy files, v2 files, or both.

### 4.1 Required readable files

Readers must continue to accept:

- `metadata.json`
- `events.jsonl` when present
- `replay.jsonl` when present

### 4.2 v2 writer outputs

A v2-capable writer should emit the following files when possible:

- `metadata.json` - canonical session metadata object
- `events.jsonl` - canonical append-only operational event stream
- `replay.jsonl` - canonical curated replay stream
- `turns.jsonl` - optional but recommended append-only minimum durable per-turn records

`turns.jsonl` is new in v2. It is a durability and resume file, not a replacement for `events.jsonl`.

### 4.3 Storage guarantees

1. Readers must tolerate sessions with only `metadata.json`.
2. Readers must tolerate sessions with only `events.jsonl`, only `replay.jsonl`, or both.
3. Readers must ignore unknown fields.
4. Writers must not delete legacy fields during additive upgrade.
5. Writers must not renumber legacy `seq` values.

### 4.4 Write ordering

For a turn that reaches execution:

1. append `turn.started`,
2. append `turn.objective`,
3. append zero or more intermediate `events.jsonl` records,
4. append replay milestones as summaries become available,
5. append terminal `turn.completed`, `turn.failed`, or `turn.cancelled`,
6. append the final `turns.jsonl` record,
7. update `metadata.json`.

If the process dies before step 6, the turn is still reconstructable from `events.jsonl`. If it dies after step 1 but before a terminal event, readers must classify the interrupted turn as `partial` and later surface any follow-on continuation as `resumed_from_partial`.

## 5. Canonical Metadata Schema

`metadata.json` is the canonical session header.

### 5.1 Canonical metadata example

```json
{
  "schema_version": 2,
  "session_format": "openplanter.session.v2",
  "session_id": "20260323-abc12345",
  "created_at": "2026-03-23T10:15:30Z",
  "updated_at": "2026-03-23T10:32:04Z",
  "workspace_id": "freebee-investigation",
  "workspace_path": "/abs/or/logical/path",
  "session_origin": "python",
  "session_kind": "investigation",
  "title": "optional human-readable title",
  "status": "active",
  "turn_count": 4,
  "last_turn_id": "turn-000004",
  "last_objective": "Investigate X and summarize findings",
  "continuity_mode": "resume",
  "source_compat": {
    "legacy_python_metadata": true,
    "desktop_metadata": false,
    "legacy_event_stream_present": true,
    "legacy_replay_stream_present": true
  },
  "capabilities": {
    "supports_events_v2": true,
    "supports_replay_v2": true,
    "supports_turns_v2": true,
    "supports_provenance_links": true,
    "supports_failure_taxonomy_v2": true
  },
  "durability": {
    "events_jsonl_present": true,
    "replay_jsonl_present": true,
    "turns_jsonl_present": false,
    "partial_records_possible": true
  },
  "active_provider": {
    "provider": "openai",
    "model": "gpt-5.2-codex",
    "request_profile": "default"
  },
  "migration": null,
  "provenance_defaults": {
    "session_dir": ".openplanter/sessions/20260323-abc12345"
  }
}
```

### 5.2 Required metadata fields for v2 writers

| Field | Type | Required | Notes |
|---|---|---:|---|
| `schema_version` | integer | yes | Must be `2`. |
| `session_format` | string | yes | Must be `openplanter.session.v2`. |
| `session_id` | string | yes | Canonical session identifier. |
| `created_at` | RFC3339 string | yes | Session creation time. |
| `updated_at` | RFC3339 string | yes | Last durable write time. |
| `session_origin` | enum | yes | `python`, `desktop`, `imported`, or `unknown`. |
| `session_kind` | enum | yes | `investigation`, `chat`, `analysis`, `repair`, or `other`. |
| `status` | enum | yes | `active`, `completed`, `failed`, `cancelled`, `partial`, or `archived`. |
| `turn_count` | integer | yes | Count of known turns, including partial turns. |
| `continuity_mode` | enum | yes | `new`, `resume`, `fork`, or `imported`. |
| `source_compat` | object | yes | What legacy shapes were detected. |
| `capabilities` | object | yes | What v2 features this session actually contains. |
| `last_turn_id` | string or null | recommended | Latest known turn identifier. |
| `last_objective` | string or null | recommended | Latest objective text if known. |
| `workspace_id` | string or null | recommended | Stable logical workspace identifier. |
| `workspace_path` | string or null | recommended | Path-oriented workspace reference when available. |

### 5.3 Additional metadata fields allowed

Writers may add namespaced fields under:

- `runtime`
- `ui`
- `extensions`

Implementations must ignore unknown fields.

### 5.4 Recommended metadata objects

#### `source_compat`

```json
{
  "legacy_python_metadata": true,
  "desktop_metadata": false,
  "legacy_event_stream_present": true,
  "legacy_replay_stream_present": true
}
```

#### `capabilities`

```json
{
  "supports_events_v2": true,
  "supports_replay_v2": true,
  "supports_turns_v2": true,
  "supports_provenance_links": true,
  "supports_failure_taxonomy_v2": true
}
```

#### `durability`

```json
{
  "events_jsonl_present": true,
  "replay_jsonl_present": true,
  "turns_jsonl_present": true,
  "partial_records_possible": true
}
```

#### `active_provider`

```json
{
  "provider": "openai",
  "model": "gpt-5.2-codex",
  "request_profile": "default"
}
```

#### `migration`

```json
{
  "upgraded_from": "legacy-python",
  "upgraded_at": "2026-03-23T12:34:56Z",
  "upgrade_mode": "additive-in-place"
}
```

### 5.5 Legacy metadata mapping

| Legacy source | Canonical field |
|---|---|
| `metadata.session_id` | `session_id` |
| `metadata.id` | `session_id` |
| `metadata.workspace` | `workspace_path` by default; may also populate `workspace_id` if the runtime can resolve one |
| `metadata.created_at` | `created_at` |
| `metadata.updated_at` | `updated_at` |
| `metadata.turn_count` | `turn_count` |
| `metadata.last_objective` | `last_objective` |

If both legacy and v2 keys are present, readers must prefer the explicit v2 keys and preserve the legacy keys unchanged.

## 6. Canonical Replay/Event Envelope

v2 defines one logical envelope used by both `events.jsonl` and `replay.jsonl`. The files differ by intended density, not by schema family.

- `events.jsonl` contains the fuller operational stream.
- `replay.jsonl` contains curated, user-facing milestones and summaries.

Each line is one JSON object matching the canonical envelope below.

### 6.1 Canonical envelope example

```json
{
  "schema_version": 2,
  "envelope": "openplanter.trace.event.v2",
  "event_id": "evt-01H...",
  "session_id": "20260323-abc12345",
  "turn_id": "turn-000004",
  "seq": 187,
  "recorded_at": "2026-03-23T10:21:12.482Z",
  "event_type": "step.summary",
  "channel": "replay",
  "status": "completed",
  "actor": {
    "kind": "assistant",
    "id": "default-agent",
    "display": "OpenPlanter",
    "runtime_family": "desktop",
    "provider": "openai",
    "model": "gpt-5.2-codex"
  },
  "payload": {
    "text": "Reviewed three documents and identified two contradictions.",
    "step_index": 2
  },
  "failure": null,
  "provenance": {
    "record_locator": {
      "file": "replay.jsonl",
      "line": 48
    },
    "parent_event_id": "evt-01G...",
    "caused_by": ["evt-01F..."],
    "source_refs": [
      {
        "kind": "event_span",
        "start_seq": 180,
        "end_seq": 186
      }
    ],
    "evidence_refs": [
      {
        "kind": "artifact",
        "id": "artifact-004",
        "label": "notes/findings.md",
        "locator": {
          "path": "notes/findings.md",
          "line_start": 15,
          "line_end": 38
        }
      }
    ],
    "ontology_refs": [],
    "generated_from": {
      "provider": "openai",
      "model": "gpt-5.2-codex",
      "request_id": "req_abc123",
      "conversation_id": "root/d1s2"
    }
  },
  "compat": {
    "legacy_role": "step-summary",
    "legacy_kind": null,
    "source_schema": "desktop-replay-v1"
  }
}
```

### 6.2 Required envelope fields

| Field | Type | Required | Notes |
|---|---|---:|---|
| `schema_version` | integer | yes | Must be `2`. |
| `envelope` | string | yes | Must be `openplanter.trace.event.v2`. |
| `event_id` | string | yes | Logical event identifier, stable across duplicate replay/event projections of the same event. |
| `session_id` | string | yes | Session identifier. |
| `turn_id` | string or null | recommended | Required for turn-scoped events. |
| `seq` | integer | yes | Monotonic append order within the current file. |
| `recorded_at` | RFC3339 string | yes | Durable write timestamp. |
| `event_type` | string | yes | Canonical event type name. |
| `channel` | enum | yes | `event`, `replay`, or `both`. |
| `status` | enum | yes | `started`, `in_progress`, `completed`, `failed`, `cancelled`, `degraded`, `partial`, or `info`. |
| `actor` | object | yes | Producer or speaker. |
| `payload` | object | yes | Event-specific body. |
| `failure` | object or null | yes | Present when the event represents failure, degraded execution, or resume lineage. |
| `provenance` | object | yes | Drill-down references and causal links. |
| `compat` | object | yes | Original legacy role/type mapping when generated from older traces. |

### 6.3 Envelope invariants

1. `seq` must increase monotonically within a file.
2. `event_id` identifies the logical event, not the physical line. If the same logical event is projected into both `events.jsonl` and `replay.jsonl`, both lines should carry the same `event_id`.
3. `turn_id` must be stable across all records that belong to the same turn.
4. `recorded_at` is the durable append timestamp, not necessarily the model or tool start time.
5. Unknown `event_type` values must be preserved and rendered generically rather than discarded.

### 6.4 Canonical actor object

```json
{
  "kind": "assistant",
  "id": "default-agent",
  "display": "OpenPlanter",
  "runtime_family": "python",
  "provider": "openai",
  "model": "gpt-5.2-codex"
}
```

Required actor fields:

- `kind`: `user`, `assistant`, `system`, `tool`, `curator`, `runtime`, or `importer`
- `runtime_family`: `python`, `desktop`, `frontend`, `imported`, or `unknown`

Recommended actor fields:

- `id`
- `display`
- `provider`
- `model`

### 6.5 Canonical event types

The following event types are the minimum shared vocabulary for v2.

#### Session-scope

- `session.started`
- `session.resumed`
- `session.completed`
- `session.failed`
- `session.cancelled`
- `session.upgraded`

#### Turn lifecycle

- `turn.started`
- `turn.objective`
- `turn.context`
- `turn.completed`
- `turn.failed`
- `turn.cancelled`
- `turn.resumed_from_partial`

#### Execution detail

- `step.started`
- `step.summary`
- `step.completed`
- `tool.called`
- `tool.completed`
- `tool.failed`
- `artifact.created`
- `artifact.updated`
- `trace.note`
- `trace.warning`
- `trace.error`

#### User-visible outputs

- `user.message`
- `assistant.message`
- `assistant.final`
- `curator.note`
- `result.summary`

#### Reliability and control

- `runtime.rate_limited`
- `runtime.timeout`
- `runtime.degraded`
- `runtime.cancel_requested`
- `runtime.resume_scheduled`

Implementations may define additional dot-namespaced event types, but the names above must retain the meanings defined here.

### 6.6 Replay selection rules

`replay.jsonl` should contain only events useful as a curated investigation narrative. Recommended inclusions:

- `session.started`
- `session.resumed`
- `turn.objective`
- `step.summary`
- `curator.note`
- `assistant.message`
- `assistant.final`
- `result.summary`
- `turn.failed`
- `turn.cancelled`
- `turn.resumed_from_partial`
- `runtime.degraded` when it changed the user-visible outcome

A replay line must still use the canonical envelope and preserve `event_id`, `turn_id`, and provenance references.

## 7. Minimum Durable Per-turn Record

Each executed turn should append one record to `turns.jsonl` after the turn reaches a terminal state. This record is the minimum unit required for resume, overview generation, handoff, and session-history cards.

### 7.1 Canonical turn record example

```json
{
  "schema_version": 2,
  "record": "openplanter.trace.turn.v2",
  "session_id": "20260323-abc12345",
  "turn_id": "turn-000004",
  "turn_index": 4,
  "started_at": "2026-03-23T10:18:00Z",
  "ended_at": "2026-03-23T10:22:41Z",
  "objective": "Compare the March 11 and March 20 findings and note contradictions.",
  "continuity": {
    "mode": "resume",
    "resumed_from_turn_id": "turn-000003",
    "resumed_from_partial": false,
    "checkpoint_ref": null
  },
  "inputs": {
    "user_message_ref": "evt-101",
    "attachments": [],
    "context_refs": ["evt-095", "evt-099"]
  },
  "outputs": {
    "assistant_final_ref": "evt-140",
    "result_summary_ref": "evt-141",
    "artifact_refs": ["artifact-004", "artifact-005"]
  },
  "execution": {
    "step_count": 3,
    "tool_call_count": 7,
    "degraded": false,
    "resumed": false
  },
  "outcome": {
    "status": "completed",
    "failure_code": null,
    "failure": null,
    "summary": "Found two contradictions and wrote a comparison note."
  },
  "provenance": {
    "event_span": {
      "start_seq": 155,
      "end_seq": 192
    },
    "replay_span": {
      "start_seq": 44,
      "end_seq": 49
    },
    "evidence_refs": [
      {
        "kind": "artifact",
        "id": "artifact-004"
      }
    ],
    "ontology_refs": []
  }
}
```

### 7.2 Required turn record fields

A v2 turn record must explicitly name:

- `session_id`
- `turn_id`
- `turn_index`
- `started_at`
- `objective`
- `continuity.mode`
- `inputs.user_message_ref` or explicit `null`
- `outputs.assistant_final_ref` or explicit `null`
- `outputs.result_summary_ref` or explicit `null`
- `outputs.artifact_refs`
- `execution.step_count`
- `execution.tool_call_count`
- `execution.degraded`
- `outcome.status`
- `outcome.failure_code`
- `outcome.failure` when `outcome.failure_code` is non-null
- `outcome.summary`
- `provenance.event_span.start_seq`
- `provenance.event_span.end_seq`

`ended_at` is required for terminal turns and may be `null` only for imported partial turns.

### 7.3 Terminal outcome values

`outcome.status` must be one of:

- `completed`
- `failed`
- `cancelled`
- `partial`
- `resumed_from_partial`

Recommended writer behavior:

- original interrupted turn => `outcome.status = "partial"`
- resumed follow-on turn => `continuity.resumed_from_partial = true`
- resumed follow-on terminal state => `outcome.status` reflects the actual terminal state (`completed`, `failed`, or `cancelled`)

Readers must still accept `resumed_from_partial` as a terminal outcome for compatibility with early v2 writers.

### 7.4 Durability rules

1. `turn.started` should be appended before substantive work begins.
2. `turn.objective` must be appended once the objective text is known.
3. A terminal turn event must be appended before the session metadata advances to the next turn.
4. If a process dies after `turn.started` but before terminal state, readers must surface the turn as `partial`.
5. If a resumed turn continues partial work, writers should append `turn.resumed_from_partial`, set `continuity.resumed_from_partial = true`, and link the original turn via `continuity.resumed_from_turn_id`.

## 8. Provenance Fields For Evidence Drill-down

Every user-visible replay item should be traceable to exact underlying evidence. v2 therefore standardizes provenance references.

### 8.1 Canonical provenance object

```json
{
  "record_locator": {
    "file": "events.jsonl",
    "line": 144
  },
  "parent_event_id": "evt-120",
  "caused_by": ["evt-118", "evt-119"],
  "source_refs": [
    {
      "kind": "jsonl_record",
      "file": "events.jsonl",
      "line": 144,
      "event_id": "evt-118"
    },
    {
      "kind": "event_span",
      "start_seq": 155,
      "end_seq": 162
    }
  ],
  "evidence_refs": [
    {
      "kind": "artifact",
      "id": "artifact-004",
      "label": "docs/findings.md",
      "locator": {
        "path": "docs/findings.md",
        "line_start": 15,
        "line_end": 38
      }
    }
  ],
  "ontology_refs": [
    {
      "object_type": "Claim",
      "object_id": "claim-92",
      "relation": "supports"
    }
  ],
  "generated_from": {
    "provider": "openai",
    "model": "gpt-5.2-codex",
    "request_id": "req_abc123",
    "conversation_id": "root/d1s2"
  }
}
```

### 8.2 Required provenance subfields

For any event in `replay.jsonl` with user-visible content (`turn.objective`, `step.summary`, `assistant.message`, `assistant.final`, `curator.note`, `result.summary`, and failure events), writers must provide:

- `provenance.source_refs` with at least one event, event-span, replay-event, or JSONL-line reference,
- `provenance.evidence_refs` as an array, possibly empty,
- `provenance.parent_event_id` when the replay entry is a summary or derivative of another event,
- `provenance.caused_by` when a tool call, runtime failure, or earlier event materially caused the replay item.

`record_locator.file` and `record_locator.line` are recommended but may be backfilled at read time when appenders do not know the final line number at write time.

### 8.3 Source reference kinds

`source_refs[].kind` must be one of:

- `event`
- `replay_event`
- `event_span`
- `jsonl_record`
- `tool_call`
- `state_snapshot`

### 8.4 Evidence reference kinds

`evidence_refs[].kind` must be one of:

- `artifact`
- `file`
- `patch`
- `tool_output`
- `message`
- `ontology_object`
- `url`
- `external_source`

### 8.5 Artifact reference shape

When `kind = "artifact"`, the reference should include:

- `id`
- `label`
- `locator.path`
- optional `locator.line_start`
- optional `locator.line_end`
- optional `locator.byte_start`
- optional `locator.byte_end`
- optional `locator.content_hash`

### 8.6 Drill-down guarantees

The spec requires the following minimum drill-down guarantees:

1. A replay entry can locate its originating turn via `turn_id`.
2. A replay entry can locate at least one underlying event, event span, or JSONL line via `source_refs`.
3. A turn record can locate its operational event span via `provenance.event_span`.
4. A final answer or curator note can point to zero or more artifacts or ontology objects via `evidence_refs` and `ontology_refs`.
5. If exact line ranges are unknown, writers must still provide the artifact path or identifier.

## 9. Failure Taxonomy

Failures and degraded states must be explicit. The canonical failure object is used in event and replay envelopes and may be embedded in `turns.jsonl` as `outcome.failure` when a turn needs durable failure detail beyond `outcome.failure_code`.

### 9.1 Canonical failure object

```json
{
  "code": "rate_limit",
  "category": "transient",
  "phase": "model_completion",
  "retryable": true,
  "resumable": true,
  "user_visible": true,
  "message": "Provider returned HTTP 429.",
  "provider": "openai",
  "provider_code": "429",
  "http_status": 429,
  "details": {
    "model": "gpt-5.2-codex",
    "request_id": "req_abc123"
  }
}
```

### 9.2 Required failure fields

- `code`
- `category`
- `phase`
- `retryable`
- `message`
- `details`

Recommended additional fields:

- `resumable`
- `user_visible`
- `provider`
- `provider_code`
- `http_status`

### 9.3 Canonical failure codes

The following codes are reserved and should be used whenever applicable:

| Code | Meaning | Typical terminal status |
|---|---|---|
| `rate_limit` | Provider or service quota/rate limit hit | `failed` or `partial` |
| `timeout` | Operation exceeded configured timeout | `failed` or `partial` |
| `cancelled` | User or runtime cancellation completed | `cancelled` |
| `degraded` | Turn completed with known degraded quality or missing steps | `completed` or `partial` |
| `resumed_from_partial` | Informational continuity code for resumed work | `completed`, `partial`, or replay-only notice |
| `network_error` | Transport-level connectivity failure | `failed` |
| `provider_error` | Remote provider internal error | `failed` |
| `tool_error` | Tool invocation failed | `failed` or `partial` |
| `validation_error` | Input or schema validation failed | `failed` |
| `storage_error` | Local persistence/read/write issue | `failed` or `partial` |
| `auth_error` | Authentication or authorization failure | `failed` |
| `dependency_unavailable` | Required service or process missing | `failed` |
| `state_corruption` | Session state or log content is malformed but partly recoverable | `failed` or `partial` |
| `unknown_error` | Unclassified failure | `failed` |

### 9.4 Failure categories

`failure.category` must be one of:

- `transient`
- `persistent`
- `user_action`
- `runtime`
- `external`
- `unknown`

### 9.5 Failure phases

`failure.phase` must be one of:

- `session_start`
- `turn_start`
- `context_load`
- `model_completion`
- `tool_execution`
- `artifact_write`
- `state_persist`
- `replay_append`
- `event_append`
- `session_finalize`
- `resume`
- `unknown`

### 9.6 Degraded execution

A turn may succeed while still recording degraded behavior. In that case:

- terminal `outcome.status` may still be `completed`,
- `execution.degraded` must be `true`,
- at least one event must carry `failure.code = "degraded"` or `event_type = "runtime.degraded"`,
- replay should include a curated degraded notice if user-visible quality was affected.

### 9.7 Cancel semantics

Cancellation must not be represented as a generic failure.

- Use `event_type = "runtime.cancel_requested"` when cancellation is requested.
- Use `turn.cancelled` for the terminal turn event.
- Set `outcome.status = "cancelled"`.
- `failure.code` may be `cancelled` for compatibility, but the cancelled terminal state remains authoritative.

## 10. Compatibility Strategy

v2 must preserve read access to old Python and newer desktop sessions without destructive migration.

### 10.1 Reader behavior

All readers must:

1. inspect `metadata.json`,
2. detect whether explicit v2 fields exist,
3. otherwise map legacy Python and desktop shapes into the canonical in-memory model,
4. tolerate sessions with only metadata,
5. tolerate sessions with only `events.jsonl`, only `replay.jsonl`, or both,
6. ignore unknown fields,
7. preserve legacy values in `compat` rather than silently dropping them.

### 10.2 Deterministic synthetic IDs for legacy records

Legacy records often lack `event_id` and `turn_id`. Readers must synthesize stable in-memory IDs when needed.

Required rules:

- missing `event_id` => synthesize `import:<file>:<seq-or-line>`
- missing `turn_id` => derive deterministic `turn-<ordinal>` from the reader's turn-grouping logic
- synthesized IDs are read-time adapters only unless a writer later performs an additive upgrade

### 10.3 Old Python session compatibility

Legacy Python sessions may have:

- `metadata.json` using `session_id`, `workspace`, `created_at`, `updated_at`,
- `events.jsonl` with types such as `session_started`, `objective`, `trace`, `step`, and `result`,
- `replay.jsonl` with `header` and `call` records keyed by `conversation_id`.

Compatibility rules:

- map legacy metadata to the canonical metadata schema,
- synthesize `schema_version = 1` in memory when absent,
- derive `turn_id` from objective/result groupings when explicit turn identifiers are missing,
- normalize legacy `result` into `assistant.final`, `result.summary`, `turn.failed`, or `turn.cancelled` based on payload status,
- preserve original record type in `compat.legacy_kind`,
- preserve `conversation_id`, provider, model, and tool payload context where present,
- do not rewrite the original files unless a writer explicitly upgrades the session.

### 10.4 Newer desktop session compatibility

Desktop sessions may have:

- `metadata.json` using `id`, `created_at`, `turn_count`, `last_objective`,
- `replay.jsonl` with `ReplayEntry` roles such as `user`, `step-summary`, `assistant`, `curator`, and `assistant-cancelled`,
- `events.jsonl` in a bridge-oriented shape with terminal `result` events.

Compatibility rules:

- map `id -> session_id`,
- map replay roles to canonical event types as follows:
  - `user` -> `user.message`
  - `step-summary` -> `step.summary`
  - `assistant` -> `assistant.message` or `assistant.final` when terminal
  - `curator` -> `curator.note`
  - `assistant-cancelled` -> `turn.cancelled`
- preserve original role in `compat.legacy_role`,
- infer `channel = "replay"` for replay-only entries,
- infer failure objects from cancelled or errored bridge result records when possible.

### 10.5 Mixed-era sessions

Some sessions already contain both legacy and desktop-style information. For mixed sessions:

- prefer explicit v2 fields when present,
- otherwise prefer more-specific per-record information over header-level inference,
- never discard the original record shape during adaptation,
- expose ambiguous mappings through `compat` instead of fabricating certainty.

### 10.6 Additive upgrade behavior

A writer may upgrade a legacy session opportunistically by appending v2-conformant records and refreshing `metadata.json` with canonical fields. When it does so:

- preserve old files and old lines,
- add `schema_version = 2` and `session_format`,
- set `source_compat` and `durability` accurately,
- append a `session.upgraded` event,
- avoid re-sequencing existing log lines,
- continue new `seq` values from the highest observable value in each file.

## 11. Rollout Plan

Rollout should happen in four additive phases.

### Phase 0 - reader-first normalization

- implement canonical in-memory adapters for legacy Python and desktop sessions,
- keep all existing writers unchanged,
- validate that UI surfaces can render the canonical model.

Exit criteria:

- existing sessions remain readable,
- overview and replay can resolve `session_id`, `turn_id`, status, and basic provenance refs.

### Phase 1 - dual-write metadata and canonical envelopes

- Python and Rust writers emit canonical metadata fields,
- new appended lines in `events.jsonl` and `replay.jsonl` use the v2 envelope,
- legacy-specific fields may remain under `compat` or writer-specific extension blocks.

Exit criteria:

- new sessions from both runtimes produce valid `schema_version = 2` headers,
- failures appear explicitly in the canonical taxonomy.

### Phase 2 - durable per-turn records

- writers append `turns.jsonl`,
- frontend and overview consumers use `turns.jsonl` when present and fall back to event reconstruction otherwise.

Exit criteria:

- interrupted sessions can be resumed or explained from per-turn records,
- handoff and overview surfaces stop relying on replay-only heuristics.

### Phase 3 - provenance-complete UI integration

- replay cards deep-link to event spans, artifacts, JSONL lines, and ontology objects,
- degraded and resumed states become visible in session history,
- graph, timeline, and session-diff views consume the canonical provenance fields.

Exit criteria:

- every replay item shown in the UI can open at least one evidence target,
- failure and degradation states are visible and filterable.

## 12. Test Matrix

All three implementation surfaces - Python, Rust, and frontend - must validate the same scenarios.

### 12.1 Fixture classes

Create and preserve fixtures for:

1. Legacy Python metadata only
2. Legacy Python metadata + events only
3. Legacy Python metadata + replay only
4. Legacy Python full session
5. Desktop metadata + replay only
6. Desktop metadata + events + replay
7. Mixed-era session
8. Fresh v2 Python session
9. Fresh v2 desktop session
10. Interrupted partial turn resumed later
11. Cancelled turn
12. Completed-but-degraded turn
13. Rate-limited turn
14. Corrupt line in one log with recovery from remaining files
15. Metadata-only archived session

### 12.2 Required assertions

For each fixture, the test suite should assert:

- canonical `session_id` resolution,
- canonical `turn_count` derivation,
- stable ordering by `seq` or imported line order,
- correct mapping of replay roles to `event_type`,
- correct terminal turn status,
- correct failure code and phase when applicable,
- presence or absence of `turns.jsonl` fallback behavior,
- provenance drill-down availability for replay items,
- no destructive rewrite required to read the session.

### 12.3 Cross-runtime matrix

| Scenario | Python reader | Rust reader | Frontend renderer |
|---|---|---|---|
| Legacy Python session loads | must pass | must pass | must pass |
| Desktop replay-only session loads | must pass | must pass | must pass |
| Fresh v2 Python session round-trips | must pass | must pass | must pass |
| Fresh v2 desktop session round-trips | must pass | must pass | must pass |
| Partial -> resumed session shows continuity | must pass | must pass | must pass |
| Cancelled turn renders correctly | must pass | must pass | must pass |
| Degraded completed turn renders warning state | must pass | must pass | must pass |
| Corrupt `replay.jsonl` line with healthy `events.jsonl` fallback | must pass | must pass | must pass |
| Corrupt `events.jsonl` line with healthy `turns.jsonl` fallback | must pass | must pass | must pass |

### 12.4 Writer conformance checks

Python and Rust writers should each have conformance tests that verify:

- `metadata.json` includes all required v2 fields,
- appended event lines contain the canonical envelope,
- `seq` is monotonic,
- every terminal turn produces a `turns.jsonl` record,
- every replay summary includes `turn_id` and `source_refs`,
- failure states use canonical codes and phases,
- cancellation is not misclassified as a generic failure.

### 12.5 Frontend conformance checks

Frontend tests should verify:

- old sessions adapt into the canonical view model without crashing,
- replay cards can surface `failure.code`, `failure.phase`, `execution.degraded`, and `continuity.resumed_from_partial`,
- evidence drill-down actions can open event spans, artifacts, JSONL lines, or ontology objects when refs exist,
- missing provenance gracefully degrades to session or turn-level navigation rather than a blank UI.

## 13. Internal Consistency Checklist

This checklist is normative. An implementation is not v2-complete unless the following fields are explicitly named and carried through all relevant layers.

### 13.1 Session identity and continuity

- `schema_version`
- `session_format`
- `session_id`
- `created_at`
- `updated_at`
- `session_origin`
- `session_kind`
- `status`
- `turn_count`
- `last_turn_id`
- `last_objective`
- `continuity_mode`
- `source_compat`
- `capabilities`
- `durability`

### 13.2 Event identity

- `event_id`
- `turn_id`
- `seq`
- `recorded_at`
- `event_type`
- `channel`
- `status`
- `actor`
- `payload`
- `failure`
- `provenance`
- `compat`

### 13.3 Turn durability

- `turn_index`
- `started_at`
- `ended_at`
- `objective`
- `continuity.mode`
- `continuity.resumed_from_turn_id`
- `continuity.resumed_from_partial`
- `inputs.user_message_ref`
- `outputs.assistant_final_ref`
- `outputs.result_summary_ref`
- `outputs.artifact_refs`
- `execution.step_count`
- `execution.tool_call_count`
- `execution.degraded`
- `outcome.status`
- `outcome.failure_code`
- `outcome.failure`
- `outcome.summary`
- `provenance.event_span.start_seq`
- `provenance.event_span.end_seq`

### 13.4 Evidence drill-down

- `provenance.record_locator.file`
- `provenance.record_locator.line`
- `provenance.parent_event_id`
- `provenance.caused_by`
- `provenance.source_refs`
- `provenance.evidence_refs`
- `provenance.ontology_refs`
- `provenance.generated_from.provider`
- `provenance.generated_from.model`
- `provenance.generated_from.request_id`
- `evidence_refs[].kind`
- `evidence_refs[].id`
- `evidence_refs[].label`
- `evidence_refs[].locator.path`

### 13.5 Reliability state

- `failure.code`
- `failure.category`
- `failure.phase`
- `failure.retryable`
- `failure.resumable`
- `failure.message`
- `failure.provider`
- `failure.provider_code`
- `failure.details`

### 13.6 Compatibility capture

- `compat.legacy_kind`
- `compat.legacy_role`
- `compat.source_schema`

If a later implementation prompt depends on a field, that field must already be explicitly named above rather than implied.

## 14. Recommended Defaults

To keep parallel implementations aligned, the following defaults are recommended:

- `session_origin = "python"` for the Python runtime and `"desktop"` for desktop-created sessions
- `session_kind = "investigation"` unless a more specific value is known
- `channel = "event"` for low-level operational entries and `"replay"` for curated user-facing lines
- `status = "info"` for non-terminal informational events
- `continuity.mode = "new"` for the first turn in a fresh session
- `failure = null` only when there is no failure or degraded condition to report

## 15. Decision Summary

Session Trace v2 standardizes:

- one canonical metadata schema in `metadata.json`,
- one shared event envelope for `events.jsonl` and `replay.jsonl`,
- one minimum durable per-turn record in `turns.jsonl`,
- one provenance contract for evidence drill-down,
- one explicit failure taxonomy,
- and one additive compatibility path across legacy Python and newer desktop sessions.

That is the minimum session contract required for OpenPlanter to treat sessions as durable investigative evidence rather than loosely related logs.
