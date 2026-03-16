/** Shared helpers for rendering compact tool argument previews. */

export const KEY_ARGS: Record<string, string> = {
  read_file: "path",
  read_image: "path",
  audio_transcribe: "path",
  write_file: "path",
  edit_file: "path",
  hashline_edit: "path",
  apply_patch: "patch",
  list_files: "glob",
  search_files: "query",
  repo_map: "glob",
  run_shell: "command",
  run_shell_bg: "command",
  check_shell_bg: "job_id",
  kill_shell_bg: "job_id",
  web_search: "query",
  fetch_url: "urls",
  subtask: "objective",
  execute: "objective",
  think: "note",
};

interface IndexedCandidate {
  index: number;
  value: string;
}

function normalizePreviewValue(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    return trimmed || null;
  }

  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }

  if (Array.isArray(value)) {
    const items = value.flatMap((item) => {
      if (typeof item === "string") {
        const trimmed = item.trim();
        return trimmed ? [trimmed] : [];
      }
      if (typeof item === "number" && Number.isFinite(item)) {
        return [String(item)];
      }
      return [];
    });
    return items.length > 0 ? items.join(", ") : null;
  }

  return null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function collectRegexCandidates(
  source: string,
  regex: RegExp,
  pickValue: (match: RegExpMatchArray) => string | null,
): IndexedCandidate[] {
  const candidates: IndexedCandidate[] = [];
  for (const match of source.matchAll(regex)) {
    const value = pickValue(match)?.trim();
    if (value) {
      candidates.push({
        index: match.index ?? Number.MAX_SAFE_INTEGER,
        value,
      });
    }
  }
  return candidates;
}

function collectCandidatesForKey(source: string, key: string): IndexedCandidate[] {
  const escapedKey = escapeRegExp(key);
  const stringRegex = new RegExp(`"${escapedKey}"\\s*:\\s*"([^"]*)`, "g");
  const arrayRegex = new RegExp(`"${escapedKey}"\\s*:\\s*\\[([^\\]]*)`, "g");
  const numberRegex = new RegExp(`"${escapedKey}"\\s*:\\s*(-?\\d+(?:\\.\\d+)?)`, "g");

  return [
    ...collectRegexCandidates(source, stringRegex, (match) => match[1] ?? null),
    ...collectRegexCandidates(source, arrayRegex, (match) => {
      const items = [...(match[1] ?? "").matchAll(/"([^"]*)/g)]
        .map((item) => item[1]?.trim() ?? "")
        .filter(Boolean);
      return items.length > 0 ? items.join(", ") : null;
    }),
    ...collectRegexCandidates(source, numberRegex, (match) => match[1] ?? null),
  ].sort((a, b) => a.index - b.index);
}

function collectFallbackCandidates(source: string): IndexedCandidate[] {
  return [
    ...collectRegexCandidates(
      source,
      /"([^"]+)"\s*:\s*"([^"]*)/g,
      (match) => match[2] ?? null,
    ),
    ...collectRegexCandidates(
      source,
      /"([^"]+)"\s*:\s*\[([^\]]*)/g,
      (match) => {
        const items = [...(match[2] ?? "").matchAll(/"([^"]*)/g)]
          .map((item) => item[1]?.trim() ?? "")
          .filter(Boolean);
        return items.length > 0 ? items.join(", ") : null;
      },
    ),
    ...collectRegexCandidates(
      source,
      /"([^"]+)"\s*:\s*(-?\d+(?:\.\d+)?)/g,
      (match) => match[2] ?? null,
    ),
  ].sort((a, b) => a.index - b.index);
}

/** Return the best compact preview for a parsed tool argument object. */
export function getToolCallKeyArg(toolName: string, args: unknown): string {
  if (!args || typeof args !== "object" || Array.isArray(args)) {
    return "";
  }

  const entries = Object.entries(args as Record<string, unknown>);
  const preferredKey = KEY_ARGS[toolName];

  if (preferredKey) {
    const preferredValue = normalizePreviewValue((args as Record<string, unknown>)[preferredKey]);
    if (preferredValue) {
      return preferredValue;
    }
  }

  for (const [, value] of entries) {
    const preview = normalizePreviewValue(value);
    if (preview) {
      return preview;
    }
  }

  return "";
}

/** Best-effort extraction from a partial JSON argument string during streaming. */
export function extractToolCallKeyArg(toolName: string, argsJson: string): string | null {
  const preferredKey = KEY_ARGS[toolName];
  if (preferredKey) {
    const preferred = collectCandidatesForKey(argsJson, preferredKey)[0];
    if (preferred) {
      return preferred.value;
    }
  }

  const fallback = collectFallbackCandidates(argsJson)[0];
  return fallback?.value ?? null;
}
