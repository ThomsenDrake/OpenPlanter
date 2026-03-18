/** /recursion slash command handler. */
import { saveSettings, updateConfig } from "../api/invoke";
import { appState } from "../state/store";
import type { ConfigView, PartialConfig, PersistentSettings } from "../api/types";
import type { CommandResult } from "./model";

const VALID_MODES = ["flat", "auto", "force-max"] as const;

function displayPolicy(policy: string): string {
  return policy.replace(/_/g, "-");
}

function normalizeMode(mode: string): "flat" | "auto" | "force-max" | null {
  const normalized = mode.trim().toLowerCase().replace(/_/g, "-");
  if (normalized === "flat" || normalized === "auto" || normalized === "force-max") {
    return normalized;
  }
  return null;
}

function parseNonNegativeInt(value: string, label: string): number | string {
  if (!/^\d+$/.test(value)) {
    return `Invalid ${label} "${value}". Expected a non-negative integer.`;
  }
  return Number.parseInt(value, 10);
}

function buildStatusLines(): string[] {
  const s = appState.get();
  return [
    `Recursion mode: ${s.recursive ? "recursive" : "flat"}`,
    `Recursion policy: ${displayPolicy(s.recursionPolicy)}`,
    `Min subtask depth: ${s.minSubtaskDepth}`,
    `Max depth: ${s.maxDepth}`,
    `Valid modes: ${VALID_MODES.join(", ")}`,
  ];
}

function applyConfig(config: ConfigView): void {
  appState.update((s) => ({
    ...s,
    recursive: config.recursive,
    recursionPolicy: config.recursion_policy,
    minSubtaskDepth: config.min_subtask_depth,
    maxDepth: config.max_depth,
  }));
}

function buildSavePayload(config: ConfigView): PersistentSettings {
  return {
    recursive: config.recursive,
    recursion_policy: config.recursion_policy,
    min_subtask_depth: config.min_subtask_depth,
    max_depth: config.max_depth,
  };
}

/** Handle /recursion [flat|auto|force-max] [--min N] [--max N] [--save]. */
export async function handleRecursionCommand(args: string): Promise<CommandResult> {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) {
    return { action: "handled", lines: buildStatusLines() };
  }

  let mode: "flat" | "auto" | "force-max" | null = null;
  let minDepth: number | undefined;
  let maxDepth: number | undefined;
  let save = false;

  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    if (part === "--save") {
      save = true;
      continue;
    }
    if (part === "--min" || part === "--max") {
      const next = parts[i + 1];
      if (!next) {
        return {
          action: "handled",
          lines: [`Missing value for ${part}. Usage: /recursion <mode> --min <N> --max <N> [--save]`],
        };
      }
      const parsed = parseNonNegativeInt(next, part === "--min" ? "min depth" : "max depth");
      if (typeof parsed === "string") {
        return { action: "handled", lines: [parsed] };
      }
      if (part === "--min") {
        minDepth = parsed;
      } else {
        maxDepth = parsed;
      }
      i += 1;
      continue;
    }
    if (part.startsWith("--")) {
      return {
        action: "handled",
        lines: [`Unknown option "${part}". Usage: /recursion <mode> --min <N> --max <N> [--save]`],
      };
    }
    if (mode !== null) {
      return {
        action: "handled",
        lines: [`Unexpected argument "${part}". Usage: /recursion <mode> --min <N> --max <N> [--save]`],
      };
    }
    mode = normalizeMode(part);
    if (mode === null) {
      return {
        action: "handled",
        lines: [`Invalid recursion mode "${part}". Expected: ${VALID_MODES.join(", ")}`],
      };
    }
  }

  const state = appState.get();
  const effectiveMode = mode ?? (state.recursive ? displayPolicy(state.recursionPolicy) : "flat");
  const partial: PartialConfig = {
    recursive: effectiveMode !== "flat",
    recursion_policy: effectiveMode === "force-max" ? "force_max" : "auto",
  };
  if (minDepth !== undefined) partial.min_subtask_depth = minDepth;
  if (maxDepth !== undefined) partial.max_depth = maxDepth;

  try {
    const config = await updateConfig(partial);
    applyConfig(config);

    const lines = [
      `Recursion mode set to: ${config.recursive ? "recursive" : "flat"}`,
      `Recursion policy: ${displayPolicy(config.recursion_policy)}`,
      `Min subtask depth: ${config.min_subtask_depth}`,
      `Max depth: ${config.max_depth}`,
    ];
    if (save) {
      await saveSettings(buildSavePayload(config));
      lines.push("(Settings saved)");
    }
    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to set recursion mode: ${e}`],
    };
  }
}
