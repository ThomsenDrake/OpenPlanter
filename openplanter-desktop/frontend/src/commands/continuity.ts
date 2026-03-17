/** /continuity slash command handler. */
import { saveSettings, updateConfig } from "../api/invoke";
import { appState } from "../state/store";
import type { CommandResult } from "./model";

const VALID_CONTINUITY_MODES = ["auto", "fresh", "continue"];

/** Handle /continuity [mode] [--save]. */
export async function handleContinuityCommand(args: string): Promise<CommandResult> {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  const requestedMode = parts[0]?.toLowerCase() ?? "";
  const save = parts.includes("--save");

  if (!requestedMode) {
    const current = appState.get().continuityMode || "auto";
    return {
      action: "handled",
      lines: [
        `Continuity mode: ${current}`,
        `Valid modes: ${VALID_CONTINUITY_MODES.join(", ")}`,
      ],
    };
  }

  if (!VALID_CONTINUITY_MODES.includes(requestedMode)) {
    return {
      action: "handled",
      lines: [
        `Invalid continuity mode "${requestedMode}". Expected: ${VALID_CONTINUITY_MODES.join(", ")}`,
      ],
    };
  }

  try {
    const config = await updateConfig({
      continuity_mode: requestedMode,
    });

    appState.update((s) => ({
      ...s,
      continuityMode: config.continuity_mode,
    }));

    const lines = [`Continuity mode set to: ${config.continuity_mode}`];
    if (save) {
      await saveSettings({ continuity_mode: config.continuity_mode });
      lines.push("(Settings saved)");
    }

    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to set continuity mode: ${e}`],
    };
  }
}
