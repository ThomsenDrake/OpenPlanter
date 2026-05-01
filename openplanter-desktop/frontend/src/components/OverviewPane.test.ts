// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { __clearHandlers, __setHandler } from "../__mocks__/tauri";

vi.mock("@tauri-apps/api/core", async () => {
  const mock = await import("../__mocks__/tauri");
  return { invoke: mock.invoke };
});

import type { InvestigationOverviewView } from "../api/types";
import { appState } from "../state/store";
import {
  OPEN_WIKI_DRAWER_EVENT,
  type OpenWikiDrawerDetail,
} from "../wiki/drawerEvents";
import { createOverviewPane } from "./OverviewPane";

function makeOverview(
  overrides: Partial<InvestigationOverviewView> = {},
): InvestigationOverviewView {
  return {
    session_id: "session-1",
    generated_at: "2026-03-17T12:00:00Z",
    snapshot: {
      focus_question_count: 1,
      supported_count: 0,
      contested_count: 1,
      outstanding_gap_count: 2,
      candidate_action_count: 1,
    },
    focus_questions: [
      {
        id: "q1",
        text: "Who controls Acme Corp?",
        priority: "high",
      },
    ],
    outstanding_gaps: [
      {
        gap_id: "gap:claim:c1:missing_evidence",
        label: "Claim c1 needs more evidence",
        status: "open",
        kind: "missing_evidence",
        scope: "claim",
        related_action_ids: ["ca_1"],
      },
    ],
    candidate_actions: [
      {
        action_id: "ca_1",
        label: "Verify claim c1",
        rationale: "claim_requires_verification",
        evidence_gap_refs: ["gap:claim:c1:missing_evidence"],
        priority: "high",
      },
    ],
    recent_revelations: [
      {
        revelation_id: "rev-1",
        occurred_at: "2026-03-17T12:05:00Z",
        title: "Acme and PAC filings overlap",
        summary:
          "The latest filing pull corroborates that Acme Corp and PAC Fund Alpha share an address across multiple records.",
        provenance: {
          source: "agent_step",
          step_index: 4,
        },
      },
    ],
    wiki_nav: {
      sources: [
        {
          source_id: "acme",
          title: "Acme Corp",
          category: "corporate",
          file_path: "wiki/acme.md",
          sections: [
            {
              section_id: "acme::summary",
              title: "Summary",
              facts: [{ fact_id: "acme::summary::jurisdiction", label: "Jurisdiction" }],
            },
          ],
        },
      ],
    },
    warnings: [],
    ...overrides,
  };
}

