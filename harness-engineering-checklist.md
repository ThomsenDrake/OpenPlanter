# Harness Engineering Implementation Checklist

Companion tracker for [harness-engineering.md](./harness-engineering.md).

Use `harness-engineering.md` as the design and architecture brief. Use this file as the execution tracker we update across sessions.

## Operating Notes

- Update `Last updated`, `Current focus`, `Next up`, and `Session log` at the end of each working session.
- Only check a box when the implementation is actually landed in the repo or clearly validated in the current branch.
- If work is partial, leave the box unchecked and add a short note under the milestone.
- If scope changes, update both this file and the relevant section of `harness-engineering.md`.

## Status Snapshot

- Last updated: 2026-04-09
- Overall status: Milestone 1 foundation is in the repo; Milestones 2-5 are still open.
- Current focus: Move from skeleton orchestration to real task execution primitives.
- Next recommended slice: `TrackerAdapter` + per-task workspace manager + a manual "Run Issue Once" path before continuous polling.
- Known repo-wide issue: `cargo test -p op-core` still fails in 3 unrelated streaming tests under `openplanter-desktop/crates/op-core/tests/test_model_streaming.rs`.

## Implementation Anchors

These are the main files already created or updated for the initial orchestration foundation:

- `openplanter-desktop/crates/op-core/src/workflow_spec.rs`
- `openplanter-desktop/crates/op-core/src/orchestrator.rs`
- `openplanter-desktop/crates/op-core/src/events.rs`
- `openplanter-desktop/crates/op-tauri/src/commands/orchestrator.rs`
- `openplanter-desktop/crates/op-tauri/src/bridge.rs`
- `openplanter-desktop/crates/op-tauri/src/state.rs`
- `openplanter-desktop/frontend/src/api/invoke.ts`
- `openplanter-desktop/frontend/src/api/events.ts`
- `openplanter-desktop/frontend/src/api/types.ts`

## Implementation Checklist

### Milestone 1: Workflow Spec + Orchestration Skeleton

Status: Completed for the initial cut

- [x] Add `WORKFLOW.md` parser in `op-core` for YAML frontmatter + markdown template body.
- [x] Resolve workflow-relative workspace root defaults from the parsed spec.
- [x] Add an `OrchestratorConfig` and in-memory runtime in `op-core`.
- [x] Add an `OrchestratorSnapshotEvent` payload shape in `op-core/src/events.rs`.
- [x] Support periodic workflow reload and preserve the last good config when reload fails.
- [x] Add Tauri bridge emission for `orchestrator:snapshot`.
- [x] Add Tauri commands to start, stop, and inspect the orchestrator runtime.
- [x] Store the orchestrator runtime in shared desktop `AppState`.
- [x] Add frontend invoke wrappers for orchestrator start/stop/snapshot.
- [x] Add frontend event listener support for orchestrator snapshots.
- [x] Add focused Rust tests for parser/runtime behavior.
- [x] Add focused frontend tests for the new invoke/event API surface.
- [ ] Connect snapshot data into a visible frontend dashboard or app store pane.
- [ ] Add a manual smoke-test flow that loads a real project `WORKFLOW.md` from the desktop app.

Notes:

- The current runtime is intentionally a skeleton. It emits idle snapshots and reload warnings, but it does not yet dispatch tracker-driven work.

### Milestone 2: GitHub Tracker Adapter + Per-Task Workspaces

Status: Not started

- [ ] Define `TrackerAdapter` trait(s) and task domain models in `op-core`.
- [ ] Implement a first `GitHubAdapter`.
- [ ] Decide where tracker credentials should live in the runtime architecture.
- [ ] Add `.openplanter/workspaces/<task_id>/` workspace management.
- [ ] Enforce workspace root containment and protect against path traversal or symlink escapes.
- [ ] Add hook execution support for `after_create`, `before_remove`, `before_run`, and `after_run`.
- [ ] Capture hook stdout/stderr into session artifacts.
- [ ] Add a manual "Run Issue Once" action before enabling unattended polling.
- [ ] Add integration tests for tracker fetch/update flows.
- [ ] Add integration tests for workspace lifecycle and hook execution.

### Milestone 3: Continuous Polling + Dashboard UX

Status: Not started

- [ ] Poll the tracker for candidate tasks on an interval.
- [ ] Add queueing with concurrency limits.
- [ ] Add retry and backoff policy.
- [ ] Add stall detection and restart behavior.
- [ ] Emit task-level updates for `queued`, `running`, `retrying`, `blocked`, and `done`.
- [ ] Build a frontend dashboard pane for orchestrator state.
- [ ] Show per-task runtime, token totals, last event, workspace path, and replay/session links.
- [ ] Add pause, resume, and refresh-now controls.
- [ ] Add end-to-end UI coverage for the dashboard flow.

### Milestone 4: Unattended Safety Profile

Status: Not started

- [ ] Define unattended-mode configuration keys in the workflow spec.
- [ ] Gate high-risk tools by default in unattended mode.
- [ ] Separate tracker credentials from model credentials.
- [ ] Start with read-only or comment/label-only tracker permissions.
- [ ] Add explicit workflow flags for risky actions like write, PR creation, merge, network, or shell.
- [ ] Add audit logging for tracker mutations.
- [ ] Document safe defaults and escalation rules for unattended execution.

### Milestone 5: Remote Workers + Daemon Mode

Status: Not started

- [ ] Define a worker abstraction such as `LocalWorker` and `SshWorker`.
- [ ] Decide whether daemon mode should be a separate crate or a minimal surface next to Tauri.
- [ ] Add headless APIs for runs, status, and streamed events.
- [ ] Support remote workspace creation and cleanup.
- [ ] Stream remote run events back into the desktop UX.
- [ ] Add capacity-aware worker selection.
- [ ] Add remote smoke tests and failure-mode coverage.

## Cross-Cutting Validation

- [x] `cargo test -p op-core workflow_spec::tests`
- [x] `cargo test -p op-core orchestrator::tests`
- [x] `cargo check -p op-tauri`
- [x] `npm test -- --run src/api/events.test.ts src/api/invoke.test.ts`
- [ ] `cargo test -p op-core` is green
- [ ] `cargo test --workspace` is green
- [ ] `cargo clippy --workspace -- -D warnings`
- [ ] `npm run test:e2e`

## Open Decisions To Carry Forward

- [ ] Decide whether the canonical workflow file should live at repo root `WORKFLOW.md`, `.openplanter/WORKFLOW.md`, or continue supporting both.
- [ ] Decide whether tracker credentials should remain in desktop app state or move behind a future daemon boundary.
- [ ] Decide whether the first tracker integration should be GitHub-only or include a memory/mock adapter for local dev loops.
- [ ] Decide whether the dashboard should live in the existing main app layout or a dedicated automation view.

## Session Log

### 2026-04-09

- Created this tracker as the execution companion to `harness-engineering.md`.
- Recorded the Milestone 1 initial cut as complete based on the existing parser, runtime, event, Tauri command, and frontend API plumbing already in the repo.
- Captured the focused checks that passed for the orchestration foundation.
- Carried forward the known unrelated `op-core` streaming test failures so future sessions do not mistake them for orchestration regressions.

### Next Session Template

- Date:
- Goal:
- Changes landed:
- Checks run:
- Blockers or decisions:
