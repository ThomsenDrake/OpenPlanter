// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sessionBaselineMocks = vi.hoisted(() => ({
  primeGraphSessionBaseline: vi.fn(async () => {}),
  resetGraphSessionState: vi.fn(),
}));

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

vi.mock("../graph/sessionBaseline", () => sessionBaselineMocks);

import { appState } from "../state/store";
import { OPEN_WIKI_DRAWER_EVENT } from "../wiki/drawerEvents";
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
    sessionBaselineMocks.primeGraphSessionBaseline.mockClear();
    sessionBaselineMocks.resetGraphSessionState.mockClear();
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

  it("primes the graph session baseline before the graph is mounted", () => {
    const pane = createInvestigationPane();
    document.body.appendChild(pane);

    window.dispatchEvent(new CustomEvent("session-changed", { detail: { isNew: true } }));

    expect(sessionBaselineMocks.resetGraphSessionState).toHaveBeenCalledWith(true);
    expect(sessionBaselineMocks.primeGraphSessionBaseline).toHaveBeenCalledTimes(1);
  });

  it("defers baseline priming to the mounted graph pane once it exists", () => {
    const pane = createInvestigationPane();
    document.body.appendChild(pane);

    const graphTab = Array.from(
      pane.querySelectorAll(".investigation-tab"),
    ).find((button) => button.textContent === "Graph") as HTMLButtonElement;
    graphTab.click();

    sessionBaselineMocks.primeGraphSessionBaseline.mockClear();
    sessionBaselineMocks.resetGraphSessionState.mockClear();

    window.dispatchEvent(new CustomEvent("session-changed", { detail: { isNew: false } }));

    expect(sessionBaselineMocks.resetGraphSessionState).not.toHaveBeenCalled();
    expect(sessionBaselineMocks.primeGraphSessionBaseline).not.toHaveBeenCalled();
  });

  it("re-dispatches wiki drawer events after lazy-mounting the graph pane", async () => {
    const pane = createInvestigationPane();
    document.body.appendChild(pane);
    const timerSpy = vi.spyOn(window, "setTimeout");

    window.dispatchEvent(new CustomEvent(OPEN_WIKI_DRAWER_EVENT, {
      detail: {
        wikiPath: "wiki/acme.md",
        source: "chat",
      },
    }));

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(appState.get().investigationViewTab).toBe("graph");
    expect(pane.querySelector(".graph-pane")).not.toBeNull();
    expect(timerSpy).toHaveBeenCalledTimes(1);
    timerSpy.mockRestore();
  });
});
