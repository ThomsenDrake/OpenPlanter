import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

import {
  getInvestigationOverview,
  getSessionHistory,
  readWikiFile,
} from "../api/invoke";
import type {
  InvestigationOverviewView,
  OverviewActionView,
  OverviewGapView,
  OverviewQuestionView,
  OverviewRevelationView,
  ReplayEntry,
  WikiNavSourceView,
} from "../api/types";
import { appState } from "../state/store";
import { OPEN_WIKI_DRAWER_EVENT, type OpenWikiDrawerDetail } from "../wiki/drawerEvents";
import { resolveWikiMarkdownHref } from "../wiki/linkResolution";

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: false,
  highlight(str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch {
        // Fall through to markdown-it default escaping.
      }
    }
    return "";
  },
});

type DocumentStatus = "idle" | "loading" | "ready" | "error";
type ReplayStatus = "idle" | "loading" | "ready" | "error";
type EvidenceLocatorKind =
  | "anchor"
  | "source_ref"
  | "evidence_ref"
  | "step"
  | "turn"
  | "event"
  | "replay_seq"
  | "replay_line";

interface EvidenceLocator {
  kind: EvidenceLocatorKind;
  value: string;
}

interface ChipLink {
  label: string;
  title?: string;
  onClick?: () => void;
}

interface ReplaySummary {
  continuityLabel: string;
  continuityDetail: string;
  healthLabel: string;
  healthDetail: string;
  failures: number;
  recoveries: number;
  entryCount: number;
  activeState: string;
  activeDetail: string;
}

const CURATED_REPLAY_LIMIT = 14;
const FAILURE_PATTERN =
  /(^error[:\s])|(\bfailed(?:\s+to)?\b)|(\brate limit\b)|(\btimed out\b)|(\btimeout\b)|(\bdegraded\b)|(\bcancelled\b)/i;
const CURATED_REPLAY_ROLES = new Set([
  "assistant",
  "assistant-cancelled",
  "curator",
  "step-summary",
  "user",
]);

