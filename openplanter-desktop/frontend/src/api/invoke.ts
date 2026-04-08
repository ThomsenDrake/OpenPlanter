/** Typed Tauri invoke wrappers. */
import { invoke } from "@tauri-apps/api/core";
import type {
  ConfigView,
  CredentialService,
  CredentialStatusMap,
  ExportSessionHandoffResult,
  GraphData,
  ImportSessionHandoffRequest,
  ImportSessionHandoffResult,
  InitStatusView,
  InvestigationOverviewView,
  MigrationInitRequest,
  MigrationInitResultView,
  MigrationSourceInspection,
  ModelInfo,
  PartialConfig,
  PersistentSettings,
  ReplayEntry,
  SessionInfo,
  StandardInitReportView,
} from "./types";

export async function solve(objective: string, sessionId: string): Promise<void> {
  return invoke("solve", { objective, sessionId });
}

export async function getSessionHistory(sessionId: string | null): Promise<ReplayEntry[]> {
  if (!sessionId) return [];
  return invoke("get_session_history", { sessionId });
}

export async function exportSessionHandoff(
  sessionId: string,
  turnId?: string | null
): Promise<ExportSessionHandoffResult> {
  return invoke("export_session_handoff", { sessionId, turnId: turnId ?? null });
}

export async function importSessionHandoff(
  request: ImportSessionHandoffRequest
): Promise<ImportSessionHandoffResult> {
  return invoke("import_session_handoff", { request });
}

export async function cancel(): Promise<void> {
  return invoke("cancel");
}

export async function getConfig(): Promise<ConfigView> {
  return invoke("get_config");
}

export async function updateConfig(partial: PartialConfig): Promise<ConfigView> {
  return invoke("update_config", { partial });
}

export async function listModels(provider: string): Promise<ModelInfo[]> {
  return invoke("list_models", { provider });
}

export async function saveSettings(settings: PersistentSettings): Promise<void> {
  return invoke("save_settings", { settings });
}

export async function saveCredential(
  service: CredentialService,
  value?: string | null
): Promise<CredentialStatusMap> {
  return invoke("save_credential", { service, value: value ?? null });
}

export async function getCredentialsStatus(): Promise<CredentialStatusMap> {
  return invoke("get_credentials_status");
}

export async function listSessions(limit?: number): Promise<SessionInfo[]> {
  return invoke("list_sessions", { limit: limit ?? null });
}

export async function openSession(
  id?: string | null,
  resume: boolean = false,
  investigationId?: string | null,
): Promise<SessionInfo> {
  return invoke("open_session", {
    id: id ?? null,
    resume,
    investigation_id: investigationId ?? null,
  });
}

export async function deleteSession(id: string): Promise<void> {
  return invoke("delete_session", { id });
}

export async function getSessionDirectory(sessionId: string): Promise<string> {
  return invoke("get_session_directory", { sessionId });
}

export async function writeSessionArtifact(
  sessionDir: string,
  filename: string,
  content: string,
): Promise<void> {
  return invoke("write_session_artifact", { sessionDir, filename, content });
}

export async function readSessionArtifact(
  sessionDir: string,
  filename: string,
): Promise<string | null> {
  return invoke("read_session_artifact", { sessionDir, filename });
}

export async function readSessionEvent(
  sessionId: string,
  eventId: string,
): Promise<Record<string, unknown> | null> {
  return invoke("read_session_event", { sessionId, eventId });
}

export async function getGraphData(): Promise<GraphData> {
  return invoke("get_graph_data");
}

export async function getInvestigationOverview(): Promise<InvestigationOverviewView> {
  return invoke("get_investigation_overview");
}

export async function readWikiFile(path: string): Promise<string> {
  return invoke("read_wiki_file", { path });
}

export async function debugLog(msg: string): Promise<void> {
  return invoke("debug_log", { msg });
}

export async function getInitStatus(): Promise<InitStatusView> {
  return invoke("get_init_status");
}

export async function runStandardInit(): Promise<StandardInitReportView> {
  return invoke("run_standard_init");
}

export async function completeFirstRunGate(): Promise<InitStatusView> {
  return invoke("complete_first_run_gate");
}

export async function inspectMigrationSource(
  path: string
): Promise<MigrationSourceInspection> {
  return invoke("inspect_migration_source", { path });
}

export async function runMigrationInit(
  request: MigrationInitRequest
): Promise<MigrationInitResultView> {
  return invoke("run_migration_init", { request });
}
