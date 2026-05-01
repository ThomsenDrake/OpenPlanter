// @vitest-environment happy-dom
import { beforeAll, beforeEach, afterAll, describe, expect, it, vi } from "vitest";
import type { GraphData } from "../api/types";
import { OPEN_WIKI_DRAWER_EVENT } from "../wiki/drawerEvents";

const mocks = vi.hoisted(() => ({
  getGraphData: vi.fn(),
  readWikiFile: vi.fn(),
  initGraph: vi.fn(),
  updateGraph: vi.fn(),
  focusNode: vi.fn(),
  bindInteractions: vi.fn(),
}));

vi.mock("../api/invoke", () => ({
  getGraphData: mocks.getGraphData,
  readWikiFile: mocks.readWikiFile,
}));

vi.mock("../graph/cytoGraph", () => ({
  initGraph: mocks.initGraph,
  updateGraph: mocks.updateGraph,
  destroyGraph: vi.fn(),
  fitView: vi.fn(),
  focusNode: mocks.focusNode,
  setLayout: vi.fn(),
  getCurrentLayout: vi.fn(() => "fcose"),
  filterByCategory: vi.fn(),
  filterByTier: vi.fn(),
  filterBySearch: vi.fn(() => []),
  filterBySession: vi.fn(() => 0),
  fitSearchMatches: vi.fn(),
  getCategories: vi.fn(() => ["contracts"]),
  getNodeIds: vi.fn(() => new Set(["usaspending"])),
}));

vi.mock("../graph/interaction", () => ({
  bindInteractions: mocks.bindInteractions,
}));

import { createGraphPane } from "./GraphPane";

const GRAPH_DATA: GraphData = {
  nodes: [
    {
      id: "usaspending",
      label: "USASpending.gov",
      category: "contracts",
      path: "wiki/contracts/usaspending.md",
      node_type: "source",
    },
  ],
  edges: [],
};

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("createGraphPane wiki drawer events", () => {
  let pane: HTMLElement;

  beforeAll(async () => {
    vi.useFakeTimers();
    mocks.getGraphData.mockResolvedValue(GRAPH_DATA);
    mocks.readWikiFile.mockResolvedValue("# Initial\n\nLoaded.");

    pane = createGraphPane();
    document.body.appendChild(pane);

    await vi.advanceTimersByTimeAsync(100);
    await vi.waitFor(() => {
      expect(mocks.initGraph).toHaveBeenCalled();
    });
  });

  beforeEach(() => {
    mocks.readWikiFile.mockReset();
    mocks.focusNode.mockReset();
    mocks.readWikiFile.mockResolvedValue("# Loaded\n\nDrawer content.");
  });

  afterAll(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("opens the drawer from window events and focuses the matching node", async () => {
    window.dispatchEvent(new CustomEvent(OPEN_WIKI_DRAWER_EVENT, {
      detail: {
        wikiPath: "wiki/contracts/usaspending.md",
        source: "chat",
        requestedTitle: "USASpending.gov",
      },
    }));

    await vi.waitFor(() => {
      expect(mocks.readWikiFile).toHaveBeenCalledWith("wiki/contracts/usaspending.md");
    });

    expect(mocks.focusNode).toHaveBeenCalledWith("usaspending");
    await vi.waitFor(() => {
      expect(pane.querySelector(".graph-source-drawer.visible")).not.toBeNull();
      expect(pane.querySelector(".graph-source-drawer-title")?.textContent).toBe("USASpending.gov");
      expect(pane.querySelector(".graph-source-drawer-body")?.textContent).toContain("Drawer content.");
    });
  });

  it("keeps the latest drawer content when requests resolve out of order", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    mocks.readWikiFile
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);

    window.dispatchEvent(new CustomEvent(OPEN_WIKI_DRAWER_EVENT, {
      detail: {
        wikiPath: "wiki/contracts/usaspending.md",
        source: "chat",
        requestedTitle: "First title",
      },
    }));
    window.dispatchEvent(new CustomEvent(OPEN_WIKI_DRAWER_EVENT, {
      detail: {
        wikiPath: "wiki/contracts/usaspending.md",
        source: "chat",
        requestedTitle: "Second title",
      },
    }));

    second.resolve("# Second\n\nNewest content.");
    await vi.waitFor(() => {
      expect(pane.querySelector(".graph-source-drawer-body")?.textContent).toContain("Newest content.");
    });

    first.resolve("# First\n\nStale content.");
    await Promise.resolve();

    expect(pane.querySelector(".graph-source-drawer-body")?.textContent).toContain("Newest content.");
    expect(pane.querySelector(".graph-source-drawer-body")?.textContent).not.toContain("Stale content.");
  });

  it("keeps the drawer open and shows an inline error when wiki loading fails", async () => {
    mocks.readWikiFile.mockRejectedValue(new Error("missing file"));

    window.dispatchEvent(new CustomEvent(OPEN_WIKI_DRAWER_EVENT, {
      detail: {
        wikiPath: "wiki/contracts/usaspending.md",
        source: "chat",
        requestedTitle: "Missing doc",
      },
    }));

    await vi.waitFor(() => {
      expect(pane.querySelector(".graph-source-drawer.visible")).not.toBeNull();
      expect(pane.querySelector(".graph-source-drawer-body")?.textContent).toContain("Failed to load");
      expect(pane.querySelector(".graph-source-drawer-body")?.textContent).toContain("missing file");
    });
  });

  it("adds stable heading ids and hides generated to-do anchor markers", async () => {
    mocks.readWikiFile.mockResolvedValue([
      "# Investigation Home: acme",
      "",
      "> Auto-generated from `investigation_state.json`.",
      "",
      "## Open To-Dos",
      "- [Call bank records team](#todo-todo_2)",
      "- [Wire records](../docs/wire%20transfer%20records%28v2%29.md)",
      "",
      "## To-Do Details",
      '<a id="todo-todo_2"></a>',
      "### TODO todo_2",
      "- **Status**: `open`",
    ].join("\n"));

    window.dispatchEvent(new CustomEvent(OPEN_WIKI_DRAWER_EVENT, {
      detail: {
        wikiPath: "wiki/investigations/acme.md",
        source: "chat",
        requestedTitle: "Generated Home",
      },
    }));

    await vi.waitFor(() => {
      expect(mocks.readWikiFile).toHaveBeenCalledWith("wiki/investigations/acme.md");
    });

    const drawerBody = pane.querySelector(".graph-source-drawer-body");
    await vi.waitFor(() => {
      expect(drawerBody?.textContent).toContain("Call bank records team");
    });
    const todoHeading = drawerBody?.querySelector<HTMLElement>('[id="todo-todo_2"]');
    expect(todoHeading?.textContent).toBe("TODO todo_2");
    expect(drawerBody?.textContent).not.toContain('<a id="todo-todo_2"></a>');

    const wireLink = Array.from(drawerBody?.querySelectorAll("a") ?? []).find(
      (anchor) => anchor.textContent === "Wire records",
    ) as HTMLAnchorElement | undefined;
    expect(wireLink?.getAttribute("href")).toBe(
      "../docs/wire%20transfer%20records%28v2%29.md",
    );
    wireLink!.click();

    await vi.waitFor(() => {
      expect(mocks.readWikiFile).toHaveBeenCalledWith(
        "wiki/docs/wire transfer records(v2).md",
      );
    });
  });
});
