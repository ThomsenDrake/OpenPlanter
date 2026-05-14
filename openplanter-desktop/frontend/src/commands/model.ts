/** /model slash command handler. */
import { getSettings, listModels, saveSettings, updateConfig } from "../api/invoke";
import type { PersistentSettings, ProviderProfile } from "../api/types";
import { appState } from "../state/store";

/** Aliases mapping short names to full model identifiers. */
export const MODEL_ALIASES: Record<string, string> = {
  opus: "anthropic-foundry/claude-opus-4-6",
  sonnet: "anthropic-foundry/claude-sonnet-4-6",
  haiku: "anthropic-foundry/claude-haiku-4-5",
  "sonnet-4": "anthropic-foundry/claude-sonnet-4-6",
  "haiku-4": "anthropic-foundry/claude-haiku-4-5",
  "opus-4": "anthropic-foundry/claude-opus-4-6",
  gpt5: "azure-foundry/gpt-5.5",
  "gpt-5": "azure-foundry/gpt-5.5",
  "gpt5.3": "azure-foundry/gpt-5.3-codex",
  "gpt-5.3": "azure-foundry/gpt-5.3-codex",
  "gpt5.4": "azure-foundry/gpt-5.4",
  "gpt-5.4": "azure-foundry/gpt-5.4",
  "gpt5.5": "azure-foundry/gpt-5.5",
  "gpt-5.5": "azure-foundry/gpt-5.5",
  kimi: "azure-foundry/Kimi-K2.5",
  gpt4o: "gpt-4o",
  "gpt-4o": "gpt-4o",
  o1: "o1",
  o3: "o3",
  "o4-mini": "o4-mini",
  glm: "glm-5",
  glm5: "glm-5",
  "glm-5": "glm-5",
  zai: "glm-5",
  "zai-glm": "zai-glm-4.6",
  llama: "llama3.2",
  mistral: "mistral",
  gemma: "gemma",
  phi: "phi",
  deepseek: "deepseek",
  qwen: "qwen-3-235b-a22b-instruct-2507",
  "qwen-3": "qwen-3-235b-a22b-instruct-2507",
};

