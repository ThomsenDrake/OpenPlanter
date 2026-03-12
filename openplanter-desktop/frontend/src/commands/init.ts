import {
  completeFirstRunGate,
  getInitStatus,
  runStandardInit,
} from "../api/invoke";
import type { InitStatusView } from "../api/types";
import { appState } from "../state/store";
import type { CommandResult } from "./model";

function statusLines(status: InitStatusView): string[] {
  return [
    `Workspace:   ${status.runtime_workspace}`,
    `Gate:        ${status.gate_state}`,
    `Initialized: ${status.onboarding_completed ? "yes" : "no"}`,
    `Wiki root:   ${status.has_runtime_wiki ? "yes" : "no"}`,
    `Wiki index:  ${status.has_runtime_index ? "yes" : "no"}`,
    `Last migration target: ${status.last_migration_target || "—"}`,
    ...status.warnings.map((warning) => `Warning: ${warning}`),
  ];
}

export async function handleInitCommand(args: string): Promise<CommandResult> {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  const subcommand = (parts[0] || "status").toLowerCase();

  if (appState.get().isInitBusy) {
    return {
      action: "handled",
      lines: ["Initialization is already running. Wait for it to finish first."],
    };
  }

  if (subcommand === "status") {
    const status = await getInitStatus();
    appState.update((s) => ({
      ...s,
      initStatus: status,
      initGateState: status.gate_state,
      initGateVisible: status.gate_state !== "ready" ? true : s.initGateVisible,
    }));
    return { action: "handled", lines: statusLines(status) };
  }

  if (subcommand === "standard") {
    try {
      appState.update((s) => ({ ...s, isInitBusy: true, migrationResult: null }));
      const report = await runStandardInit();
      const status = await getInitStatus();
      appState.update((s) => ({
        ...s,
        isInitBusy: false,
        initStatus: status,
        initGateState: status.gate_state,
        initGateVisible: status.gate_state !== "ready" ? true : false,
        initGateMode: "standard",
        migrationProgress: null,
      }));
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("curator-done"));
      }
      return {
        action: "handled",
        lines: [
          `Standard init completed for ${report.workspace}.`,
          `Created paths: ${report.created_paths.length}`,
          `Copied files: ${report.copied_paths.length}`,
          `Skipped existing: ${report.skipped_existing}`,
          ...statusLines(status),
        ],
      };
    } catch (error) {
      appState.update((s) => ({ ...s, isInitBusy: false }));
      return {
        action: "handled",
        lines: [`Standard init failed: ${error}`],
      };
    }
  }

  if (subcommand === "migrate") {
    appState.update((s) => ({
      ...s,
      initGateVisible: true,
      initGateMode: "migration",
      migrationResult: null,
    }));
    return {
      action: "handled",
      lines: ["Opened Migration Init. Add a target workspace and one or more sources in the setup panel."],
    };
  }

  if (subcommand === "open") {
    appState.update((s) => ({
      ...s,
      initGateVisible: true,
      initGateMode: s.initGateMode,
    }));
    return {
      action: "handled",
      lines: ["Opened the workspace initialization panel."],
    };
  }

  if (subcommand === "done") {
    try {
      appState.update((s) => ({ ...s, isInitBusy: true }));
      const status = await completeFirstRunGate();
      appState.update((s) => ({
        ...s,
        isInitBusy: false,
        initStatus: status,
        initGateState: status.gate_state,
        initGateVisible: status.gate_state !== "ready",
      }));
      return { action: "handled", lines: statusLines(status) };
    } catch (error) {
      appState.update((s) => ({ ...s, isInitBusy: false }));
      return {
        action: "handled",
        lines: [`Failed to complete onboarding: ${error}`],
      };
    }
  }

  return {
    action: "handled",
    lines: [
      `Unknown /init subcommand: ${subcommand}`,
      "Use /init status, /init standard, or /init migrate.",
    ],
  };
}
