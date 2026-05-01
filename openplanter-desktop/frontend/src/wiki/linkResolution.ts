const PROTOCOL_RE = /^[a-zA-Z][a-zA-Z\d+.-]*:/;
const ENCODED_PATH_DELIMITER_RE = /%(?:2[fF]|5[cC]|3[fF]|23)/;

function normalizeBaseWikiPath(baseWikiPath?: string | null): string | null {
  if (!baseWikiPath) return null;
  const trimmed = baseWikiPath.trim();
  if (!trimmed.startsWith("wiki/")) return null;
  if (!trimmed.endsWith(".md")) return null;
  if (trimmed.includes("..")) return null;
  if (trimmed.includes("?") || trimmed.includes("#")) return null;
  return trimmed;
}

function decodeWikiPathSegment(segment: string, decodePercentEncoding: boolean): string | null {
  if (!decodePercentEncoding) return segment;
  if (ENCODED_PATH_DELIMITER_RE.test(segment)) return null;
  const withBarePercentsEscaped = segment.replace(/%(?![0-9A-Fa-f]{2})/g, "%25");
  try {
    const decoded = decodeURIComponent(withBarePercentsEscaped);
    if (
      decoded.includes("/") ||
      decoded.includes("\\") ||
      decoded.includes("?") ||
      decoded.includes("#")
    ) {
      return null;
    }
    return decoded;
  } catch {
    return segment;
  }
}

export function resolveWikiMarkdownHref(
  href: string,
  options?: { baseWikiPath?: string | null; decodePercentEncoding?: boolean },
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
  for (const rawSegment of rawSegments) {
    const segment = decodeWikiPathSegment(rawSegment, options?.decodePercentEncoding === true);
    if (segment == null) return null;
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
