import { appState } from "../state/store";
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

  tabs.append(overviewTab, graphTab);
  pane.append(tabs, content);

  updateActiveTab(appState.get().investigationViewTab);

  return pane;
}
