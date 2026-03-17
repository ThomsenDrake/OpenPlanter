const PROTOCOL_RE = /^[a-zA-Z][a-zA-Z\d+.-]*:/;

function normalizeBaseWikiPath(baseWikiPath?: string | null): string | null {
  if (!baseWikiPath) return null;
  const trimmed = baseWikiPath.trim();
  if (!trimmed.startsWith("wiki/")) return null;
  if (!trimmed.endsWith(".md")) return null;
  if (trimmed.includes("..")) return null;
  if (trimmed.includes("?") || trimmed.includes("#")) return null;
  return trimmed;
}

export function resolveWikiMarkdownHref(
  href: string,
  options?: { baseWikiPath?: string | null },
): string | null {
  const trimmed = href.trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("#")) return null;
  if (PROTOCOL_RE.test(trimmed)) return null;
  if (trimmed.startsWith("/") || trimmed.startsWith("\\")) return null;
  if (trimmed.includes("\\") || trimmed.includes("?")) return null;

  const withoutFragment = trimmed.split("#", 1)[0];
  if (!withoutFragment || !withoutFragment.endsWith(".md")) return null;

  const normalizedBase = normalizeBaseWikiPath(options?.baseWikiPath);
  const baseSegments = normalizedBase
    ? normalizedBase.slice("wiki/".length).split("/").slice(0, -1)
    : [];
  const rawSegments = withoutFragment.startsWith("wiki/")
    ? withoutFragment.slice("wiki/".length).split("/")
    : [...baseSegments, ...withoutFragment.split("/")];

  const normalizedSegments: string[] = [];
  for (const segment of rawSegments) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (normalizedSegments.length === 0) return null;
      normalizedSegments.pop();
      continue;
    }
    normalizedSegments.push(segment);
  }

  if (normalizedSegments.length === 0) return null;
  return `wiki/${normalizedSegments.join("/")}`;
}
