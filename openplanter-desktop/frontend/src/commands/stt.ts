/** /stt slash command handler. */
import { getSettings, saveSettings, updateConfig } from "../api/invoke";
import type { PersistentSettings } from "../api/types";
import { appState } from "../state/store";
import type { CommandResult } from "./model";

function profileIdFor(provider: string, model: string): string {
  return `${provider}-${model}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "stt-default";
}

function titleCaseProvider(provider: string): string {
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}

function formatSttProfiles(settings: PersistentSettings): string[] {
  const pool = settings.profiles?.stt ?? {};
  const ids = Object.keys(pool).sort();
  if (ids.length === 0) return ["No saved STT profiles."];
  const active = settings.active_profiles?.stt ?? "";
  return [
    "STT profiles:",
    ...ids.map((id) => {
      const profile = pool[id];
      const marker = id === active ? "*" : " ";
      const name = profile.name ? `${profile.name}: ` : "";
      return `${marker} ${id} - ${name}${profile.provider}/${profile.model}`;
    }),
  ];
}

/** Handle /stt [model] [--save]. */
export async function handleSttCommand(args: string): Promise<CommandResult> {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  const save = parts.includes("--save");
  const subcommand = parts.find((part) => part !== "--save") ?? "";

  if (!subcommand) {
    const state = appState.get();
    return {
      action: "handled",
      lines: [
        `STT provider: ${state.sttProvider || "mistral"}`,
        `STT model: ${state.sttModel || "voxtral-mini-latest"}`,
        `Profile: ${state.sttProfileName || state.sttProfileId || "(none)"}`,
        "Usage: /stt <model> [--save]",
      ],
    };
  }

  if (subcommand === "profiles" || subcommand === "profile") {
    const profileId = subcommand === "profile" ? parts[1] : "";
    try {
      const settings = await getSettings();
      if (!profileId) {
        return {
          action: "handled",
          lines: formatSttProfiles(settings),
        };
      }
      const profile = settings.profiles?.stt?.[profileId];
      if (!profile) {
        return {
          action: "handled",
          lines: [`Unknown STT profile "${profileId}".`, ...formatSttProfiles(settings)],
        };
      }
      const config = await updateConfig({ stt_profile_id: profileId });
      await saveSettings({ active_profiles: { stt: profileId } });
      appState.update((s) => ({
        ...s,
        sttProvider: config.stt_provider,
        sttModel: config.stt_model,
        sttProfileId: config.stt_profile_id,
        sttProfileName: config.stt_profile_name,
      }));
      return {
        action: "handled",
        lines: [`Switched to STT profile: ${profileId}`],
      };
    } catch (e) {
      return {
        action: "handled",
        lines: [`Failed to switch STT profile: ${e}`],
      };
    }
  }

  try {
    const config = await updateConfig({ stt_model: subcommand });
    appState.update((s) => ({
      ...s,
      sttProvider: config.stt_provider,
      sttModel: config.stt_model,
      sttProfileId: config.stt_profile_id,
      sttProfileName: config.stt_profile_name,
    }));

    const lines = [`STT model set to: ${config.stt_model}`];
    if (save) {
      const profileId = profileIdFor(config.stt_provider, config.stt_model);
      const profileName = `${titleCaseProvider(config.stt_provider)} ${config.stt_model} STT`;
      await saveSettings({
        active_profiles: { stt: profileId },
        profiles: {
          stt: {
            [profileId]: {
              name: profileName,
              provider: config.stt_provider,
              adapter: "speech-to-text",
              model: config.stt_model,
              base_url: config.stt_base_url,
              auth_ref: config.stt_provider,
              options: {
                max_bytes: config.stt_max_bytes,
                chunk_max_seconds: config.stt_chunk_max_seconds,
                chunk_overlap_seconds: config.stt_chunk_overlap_seconds,
                max_chunks: config.stt_max_chunks,
                request_timeout_sec: config.stt_request_timeout_sec,
              },
            },
          },
        },
        mistral_transcription_base_url: config.stt_base_url,
        mistral_transcription_model: config.stt_model,
        mistral_transcription_max_bytes: config.stt_max_bytes,
        mistral_transcription_chunk_max_seconds: config.stt_chunk_max_seconds,
        mistral_transcription_chunk_overlap_seconds: config.stt_chunk_overlap_seconds,
        mistral_transcription_max_chunks: config.stt_max_chunks,
        mistral_transcription_request_timeout_sec: config.stt_request_timeout_sec,
      });
      appState.update((s) => ({
        ...s,
        sttProfileId: profileId,
        sttProfileName: profileName,
      }));
      lines.push(`(Saved STT profile: ${profileId})`);
    }
    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to set STT model: ${e}`],
    };
  }
}
