# RFC 0001: Research Normalization and Future Action Layer

- **Status:** Draft
- **Authors:** OpenPlanter contributors
- **Last Updated:** 2026-03-13
- **Audience:** Agent/runtime, ontology, and workflow maintainers

## 1) Summary

This RFC defines a two-part architecture for ontology-first investigations:

1. **Research normalization**: all incoming research artifacts (local files, web fetches, transcripts, API responses, search results) are normalized into a single **Evidence** model.
2. **Future action layer**: unresolved questions derived from evidence/claims become explicit **NextAction** records with expected payoff, required inputs, and provenance-backed rationale.

The design is intentionally provenance-heavy: every normalized object and every action recommendation must preserve where it came from, when it was observed, and how confident we are in its freshness and relevance.

## 2) Motivation

Investigations currently involve heterogeneous inputs with inconsistent metadata and ad hoc follow-up planning. This causes:

- brittle downstream extraction/claiming logic,
- weak comparability between evidence types,
- missing or lossy provenance,
- and no unified, inspectable queue of “what to do next.”

For an ontology-first workflow, we need stable primitives:

- **Evidence** as the canonical atomic observation unit,
- **Claim** as a typed assertion grounded in evidence,
- **Question** as explicit uncertainty,
- **NextAction** as executable resolution path with expected payoff.

## 3) Goals

1. Define a canonical evidence model that all ingestion paths map to.
2. Preserve complete provenance chains (source, retrieval, transforms, extractor versions).
3. Track freshness/temporal validity separately from extraction confidence.
4. Standardize extracted entities and links between evidence and claims.
5. Convert unresolved questions into prioritized, auditable next actions.
6. Keep the model implementation-agnostic enough for CLI and desktop workflows.

## 4) Non-goals

- Prescribing a specific storage backend (SQLite, graph DB, document store).
- Replacing existing dataset-specific fetchers.
- Defining UI pixel-level behavior for action rendering.
- Mandating one ranking model for payoff estimation.

## 5) Design Principles

1. **Ontology first**: entities, relations, claims, and questions use typed ontology IDs before free-form tags.
2. **Provenance by default**: no evidence/claim/action without source and processing lineage.
3. **Lossless normalization**: preserve source-native payloads; add normalized projections.
4. **Temporal explicitness**: distinguish publication date, retrieval date, and validity window.
5. **Actionability over verbosity**: unresolved uncertainty should produce concrete, bounded next actions.
6. **Composable confidence**: extraction confidence, source reliability, and freshness decay are separate signals.

## 6) Canonical Evidence Model

`Evidence` is the normalized envelope for every incoming artifact.

```yaml
Evidence:
  evidence_id: ev_<ULID>
  kind: [local_file, web_fetch, transcript, api_response, search_result]
  modality: [text, html, json, pdf, audio, video, table, mixed]

  content:
    raw_ref: <pointer to immutable raw bytes/blob>
    normalized_text: <UTF-8 text projection, optional>
    normalized_structured: <JSON projection, optional>
    chunks: [
      {
        chunk_id: ch_<ULID>,
        type: [paragraph, table_row, json_path, timestamped_utterance],
        locator: <offset/span/xpath/jsonpath/timestamp>,
        text: <chunk text>,
        hash: <sha256>
      }
    ]

  provenance:
    source_type: [filesystem, http, api, search_index, transcript_pipeline]
    source_uri: <file://... | https://... | api://provider/endpoint>
    source_title: <best available title>
    publisher: <org/person/system>
    acquisition:
      observed_at: <UTC timestamp>
      retrieved_at: <UTC timestamp>
      retrieval_method: <tool + version>
      request_fingerprint: <canonicalized request hash>
      response_fingerprint: <response hash/etag>
    processing_lineage:
      - stage: [decode, ocr, asr, parse, chunk, extract]
        tool: <name>
        version: <semver/git sha>
        run_id: <pipeline run id>
        timestamp: <UTC>

  freshness:
    published_at: <UTC optional>
    effective_from: <UTC optional>
    effective_to: <UTC optional>
    stale_after: <UTC optional>
    recency_score: <0..1>
    decay_policy: [none, linear, exponential, source_defined]

  reliability:
    source_reliability_score: <0..1>
    extraction_confidence: <0..1>
    integrity:
      checksum: <sha256>
      signature_verified: <bool optional>

  ontology_links:
    entities: [
      {
        entity_id: ent_<ULID>,
        ontology_type: <Person|Organization|Asset|Contract|Event|Location|...>,
        mention_span: <chunk locator>,
        confidence: <0..1>,
        resolution_state: [resolved, candidate, unresolved]
      }
    ]
    relations: [
      {
        relation_id: rel_<ULID>,
        predicate: <ontology predicate>,
        subject_entity_id: ent_...,
        object_entity_id: ent_...,
        confidence: <0..1>
      }
    ]

  claim_links:
    supports: [cl_<ULID>]
    contradicts: [cl_<ULID>]
    mentions: [cl_<ULID>]

  governance:
    sensitivity: [public, internal, restricted]
    license: <SPDX or source term>
```

