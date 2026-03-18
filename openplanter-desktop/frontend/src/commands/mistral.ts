/** /mistral slash command handler. */
import {
  getCredentialsStatus,
  saveCredential,
  saveSettings,
  updateConfig,
} from "../api/invoke";
import type { CredentialService, CredentialStatusMap } from "../api/types";
import { appState } from "../state/store";
import type { CommandResult } from "./model";

const KEY_MODE_VALUES = ["shared", "override"] as const;
type KeyModeValue = (typeof KEY_MODE_VALUES)[number];
type KeyTargetName = "shared-key" | "docai-key" | "transcription-key";

const KEY_TARGETS: Record<
  KeyTargetName,
  { service: CredentialService; label: string; statusLabel: string }
> = {
  "shared-key": {
    service: "mistral",
    label: "Mistral shared",
    statusLabel: "Mistral shared key",
  },
  "docai-key": {
    service: "mistral_document_ai",
    label: "Mistral Document AI override",
    statusLabel: "Document AI override key",
  },
  "transcription-key": {
    service: "mistral_transcription",
    label: "Mistral transcription",
    statusLabel: "Transcription key",
  },
};

export const MISTRAL_USAGE =
  "Usage: /mistral status|key-mode <shared|override> [--save]|shared-key set <value>|shared-key clear|docai-key set <value>|docai-key clear|transcription-key set <value>|transcription-key clear";

function currentKeyMode(): KeyModeValue {
  return appState.get().mistralDocumentAiUseSharedKey ? "shared" : "override";
}

function formatCredentialState(configured: boolean): string {
  return configured ? "configured" : "missing";
}

function formatMistralStatusLines(status: CredentialStatusMap): string[] {
  return [
    `Document AI key mode: ${currentKeyMode()}`,
    `Mistral shared key: ${formatCredentialState(status.mistral ?? false)}`,
    `Document AI override key: ${formatCredentialState(status.mistral_document_ai ?? false)}`,
    `Transcription key: ${formatCredentialState(status.mistral_transcription ?? false)}`,
  ];
}

async function showStatus(includeUsage: boolean): Promise<CommandResult> {
  try {
    const status = await getCredentialsStatus();
    const lines = formatMistralStatusLines(status);
    if (includeUsage) {
      lines.push(MISTRAL_USAGE);
    }
    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to load Mistral configuration: ${e}`],
    };
  }
}

async function handleKeyMode(parts: string[]): Promise<CommandResult> {
  const requestedMode = parts[1]?.toLowerCase() ?? "";
  const save = parts.includes("--save");

  if (!requestedMode) {
    return {
      action: "handled",
      lines: [
        `Document AI key mode: ${currentKeyMode()}`,
        "Usage: /mistral key-mode <shared|override> [--save]",
      ],
    };
  }

  if (!KEY_MODE_VALUES.includes(requestedMode as KeyModeValue)) {
    return {
      action: "handled",
      lines: [
        `Invalid Document AI key mode "${requestedMode}". Expected: ${KEY_MODE_VALUES.join(", ")}`,
      ],
    };
  }

  try {
    const config = await updateConfig({
      mistral_document_ai_use_shared_key: requestedMode === "shared",
    });

    appState.update((state) => ({
      ...state,
      mistralDocumentAiUseSharedKey: config.mistral_document_ai_use_shared_key,
    }));

    const mode = config.mistral_document_ai_use_shared_key ? "shared" : "override";
    const lines = [`Document AI key mode set to: ${mode}`];

    if (save) {
      try {
        await saveSettings({
          mistral_document_ai_use_shared_key:
            config.mistral_document_ai_use_shared_key,
        });
        lines.push("(Settings saved)");
      } catch (e) {
        lines.push(`Runtime updated, but failed to save settings: ${e}`);
      }
    }

    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to update Document AI key mode: ${e}`],
    };
  }
}

async function handleCredentialAction(parts: string[]): Promise<CommandResult> {
  const target = KEY_TARGETS[parts[0].toLowerCase() as KeyTargetName];
  const operation = parts[1]?.toLowerCase() ?? "";

  if (!operation) {
    return {
      action: "handled",
      lines: [
        `Usage: /mistral ${parts[0]} <set <value>|clear>`,
      ],
    };
  }

  if (operation === "set") {
    const value = parts.slice(2).join(" ").trim();
    if (!value) {
      return {
        action: "handled",
        lines: [`Usage: /mistral ${parts[0]} set <value>`],
      };
    }

    try {
      const status = await saveCredential(target.service, value);
      return {
        action: "handled",
        lines: [
          `Saved ${target.label} workspace key.`,
          ...formatMistralStatusLines(status),
        ],
        sensitive: true,
      };
    } catch (e) {
      return {
        action: "handled",
        lines: [`Failed to save ${target.label} key.`],
        sensitive: true,
      };
    }
  }

  if (operation === "clear") {
    try {
      const status = await saveCredential(target.service, null);
      const lines = [`Cleared ${target.label} workspace key.`];
      if (status[target.service]) {
        lines.push("This service is still configured from env or .env.");
      }
      lines.push(...formatMistralStatusLines(status));
      return { action: "handled", lines };
    } catch (e) {
      return {
        action: "handled",
        lines: [`Failed to clear ${target.label} key: ${e}`],
      };
    }
  }

  return {
    action: "handled",
    lines: [
      `Unknown ${target.statusLabel.toLowerCase()} action "${operation}".`,
      `Usage: /mistral ${parts[0]} <set <value>|clear>`,
    ],
  };
}

/** Handle /mistral [status|key-mode|shared-key|docai-key|transcription-key]. */
export async function handleMistralCommand(args: string): Promise<CommandResult> {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  const action = parts[0]?.toLowerCase() ?? "";

  if (!action || action === "status") {
    return showStatus(!action);
  }

  if (action === "key-mode") {
    return handleKeyMode(parts);
  }

  if (action in KEY_TARGETS) {
    return handleCredentialAction(parts);
  }

  return {
    action: "handled",
    lines: [`Unknown /mistral action "${action}".`, MISTRAL_USAGE],
  };
}