export function createOverviewPane(): HTMLElement {
  const pane = document.createElement("div");
  pane.className = "overview-pane";

  const header = document.createElement("div");
  header.className = "overview-header";

  const alerts = document.createElement("div");
  alerts.className = "overview-alerts";

  const body = document.createElement("div");
  body.className = "overview-body";

  const main = document.createElement("div");
  main.className = "overview-main";

  const replaySection = createSection("Curated Replay");
  const snapshotSection = createSection("Investigation Snapshot");
  const gapsSection = createSection("Outstanding Gaps");
  const actionsSection = createSection("Candidate Actions");
  const revelationsSection = createSection("Recent Revelations");
  const detailSection = createSection("Wiki Navigation");
  detailSection.body.classList.add("overview-document");

  const documentControls = document.createElement("div");
  documentControls.className = "overview-document-controls";

  const documentSelectLabel = document.createElement("label");
  documentSelectLabel.className = "overview-document-select-label";
  documentSelectLabel.textContent = "Page";

  const documentSelect = document.createElement("select");
  documentSelect.className = "overview-document-select";
  documentSelect.addEventListener("change", () => {
    if (documentSelect.value) {
      setSelectedPath(documentSelect.value);
    }
  });
  documentSelectLabel.appendChild(documentSelect);
  documentControls.appendChild(documentSelectLabel);

  const documentTitleEl = document.createElement("div");
  documentTitleEl.className = "overview-document-title";

  const documentViewport = document.createElement("div");
  documentViewport.className = "overview-document-viewport";

  const documentStatusEl = document.createElement("div");
  documentStatusEl.className = "overview-empty";

  const documentContentEl = document.createElement("div");
  documentContentEl.className = "overview-document-body rendered";

  documentViewport.append(documentStatusEl, documentContentEl);
  detailSection.body.append(documentControls, documentTitleEl, documentViewport);

  main.append(
    replaySection.section,
    snapshotSection.section,
    gapsSection.section,
    actionsSection.section,
    revelationsSection.section,
    detailSection.section,
  );
  body.append(main);
  pane.append(header, alerts, body);

  let refreshTimer: number | null = null;
  let refreshSeq = 0;
  let docSeq = 0;
  let replaySeq = 0;
  let documentStatus: DocumentStatus = "idle";
  let replayStatus: ReplayStatus = "idle";
  let documentHtml = "";
  let documentTitle = "Wiki document";
  let documentError = "";
  let replayError = "";
  let loadedDocumentPath: string | null = null;
  let replayEntries: ReplayEntry[] = [];
  let selectedReplaySeq: number | null = null;

  const initialState = appState.get();
  let lastOverviewData = initialState.overviewData;
  let lastOverviewStatus = initialState.overviewStatus;
  let lastOverviewError = initialState.overviewError;
  let lastOverviewSelectedWikiPath = initialState.overviewSelectedWikiPath;
  let lastContinuityMode = initialState.continuityMode;
  let lastLoopHealth = initialState.loopHealth;
  let lastLastCompletion = initialState.lastCompletion;

  function createCardList<T>(
    items: T[],
    renderItem: (item: T) => HTMLElement,
    emptyText: string,
  ): HTMLElement {
    const wrapper = document.createElement("div");
    wrapper.className = "overview-card-list";
    if (items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "overview-empty";
      empty.textContent = emptyText;
      wrapper.appendChild(empty);
      return wrapper;
    }
    for (const item of items) {
      wrapper.appendChild(renderItem(item));
    }
    return wrapper;
  }

  function sectionCard(title: string, value: string): HTMLElement {
    const card = document.createElement("div");
    card.className = "overview-stat";
    const label = document.createElement("div");
    label.className = "overview-stat-label";
    label.textContent = title;
    const amount = document.createElement("div");
    amount.className = "overview-stat-value";
    amount.textContent = value;
    card.append(label, amount);
    return card;
  }

  function formatTimestamp(value?: string | null): string {
    if (!value) return "Unknown";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function truncate(text: string, maxLength: number): string {
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength - 1)}…`;
  }

  function titleCase(value: string): string {
    return value
      .replace(/[_-]+/g, " ")
      .trim()
      .replace(/\b\w/g, (match) => match.toUpperCase());
  }

  function normalizeReplayRole(role: string): string {
    return role.trim().toLowerCase();
  }

  function replayRoleLabel(role: string): string {
    const normalized = normalizeReplayRole(role);
    if (normalized === "step-summary") return "Step";
    if (normalized === "assistant-cancelled") return "Cancelled";
    if (!normalized) return "Entry";
    return titleCase(normalized);
  }

  function replayEntryTitle(entry: ReplayEntry): string {
    const normalized = normalizeReplayRole(entry.role);
    if (normalized === "user") return "Objective";
    if (normalized === "step-summary") {
      return entry.step_number ? `Step ${entry.step_number}` : "Step Summary";
    }
    if (normalized === "curator") return "Curator Update";
    if (normalized === "assistant-cancelled") return "Cancelled Run";
    if (normalized === "assistant") return "Assistant Response";
    return replayRoleLabel(entry.role);
  }

  function replayPreview(entry: ReplayEntry): string {
    const normalized = normalizeReplayRole(entry.role);
    if (normalized === "step-summary") {
      const preview = (entry.step_model_preview || entry.content || "").trim();
      return preview || "Step summary pending.";
    }
    const text = (entry.content || "").trim();
    if (!text) return "(no content)";
    return truncate(text, 280);
  }

  function isFailureEntry(entry: ReplayEntry): boolean {
    const normalized = normalizeReplayRole(entry.role);
    if (normalized === "user") return false;
    if (normalized !== "assistant" && normalized !== "assistant-cancelled") {
      return normalized.includes("error");
    }
    return (
      normalized === "assistant-cancelled" ||
      normalized.includes("error") ||
      FAILURE_PATTERN.test(replayPreview(entry))
    );
  }

  function isRecoveryEntry(entry: ReplayEntry): boolean {
    const normalized = normalizeReplayRole(entry.role);
    return (
      normalized === "assistant" ||
      normalized === "curator" ||
      normalized === "step-summary"
    );
  }

  function summarizeReplay(entries: ReplayEntry[]): ReplaySummary {
    const state = appState.get();
    const objectiveTurns = entries.filter(
      (entry) => normalizeReplayRole(entry.role) === "user",
    ).length;
    let failures = 0;
    let recoveries = 0;
    let pendingFailure = false;

    for (const entry of entries) {
      if (isFailureEntry(entry)) {
        failures += 1;
        pendingFailure = true;
        continue;
      }
      if (pendingFailure && isRecoveryEntry(entry)) {
        recoveries += 1;
        pendingFailure = false;
      }
    }

    const continuityMode = (state.continuityMode || "auto").toLowerCase();
    const continuityLabel =
      continuityMode === "continue"
        ? "Resume Mode"
        : continuityMode === "fresh"
          ? "Fresh Mode"
          : objectiveTurns > 1
            ? "Auto Context"
            : "Auto Mode";

    const continuityDetail =
      objectiveTurns > 1
        ? `Replay spans ${objectiveTurns} objective turns, so prior work remains part of the current investigation thread.`
        : continuityMode === "fresh"
          ? "Each run starts from a fresh prompt context, while the replay stays available for review and handoff."
          : "This session has a single recorded objective so far; continuity will deepen as follow-up turns accumulate.";

    const healthLabel =
      failures === 0 ? "Stable" : recoveries > 0 ? "Recovered" : "Degraded";

    const healthDetail =
      failures === 0
        ? "No failure markers were detected in the curated replay."
        : recoveries > 0
          ? `${failures} failure signal${failures === 1 ? "" : "s"} appeared in replay, followed by ${recoveries} recovery point${recoveries === 1 ? "" : "s"}.`
          : `${failures} failure signal${failures === 1 ? "" : "s"} appeared in replay without a later recovery point yet.`;

    let activeState = "Waiting";
    let activeDetail = "Start an objective to build a replay trail.";
    if (state.isRunning && state.loopHealth) {
      activeState = `Live ${titleCase(state.loopHealth.phase)}`;
      activeDetail = `Step ${state.loopHealth.step} at depth ${state.loopHealth.depth} is currently in progress.`;
    } else if (state.lastCompletion?.kind === "partial") {
      activeState = "Partial Result";
      activeDetail =
        "The last run stopped cleanly at its bounded step budget. Resume to continue from the saved state.";
    } else if (state.lastCompletion) {
      activeState = titleCase(state.lastCompletion.kind || "completed");
      activeDetail = state.lastCompletion.reason
        ? `Last completion reason: ${titleCase(state.lastCompletion.reason)}.`
        : "The last run completed without an active recovery condition.";
    } else if (entries.length > 0) {
      activeState = "Idle";
      activeDetail = "No agent run is active right now, but the replay context is preserved.";
    }

    return {
      continuityLabel,
      continuityDetail,
      healthLabel,
      healthDetail,
      failures,
      recoveries,
      entryCount: entries.length,
      activeState,
      activeDetail,
    };
  }

  function findSourceByPath(
    overview: InvestigationOverviewView | null,
    path: string | null,
  ): WikiNavSourceView | null {
    if (!overview || !path) return null;
    return overview.wiki_nav.sources.find((source) => source.file_path === path) ?? null;
  }

  function chooseSelectedPath(
    overview: InvestigationOverviewView,
    currentPath: string | null,
  ): string | null {
    if (currentPath && findSourceByPath(overview, currentPath)) {
      return currentPath;
    }
    return overview.wiki_nav.sources[0]?.file_path ?? null;
  }

  function findElementsByData(
    root: ParentNode,
    attribute: string,
    value: string,
  ): HTMLElement[] {
    const datasetKey = attribute.replace(/-([a-z])/g, (_, letter: string) =>
      letter.toUpperCase(),
    );
    return Array.from(root.querySelectorAll<HTMLElement>(`[data-${attribute}]`)).filter(
      (element) => element.dataset[datasetKey] === value,
    );
  }

  function focusElement(element: HTMLElement | null): boolean {
    if (!element) return false;
    element.scrollIntoView({ behavior: "smooth", block: "center" });
    const previousOutline = element.style.outline;
    const previousOutlineOffset = element.style.outlineOffset;
    element.style.outline = "1px solid var(--accent)";
    element.style.outlineOffset = "2px";
    window.setTimeout(() => {
      element.style.outline = previousOutline;
      element.style.outlineOffset = previousOutlineOffset;
    }, 1400);
    return true;
  }

  function focusOverviewCard(
    root: ParentNode,
    attribute: string,
    value: string,
  ): boolean {
    return focusElement(findElementsByData(root, attribute, value)[0] ?? null);
  }

  function decodeLocatorValue(value: string): string {
    const withPipes = value.replace(/%7C/gi, "|");
    try {
      return decodeURIComponent(withPipes);
    } catch {
      return withPipes;
    }
  }

  function dedupeLocators(locators: EvidenceLocator[]): EvidenceLocator[] {
    const seen = new Set<string>();
    const deduped: EvidenceLocator[] = [];
    for (const locator of locators) {
      const key = `${locator.kind}:${locator.value}`;
      if (seen.has(key)) continue;
      seen.add(key);
      deduped.push(locator);
    }
    return deduped;
  }

  function parseRevelationLocators(revelation: OverviewRevelationView): EvidenceLocator[] {
    const locators: EvidenceLocator[] = [];
    if (revelation.revelation_id.startsWith("openplanter.revelation|")) {
      const parts = revelation.revelation_id.slice("openplanter.revelation|".length).split("|");
      for (const part of parts) {
        const separatorIndex = part.indexOf(":");
        if (separatorIndex <= 0) continue;
        const key = part.slice(0, separatorIndex) as EvidenceLocatorKind;
        const value = decodeLocatorValue(part.slice(separatorIndex + 1).trim());
        if (!value) continue;
        if (
          key === "anchor" ||
          key === "source_ref" ||
          key === "evidence_ref" ||
          key === "step" ||
          key === "turn" ||
          key === "event" ||
          key === "replay_seq" ||
          key === "replay_line"
        ) {
          locators.push({ kind: key, value });
        }
      }
    }

    if (revelation.provenance.step_index != null) {
      locators.push({ kind: "step", value: String(revelation.provenance.step_index) });
    }
    if (revelation.provenance.turn_id) {
      locators.push({ kind: "turn", value: revelation.provenance.turn_id });
    }
    if (revelation.provenance.event_id) {
      locators.push({ kind: "event", value: revelation.provenance.event_id });
    }
    if (revelation.provenance.replay_seq != null) {
      locators.push({
        kind: "replay_seq",
        value: String(revelation.provenance.replay_seq),
      });
    }
    if (revelation.provenance.replay_line != null) {
      locators.push({
        kind: "replay_line",
        value: String(revelation.provenance.replay_line),
      });
    }
    for (const value of revelation.provenance.source_refs ?? []) {
      locators.push({ kind: "source_ref", value });
    }
    for (const value of revelation.provenance.evidence_refs ?? []) {
      locators.push({ kind: "evidence_ref", value });
    }

    return dedupeLocators(locators);
  }

  function findReplaySeqForLocator(locator: EvidenceLocator): number | null {
    if (locator.kind === "replay_seq" || locator.kind === "replay_line") {
      const parsed = Number.parseInt(locator.value, 10);
      if (Number.isFinite(parsed) && replayEntries.some((entry) => entry.seq === parsed)) {
        return parsed;
      }
    }

    if (locator.kind === "step") {
      const step = Number.parseInt(locator.value, 10);
      if (Number.isFinite(step)) {
        const match = [...replayEntries]
          .reverse()
          .find((entry) => entry.step_number === step && isCuratedReplayEntry(entry));
        return match?.seq ?? null;
      }
    }

    const importMatch = locator.value.match(
      /(?:import:replay\.jsonl:|jsonl_record:replay\.jsonl:|replay_event:)(\d+)/,
    );
    if (importMatch) {
      const parsed = Number.parseInt(importMatch[1], 10);
      if (Number.isFinite(parsed) && replayEntries.some((entry) => entry.seq === parsed)) {
        return parsed;
      }
    }

    return null;
  }

  function extractWikiPath(locatorValue: string): string | null {
    const trimmed = locatorValue.trim();
    if (!trimmed) return null;
    if (trimmed.startsWith("wiki:")) return trimmed.slice("wiki:".length);
    if (trimmed.startsWith("source:wiki/")) return trimmed.slice("source:".length);
    if (trimmed.startsWith("import:wiki/")) return trimmed.slice("import:".length);
    if (trimmed.startsWith("wiki/")) return trimmed;

    const wikiIndex = trimmed.indexOf("wiki/");
    if (wikiIndex >= 0) {
      return trimmed.slice(wikiIndex);
    }
    return null;
  }

  function openWikiEvidence(wikiPath: string, requestedTitle?: string): boolean {
    const normalized = wikiPath.trim();
    if (!normalized) return false;
    setSelectedPath(normalized);
    const detail: OpenWikiDrawerDetail = {
      wikiPath: normalized,
      source: "chat",
      requestedTitle,
    };
    window.dispatchEvent(new CustomEvent<OpenWikiDrawerDetail>(OPEN_WIKI_DRAWER_EVENT, { detail }));
    return true;
  }

  function focusReplay(seq: number): boolean {
    selectedReplaySeq = seq;
    render();
    window.setTimeout(() => {
      focusElement(
        replaySection.body.querySelector<HTMLElement>(`[data-replay-seq="${seq}"]`),
      );
    }, 0);
    return true;
  }

  function navigateLocator(locator: EvidenceLocator, requestedTitle?: string): boolean {
    const wikiPath = extractWikiPath(locator.value);
    if (wikiPath) {
      return openWikiEvidence(wikiPath, requestedTitle);
    }

    if (locator.value.startsWith("gap:")) {
      return focusOverviewCard(
        gapsSection.body,
        "gap-id",
        locator.value.slice("gap:".length),
      );
    }

    if (locator.value.startsWith("action:")) {
      return focusOverviewCard(
        actionsSection.body,
        "action-id",
        locator.value.slice("action:".length),
      );
    }

    const replayEntrySeq = findReplaySeqForLocator(locator);
    if (replayEntrySeq != null) {
      return focusReplay(replayEntrySeq);
    }

    return false;
  }

  function locatorLabel(locator: EvidenceLocator): string {
    switch (locator.kind) {
      case "step":
        return `step ${locator.value}`;
      case "turn":
        return `turn ${truncate(locator.value, 18)}`;
      case "event":
        return `event ${truncate(locator.value, 18)}`;
      case "replay_seq":
        return `replay #${locator.value}`;
      case "replay_line":
        return `line ${locator.value}`;
      case "source_ref": {
        const wikiPath = extractWikiPath(locator.value);
        return wikiPath ? truncate(wikiPath.replace(/^wiki\//, ""), 24) : truncate(locator.value, 24);
      }
      case "evidence_ref":
        if (locator.value.startsWith("gap:")) {
          return truncate(locator.value.slice("gap:".length), 24);
        }
        return truncate(locator.value, 24);
      default:
        return truncate(locator.value, 24);
    }
  }

  function isActionableLocator(locator: EvidenceLocator): boolean {
    if (extractWikiPath(locator.value)) return true;
    if (locator.value.startsWith("gap:") || locator.value.startsWith("action:")) return true;
    return findReplaySeqForLocator(locator) != null;
  }

  function appendChipRow(
    host: HTMLElement,
    labelText: string,
    chips: ChipLink[],
  ): void {
    if (chips.length === 0) return;

    const label = document.createElement("div");
    label.className = "overview-card-meta";
    label.textContent = labelText;
    host.appendChild(label);

    const row = document.createElement("div");
    row.className = "overview-card-meta";
    row.style.display = "flex";
    row.style.flexWrap = "wrap";
    row.style.gap = "6px";
    row.style.marginTop = "6px";

    for (const chip of chips) {
      if (chip.onClick) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "overview-pill";
        button.style.cursor = "pointer";
        button.textContent = chip.label;
        if (chip.title) {
          button.title = chip.title;
        }
        button.addEventListener("click", chip.onClick);
        row.appendChild(button);
      } else {
        const pill = document.createElement("span");
        pill.className = "overview-pill";
        pill.textContent = chip.label;
        if (chip.title) {
          pill.title = chip.title;
        }
        row.appendChild(pill);
      }
    }

    host.appendChild(row);
  }

  function buildLocatorChips(
    locators: EvidenceLocator[],
    requestedTitle?: string,
  ): ChipLink[] {
    return locators.map((locator) => {
      const actionable = isActionableLocator(locator);
      return {
        label: locatorLabel(locator),
        title: locator.value,
        onClick: actionable
          ? () => {
              navigateLocator(locator, requestedTitle);
            }
          : undefined,
      };
    });
  }

  async function loadDocument(
    path: string | null,
    overview: InvestigationOverviewView | null = appState.get().overviewData,
  ): Promise<void> {
    docSeq += 1;
    const seq = docSeq;

    if (!path) {
      documentStatus = "idle";
      documentTitle = "Wiki document";
      documentHtml = "";
      documentError = "";
      loadedDocumentPath = null;
      render();
      return;
    }

    const source = findSourceByPath(overview, path);
    documentTitle = source?.title ?? path.replace(/^wiki\//, "").replace(/\.md$/, "");
    documentStatus = "loading";
    documentHtml = "";
    documentError = "";
    render();

    try {
      const content = await readWikiFile(path);
      if (seq !== docSeq) return;
      documentStatus = "ready";
      documentHtml = md.render(content);
      documentError = "";
      loadedDocumentPath = path;
      render();
      interceptDocumentLinks();
      documentViewport.scrollTop = 0;
    } catch (error) {
      if (seq !== docSeq) return;
      documentStatus = "error";
      documentHtml = "";
      documentError = String(error);
      loadedDocumentPath = null;
      render();
    }
  }

  async function loadReplay(sessionId: string | null): Promise<void> {
    replaySeq += 1;
    const seq = replaySeq;
    replayStatus = sessionId ? "loading" : "idle";
    replayError = "";
    replayEntries = sessionId ? replayEntries : [];
    selectedReplaySeq = null;
    render();

    if (!sessionId) {
      return;
    }

    try {
      const history = await getSessionHistory(sessionId);
      if (seq !== replaySeq) return;
      replayEntries = history;
      replayStatus = "ready";
      replayError = "";
      render();
    } catch (error) {
      if (seq !== replaySeq) return;
      replayEntries = [];
      replayStatus = "error";
      replayError = String(error);
      render();
    }
  }

  function setSelectedPath(path: string): void {
    const { overviewSelectedWikiPath } = appState.get();
    if (
      path === overviewSelectedWikiPath &&
      (documentStatus === "loading" ||
        (documentStatus === "ready" && loadedDocumentPath === path))
    ) {
      return;
    }

    appState.update((state) => ({
      ...state,
      overviewSelectedWikiPath: path,
    }));
    void loadDocument(path);
  }

  function interceptDocumentLinks(): void {
    documentContentEl.querySelectorAll("a").forEach((anchor) => {
      const href = anchor.getAttribute("href");
      if (!href) return;
      anchor.addEventListener("click", (event) => {
        const resolvedPath = resolveWikiMarkdownHref(href, {
          baseWikiPath: loadedDocumentPath,
        });
        if (!resolvedPath) return;

        event.preventDefault();
        setSelectedPath(resolvedPath);
      });
    });
  }

  async function refreshOverview(): Promise<void> {
    refreshSeq += 1;
    const seq = refreshSeq;

    appState.update((state) => ({
      ...state,
      overviewStatus: "loading",
      overviewError: null,
    }));

    try {
      const overview = await getInvestigationOverview();
      if (seq !== refreshSeq) return;

      const selectedPath = chooseSelectedPath(
        overview,
        appState.get().overviewSelectedWikiPath,
      );

      appState.update((state) => ({
        ...state,
        overviewStatus: "ready",
        overviewData: overview,
        overviewError: null,
        overviewSelectedWikiPath: selectedPath,
      }));

      void loadReplay(overview.session_id ?? appState.get().sessionId);

      if (selectedPath !== loadedDocumentPath || documentStatus !== "ready") {
        void loadDocument(selectedPath, overview);
      }
    } catch (error) {
      if (seq !== refreshSeq) return;
      appState.update((state) => ({
        ...state,
        overviewStatus: "error",
        overviewError: String(error),
      }));
      void loadReplay(appState.get().sessionId);
    }
  }

  function scheduleRefresh(delayMs: number): void {
    if (!pane.isConnected) {
      return;
    }
    if (refreshTimer) {
      window.clearTimeout(refreshTimer);
    }
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null;
      void refreshOverview();
    }, delayMs);
  }

  function renderAlerts(): void {
    alerts.innerHTML = "";
    const { overviewError, overviewData, overviewStatus } = appState.get();
    if (overviewError) {
      const error = document.createElement("div");
      error.className = "overview-alert overview-alert-error";
      error.textContent = `Overview failed to load: ${overviewError}`;
      alerts.appendChild(error);
    } else if (overviewStatus === "loading" && !overviewData) {
      const loading = document.createElement("div");
      loading.className = "overview-alert";
      loading.textContent = "Loading investigation overview...";
      alerts.appendChild(loading);
    }

    for (const warning of overviewData?.warnings ?? []) {
      const item = document.createElement("div");
      item.className = "overview-alert";
      item.textContent = warning;
      alerts.appendChild(item);
    }
  }

  function renderQuestion(question: OverviewQuestionView): HTMLElement {
    const item = document.createElement("div");
    item.className = "overview-card";

    const top = document.createElement("div");
    top.className = "overview-card-top";

    const title = document.createElement("div");
    title.className = "overview-card-title";
    title.textContent = question.text;

    const badge = document.createElement("span");
    badge.className = "overview-pill";
    badge.textContent = question.priority;

    top.append(title, badge);
    item.appendChild(top);

    if (question.updated_at) {
      const meta = document.createElement("div");
      meta.className = "overview-card-meta";
      meta.textContent = `Updated ${formatTimestamp(question.updated_at)}`;
      item.appendChild(meta);
    }

    return item;
  }

  function renderSnapshot(
    overview: InvestigationOverviewView | null,
    questions: OverviewQuestionView[],
  ): void {
    snapshotSection.body.innerHTML = "";
    if (!overview) {
      const empty = document.createElement("div");
      empty.className = "overview-empty";
      empty.textContent = "No investigation overview available yet.";
      snapshotSection.body.appendChild(empty);
      return;
    }

    const stats = document.createElement("div");
    stats.className = "overview-stats";
    stats.append(
      sectionCard("Focus Questions", String(overview.snapshot.focus_question_count)),
      sectionCard("Supported", String(overview.snapshot.supported_count)),
      sectionCard("Contested", String(overview.snapshot.contested_count)),
      sectionCard(
        "Outstanding Gaps",
        String(overview.snapshot.outstanding_gap_count),
      ),
      sectionCard(
        "Candidate Actions",
        String(overview.snapshot.candidate_action_count),
      ),
      sectionCard("Last Updated", formatTimestamp(overview.generated_at)),
    );
    snapshotSection.body.appendChild(stats);

    const questionBlock = document.createElement("div");
    questionBlock.className = "overview-subsection";
    const title = document.createElement("div");
    title.className = "overview-subsection-title";
    title.textContent = "Focus Questions";
    questionBlock.appendChild(title);
    questionBlock.appendChild(
      createCardList(
        questions,
        (question) => renderQuestion(question),
        "No active focus questions.",
      ),
    );
    snapshotSection.body.appendChild(questionBlock);
  }

  function renderGap(
    gap: OverviewGapView,
    actionLookup: Map<string, OverviewActionView>,
  ): HTMLElement {
    const item = document.createElement("div");
    item.className = "overview-card";
    item.dataset.gapId = gap.gap_id;

    const top = document.createElement("div");
    top.className = "overview-card-top";

    const title = document.createElement("div");
    title.className = "overview-card-title";
    title.textContent = gap.label;

    const badge = document.createElement("span");
    badge.className = "overview-pill";
    badge.textContent = gap.kind;

    top.append(title, badge);
    item.appendChild(top);

    const meta = document.createElement("div");
    meta.className = "overview-card-meta";
    meta.textContent = `${gap.scope} gap${gap.related_action_ids.length > 0 ? ` • ${gap.related_action_ids.length} linked action${gap.related_action_ids.length === 1 ? "" : "s"}` : ""}`;
    item.appendChild(meta);

    if (gap.related_action_ids.length > 0) {
      appendChipRow(
        item,
        "Evidence Links",
        gap.related_action_ids.map((actionId) => ({
          label: truncate(actionLookup.get(actionId)?.label ?? actionId, 28),
          title: actionLookup.get(actionId)?.label ?? actionId,
          onClick: () => {
            focusOverviewCard(actionsSection.body, "action-id", actionId);
          },
        })),
      );
    }

    return item;
  }

  function renderAction(
    action: OverviewActionView,
    gapLookup: Map<string, OverviewGapView>,
  ): HTMLElement {
    const item = document.createElement("div");
    item.className = "overview-card";
    item.dataset.actionId = action.action_id;

    const top = document.createElement("div");
    top.className = "overview-card-top";

    const title = document.createElement("div");
    title.className = "overview-card-title";
    title.textContent = action.label;

    const badge = document.createElement("span");
    badge.className = "overview-pill";
    badge.textContent = action.priority;

    top.append(title, badge);
    item.appendChild(top);

    if (action.rationale) {
      const rationale = document.createElement("div");
      rationale.className = "overview-card-body";
      rationale.textContent = action.rationale;
      item.appendChild(rationale);
    }

    if (action.evidence_gap_refs.length > 0) {
      const meta = document.createElement("div");
      meta.className = "overview-card-meta";
      meta.textContent = `Depends on ${action.evidence_gap_refs.length} gap${action.evidence_gap_refs.length === 1 ? "" : "s"}`;
      item.appendChild(meta);

      appendChipRow(
        item,
        "Evidence Links",
        action.evidence_gap_refs.map((gapId) => ({
          label: truncate(gapLookup.get(gapId)?.label ?? gapId, 28),
          title: gapLookup.get(gapId)?.label ?? gapId,
          onClick: () => {
            focusOverviewCard(gapsSection.body, "gap-id", gapId);
          },
        })),
      );
    }

    return item;
  }

  function renderRevelation(revelation: OverviewRevelationView): HTMLElement {
    const item = document.createElement("div");
    item.className = "overview-card";

    const title = document.createElement("div");
    title.className = "overview-card-title";
    title.textContent = revelation.title;
    item.appendChild(title);

    const body = document.createElement("div");
    body.className = "overview-card-body";
    body.textContent = revelation.summary;
    item.appendChild(body);

    const meta = document.createElement("div");
    meta.className = "overview-card-meta";
    meta.textContent = `${formatTimestamp(revelation.occurred_at)} • ${revelation.provenance.source}${revelation.provenance.step_index != null ? ` • step ${revelation.provenance.step_index}` : ""}`;
    item.appendChild(meta);

    const locators = parseRevelationLocators(revelation);
    appendChipRow(item, "Evidence Trail", buildLocatorChips(locators, revelation.title));

    return item;
  }

  function isCuratedReplayEntry(entry: ReplayEntry): boolean {
    const normalized = normalizeReplayRole(entry.role);
    return CURATED_REPLAY_ROLES.has(normalized) || normalized.includes("error");
  }

  function buildReplayRevelationIndex(
    overview: InvestigationOverviewView | null,
  ): Map<number, OverviewRevelationView> {
    const index = new Map<number, OverviewRevelationView>();
    for (const revelation of overview?.recent_revelations ?? []) {
      const locators = parseRevelationLocators(revelation);
      const matchedReplaySeq =
        locators
          .map((locator) => findReplaySeqForLocator(locator))
          .find((value): value is number => value != null) ?? null;
      if (matchedReplaySeq != null && !index.has(matchedReplaySeq)) {
        index.set(matchedReplaySeq, revelation);
      }
    }
    return index;
  }

  function renderReplayEntry(
    entry: ReplayEntry,
    linkedRevelation: OverviewRevelationView | null,
  ): HTMLElement {
    const card = document.createElement("div");
    card.className = "overview-card";
    card.dataset.replaySeq = String(entry.seq);
    if (selectedReplaySeq === entry.seq) {
      card.style.outline = "1px solid var(--accent)";
      card.style.outlineOffset = "2px";
    }

    const top = document.createElement("div");
    top.className = "overview-card-top";

    const title = document.createElement("div");
    title.className = "overview-card-title";
    title.textContent = replayEntryTitle(entry);

    const badge = document.createElement("span");
    badge.className = "overview-pill";
    badge.textContent = replayRoleLabel(entry.role);

    top.append(title, badge);
    card.appendChild(top);

    const preview = document.createElement("div");
    preview.className = "overview-card-body";
    preview.textContent = replayPreview(entry);
    card.appendChild(preview);

    const metaParts = [formatTimestamp(entry.timestamp)];
    if (entry.step_number != null) {
      metaParts.push(`step ${entry.step_number}`);
    }
    if (entry.step_depth != null) {
      metaParts.push(`depth ${entry.step_depth}`);
    }
    if (entry.step_tool_calls?.length) {
      metaParts.push(
        `${entry.step_tool_calls.length} tool${entry.step_tool_calls.length === 1 ? "" : "s"}`,
      );
    }

    const meta = document.createElement("div");
    meta.className = "overview-card-meta";
    meta.textContent = metaParts.join(" • ");
    card.appendChild(meta);

    if (linkedRevelation) {
      const linkedMeta = document.createElement("div");
      linkedMeta.className = "overview-card-meta";
      linkedMeta.textContent = `Surfaced as revelation: ${linkedRevelation.title}`;
      card.appendChild(linkedMeta);

      const revelationLocators = parseRevelationLocators(linkedRevelation).filter(
        (locator) => {
          if (locator.kind === "replay_seq") {
            return locator.value !== String(entry.seq);
          }
          return true;
        },
      );
      appendChipRow(
        card,
        "Evidence Links",
        buildLocatorChips(revelationLocators, linkedRevelation.title),
      );
    }

    return card;
  }

  function renderCuratedReplay(overview: InvestigationOverviewView | null): void {
    replaySection.body.innerHTML = "";

    const summary = summarizeReplay(replayEntries);
    const stats = document.createElement("div");
    stats.className = "overview-stats";
    stats.append(
      sectionCard("Continuity", summary.continuityLabel),
      sectionCard("Replay Health", summary.healthLabel),
      sectionCard("Failures", String(summary.failures)),
      sectionCard("Recoveries", String(summary.recoveries)),
      sectionCard("Entries", String(summary.entryCount)),
      sectionCard("State", summary.activeState),
    );
    replaySection.body.appendChild(stats);

    const continuityDetail = document.createElement("div");
    continuityDetail.className = "overview-card-meta";
    continuityDetail.textContent = summary.continuityDetail;
    replaySection.body.appendChild(continuityDetail);

    const healthDetail = document.createElement("div");
    healthDetail.className = "overview-card-meta";
    healthDetail.textContent = summary.healthDetail;
    replaySection.body.appendChild(healthDetail);

    const activeDetail = document.createElement("div");
    activeDetail.className = "overview-card-meta";
    activeDetail.textContent = summary.activeDetail;
    replaySection.body.appendChild(activeDetail);

    if (appState.get().lastCompletion?.kind === "partial") {
      const partial = document.createElement("div");
      partial.className = "overview-alert";
      partial.textContent =
        "Partial completion recorded. Resume to continue from the saved investigation state.";
      replaySection.body.appendChild(partial);
    }

    if (replayStatus === "loading") {
      const loading = document.createElement("div");
      loading.className = "overview-empty";
      loading.textContent = "Loading curated replay...";
      replaySection.body.appendChild(loading);
      return;
    }

    if (replayStatus === "error") {
      const error = document.createElement("div");
      error.className = "overview-alert overview-alert-error";
      error.textContent = `Replay unavailable: ${replayError}`;
      replaySection.body.appendChild(error);
      return;
    }

    const revelationByReplaySeq = buildReplayRevelationIndex(overview);
    const curated = replayEntries
      .filter((entry) => isCuratedReplayEntry(entry))
      .slice(-CURATED_REPLAY_LIMIT)
      .reverse();

    replaySection.body.appendChild(
      createCardList(
        curated,
        (entry) => renderReplayEntry(entry, revelationByReplaySeq.get(entry.seq) ?? null),
        appState.get().sessionId
          ? "Run an objective to populate the replay timeline."
          : "Open a session to view replay highlights.",
      ),
    );
  }

  function renderDocumentNav(overview: InvestigationOverviewView | null): void {
    const selectedPath = appState.get().overviewSelectedWikiPath;

    if (!overview || overview.wiki_nav.sources.length === 0) {
      documentSelect.innerHTML = "";
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No wiki pages available";
      documentSelect.appendChild(option);
      documentSelect.disabled = true;
      return;
    }

    documentSelect.disabled = false;
    documentSelect.innerHTML = "";

    let currentCategory = "";
    let categoryGroup: HTMLOptGroupElement | null = null;
    for (const source of overview.wiki_nav.sources) {
      if (source.category !== currentCategory) {
        currentCategory = source.category;
        categoryGroup = document.createElement("optgroup");
        categoryGroup.label = currentCategory;
        documentSelect.appendChild(categoryGroup);
      }

      const option = document.createElement("option");
      option.value = source.file_path;
      option.textContent = source.title;
      (categoryGroup ?? documentSelect).appendChild(option);
    }

    documentSelect.value = selectedPath ?? overview.wiki_nav.sources[0]?.file_path ?? "";
  }

  function renderDocument(overview: InvestigationOverviewView | null): void {
    documentTitleEl.textContent = documentTitle;

    if (!overview || !appState.get().overviewSelectedWikiPath) {
      documentStatusEl.textContent =
        "Select a wiki page to inspect the underlying document.";
      documentStatusEl.hidden = false;
      documentContentEl.hidden = true;
      documentContentEl.innerHTML = "";
      return;
    }

    if (documentStatus === "loading") {
      documentStatusEl.textContent = "Loading wiki document...";
      documentStatusEl.hidden = false;
      documentContentEl.hidden = true;
      documentContentEl.innerHTML = "";
      return;
    }

    if (documentStatus === "error") {
      documentStatusEl.textContent = `Failed to load wiki document: ${documentError}`;
      documentStatusEl.hidden = false;
      documentContentEl.hidden = true;
      documentContentEl.innerHTML = "";
      return;
    }

    if (documentStatus === "ready") {
      documentStatusEl.hidden = true;
      documentContentEl.hidden = false;
      if (documentContentEl.innerHTML !== documentHtml) {
        documentContentEl.innerHTML = documentHtml;
      }
      return;
    }

    documentStatusEl.textContent = "No wiki document selected.";
    documentStatusEl.hidden = false;
    documentContentEl.hidden = true;
    documentContentEl.innerHTML = "";
  }

  function render(): void {
    const state = appState.get();
    const overview = state.overviewData;
    const actionLookup = new Map<string, OverviewActionView>(
      (overview?.candidate_actions ?? []).map((action) => [action.action_id, action] as const),
    );
    const gapLookup = new Map<string, OverviewGapView>(
      (overview?.outstanding_gaps ?? []).map((gap) => [gap.gap_id, gap] as const),
    );

    header.innerHTML = "";
    const heading = document.createElement("div");
    heading.className = "overview-heading";
    heading.textContent = "Current Investigation";
    header.appendChild(heading);

    renderAlerts();
    renderCuratedReplay(overview);
    renderSnapshot(overview, overview?.focus_questions ?? []);

    gapsSection.body.innerHTML = "";
    gapsSection.body.appendChild(
      createCardList(
        overview?.outstanding_gaps ?? [],
        (gap) => renderGap(gap, actionLookup),
        "No outstanding gaps right now.",
      ),
    );

    actionsSection.body.innerHTML = "";
    actionsSection.body.appendChild(
      createCardList(
        overview?.candidate_actions ?? [],
        (action) => renderAction(action, gapLookup),
        "No candidate actions available.",
      ),
    );

    revelationsSection.body.innerHTML = "";
    revelationsSection.body.appendChild(
      createCardList(
        overview?.recent_revelations ?? [],
        (revelation) => renderRevelation(revelation),
        "No recent revelations yet.",
      ),
    );

    renderDocumentNav(overview);
    renderDocument(overview);
  }

  appState.subscribe((state) => {
    const shouldRender =
      state.overviewData !== lastOverviewData ||
      state.overviewStatus !== lastOverviewStatus ||
      state.overviewError !== lastOverviewError ||
      state.overviewSelectedWikiPath !== lastOverviewSelectedWikiPath ||
      state.continuityMode !== lastContinuityMode ||
      state.loopHealth !== lastLoopHealth ||
      state.lastCompletion !== lastLastCompletion;

    lastOverviewData = state.overviewData;
    lastOverviewStatus = state.overviewStatus;
    lastOverviewError = state.overviewError;
    lastOverviewSelectedWikiPath = state.overviewSelectedWikiPath;
    lastContinuityMode = state.continuityMode;
    lastLoopHealth = state.loopHealth;
    lastLastCompletion = state.lastCompletion;

    if (shouldRender) {
      render();
    }
  });

  window.addEventListener("session-changed", () => {
    loadedDocumentPath = null;
    documentStatus = "idle";
    documentHtml = "";
    documentTitle = "Wiki document";
    documentError = "";
    replayEntries = [];
    replayStatus = "idle";
    replayError = "";
    selectedReplaySeq = null;
    render();
    scheduleRefresh(0);
  });
  window.addEventListener("curator-done", () => {
    scheduleRefresh(0);
  });
  window.addEventListener("agent-step", () => {
    scheduleRefresh(1200);
  });
  window.addEventListener("agent-finished", () => {
    scheduleRefresh(0);
  });

  render();
  void refreshOverview();

  return pane;
}

function createSection(title: string): { section: HTMLElement; body: HTMLElement } {
  const section = document.createElement("section");
  section.className = "overview-section";

  const heading = document.createElement("div");
  heading.className = "overview-section-title";
  heading.textContent = title;

  const body = document.createElement("div");
  body.className = "overview-section-body";

  section.append(heading, body);
  return { section, body };
}
