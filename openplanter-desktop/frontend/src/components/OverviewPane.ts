import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

import { getInvestigationOverview, readWikiFile } from "../api/invoke";
import type {
  InvestigationOverviewView,
  OverviewActionView,
  OverviewGapView,
  OverviewQuestionView,
  OverviewRevelationView,
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
  let documentStatus: DocumentStatus = "idle";
  let documentHtml = "";
  let documentTitle = "Wiki document";
  let documentError = "";
  let loadedDocumentPath: string | null = null;

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

    return item;
  }

  function renderAction(action: OverviewActionView): HTMLElement {
    const item = document.createElement("div");
    item.className = "overview-card";

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
    heading.textContent = "Current Investigation";
    header.appendChild(heading);

    renderAlerts();
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
