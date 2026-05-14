/** /embeddings slash command handler. */
import { getSettings, saveSettings, updateConfig } from "../api/invoke";
import type { PersistentSettings } from "../api/types";
import { appState } from "../state/store";
import type { CommandResult } from "./model";

const VALID_EMBEDDINGS_PROVIDERS = ["voyage", "mistral"];

function embeddingModelFor(provider: string): string {
  return provider === "mistral" ? "mistral-embed" : "voyage-4";
}

function embeddingBaseUrlFor(provider: string): string {
  return provider === "mistral" ? "https://api.mistral.ai" : "https://api.voyageai.com";
}

function profileIdFor(provider: string, model: string): string {
  return `${provider}-${model}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "embedding-default";
}

function formatEmbeddingProfiles(settings: PersistentSettings): string[] {
  const pool = settings.profiles?.embedding ?? {};
  const ids = Object.keys(pool).sort();
  if (ids.length === 0) return ["No saved embedding profiles."];
  const active = settings.active_profiles?.embedding ?? "";
  return [
    "Embedding profiles:",
    ...ids.map((id) => {
      const profile = pool[id];
      const marker = id === active ? "*" : " ";
      const name = profile.name ? `${profile.name}: ` : "";
      return `${marker} ${id} - ${name}${profile.provider}/${profile.model}`;
    }),
  ];
}

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
        `Profile: ${state.embeddingProfileName || state.embeddingProfileId || "(none)"}`,
        `Retrieval: ${state.embeddingsStatus || "disabled"} | ${state.embeddingsStatusDetail}`,
        `Hybrid retrieval: ${state.embeddingsMode || "documents+ontology"} (${state.embeddingsPacketVersion || "retrieval-v3"})`,
        `Valid providers: ${VALID_EMBEDDINGS_PROVIDERS.join(", ")}`,
      ],
    };
  }

  if (requestedProvider === "profiles" || requestedProvider === "profile") {
    const profileId = requestedProvider === "profile" ? parts[1] : "";
    try {
      const settings = await getSettings();
      if (!profileId) {
        return {
          action: "handled",
          lines: formatEmbeddingProfiles(settings),
        };
      }
      const profile = settings.profiles?.embedding?.[profileId];
      if (!profile) {
        return {
          action: "handled",
          lines: [
            `Unknown embedding profile "${profileId}".`,
            ...formatEmbeddingProfiles(settings),
          ],
        };
      }
      const config = await updateConfig({ embedding_profile_id: profileId });
      await saveSettings({ active_profiles: { embedding: profileId } });
      appState.update((s) => ({
        ...s,
        embeddingsProvider: config.embeddings_provider,
        embeddingsModel: config.embeddings_model,
        embeddingProfileId: config.embedding_profile_id,
        embeddingProfileName: config.embedding_profile_name,
        embeddingsStatus: config.embeddings_status,
        embeddingsStatusDetail: config.embeddings_status_detail,
        embeddingsMode: config.embeddings_mode,
        embeddingsPacketVersion: config.embeddings_packet_version,
      }));
      return {
        action: "handled",
        lines: [`Switched to embedding profile: ${profileId}`],
      };
    } catch (e) {
      return {
        action: "handled",
        lines: [`Failed to switch embedding profile: ${e}`],
      };
    }
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
      embeddingsModel: config.embeddings_model,
      embeddingProfileId: config.embedding_profile_id,
      embeddingProfileName: config.embedding_profile_name,
      embeddingsStatus: config.embeddings_status,
      embeddingsStatusDetail: config.embeddings_status_detail,
      embeddingsMode: config.embeddings_mode,
      embeddingsPacketVersion: config.embeddings_packet_version,
    }));

    const lines = [
      `Embeddings provider set to: ${config.embeddings_provider}`,
      `Retrieval: ${config.embeddings_status} | ${config.embeddings_status_detail}`,
      `Hybrid retrieval: ${config.embeddings_mode} (${config.embeddings_packet_version})`,
    ];
    if (save) {
      const model = config.embeddings_model || embeddingModelFor(config.embeddings_provider);
      const profileId = profileIdFor(config.embeddings_provider, model);
      const profileName = `${config.embeddings_provider[0].toUpperCase()}${config.embeddings_provider.slice(1)} embeddings`;
      await saveSettings({
        embeddings_provider: config.embeddings_provider,
        active_profiles: { embedding: profileId },
        profiles: {
          embedding: {
            [profileId]: {
              name: profileName,
              provider: config.embeddings_provider,
              adapter: "embedding",
              model,
              base_url: embeddingBaseUrlFor(config.embeddings_provider),
              auth_ref: config.embeddings_provider,
            },
          },
        },
      });
      appState.update((s) => ({
        ...s,
        embeddingProfileId: profileId,
        embeddingProfileName: profileName,
      }));
      lines.push(`(Saved embedding profile: ${profileId})`);
    }

    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to set embeddings provider: ${e}`],
    };
  }
}
