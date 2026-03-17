export const OPEN_WIKI_DRAWER_EVENT = "open-wiki-drawer";

export type OpenWikiDrawerSource = "chat" | "graph" | "drawer";

export interface OpenWikiDrawerDetail {
  wikiPath: string;
  source: OpenWikiDrawerSource;
  requestedTitle?: string;
}