describe("createOverviewPane", () => {
  const originalState = appState.get();

  beforeEach(() => {
    appState.set({
      ...originalState,
      overviewStatus: "idle",
      overviewData: null,
      overviewError: null,
      overviewSelectedWikiPath: null,
    });
    (HTMLElement.prototype as { scrollIntoView?: () => void }).scrollIntoView = () => {};
    __setHandler("read_wiki_file", ({ path }: { path: string }) => `# ${path}\n\nMock wiki document`);
    __setHandler("get_session_history", () => []);
  });

  afterEach(() => {
    __clearHandlers();
    appState.set(originalState);
    document.body.innerHTML = "";
  });

  it("renders overview data after the initial load", async () => {
    __setHandler("get_investigation_overview", () => makeOverview());

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Investigation Home");
      expect(pane.textContent).toContain("Current Conclusions & Proofs");
      expect(pane.textContent).toContain("Who controls Acme Corp?");
      expect(pane.textContent).toContain("Claim c1 needs more evidence");
      expect(pane.textContent).toContain("Acme and PAC filings overlap");
      expect(pane.querySelector(".overview-document-select")).not.toBeNull();
      expect(pane.querySelector(".overview-nav")).toBeNull();
      expect(pane.textContent).toContain("Acme Corp");
    });
  });

  it("defaults document view to investigation home with open to-dos", async () => {
    const readPaths: string[] = [];
    __setHandler("read_wiki_file", ({ path }: { path: string }) => {
      readPaths.push(path);
      return `# ${path}\n\nMock wiki document`;
    });
    __setHandler("get_investigation_overview", () => makeOverview());

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Current Status");
      expect(pane.textContent).toContain("Current Conclusions & Proofs");
      expect(pane.textContent).toContain("Open Questions");
      expect(pane.textContent).toContain("Documents / Evidence Needed");
      expect(pane.textContent).toContain("Open To-dos");
      expect(pane.textContent).toContain("Verify claim c1");
    });
    expect(appState.get().overviewSelectedWikiPath).toBe("openplanter://investigation-home");
    expect(readPaths).toEqual([]);
  });

  it("encodes wiki source links from investigation home markdown", async () => {
    const readPaths: string[] = [];
    __setHandler("read_wiki_file", ({ path }: { path: string }) => {
      readPaths.push(path);
      return `# ${path}\n\nMock wiki document`;
    });
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        focus_questions: [
          {
            id: "q1",
            text: "What is in the Q1 notes draft?",
            priority: "high",
          },
        ],
        wiki_nav: {
          sources: [
            {
              source_id: "q1-notes",
              title: "Q1 notes draft",
              category: "records",
              file_path: "wiki/Q1 notes (draft).md",
              sections: [],
            },
          ],
        },
      }),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Needed documents");
      expect(pane.textContent).toContain("Q1 notes draft");
    });

    const sourceLink = Array.from(pane.querySelectorAll("a")).find(
      (anchor) => anchor.textContent === "Q1 notes draft",
    ) as HTMLAnchorElement | undefined;
    expect(sourceLink).toBeDefined();
    expect(sourceLink?.getAttribute("href")).toBe("wiki/Q1%20notes%20%28draft%29.md");

    sourceLink!.click();

    await vi.waitFor(() => {
      expect(appState.get().overviewSelectedWikiPath).toBe("wiki/Q1 notes (draft).md");
      expect(readPaths).toEqual(["wiki/Q1 notes (draft).md"]);
    });
  });

  it("preserves literal percent-hex wiki source filenames from investigation home", async () => {
    const readPaths: string[] = [];
    __setHandler("read_wiki_file", ({ path }: { path: string }) => {
      readPaths.push(path);
      return `# ${path}\n\nMock wiki document`;
    });
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        focus_questions: [
          {
            id: "q1",
            text: "What revenue growth records are available?",
            priority: "high",
          },
        ],
        wiki_nav: {
          sources: [
            {
              source_id: "revenue-growth",
              title: "Revenue growth",
              category: "records",
              file_path: "wiki/revenue%20growth.md",
              sections: [],
            },
          ],
        },
      }),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Revenue growth");
    });

    const sourceLink = Array.from(pane.querySelectorAll("a")).find(
      (anchor) => anchor.textContent === "Revenue growth",
    ) as HTMLAnchorElement | undefined;
    expect(sourceLink).toBeDefined();
    expect(sourceLink?.getAttribute("href")).toBe("wiki/revenue%2520growth.md");

    sourceLink!.click();

    await vi.waitFor(() => {
      expect(appState.get().overviewSelectedWikiPath).toBe("wiki/revenue%20growth.md");
      expect(readPaths).toEqual(["wiki/revenue%20growth.md"]);
    });
  });

  it("preserves literal percent-hex links from manual investigation wiki pages", async () => {
    const manualPath = "wiki/investigations/manual.md";
    const literalTargetPath = "wiki/revenue%20growth.md";
    const readPaths: string[] = [];
    appState.update((state) => ({
      ...state,
      overviewSelectedWikiPath: manualPath,
    }));
    __setHandler("read_wiki_file", ({ path }: { path: string }) => {
      readPaths.push(path);
      if (path !== manualPath) {
        return `# ${path}`;
      }
      return [
        "# Manual Investigation Notes",
        "",
        "- [Revenue Growth](../revenue%20growth.md)",
      ].join("\n");
    });
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        wiki_nav: {
          sources: [
            {
              source_id: "manual",
              title: "Manual Investigation Notes",
              category: "investigations",
              file_path: manualPath,
              sections: [],
            },
          ],
        },
      }),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Revenue Growth");
    });

    const revenueLink = Array.from(pane.querySelectorAll("a")).find(
      (anchor) => anchor.textContent === "Revenue Growth",
    ) as HTMLAnchorElement | undefined;
    expect(revenueLink?.getAttribute("href")).toBe("../revenue%20growth.md");
    revenueLink!.click();

    await vi.waitFor(() => {
      expect(appState.get().overviewSelectedWikiPath).toBe(literalTargetPath);
      expect(readPaths).toEqual([manualPath, literalTargetPath]);
    });
  });

  it("adds markdown heading ids for generated to-do fragment links", async () => {
    const generatedPath = "wiki/investigations/acme.md";
    const decodedTargetPath = "wiki/docs/wire transfer records(v2).md";
    const readPaths: string[] = [];
    appState.update((state) => ({
      ...state,
      overviewSelectedWikiPath: generatedPath,
    }));
    __setHandler("read_wiki_file", ({ path }: { path: string }) => {
      readPaths.push(path);
      if (path !== generatedPath) {
        return `# ${path}`;
      }
      return [
        "# Investigation Home: acme",
        "",
        "> Auto-generated from `investigation_state.json`.",
        "",
        "## Open To-Dos",
        "- [Call bank records team](#todo-todo_2)",
        "- [Punctuated task](#todo-todo)",
        "- [Wire records](../docs/wire%20transfer%20records%28v2%29.md)",
        "",
        "## To-Do Details",
        '<a id="todo-todo_2"></a>',
        "### TODO todo_2",
        "- **Status**: `open`",
        '<a id="todo-todo"></a>',
        "### TODO .todo",
        "- **Status**: `open`",
      ].join("\n");
    });
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        wiki_nav: {
          sources: [
            {
              source_id: "generated-home",
              title: "Generated Home",
              category: "investigation",
              file_path: generatedPath,
              sections: [],
            },
          ],
        },
      }),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Call bank records team");
    });

    const todoLink = Array.from(pane.querySelectorAll("a")).find(
      (anchor) => anchor.textContent === "Call bank records team",
    ) as HTMLAnchorElement | undefined;
    expect(todoLink?.getAttribute("href")).toBe("#todo-todo_2");
    const todoHeading = pane.querySelector<HTMLElement>('[id="todo-todo_2"]');
    expect(todoHeading?.textContent).toBe("TODO todo_2");
    expect(pane.textContent).not.toContain('<a id="todo-todo_2"></a>');
    const punctuatedLink = Array.from(pane.querySelectorAll("a")).find(
      (anchor) => anchor.textContent === "Punctuated task",
    ) as HTMLAnchorElement | undefined;
    expect(punctuatedLink?.getAttribute("href")).toBe("#todo-todo");
    const punctuatedHeading = pane.querySelector<HTMLElement>('[id="todo-todo"]');
    expect(punctuatedHeading?.textContent).toBe("TODO .todo");

    const wireLink = Array.from(pane.querySelectorAll("a")).find(
      (anchor) => anchor.textContent === "Wire records",
    ) as HTMLAnchorElement | undefined;
    expect(wireLink?.getAttribute("href")).toBe(
      "../docs/wire%20transfer%20records%28v2%29.md",
    );
    wireLink!.click();

    await vi.waitFor(() => {
      expect(appState.get().overviewSelectedWikiPath).toBe(decodedTargetPath);
      expect(readPaths).toEqual([generatedPath, decodedTargetPath]);
    });
  });

  it("links investigation home entries to overview cards and replay", async () => {
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        recent_revelations: [
          {
            revelation_id: "rev-linked",
            occurred_at: "2026-03-17T12:05:00Z",
            title: "Linked proof trail",
            summary: "This proof should link to a gap, action, and replay entry.",
            provenance: {
              source: "agent_step",
              replay_seq: 7,
              evidence_refs: ["gap:claim:c1:missing_evidence", "action:ca_1"],
            },
          },
        ],
      }),
    );
    __setHandler("get_session_history", () => [
      {
        seq: 7,
        timestamp: "2026-03-17T12:04:00Z",
        role: "assistant",
        content: "Replay evidence entry",
      },
    ]);

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Linked proof trail");
      expect(pane.textContent).toContain("Replay evidence entry");
    });

    const findLink = (prefix: string): HTMLAnchorElement => {
      const link = Array.from(pane.querySelectorAll("a")).find((anchor) =>
        anchor.getAttribute("href")?.startsWith(prefix),
      ) as HTMLAnchorElement | undefined;
      expect(link).toBeDefined();
      return link!;
    };

    findLink("openplanter://overview/action/").click();
    const actionCard = pane.querySelector('[data-action-id="ca_1"]') as HTMLElement | null;
    expect(actionCard?.style.outline).toContain("var(--accent)");

    findLink("openplanter://overview/gap/").click();
    const gapCard = pane.querySelector(
      '[data-gap-id="gap:claim:c1:missing_evidence"]',
    ) as HTMLElement | null;
    expect(gapCard?.style.outline).toContain("var(--accent)");

    findLink("openplanter://overview/replay/").click();
    await new Promise((resolve) => setTimeout(resolve, 0));
    const replayCard = pane.querySelector('[data-replay-seq="7"]') as HTMLElement | null;
    expect(replayCard?.style.outline).toContain("var(--accent)");
  });

  it("refreshes the overview when curator updates arrive", async () => {
    let callCount = 0;
    __setHandler("get_investigation_overview", () => {
      callCount += 1;
      return makeOverview({
        focus_questions: [
          {
            id: "q1",
            text: callCount === 1 ? "Who controls Acme Corp?" : "What ties Acme to PAC Fund Alpha?",
            priority: "high",
          },
        ],
        snapshot: {
          focus_question_count: 1,
          supported_count: 0,
          contested_count: 1,
          outstanding_gap_count: 2,
          candidate_action_count: 1,
        },
      });
    });

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Who controls Acme Corp?");
    });

    window.dispatchEvent(new CustomEvent("curator-done"));

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("What ties Acme to PAC Fund Alpha?");
    });
  });

  it("ignores stale overview responses that resolve out of order", async () => {
    let firstResolve: ((value: InvestigationOverviewView) => void) | null = null;
    let secondResolve: ((value: InvestigationOverviewView) => void) | null = null;
    let calls = 0;

    __setHandler("get_investigation_overview", () => {
      calls += 1;
      return new Promise<InvestigationOverviewView>((resolve) => {
        if (calls === 1) {
          firstResolve = resolve;
        } else {
          secondResolve = resolve;
        }
      });
    });

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    window.dispatchEvent(new CustomEvent("session-changed", { detail: { isNew: false } }));
    await vi.waitFor(() => {
      expect(calls).toBe(2);
    });

    expect(secondResolve).not.toBeNull();
    secondResolve!(
      makeOverview({
        focus_questions: [
          {
            id: "q2",
            text: "Fresh overview wins",
            priority: "critical",
          },
        ],
      }),
    );

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Fresh overview wins");
    });

    expect(firstResolve).not.toBeNull();
    firstResolve!(
      makeOverview({
        focus_questions: [
          {
            id: "q1",
            text: "Stale overview should be ignored",
            priority: "low",
          },
        ],
      }),
    );

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(pane.textContent).not.toContain("Stale overview should be ignored");
  });

  it("invalidates stale replay responses when the session changes", async () => {
    let sessionOneHistoryResolve: ((value: Array<{
      seq: number;
      timestamp: string;
      role: string;
      content: string;
    }>) => void) | null = null;

    __setHandler("get_investigation_overview", () =>
      makeOverview({
        session_id: "session-1",
      }),
    );
    __setHandler("get_session_history", ({ sessionId }: { sessionId: string }) => {
      if (sessionId === "session-1") {
        return new Promise((resolve) => {
          sessionOneHistoryResolve = resolve;
        });
      }
      return [];
    });

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(sessionOneHistoryResolve).not.toBeNull();
    });

    window.dispatchEvent(new CustomEvent("session-changed", { detail: { isNew: false } }));

    sessionOneHistoryResolve!([
      {
        seq: 1,
        timestamp: "2026-03-17T12:06:00Z",
        role: "assistant",
        content: "Stale replay from the previous session",
      },
    ]);

    await Promise.resolve();
    await Promise.resolve();

    expect(pane.textContent).not.toContain("Stale replay from the previous session");

    await new Promise((resolve) => setTimeout(resolve, 0));
    await Promise.resolve();
    await Promise.resolve();
  });

  it("keeps the selected wiki page stable across overview refreshes", async () => {
    let overviewCalls = 0;
    const readPaths: string[] = [];
    const wikiSources = [
      {
        source_id: "acme",
        title: "Acme Corp",
        category: "corporate",
        file_path: "wiki/acme.md",
        sections: [],
      },
      {
        source_id: "budget",
        title: "Budget Documents",
        category: "public-records",
        file_path: "wiki/budget.md",
        sections: [],
      },
    ];

    __setHandler("read_wiki_file", ({ path }: { path: string }) => {
      readPaths.push(path);
      return `# ${path}\n\nMock wiki document`;
    });

    __setHandler("get_investigation_overview", () => {
      overviewCalls += 1;
      return makeOverview({
        focus_questions: [
          {
            id: "q1",
            text:
              overviewCalls === 1
                ? "Who controls Acme Corp?"
                : "What changed in the refreshed overview?",
            priority: "high",
          },
        ],
        wiki_nav: {
          sources: wikiSources,
        },
      });
    });

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    const documentSelect = pane.querySelector(
      ".overview-document-select",
    ) as HTMLSelectElement;

    await vi.waitFor(() => {
      expect(documentSelect.options.length).toBe(3);
      expect(readPaths).toEqual([]);
    });

    documentSelect.value = "wiki/budget.md";
    documentSelect.dispatchEvent(new Event("change"));

    await vi.waitFor(() => {
      expect(appState.get().overviewSelectedWikiPath).toBe("wiki/budget.md");
      expect(pane.textContent).toContain("wiki/budget.md");
    });

    window.dispatchEvent(new CustomEvent("curator-done"));

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("What changed in the refreshed overview?");
    });

    expect(documentSelect.value).toBe("wiki/budget.md");
    expect(readPaths).toEqual(["wiki/budget.md"]);
  });

  it("keeps the wiki viewport mounted across unrelated app state updates", async () => {
    __setHandler("get_investigation_overview", () => makeOverview());

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    const viewport = pane.querySelector(
      ".overview-document-viewport",
    ) as HTMLDivElement;

    await vi.waitFor(() => {
      expect(viewport).not.toBeNull();
      expect(pane.textContent).toContain("Current Conclusions & Proofs");
    });

    viewport.scrollTop = 64;

    appState.update((state) => ({
      ...state,
      inputTokens: state.inputTokens + 10,
    }));

    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(pane.querySelector(".overview-document-viewport")).toBe(viewport);
    expect(viewport.scrollTop).toBe(64);
  });

  it("renders step zero replay entries as Step 0", async () => {
    __setHandler("get_investigation_overview", () => makeOverview());
    __setHandler("get_session_history", () => [
      {
        seq: 7,
        timestamp: "2026-03-17T12:04:00Z",
        role: "step-summary",
        content: "Initial summary",
        step_number: 0,
        step_model_preview: "Initial summary",
      },
    ]);

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Step 0");
    });
  });

  it("falls back to compact tool summaries when a step has no text preview", async () => {
    __setHandler("get_investigation_overview", () => makeOverview());
    __setHandler("get_session_history", () => [
      {
        seq: 7,
        timestamp: "2026-03-17T12:04:00Z",
        role: "step-summary",
        content: "",
        step_number: 7,
        step_tool_calls: [
          { name: "read_file", key_arg: "/src/main.ts", elapsed: 80 },
        ],
      },
      {
        seq: 8,
        timestamp: "2026-03-17T12:05:00Z",
        role: "step-summary",
        content: "",
        step_number: 8,
        step_tool_calls: [
          { name: "read_file", key_arg: "/src/main.ts", elapsed: 80 },
          { name: "run_shell", key_arg: "npm test", elapsed: 120 },
        ],
      },
      {
        seq: 9,
        timestamp: "2026-03-17T12:06:00Z",
        role: "step-summary",
        content: "",
        step_number: 9,
        step_tool_calls: [
          { name: "read_file", key_arg: "/src/main.ts", elapsed: 80 },
          { name: "run_shell", key_arg: "npm test", elapsed: 120 },
          { name: "web_search", key_arg: "trace bugs", elapsed: 250 },
        ],
      },
    ]);

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain('Ran read_file "/src/main.ts"');
      expect(pane.textContent).toContain(
        'Ran 2 tools: read_file "/src/main.ts"; run_shell "npm test"',
      );
      expect(pane.textContent).toContain(
        'Ran 3 tools: read_file "/src/main.ts"; run_shell "npm test"; +1 more',
      );
    });
  });

  it("uses replay line locators to focus the matching replay entry by file order", async () => {
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        recent_revelations: [
          {
            revelation_id: "openplanter.revelation|replay_line:1",
            occurred_at: "2026-03-17T12:05:00Z",
            title: "Line-based evidence",
            summary: "Should focus the first replay line even when seq differs.",
            provenance: {
              source: "agent_step",
              step_index: 0,
            },
          },
        ],
      }),
    );
    __setHandler("get_session_history", () => [
      {
        seq: 42,
        timestamp: "2026-03-17T12:04:00Z",
        role: "assistant",
        content: "First replay entry",
      },
      {
        seq: 99,
        timestamp: "2026-03-17T12:06:00Z",
        role: "assistant",
        content: "Second replay entry",
      },
    ]);

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Line-based evidence");
      expect(pane.textContent).toContain("First replay entry");
    });

    const lineChip = Array.from(pane.querySelectorAll("button")).find(
      (button) => button.textContent === "line 1",
    ) as HTMLButtonElement | undefined;
    expect(lineChip).toBeDefined();

    lineChip!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    const focused = pane.querySelector('[data-replay-seq="42"]') as HTMLElement | null;
    expect(focused).not.toBeNull();
    expect(focused?.style.outline).toContain("var(--accent)");
  });

  it("keeps a focused replay target visible even when it falls outside the default replay window", async () => {
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        recent_revelations: [
          {
            revelation_id: "openplanter.revelation|replay_seq:1",
            occurred_at: "2026-03-17T12:05:00Z",
            title: "Older replay anchor",
            summary: "This revelation anchors to the oldest replay entry.",
            provenance: {
              source: "agent_step",
              step_index: 1,
            },
          },
        ],
      }),
    );
    __setHandler("get_session_history", () =>
      Array.from({ length: 16 }, (_, index) => ({
        seq: index + 1,
        timestamp: `2026-03-17T12:${String(index).padStart(2, "0")}:00Z`,
        role: "assistant",
        content: `Replay entry ${index + 1}`,
      })),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Replay entry 16");
    });

    const replayChip = Array.from(pane.querySelectorAll("button")).find(
      (button) => button.textContent === "replay #1",
    ) as HTMLButtonElement | undefined;
    expect(replayChip).toBeDefined();

    replayChip!.click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    const focused = pane.querySelector('[data-replay-seq="1"]') as HTMLElement | null;
    expect(focused).not.toBeNull();
    expect(focused?.style.outline).toContain("var(--accent)");
  });

  it("normalizes wiki locators that use the wiki: prefix", async () => {
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        recent_revelations: [
          {
            revelation_id: "rev-1",
            occurred_at: "2026-03-17T12:05:00Z",
            title: "Wiki locator",
            summary: "This locator should open the namespaced wiki path.",
            provenance: {
              source: "agent_step",
              source_refs: ["wiki:acme.md"],
            },
          },
        ],
      }),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Wiki locator");
    });

    let openedDetail: OpenWikiDrawerDetail | null = null;
    const listener = ((event: CustomEvent<OpenWikiDrawerDetail>) => {
      openedDetail = event.detail;
    }) as EventListener;
    window.addEventListener(OPEN_WIKI_DRAWER_EVENT, listener);

    const wikiChip = Array.from(pane.querySelectorAll("button")).find(
      (button) => button.textContent === "acme.md",
    ) as HTMLButtonElement | undefined;
    expect(wikiChip).toBeDefined();

    wikiChip!.click();

    const detail = openedDetail as OpenWikiDrawerDetail | null;
    expect(detail).not.toBeNull();
    if (!detail) {
      throw new Error("Expected wiki drawer detail");
    }
    expect(detail.wikiPath).toBe("wiki/acme.md");
    expect(appState.get().overviewSelectedWikiPath).toBe("wiki/acme.md");

    window.removeEventListener(OPEN_WIKI_DRAWER_EVENT, listener);
  });

  it("does not treat unrelated nowiki references as wiki navigation targets", async () => {
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        recent_revelations: [
          {
            revelation_id: "rev-nowiki",
            occurred_at: "2026-03-17T12:05:00Z",
            title: "Opaque source ref",
            summary: "This source ref should remain informational only.",
            provenance: {
              source: "agent_step",
              source_refs: ["nowiki/file.md"],
            },
          },
        ],
      }),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Opaque source ref");
    });

    expect(pane.querySelector('button[title="nowiki/file.md"]')).toBeNull();
    expect(pane.querySelector('span[title="nowiki/file.md"]')).not.toBeNull();
  });

  it("focuses the matching gap card from revelation evidence chips", async () => {
    __setHandler("get_investigation_overview", () =>
      makeOverview({
        recent_revelations: [
          {
            revelation_id: "rev-gap",
            occurred_at: "2026-03-17T12:05:00Z",
            title: "Gap-linked evidence",
            summary: "This should focus the existing gap card.",
            provenance: {
              source: "agent_step",
              evidence_refs: ["gap:claim:c1:missing_evidence"],
            },
          },
        ],
      }),
    );

    const pane = createOverviewPane();
    document.body.appendChild(pane);

    await vi.waitFor(() => {
      expect(pane.textContent).toContain("Gap-linked evidence");
      expect(pane.textContent).toContain("Claim c1 needs more evidence");
    });

    const gapChip = pane.querySelector(
      'button[title="gap:claim:c1:missing_evidence"]',
    ) as HTMLButtonElement | null;
    expect(gapChip).not.toBeNull();

    gapChip!.click();

    const gapCard = pane.querySelector(
      '[data-gap-id="gap:claim:c1:missing_evidence"]',
    ) as HTMLElement | null;
    expect(gapCard).not.toBeNull();
    expect(gapCard?.style.outline).toContain("var(--accent)");
  });
});
