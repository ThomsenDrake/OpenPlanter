// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./OverviewPane", () => ({
  createOverviewPane: () => {
    const el = document.createElement("div");
    el.className = "overview-pane";
    return el;
  },
}));

vi.mock("./GraphPane", () => ({
  createGraphPane: () => {
    const el = document.createElement("div");
    el.className = "graph-pane";
    return el;
  },
}));

import { appState } from "../state/store";
import { createInvestigationPane } from "./InvestigationPane";

describe("createInvestigationPane", () => {
  const originalState = appState.get();

  beforeEach(() => {
    appState.set({
      ...originalState,
      investigationViewTab: "overview",
    });
  });

  afterEach(() => {
    appState.set(originalState);
    document.body.innerHTML = "";
  });

  it("shows the overview tab by default and lazy-mounts the graph", () => {
    const pane = createInvestigationPane();
    document.body.appendChild(pane);

    expect(pane.querySelector(".overview-pane")).not.toBeNull();
    expect(pane.querySelector(".graph-pane")).toBeNull();
    expect(
      pane.querySelector(".investigation-tab.active")?.textContent,
    ).toBe("Overview");
  });

  it("mounts the graph pane when the graph tab is selected", () => {
    const pane = createInvestigationPane();
    document.body.appendChild(pane);

    const graphTab = Array.from(
      pane.querySelectorAll(".investigation-tab"),
    ).find((button) => button.textContent === "Graph") as HTMLButtonElement;
    graphTab.click();

    expect(appState.get().investigationViewTab).toBe("graph");
    expect(pane.querySelector(".graph-pane")).not.toBeNull();
    expect(
      pane.querySelector(".investigation-tab.active")?.textContent,
    ).toBe("Graph");
  });
});
