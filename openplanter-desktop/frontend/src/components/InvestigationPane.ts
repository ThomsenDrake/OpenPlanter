import { appState } from "../state/store";
import {
  primeGraphSessionBaseline,
  resetGraphSessionState,
} from "../graph/sessionBaseline";
import { OPEN_WIKI_DRAWER_EVENT, type OpenWikiDrawerDetail } from "../wiki/drawerEvents";
import { createGraphPane } from "./GraphPane";
import { createOverviewPane } from "./OverviewPane";

export function createInvestigationPane(): HTMLElement {
  const pane = document.createElement("div");
  pane.className = "investigation-pane";

  const tabs = document.createElement("div");
  tabs.className = "investigation-tabs";

  const overviewTab = document.createElement("button");
  overviewTab.className = "investigation-tab";
  overviewTab.textContent = "Overview";

  const graphTab = document.createElement("button");
  graphTab.className = "investigation-tab";
  graphTab.textContent = "Graph";

  const content = document.createElement("div");
  content.className = "investigation-content";

  const overviewPane = createOverviewPane();
  content.appendChild(overviewPane);

  let graphPane: HTMLElement | null = null;
  let activeTab = "";
  let pendingWikiRedispatch: number | null = null;

  function ensureGraphPane(): HTMLElement {
    if (!graphPane) {
      graphPane = createGraphPane();
      graphPane.style.display = "none";
      content.appendChild(graphPane);
    }
    return graphPane;
  }

  function updateActiveTab(tab: "overview" | "graph"): void {
    if (tab === activeTab) {
      return;
    }
    activeTab = tab;

    overviewTab.classList.toggle("active", tab === "overview");
    graphTab.classList.toggle("active", tab === "graph");

    overviewPane.style.display = tab === "overview" ? "flex" : "none";
    if (tab === "graph") {
      const graph = ensureGraphPane();
      graph.style.display = "flex";
    } else if (graphPane) {
      graphPane.style.display = "none";
    }

    window.dispatchEvent(
      new CustomEvent("investigation-tab-changed", { detail: { tab } }),
    );
  }

  overviewTab.addEventListener("click", () => {
    appState.update((state) => ({
      ...state,
      investigationViewTab: "overview",
    }));
  });
  graphTab.addEventListener("click", () => {
    appState.update((state) => ({
      ...state,
      investigationViewTab: "graph",
    }));
  });

  appState.subscribe((state) => {
    updateActiveTab(state.investigationViewTab);
  });

  window.addEventListener("session-changed", ((e: CustomEvent<{ isNew: boolean }>) => {
    if (graphPane) {
      return;
    }

    resetGraphSessionState(e.detail?.isNew ?? false);
    void primeGraphSessionBaseline();
  }) as EventListener);

  window.addEventListener(OPEN_WIKI_DRAWER_EVENT, ((e: CustomEvent<OpenWikiDrawerDetail>) => {
    const detail = e.detail;
    if (!detail) return;
    if (pendingWikiRedispatch != null) {
      window.clearTimeout(pendingWikiRedispatch);
      pendingWikiRedispatch = null;
    }
    // Capture this before switching tabs. The state update below synchronously mounts the
    // graph pane via the store subscription, but listeners added during the current dispatch
    // will not observe this event.
    const needsRedispatch = !graphPane;

    if (appState.get().investigationViewTab !== "graph") {
      appState.update((state) => ({
        ...state,
        investigationViewTab: "graph",
      }));
    }

    if (needsRedispatch) {
      pendingWikiRedispatch = window.setTimeout(() => {
        pendingWikiRedispatch = null;
        window.dispatchEvent(
          new CustomEvent<OpenWikiDrawerDetail>(OPEN_WIKI_DRAWER_EVENT, { detail }),
        );
      }, 0);
    }
  }) as EventListener);

  tabs.append(overviewTab, graphTab);
  pane.append(tabs, content);

  updateActiveTab(appState.get().investigationViewTab);

  return pane;
}
