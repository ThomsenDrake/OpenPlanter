import {
  getInitStatus,
  inspectMigrationSource,
  runMigrationInit,
  runStandardInit,
} from "../api/invoke";
import type { MigrationSourceInspection } from "../api/types";
import { appState } from "../state/store";

interface SourceDraft {
  path: string;
  inspection: MigrationSourceInspection | null;
}

export function createWorkspaceInitGate(): HTMLElement {
  const overlay = document.createElement("div");
  overlay.className = "workspace-init-gate";
  overlay.style.position = "fixed";
  overlay.style.inset = "0";
  overlay.style.display = "none";
  overlay.style.alignItems = "center";
  overlay.style.justifyContent = "center";
  overlay.style.background = "rgba(6, 10, 14, 0.78)";
  overlay.style.zIndex = "999";

  const panel = document.createElement("div");
  panel.className = "workspace-init-panel";
  panel.style.width = "min(760px, 92vw)";
  panel.style.maxHeight = "88vh";
  panel.style.overflow = "auto";
  panel.style.padding = "20px";
  panel.style.borderRadius = "16px";
  panel.style.background = "var(--bg-secondary)";
  panel.style.border = "1px solid var(--border)";
  panel.style.boxShadow = "0 24px 80px rgba(0, 0, 0, 0.35)";
  overlay.appendChild(panel);

  let targetWorkspace = "";
  let sources: SourceDraft[] = [{ path: "", inspection: null }];
  let localError = "";

  function ensureDefaultTarget(): void {
    const workspace = appState.get().workspace;
    if (!targetWorkspace && workspace) {
      targetWorkspace = `${workspace}-desktop`;
    }
  }

  async function refreshStatus(): Promise<void> {
    const status = await getInitStatus();
    appState.update((s) => ({
      ...s,
      initStatus: status,
      initGateState: status.gate_state,
      initGateVisible: status.gate_state !== "ready" ? true : s.initGateVisible,
    }));
  }

  function visibilityState(): boolean {
    const state = appState.get();
    return state.initGateVisible || state.initGateState !== "ready";
  }

  function updateBusy(isInitBusy: boolean): void {
    appState.update((s) => ({ ...s, isInitBusy }));
  }

  async function handleStandardInit(): Promise<void> {
    localError = "";
    updateBusy(true);
    try {
      await runStandardInit();
      await refreshStatus();
      appState.update((s) => ({
        ...s,
        initGateVisible: false,
        initGateMode: "standard",
        migrationProgress: null,
        migrationResult: null,
      }));
      window.dispatchEvent(new CustomEvent("curator-done"));
    } catch (error) {
      localError = `Standard init failed: ${error}`;
    } finally {
      updateBusy(false);
      render();
    }
  }

  async function handleInspect(index: number): Promise<void> {
    const draft = sources[index];
    if (!draft || !draft.path.trim()) {
      localError = "Enter a source path before inspecting it.";
      render();
      return;
    }
    localError = "";
    updateBusy(true);
    try {
      const inspection = await inspectMigrationSource(draft.path.trim());
      sources[index] = { ...draft, inspection };
    } catch (error) {
      localError = `Inspection failed: ${error}`;
    } finally {
      updateBusy(false);
      render();
    }
  }

  async function handleMigration(): Promise<void> {
    const trimmedTarget = targetWorkspace.trim();
    const trimmedSources = sources
      .map((source) => source.path.trim())
      .filter(Boolean);
    if (!trimmedTarget) {
      localError = "Enter a target workspace path.";
      render();
      return;
    }
    if (trimmedSources.length === 0) {
      localError = "Add at least one source workspace or research directory.";
      render();
      return;
    }

    localError = "";
    appState.update((s) => ({
      ...s,
      isInitBusy: true,
      migrationProgress: null,
      migrationResult: null,
      initGateMode: "migration",
      initGateVisible: true,
    }));
    try {
      const result = await runMigrationInit({
        target_workspace: trimmedTarget,
        sources: trimmedSources.map((path) => ({ path })),
      });
      appState.update((s) => ({
        ...s,
        isInitBusy: false,
        migrationResult: result,
        initGateVisible: true,
      }));
    } catch (error) {
      localError = `Migration failed: ${error}`;
      updateBusy(false);
    } finally {
      render();
    }
  }

  function renderSourceRow(index: number, stateBusy: boolean): HTMLElement {
    const draft = sources[index];
    const row = document.createElement("div");
    row.style.display = "grid";
    row.style.gridTemplateColumns = "1fr auto auto";
    row.style.gap = "8px";
    row.style.marginBottom = "10px";

    const input = document.createElement("input");
    input.type = "text";
    input.value = draft.path;
    input.placeholder = "/path/to/openplanter-workspace-or-research-dir";
    input.disabled = stateBusy;
    input.addEventListener("input", () => {
      sources[index] = { path: input.value, inspection: null };
    });

    const inspectBtn = document.createElement("button");
    inspectBtn.textContent = "Inspect";
    inspectBtn.disabled = stateBusy;
    inspectBtn.addEventListener("click", () => {
      void handleInspect(index);
    });

    const removeBtn = document.createElement("button");
    removeBtn.textContent = "Remove";
    removeBtn.disabled = stateBusy || sources.length === 1;
    removeBtn.addEventListener("click", () => {
      sources.splice(index, 1);
      render();
    });

    row.appendChild(input);
    row.appendChild(inspectBtn);
    row.appendChild(removeBtn);

    if (draft.inspection) {
      const details = document.createElement("div");
      details.style.gridColumn = "1 / -1";
      details.style.padding = "8px 10px";
      details.style.border = "1px solid var(--border)";
      details.style.borderRadius = "10px";
      details.style.background = "var(--bg-tertiary)";
      details.textContent = [
        `kind=${draft.inspection.kind}`,
        `markdown=${draft.inspection.markdown_files}`,
        `sessions=${draft.inspection.has_sessions ? "yes" : "no"}`,
        `settings=${draft.inspection.has_settings ? "yes" : "no"}`,
        `credentials=${draft.inspection.has_credentials ? "yes" : "no"}`,
        `runtime_wiki=${draft.inspection.has_runtime_wiki ? "yes" : "no"}`,
      ].join("  |  ");
      row.appendChild(details);
    }

    return row;
  }

  function render(): void {
    ensureDefaultTarget();
    const state = appState.get();
    const visible = visibilityState();
    overlay.style.display = visible ? "flex" : "none";
    if (!visible) {
      return;
    }

    panel.replaceChildren();

    const title = document.createElement("h2");
    title.textContent = "Workspace Initialization";
    panel.appendChild(title);

    const intro = document.createElement("p");
    intro.textContent =
      state.initGateState !== "ready"
        ? "Choose Standard Init to prepare the current workspace, or Migration Init to build a new Desktop workspace from one or more existing sources."
        : "Manage the current workspace or open a migration flow to build a new Desktop workspace.";
    panel.appendChild(intro);

    const modeBar = document.createElement("div");
    modeBar.style.display = "flex";
    modeBar.style.gap = "8px";
    modeBar.style.marginBottom = "14px";

    const standardTab = document.createElement("button");
    standardTab.textContent = "Standard Init";
    standardTab.disabled = state.isInitBusy;
    standardTab.style.fontWeight = state.initGateMode === "standard" ? "700" : "400";
    standardTab.addEventListener("click", () => {
      appState.update((s) => ({ ...s, initGateMode: "standard", migrationResult: null }));
    });

    const migrationTab = document.createElement("button");
    migrationTab.textContent = "Migration Init";
    migrationTab.disabled = state.isInitBusy;
    migrationTab.style.fontWeight = state.initGateMode === "migration" ? "700" : "400";
    migrationTab.addEventListener("click", () => {
      appState.update((s) => ({ ...s, initGateMode: "migration" }));
    });

    modeBar.appendChild(standardTab);
    modeBar.appendChild(migrationTab);
    panel.appendChild(modeBar);

    if (state.initStatus) {
      const status = document.createElement("div");
      status.style.padding = "10px 12px";
      status.style.border = "1px solid var(--border)";
      status.style.borderRadius = "12px";
      status.style.background = "var(--bg-tertiary)";
      status.style.marginBottom = "14px";
      status.textContent = [
        `workspace=${state.initStatus.runtime_workspace}`,
        `gate=${state.initStatus.gate_state}`,
        `wiki=${state.initStatus.has_runtime_index ? "ready" : "missing"}`,
        `last_migration=${state.initStatus.last_migration_target || "—"}`,
      ].join("  |  ");
      panel.appendChild(status);
    }

    if (state.migrationProgress) {
      const progress = document.createElement("div");
      progress.style.padding = "10px 12px";
      progress.style.border = "1px solid var(--border)";
      progress.style.borderRadius = "12px";
      progress.style.background = "rgba(57, 148, 255, 0.08)";
      progress.style.marginBottom = "14px";
      progress.textContent = `[${state.migrationProgress.stage}] ${state.migrationProgress.message}`;
      panel.appendChild(progress);
    }

    if (state.migrationResult) {
      const result = document.createElement("div");
      result.style.padding = "12px";
      result.style.border = "1px solid var(--border)";
      result.style.borderRadius = "12px";
      result.style.background = "rgba(56, 184, 90, 0.10)";
      result.style.marginBottom = "14px";
      result.textContent = [
        `Target: ${state.migrationResult.target_workspace}`,
        `Sessions copied: ${state.migrationResult.sessions_copied}`,
        `Sessions renamed: ${state.migrationResult.sessions_renamed}`,
        `Wiki pages available: ${state.migrationResult.wiki_files_synthesized}`,
        `Curator summary: ${state.migrationResult.rewrite_summary}`,
        state.migrationResult.restart_message,
      ].join("\n");
      panel.appendChild(result);
    }

    if (localError) {
      const error = document.createElement("div");
      error.style.padding = "10px 12px";
      error.style.border = "1px solid rgba(255, 99, 99, 0.45)";
      error.style.borderRadius = "12px";
      error.style.background = "rgba(255, 99, 99, 0.10)";
      error.style.marginBottom = "14px";
      error.textContent = localError;
      panel.appendChild(error);
    }

    if (state.initGateMode === "standard") {
      const block = document.createElement("div");
      const body = document.createElement("p");
      body.textContent =
        "Standard Init prepares the current workspace, creates the runtime wiki skeleton, and marks the Desktop onboarding flow complete.";
      const button = document.createElement("button");
      button.textContent = state.isInitBusy ? "Initializing..." : "Initialize Current Workspace";
      button.disabled = state.isInitBusy;
      button.addEventListener("click", () => {
        void handleStandardInit();
      });
      block.appendChild(body);
      block.appendChild(button);
      panel.appendChild(block);
    } else {
      const migration = document.createElement("div");

      const targetLabel = document.createElement("label");
      targetLabel.textContent = "Target Workspace";
      targetLabel.style.display = "block";
      targetLabel.style.marginBottom = "6px";
      migration.appendChild(targetLabel);

      const targetInput = document.createElement("input");
      targetInput.type = "text";
      targetInput.value = targetWorkspace;
      targetInput.placeholder = "/path/to/new-desktop-workspace";
      targetInput.style.width = "100%";
      targetInput.style.marginBottom = "14px";
      targetInput.disabled = state.isInitBusy;
      targetInput.addEventListener("input", () => {
        targetWorkspace = targetInput.value;
      });
      migration.appendChild(targetInput);

      const sourcesHeader = document.createElement("div");
      sourcesHeader.textContent = "Migration Sources";
      sourcesHeader.style.fontWeight = "700";
      sourcesHeader.style.marginBottom = "8px";
      migration.appendChild(sourcesHeader);

      const sourceList = document.createElement("div");
      for (let index = 0; index < sources.length; index += 1) {
        sourceList.appendChild(renderSourceRow(index, state.isInitBusy));
      }
      migration.appendChild(sourceList);

      const actions = document.createElement("div");
      actions.style.display = "flex";
      actions.style.gap = "8px";
      actions.style.marginTop = "12px";

      const addBtn = document.createElement("button");
      addBtn.textContent = "Add Source";
      addBtn.disabled = state.isInitBusy;
      addBtn.addEventListener("click", () => {
        sources.push({ path: "", inspection: null });
        render();
      });

      const migrateBtn = document.createElement("button");
      migrateBtn.textContent = state.isInitBusy ? "Migrating..." : "Run Migration Init";
      migrateBtn.disabled = state.isInitBusy;
      migrateBtn.addEventListener("click", () => {
        void handleMigration();
      });

      actions.appendChild(addBtn);
      actions.appendChild(migrateBtn);
      migration.appendChild(actions);
      panel.appendChild(migration);
    }

    if (state.initGateState === "ready") {
      const closeBtn = document.createElement("button");
      closeBtn.textContent = "Close";
      closeBtn.style.marginTop = "16px";
      closeBtn.disabled = state.isInitBusy;
      closeBtn.addEventListener("click", () => {
        appState.update((s) => ({ ...s, initGateVisible: false }));
      });
      panel.appendChild(closeBtn);
    }
  }

  appState.subscribe(render);
  render();
  return overlay;
}