### Required fields

At minimum: `evidence_id`, `kind`, `provenance.source_uri`, `provenance.acquisition.retrieved_at`, and one content representation (`raw_ref`, `normalized_text`, or `normalized_structured`).

## 7) Source-Specific Normalization Contracts

Each ingestion path maps into the same `Evidence` envelope with source-specific adapters.

### 7.1 Local files

- `kind=local_file`
- `source_uri=file://<absolute path>`
- fingerprint from file bytes + inode metadata snapshot
- if structured file (CSV/JSON/Parquet), populate `normalized_structured`
- if text-like, also populate `normalized_text` and paragraph chunks

### 7.2 Web fetches

- `kind=web_fetch`
- `source_uri=https://...` after redirect resolution
- store HTTP metadata in provenance extension (status, etag, cache-control)
- keep raw HTML/PDF bytes immutable, plus extracted text projection
- capture canonical URL and retrieval agent identity

### 7.3 Transcripts (audio/video/meeting/call)

- `kind=transcript`
- include ASR engine/version in `processing_lineage`
- chunk type defaults to `timestamped_utterance`
- provenance should include media source and diarization metadata when available

### 7.4 API responses

- `kind=api_response`
- `source_uri=api://<provider>/<endpoint>` and request fingerprint
- normalized structured projection is primary
- capture pagination context and token scopes in provenance extension

### 7.5 Search results

- `kind=search_result`
- represent each result item as independent evidence with query provenance
- include ranking metadata (rank, score, provider)
- link result evidence to follow-up fetched evidence via derivation edges

## 8) Provenance and Freshness Semantics

### 8.1 Provenance chain

Every derived artifact stores:

- parent evidence IDs,
- transformation stage,
- tool version,
- timestamp.

This enables full replay from claim/action back to raw source.

### 8.2 Freshness semantics

Freshness is not binary. We compute:

- `recency_score` from source-specific decay policy,
- `stale_after` from explicit source directives if present,
- investigation-time override for domains where historical records remain valid.

Claims should consume freshness as a weighting factor, not a hard validity gate.

## 9) Entities, Claims, and Linking

## 9.1 Entity extraction and resolution

Entity mentions are extracted per chunk and mapped to ontology types. Resolution pipeline states:

1. `unresolved` (new mention)
2. `candidate` (one or more possible canonical entities)
3. `resolved` (canonical entity assigned)

Each state transition writes provenance (`who/what/when/how`).

### 9.2 Claim model (minimal)

```yaml
Claim:
  claim_id: cl_<ULID>
  claim_type: <ontology assertion type>
  subject_entity_id: ent_...
  predicate: <ontology predicate>
  object: <entity_id | literal>
  status: [proposed, supported, disputed, rejected]
  support_evidence_ids: [ev_...]
  contradiction_evidence_ids: [ev_...]
  confidence: <0..1>
  last_evaluated_at: <UTC>
```

Evidence links to claims through `supports`, `contradicts`, or `mentions`.

### 9.3 Contradiction handling

Contradictions are first-class edges, not overwrite events. Investigations should preserve both competing evidence sets and open a resolving question if conflict materially affects conclusions.

## 10) Unresolved Questions → Next Actions

`Question` records represent uncertainty or missing information; `NextAction` records represent concrete attempts to resolve it.

### 10.1 Question model

