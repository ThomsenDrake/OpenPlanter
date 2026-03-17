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

  const nav = document.createElement("aside");
  nav.className = "overview-nav";

  const snapshotSection = createSection("Investigation Snapshot");
  const gapsSection = createSection("Outstanding Gaps");
  const actionsSection = createSection("Candidate Actions");
  const revelationsSection = createSection("Recent Revelations");
  const detailSection = createSection("Wiki Drill-down");
  detailSection.body.classList.add("overview-document");

  const navTitle = document.createElement("div");
  navTitle.className = "overview-nav-title";
  navTitle.textContent = "Wiki Navigation";

  const navBody = document.createElement("div");
  navBody.className = "overview-nav-body";

  nav.append(navTitle, navBody);
  main.append(
    snapshotSection.section,
    gapsSection.section,
    actionsSection.section,
    revelationsSection.section,
    detailSection.section,
  );
  body.append(main, nav);
  pane.append(header, alerts, body);

  let refreshTimer: number | null = null;
  let refreshSeq = 0;
  let docSeq = 0;
  let documentStatus: DocumentStatus = "idle";
  let documentHtml = "";
  let documentTitle = "Wiki document";
  let documentError = "";

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
      render();
      interceptDocumentLinks();
    } catch (error) {
      if (seq !== docSeq) return;
      documentStatus = "error";
      documentHtml = "";
      documentError = String(error);
      render();
    }
  }

  function setSelectedPath(path: string): void {
    appState.update((state) => ({
      ...state,
      overviewSelectedWikiPath: path,
    }));
    void loadDocument(path);
  }

  function interceptDocumentLinks(): void {
    detailSection.body.querySelectorAll("a").forEach((anchor) => {
      const href = anchor.getAttribute("href");
      if (!href || !href.endsWith(".md")) return;
      if (href.startsWith("http://") || href.startsWith("https://")) return;
      anchor.addEventListener("click", (event) => {
        event.preventDefault();
        const resolvedPath = href.startsWith("wiki/") ? href : `wiki/${href}`;
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

      void loadDocument(selectedPath, overview);
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

  function renderNav(overview: InvestigationOverviewView | null): void {
    navBody.innerHTML = "";
    const selectedPath = appState.get().overviewSelectedWikiPath;

    if (!overview || overview.wiki_nav.sources.length === 0) {
      const empty = document.createElement("div");
      empty.className = "overview-empty";
      empty.textContent = "No wiki sources available yet.";
      navBody.appendChild(empty);
      return;
    }

    let currentCategory = "";
    for (const source of overview.wiki_nav.sources) {
      if (source.category !== currentCategory) {
        currentCategory = source.category;
        const category = document.createElement("div");
        category.className = "overview-nav-category";
        category.textContent = currentCategory;
        navBody.appendChild(category);
      }

      const sourceWrap = document.createElement("div");
      sourceWrap.className = "overview-nav-source-block";

      const sourceButton = document.createElement("button");
      sourceButton.className = "overview-nav-source";
      if (selectedPath === source.file_path) {
        sourceButton.classList.add("active");
      }
      sourceButton.textContent = source.title;
      sourceButton.addEventListener("click", () => setSelectedPath(source.file_path));
      sourceWrap.appendChild(sourceButton);

      if (source.sections.length > 0) {
        const sections = document.createElement("div");
        sections.className = "overview-nav-sections";
        for (const section of source.sections) {
          const sectionButton = document.createElement("button");
          sectionButton.className = "overview-nav-section";
          sectionButton.textContent = section.title;
          sectionButton.addEventListener("click", () => setSelectedPath(source.file_path));
          sections.appendChild(sectionButton);

          if (section.facts.length > 0) {
            const facts = document.createElement("div");
            facts.className = "overview-nav-facts";
            for (const fact of section.facts) {
              const factButton = document.createElement("button");
              factButton.className = "overview-nav-fact";
              factButton.textContent = fact.label;
              factButton.addEventListener("click", () => setSelectedPath(source.file_path));
              facts.appendChild(factButton);
            }
            sections.appendChild(facts);
          }
        }
        sourceWrap.appendChild(sections);
      }

      navBody.appendChild(sourceWrap);
    }
  }

  function renderDocument(overview: InvestigationOverviewView | null): void {
    detailSection.body.innerHTML = "";

    const title = document.createElement("div");
    title.className = "overview-document-title";
    title.textContent = documentTitle;
    detailSection.body.appendChild(title);

    if (!overview || !appState.get().overviewSelectedWikiPath) {
      const empty = document.createElement("div");
      empty.className = "overview-empty";
      empty.textContent = "Select a wiki source to inspect the underlying document.";
      detailSection.body.appendChild(empty);
      return;
    }

    if (documentStatus === "loading") {
      const loading = document.createElement("div");
      loading.className = "overview-empty";
      loading.textContent = "Loading wiki document...";
      detailSection.body.appendChild(loading);
      return;
    }

    if (documentStatus === "error") {
      const error = document.createElement("div");
      error.className = "overview-empty";
      error.textContent = `Failed to load wiki document: ${documentError}`;
      detailSection.body.appendChild(error);
      return;
    }

    if (documentStatus === "ready") {
      const content = document.createElement("div");
      content.className = "overview-document-body rendered";
      content.innerHTML = documentHtml;
      detailSection.body.appendChild(content);
      return;
    }

    const idle = document.createElement("div");
    idle.className = "overview-empty";
    idle.textContent = "No wiki document selected.";
    detailSection.body.appendChild(idle);
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

    renderNav(overview);
    renderDocument(overview);
  }

  appState.subscribe(() => {
    render();
  });

  window.addEventListener("session-changed", () => {
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
