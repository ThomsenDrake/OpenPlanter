/** /embeddings slash command handler. */
import { saveSettings, updateConfig } from "../api/invoke";
import { appState } from "../state/store";
import type { CommandResult } from "./model";

const VALID_EMBEDDINGS_PROVIDERS = ["voyage", "mistral"];

/** Handle /embeddings [provider] [--save]. */
export async function handleEmbeddingsCommand(args: string): Promise<CommandResult> {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  const requestedProvider = parts[0]?.toLowerCase() ?? "";
  const save = parts.includes("--save");

  if (!requestedProvider) {
    const state = appState.get();
    return {
      action: "handled",
      lines: [
        `Embeddings provider: ${state.embeddingsProvider || "voyage"}`,
        `Retrieval: ${state.embeddingsStatus || "disabled"} | ${state.embeddingsStatusDetail}`,
        `Valid providers: ${VALID_EMBEDDINGS_PROVIDERS.join(", ")}`,
      ],
    };
  }

  if (!VALID_EMBEDDINGS_PROVIDERS.includes(requestedProvider)) {
    return {
      action: "handled",
      lines: [
        `Invalid embeddings provider "${requestedProvider}". Expected: ${VALID_EMBEDDINGS_PROVIDERS.join(", ")}`,
      ],
    };
  }

  try {
    const config = await updateConfig({
      embeddings_provider: requestedProvider,
    });

    appState.update((s) => ({
      ...s,
      embeddingsProvider: config.embeddings_provider,
      embeddingsStatus: config.embeddings_status,
      embeddingsStatusDetail: config.embeddings_status_detail,
    }));

    const lines = [
      `Embeddings provider set to: ${config.embeddings_provider}`,
      `Retrieval: ${config.embeddings_status} | ${config.embeddings_status_detail}`,
    ];
    if (save) {
      await saveSettings({ embeddings_provider: config.embeddings_provider });
      lines.push("(Settings saved)");
    }

    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to set embeddings provider: ${e}`],
    };
  }
}