```yaml
Question:
  question_id: q_<ULID>
  text: <natural language uncertainty>
  ontology_scope: [entity_ids, claim_ids, predicates]
  blocking_level: [critical, high, medium, low]
  created_from:
    evidence_ids: [ev_...]
    claim_ids: [cl_...]
  status: [open, in_progress, resolved, abandoned]
```

### 10.2 NextAction model

```yaml
NextAction:
  action_id: act_<ULID>
  question_id: q_<ULID>
  action_type: [fetch, search, extract, resolve_entity, verify_claim, request_human_input]
  hypothesis: <what this action aims to confirm/deny>

  required_inputs:
    required_evidence_kinds: [api_response, web_fetch, ...]
    required_entities: [ent_...]
    required_claims: [cl_...]
    external_dependencies: [api_key:provider, tool:ocr_v2]

  expected_payoff:
    uncertainty_reduction: <0..1>
    decision_impact: <0..1>
    graph_expansion_value: <0..1>
    estimated_cost: <time/compute/API>
    payoff_score: <normalized scalar>

  execution:
    suggested_tools: [web_search, fetch_url, read_file, ...]
    acceptance_criteria:
      - <objective completion criterion>
    stop_conditions:
      - <condition>

  provenance:
    generated_by: <planner component + version>
    generated_at: <UTC>
    based_on_evidence_ids: [ev_...]
    based_on_claim_ids: [cl_...]

  status: [queued, ready, blocked, running, completed, failed, superseded]
```

### 10.3 Payoff scoring guidance

Default heuristic:

`payoff_score = (0.45 * uncertainty_reduction) + (0.35 * decision_impact) + (0.20 * graph_expansion_value) - cost_penalty`

Where `cost_penalty` is normalized from estimated resource cost and latency. Weights are configurable by investigation profile.

### 10.4 Required input semantics

Actions are only `ready` when all required inputs are available/resolved. Otherwise they remain `blocked` and should emit explicit dependency hints (e.g., “requires canonical entity for vendor alias X”).

## 11) Workflow Integration (Ontology-First Investigation)

1. Ingest source artifact.
2. Normalize to `Evidence` + provenance/freshness.
3. Extract entity mentions and candidate relations.
4. Generate/update claims with support/contradiction links.
5. Detect unresolved questions (missing evidence, unresolved entity, contradictory claims).
6. Materialize ranked `NextAction` queue.
7. Execute top ready actions; loop until stop criteria are satisfied.

Stop criteria examples:

- no critical questions remain,
- marginal payoff of top action below threshold,
- time/budget exhausted,
- human reviewer sign-off.

## 12) Minimal Implementation Plan

### Phase 1: Data contracts

- Introduce versioned schema definitions for `Evidence`, `Claim`, `Question`, `NextAction`.
- Add adapter interfaces for each source kind.

### Phase 2: Provenance/freshness enforcement

- Reject evidence writes missing required provenance fields.
- Add freshness scoring utility with source-specific decay presets.

### Phase 3: Question/action engine

- Add unresolved-question detector.
- Add action generator with payoff scoring and dependency gating.

### Phase 4: Observability

- Add lineage trace views (claim → evidence → raw source).
- Add action queue diagnostics (why blocked, why ranked).

## 13) Backward Compatibility

- Existing fetch/extract scripts remain valid as long as adapters can map their outputs into `Evidence`.
- Legacy records can be wrapped as `Evidence` with partial fields and `normalization_version=legacy` until reprocessed.

## 14) Open Questions

1. Should search result evidence always remain separate from fetched page evidence, or be auto-merged when identical URLs/content hashes match?
2. Which domains require non-decaying freshness (e.g., incorporation date) by default?
3. Should payoff scoring be globally configured or profile-specific per investigation objective?
4. How should human-authored notes be modeled: separate `kind=analyst_note` or `local_file` subtype?

## 15) Acceptance Criteria

This RFC is accepted when:

1. Every ingestion pathway can emit schema-valid `Evidence` objects.
2. Every claim can be traced to one or more evidence items with provenance lineage.
3. Every open high/critical question has at least one generated `NextAction`.
4. Action queue exposes payoff and blocked-input explanations.
5. Replay from action → question → claim → evidence → raw source is possible in tooling.
