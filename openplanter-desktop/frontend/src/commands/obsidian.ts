import {
  configureObsidianExport,
  exportObsidianInvestigation,
  getObsidianExportStatus,
  openObsidianInvestigation,
} from "../api/invoke";
import type { ConfigureObsidianExportRequest } from "../api/types";
import { appState } from "../state/store";
import type { CommandResult } from "./model";

export const OBSIDIAN_USAGE =
  "/obsidian status|enable <vault-path> [--mode fresh-vault|existing-vault-folder] [--subdir OpenPlanter] [--canvas|--no-canvas]|disable|export|open";

function tokenizeArgs(input: string): string[] {
  const tokens: string[] = [];
  let current = "";
  let quote: string | null = null;
  for (let index = 0; index < input.length; index += 1) {
    const ch = input[index];
    if (quote) {
      if (ch === quote) quote = null;
      else current += ch;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      continue;
    }
    if (/\s/.test(ch)) {
      if (current) {
        tokens.push(current);
        current = "";
      }
      continue;
    }
    current += ch;
  }
  if (current) tokens.push(current);
  return tokens;
}

function statusLines(status: Awaited<ReturnType<typeof getObsidianExportStatus>>): string[] {
  return [
    `Obsidian export: ${status.enabled ? "enabled" : "disabled"}`,
    `Configured:       ${status.configured ? "yes" : "no"}`,
    `Mode:             ${status.mode}`,
    `Root:             ${status.root || "—"}`,
    `Target:           ${status.target_root || "—"}`,
    `Subdir:           ${status.subdir}`,
    `Canvas:           ${status.generate_canvas ? "yes" : "no"}`,
    ...status.warnings.map((warning) => `Warning: ${warning}`),
  ];
}

function flagValue(tokens: string[], flag: string): string | null {
  const index = tokens.indexOf(flag);
  if (index < 0) return null;
  const value = tokens[index + 1];
  if (!value || value.startsWith("--")) return null;
  return value;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return String(error);
}

export async function handleObsidianCommand(args: string): Promise<CommandResult> {
  try {
    return await handleObsidianCommandInner(args);
  } catch (error) {
    return {
      action: "handled",
      lines: [`Obsidian command failed: ${errorMessage(error)}`],
    };
  }
}

async function handleObsidianCommandInner(args: string): Promise<CommandResult> {
  const tokens = tokenizeArgs(args);
  const subcommand = (tokens.shift() || "status").toLowerCase();

  if (subcommand === "status") {
    const status = await getObsidianExportStatus();
    return { action: "handled", lines: statusLines(status) };
  }

  if (subcommand === "disable") {
    const status = await configureObsidianExport({ enabled: false });
    appState.update((s) => ({ ...s, obsidianExportEnabled: false }));
    return { action: "handled", lines: ["Obsidian export disabled.", ...statusLines(status)] };
  }

  if (subcommand === "enable") {
    const modeIndex = tokens.indexOf("--mode");
    const subdirIndex = tokens.indexOf("--subdir");
    const canvas = tokens.includes("--canvas");
    const noCanvas = tokens.includes("--no-canvas");
    if (canvas && noCanvas) {
      return { action: "handled", lines: ["Choose either --canvas or --no-canvas.", `Usage: ${OBSIDIAN_USAGE}`] };
    }
    const mode = modeIndex >= 0 ? flagValue(tokens, "--mode") : undefined;
    const subdir = subdirIndex >= 0 ? flagValue(tokens, "--subdir") : undefined;
    if (modeIndex >= 0 && !mode) {
      return { action: "handled", lines: ["Missing value for --mode.", `Usage: ${OBSIDIAN_USAGE}`] };
    }
    if (subdirIndex >= 0 && !subdir) {
      return { action: "handled", lines: ["Missing value for --subdir.", `Usage: ${OBSIDIAN_USAGE}`] };
    }
    const pathTokens = tokens.filter((token, index) => {
      if (token === "--mode" || token === "--subdir" || token === "--canvas" || token === "--no-canvas") return false;
      if (modeIndex >= 0 && index === modeIndex + 1) return false;
      if (subdirIndex >= 0 && index === subdirIndex + 1) return false;
      return true;
    });
    const root = pathTokens.join(" ").trim();
    if (!root) {
      return {
        action: "handled",
        lines: ["Usage: /obsidian enable <vault-path> [--mode fresh-vault|existing-vault-folder] [--subdir OpenPlanter] [--no-canvas]"],
      };
    }
    const request: ConfigureObsidianExportRequest = {
      enabled: true,
      root,
    };
    if (mode) request.mode = mode;
    if (subdir) request.subdir = subdir;
    if (canvas) request.generateCanvas = true;
    if (noCanvas) request.generateCanvas = false;
    const status = await configureObsidianExport(request);
    appState.update((s) => ({
      ...s,
      obsidianExportEnabled: status.enabled,
      obsidianExportRoot: status.root,
      obsidianExportMode: status.mode,
      obsidianExportSubdir: status.subdir,
      obsidianGenerateCanvas: status.generate_canvas,
    }));
    return { action: "handled", lines: ["Obsidian export enabled.", ...statusLines(status)] };
  }

  if (subcommand === "export") {
    const sessionId = appState.get().sessionId;
    if (!sessionId) return { action: "handled", lines: ["No active session selected."] };
    const result = await exportObsidianInvestigation(sessionId);
    return {
      action: "handled",
      lines: [
        `Exported Obsidian pack: ${result.home_path}`,
        `Files written: ${result.files_written.length}`,
        ...result.warnings.map((warning) => `Warning: ${warning}`),
      ],
    };
  }

  if (subcommand === "open") {
    const sessionId = appState.get().sessionId;
    if (!sessionId) return { action: "handled", lines: ["No active session selected."] };
    const result = await openObsidianInvestigation(sessionId);
    return {
      action: "handled",
      lines: [`Opened Obsidian: ${result.export.home_path}`],
    };
  }

  return {
    action: "handled",
    lines: [`Unknown /obsidian subcommand: ${subcommand}`, `Usage: ${OBSIDIAN_USAGE}`],
  };
}