/** Infer provider from a model name, matching builder.rs patterns. */
export function inferProvider(model: string): string | null {
  if (/^anthropic-foundry\//i.test(model)) return "anthropic";
  if (/^azure-foundry\//i.test(model)) return "openai";
  if (model.includes("/")) return "openrouter";
  if (/^claude/i.test(model)) return "anthropic";
  if (/^(llama.*cerebras|qwen-3|gpt-oss)/i.test(model)) return "cerebras";
  if (/^(glm|zai-glm)/i.test(model)) return "zai";
  if (/^(gpt|o[1-4]-|o[1-4]$|chatgpt|dall-e|tts-|whisper)/i.test(model)) return "openai";
  if (/^(llama|mistral|gemma|phi|codellama|deepseek|vicuna|tinyllama|neural-chat|dolphin|wizardlm|orca|nous-hermes|command-r|qwen(?!-3))/i.test(model)) return "ollama";
  return null;
}

function buildProviderDefaultModelSettings(
  provider: string,
  model: string,
  existingProfile?: ProviderProfile | null,
): PersistentSettings {
  const profileId = profileIdFor(provider, model);
  const profileName = `${provider} ${model}`;
  const profile: ProviderProfile = {
    name: existingProfile?.name ?? profileName,
    provider,
    adapter: existingProfile?.adapter ?? defaultAdapterFor(provider),
    model,
    auth_ref: existingProfile?.auth_ref === undefined ? provider : existingProfile.auth_ref,
    options: existingProfile?.options ? { ...existingProfile.options } : {},
  };
  if (existingProfile?.base_url !== undefined) {
    profile.base_url = existingProfile.base_url;
  }
  const base: PersistentSettings = {
    default_model: model,
    active_profiles: { llm: profileId },
    profiles: {
      llm: {
        [profileId]: profile,
      },
    },
  };
  switch (provider) {
    case "openai":
      return { ...base, default_model_openai: model };
    case "anthropic":
      return { ...base, default_model_anthropic: model };
    case "openrouter":
      return { ...base, default_model_openrouter: model };
    case "cerebras":
      return { ...base, default_model_cerebras: model };
    case "zai":
      return { ...base, default_model_zai: model };
    case "ollama":
      return { ...base, default_model_ollama: model };
    default:
      return base;
  }
}

function defaultAdapterFor(provider: string): string {
  return provider === "anthropic" ? "anthropic" : "openai-compatible";
}

function findExistingLlmProfile(
  settings: PersistentSettings,
  profileId: string,
  provider: string,
  model: string,
): ProviderProfile | null {
  const pool = settings.profiles?.llm ?? {};
  const direct = pool[profileId];
  if (direct) return direct;

  const activeId = settings.active_profiles?.llm;
  const active = activeId ? pool[activeId] : null;
  if (active?.provider === provider && active.model === model) return active;

  return Object.values(pool).find(
    (profile) => profile.provider === provider && profile.model === model,
  ) ?? null;
}

function profileIdFor(provider: string, model: string): string {
  const slug = `${provider}-${model}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "llm-default";
}

function formatLlmProfiles(settings: PersistentSettings): string[] {
  const pool = settings.profiles?.llm ?? {};
  const ids = Object.keys(pool).sort();
  if (ids.length === 0) return ["No saved LLM profiles."];
  const active = settings.active_profiles?.llm ?? "";
  return [
    "LLM profiles:",
    ...ids.map((id) => {
      const profile = pool[id];
      const marker = id === active ? "*" : " ";
      const name = profile.name ? `${profile.name}: ` : "";
      return `${marker} ${id} - ${name}${profile.provider}/${profile.model}`;
    }),
  ];
}

export interface CommandResult {
  action: "handled" | "clear" | "quit";
  lines: string[];
  sensitive?: boolean;
}

/** Handle /model [args]. */
export async function handleModelCommand(args: string): Promise<CommandResult> {
  const parts = args.trim().split(/\s+/).filter(Boolean);
  const subcommand = parts[0] || "";

  if (!subcommand) {
    const s = appState.get();
    const aliasEntries = Object.entries(MODEL_ALIASES)
      .map(([k, v]) => `  ${k} -> ${v}`)
      .join("\n");
    return {
      action: "handled",
      lines: [
        `Provider: ${s.provider}`,
        `Model:    ${s.model}`,
        `Profile:  ${s.llmProfileName || s.llmProfileId || "(none)"}`,
        `Z.AI plan: ${s.zaiPlan || "paygo"}`,
        "",
        "Aliases:",
        aliasEntries,
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
          lines: formatLlmProfiles(settings),
        };
      }
      const profile = settings.profiles?.llm?.[profileId];
      if (!profile) {
        return {
          action: "handled",
          lines: [`Unknown LLM profile "${profileId}".`, ...formatLlmProfiles(settings)],
        };
      }
      const config = await updateConfig({ llm_profile_id: profileId });
      await saveSettings({ active_profiles: { llm: profileId } });
      appState.update((s) => ({
        ...s,
        provider: config.provider,
        model: config.model,
        reasoningEffort: config.reasoning_effort,
        llmProfileId: config.llm_profile_id,
        llmProfileName: config.llm_profile_name,
        zaiPlan: config.zai_plan,
      }));
      return {
        action: "handled",
        lines: [`Switched to LLM profile: ${profileId}`],
      };
    } catch (e) {
      return {
        action: "handled",
        lines: [`Failed to switch LLM profile: ${e}`],
      };
    }
  }

  if (subcommand === "list") {
    const filter = parts[1] || "all";
    try {
      const models = await listModels(filter);
      if (models.length === 0) {
        return {
          action: "handled",
          lines: [`No models found for provider "${filter}".`],
        };
      }
      const lines = models.map(
        (m) => `  ${m.id}${m.name ? ` (${m.name})` : ""} [${m.provider}]`,
      );
      return {
        action: "handled",
        lines: [`Models for ${filter}:`, ...lines],
      };
    } catch (e) {
      return {
        action: "handled",
        lines: [`Failed to list models: ${e}`],
      };
    }
  }

  const modelName = subcommand;
  const save = parts.includes("--save");
  const resolved = MODEL_ALIASES[modelName.toLowerCase()] ?? modelName;
  const provider = inferProvider(resolved);

  if (!provider) {
    return {
      action: "handled",
      lines: [
        `Cannot infer provider for "${resolved}". Specify full model name or use a known alias.`,
      ],
    };
  }

  try {
    const config = await updateConfig({
      model: resolved,
      provider,
    });

    appState.update((s) => ({
      ...s,
      provider: config.provider,
      model: config.model,
      reasoningEffort: config.reasoning_effort,
      llmProfileId: config.llm_profile_id,
      llmProfileName: config.llm_profile_name,
      zaiPlan: config.zai_plan,
    }));

    const lines = [`Switched to ${config.provider}/${config.model}`];
    if (save) {
      const profileId = profileIdFor(config.provider, config.model);
      let existingProfile: ProviderProfile | null = null;
      try {
        const settings = await getSettings();
        existingProfile = findExistingLlmProfile(
          settings,
          profileId,
          config.provider,
          config.model,
        );
      } catch {
        existingProfile = null;
      }
      const saved = buildProviderDefaultModelSettings(
        config.provider,
        config.model,
        existingProfile,
      );
      await saveSettings(saved);
      const savedProfileId = saved.active_profiles?.llm ?? "";
      appState.update((s) => ({
        ...s,
        llmProfileId: savedProfileId,
        llmProfileName: saved.profiles?.llm?.[savedProfileId]?.name ?? null,
      }));
      lines.push("(Settings saved)");
      lines.push(`(Saved LLM profile: ${savedProfileId})`);
    }

    return { action: "handled", lines };
  } catch (e) {
    return {
      action: "handled",
      lines: [`Failed to switch model: ${e}`],
    };
  }
}
