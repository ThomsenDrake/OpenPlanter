import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

import { getInvestigationOverview, getSessionHistory, readWikiFile } from "../api/invoke";
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

type RevelationRef = {
  key: string;
  kind: "source_ref" | "evidence_ref" | "turn" | "event" | "step";
  raw: string;
};

const REPLAY_FOCUS_EVENT = "overview-replay-focus";

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

  function parseRevelationRefs(revelation: OverviewRevelationView): RevelationRef[] {
    const refs = new Map<string, RevelationRef>();
    for (const sourceRef of revelation.provenance.source_refs ?? []) {
      refs.set(`source_ref:${sourceRef}`, {
        key: `source_ref:${sourceRef}`,
        kind: "source_ref",
        raw: sourceRef,
      });
    }
    for (const evidenceRef of revelation.provenance.evidence_refs ?? []) {
      refs.set(`evidence_ref:${evidenceRef}`, {
        key: `evidence_ref:${evidenceRef}`,
        kind: "evidence_ref",
        raw: evidenceRef,
      });
    }
    if (revelation.provenance.turn_id) {
      refs.set(`turn:${revelation.provenance.turn_id}`, {
        key: `turn:${revelation.provenance.turn_id}`,
        kind: "turn",
        raw: revelation.provenance.turn_id,
      });
    }
    if (revelation.provenance.event_id) {
      refs.set(`event:${revelation.provenance.event_id}`, {
        key: `event:${revelation.provenance.event_id}`,
        kind: "event",
        raw: revelation.provenance.event_id,
      });
    }

    const suffix = revelation.revelation_id.split("|").slice(1);
    for (const part of suffix) {
      const [prefix, ...rest] = part.split(":");
      const value = rest.join(":").trim();
      if (!value) continue;
      if (prefix === "source_ref") {
        refs.set(`source_ref:${value}`, { key: `source_ref:${value}`, kind: "source_ref", raw: value });
      } else if (prefix === "evidence_ref") {
        refs.set(`evidence_ref:${value}`, {
          key: `evidence_ref:${value}`,
          kind: "evidence_ref",
          raw: value,
        });
      } else if (prefix === "turn") {
        refs.set(`turn:${value}`, { key: `turn:${value}`, kind: "turn", raw: value });
      } else if (prefix === "event") {
        refs.set(`event:${value}`, { key: `event:${value}`, kind: "event", raw: value });
      } else if (prefix === "step") {
        refs.set(`step:${value}`, { key: `step:${value}`, kind: "step", raw: value });
      }
    }

    return Array.from(refs.values());
  }

  function isReplayHighlightable(entry: ReplayEntry): boolean {
    return entry.role === "step-summary" || entry.role === "curator" || entry.role === "assistant";
  }

  function replayStateSummary(entries: ReplayEntry[]): {
    continuity: string;
    failure: string;
    recovery: string;
  } {
    const continuity = appState.get().continuityMode || "auto";
    const lastError = [...entries].reverse().find((entry) => entry.role === "error");
    const errorWithinLastFive = [...entries].slice(-5).some((entry) => entry.role === "error");
    const recentSummary = [...entries].reverse().find((entry) => entry.role === "step-summary" || entry.role === "assistant");

    return {
      continuity,
      failure: lastError
        ? `Recent failure: ${lastError.content.slice(0, 90)}${lastError.content.length > 90 ? "…" : ""}`
        : "No failures recorded in replay.",
      recovery: recentSummary && errorWithinLastFive
        ? `Recovered via ${recentSummary.role === "step-summary" ? "step summary" : "assistant response"}.`
        : errorWithinLastFive
          ? "Failure still active; no recovery event observed yet."
          : "Session appears stable.",
    };
  }

  function matchReplayByRef(ref: RevelationRef): ReplayEntry | null {
    if (ref.kind === "step") {
      const stepIndex = Number.parseInt(ref.raw, 10);
      if (Number.isFinite(stepIndex)) {
        return [...replayEntries].reverse().find((entry) => entry.step_number === stepIndex) ?? null;
      }
    }

    const rawLower = ref.raw.toLowerCase();
    return [...replayEntries].reverse().find((entry) => {
      const haystack = [entry.content, entry.tool_name, entry.conversation_path]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(rawLower);
    }) ?? null;
  }

  function focusReplay(seq: number): void {
    selectedReplaySeq = seq;
    renderReplay(appState.get().overviewData);
    window.dispatchEvent(new CustomEvent(REPLAY_FOCUS_EVENT, { detail: { seq } }));
  }

  function renderEvidenceLinks(refs: RevelationRef[], context: string): HTMLElement | null {
    if (refs.length === 0) return null;

    const wrap = document.createElement("div");
    wrap.className = "overview-card-meta";
    wrap.style.display = "flex";
    wrap.style.flexWrap = "wrap";
    wrap.style.gap = "6px";

    for (const ref of refs) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "overview-pill";
      button.style.cursor = "pointer";
      button.textContent = `${ref.kind}: ${truncate(ref.raw, 28)}`;
      button.title = ref.raw;
      button.addEventListener("click", () => {
        const match = matchReplayByRef(ref);
        if (match) {
          focusReplay(match.seq);
        }
      });
      wrap.appendChild(button);
    }

    const label = document.createElement("div");
    label.className = "overview-card-meta";
    label.textContent = `${context} evidence links`;

    const container = document.createElement("div");
    container.append(label, wrap);
    return container;
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

  async function refreshReplay(sessionId: string | null): Promise<void> {
    replaySeq += 1;
    const seq = replaySeq;

    if (!sessionId) {
      replayStatus = "idle";
      replayEntries = [];
      replayError = "";
      selectedReplaySeq = null;
      renderReplay(appState.get().overviewData);
      return;
    }

    replayStatus = "loading";
    replayError = "";
    renderReplay(appState.get().overviewData);

    try {
      const history = await getSessionHistory(sessionId);
      if (seq !== replaySeq) return;
      replayStatus = "ready";
      replayEntries = history;
      replayError = "";
      if (selectedReplaySeq && !history.some((entry) => entry.seq === selectedReplaySeq)) {
        selectedReplaySeq = null;
      }
      renderReplay(appState.get().overviewData);
    } catch (error) {
      if (seq !== replaySeq) return;
      replayStatus = "error";
      replayError = String(error);
      replayEntries = [];
      selectedReplaySeq = null;
      renderReplay(appState.get().overviewData);
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

      void refreshReplay(overview.session_id ?? appState.get().sessionId);

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
      void refreshReplay(appState.get().sessionId);
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

  function renderReplay(overview: InvestigationOverviewView | null): void {
    replaySection.body.innerHTML = "";

    const summary = replayStateSummary(replayEntries);
    const stats = document.createElement("div");
    stats.className = "overview-stats";
    stats.append(
      sectionCard("Entries", String(replayEntries.length)),
      sectionCard("Continuity", summary.continuity),
      sectionCard("Failure State", summary.failure),
      sectionCard("Recovery", summary.recovery),
    );
    replaySection.body.appendChild(stats);

    if (replayStatus === "loading") {
      const loading = document.createElement("div");
      loading.className = "overview-empty";
      loading.textContent = "Loading curated replay...";
      replaySection.body.appendChild(loading);
      return;
    }

    if (replayStatus === "error") {
      const error = document.createElement("div");
      error.className = "overview-empty";
      error.textContent = `Replay unavailable: ${replayError}`;
      replaySection.body.appendChild(error);
      return;
    }

    const curated = replayEntries
      .filter(isReplayHighlightable)
      .slice(-14)
      .reverse();

    replaySection.body.appendChild(
      createCardList(
        curated,
        (entry) => {
          const card = document.createElement("div");
          card.className = "overview-card";
          if (selectedReplaySeq === entry.seq) {
            card.style.outline = "1px solid var(--accent, #6ca0ff)";
          }

          const top = document.createElement("div");
          top.className = "overview-card-top";

          const title = document.createElement("div");
          title.className = "overview-card-title";
          title.textContent = `${entry.role.replace(/-/g, " ")} #${entry.seq}`;

          const badge = document.createElement("button");
          badge.className = "overview-pill";
          badge.textContent = "Focus";
          badge.type = "button";
          badge.style.cursor = "pointer";
          badge.addEventListener("click", () => focusReplay(entry.seq));

          top.append(title, badge);
          card.appendChild(top);

          const bodyEl = document.createElement("div");
          bodyEl.className = "overview-card-body";
          bodyEl.textContent = truncate(entry.content, 260);
          card.appendChild(bodyEl);

          const meta = document.createElement("div");
          meta.className = "overview-card-meta";
          const fragments = [formatTimestamp(entry.timestamp)];
          if (entry.step_number) fragments.push(`step ${entry.step_number}`);
          if (entry.tool_name) fragments.push(entry.tool_name);
          meta.textContent = fragments.join(" • ");
          card.appendChild(meta);

          return card;
        },
        overview
          ? "No curated replay entries yet."
          : "Open a session to view replay highlights.",
      ),
    );
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
      sectionCard("Outstanding Gaps", String(overview.snapshot.outstanding_gap_count)),
      sectionCard("Candidate Actions", String(overview.snapshot.candidate_action_count)),
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

  function renderGap(gap: OverviewGapView): HTMLElement {
    const item = document.createElement("div");
    item.className = "overview-card";
    item.id = `overview-gap-${gap.gap_id}`;

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
      const linkWrap = document.createElement("div");
      linkWrap.className = "overview-card-meta";
      linkWrap.textContent = "Evidence links:";
      const chips = document.createElement("div");
      chips.style.display = "flex";
      chips.style.flexWrap = "wrap";
      chips.style.gap = "6px";
      for (const actionId of gap.related_action_ids) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "overview-pill";
        chip.style.cursor = "pointer";
        chip.textContent = `action:${truncate(actionId, 20)}`;
        chip.addEventListener("click", () => {
          document
            .getElementById(`overview-action-${actionId}`)
            ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
        chips.appendChild(chip);
      }
      item.append(linkWrap, chips);
    }

    return item;
  }

  function renderAction(action: OverviewActionView): HTMLElement {
    const item = document.createElement("div");
    item.className = "overview-card";
    item.id = `overview-action-${action.action_id}`;

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

      const chips = document.createElement("div");
      chips.style.display = "flex";
      chips.style.flexWrap = "wrap";
      chips.style.gap = "6px";
      for (const gapId of action.evidence_gap_refs) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "overview-pill";
        chip.style.cursor = "pointer";
        chip.textContent = `gap:${truncate(gapId, 20)}`;
        chip.addEventListener("click", () => {
          document
            .getElementById(`overview-gap-${gapId}`)
            ?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        });
        chips.appendChild(chip);
      }
      item.appendChild(chips);
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
    meta.textContent = `${formatTimestamp(revelation.occurred_at)} • ${revelation.provenance.source}${revelation.provenance.step_index ? ` • step ${revelation.provenance.step_index}` : ""}`;
    item.appendChild(meta);

    const refs = parseRevelationRefs(revelation);
    const evidenceLinks = renderEvidenceLinks(refs, "Revelation");
    if (evidenceLinks) {
      item.appendChild(evidenceLinks);
    }

    return item;
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
      documentStatusEl.textContent = "Select a wiki page to inspect the underlying document.";
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

    header.innerHTML = "";
    const heading = document.createElement("div");
    heading.className = "overview-heading";
    heading.textContent = "Curated Investigation Replay";
    header.appendChild(heading);

    renderAlerts();
    renderReplay(overview);
    renderSnapshot(overview, overview?.focus_questions ?? []);

    gapsSection.body.innerHTML = "";
    gapsSection.body.appendChild(
      createCardList(
        overview?.outstanding_gaps ?? [],
        (gap) => renderGap(gap),
        "No outstanding gaps right now.",
      ),
    );

    actionsSection.body.innerHTML = "";
    actionsSection.body.appendChild(
      createCardList(
        overview?.candidate_actions ?? [],
        (action) => renderAction(action),
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
      state.overviewSelectedWikiPath !== lastOverviewSelectedWikiPath;

    lastOverviewData = state.overviewData;
    lastOverviewStatus = state.overviewStatus;
    lastOverviewError = state.overviewError;
    lastOverviewSelectedWikiPath = state.overviewSelectedWikiPath;

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
    replayStatus = "idle";
    replayEntries = [];
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

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}…`;
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
