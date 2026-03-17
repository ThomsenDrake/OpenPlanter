// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { __clearHandlers, __setHandler } from "../__mocks__/tauri";

vi.mock("@tauri-apps/api/core", async () => {
  const mock = await import("../__mocks__/tauri");
  return { invoke: mock.invoke };
});

import type { InvestigationOverviewView } from "../api/types";
import { appState } from "../state/store";
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
    __setHandler("read_wiki_file", ({ path }: { path: string }) => `# ${path}\n\nMock wiki document`);
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
      expect(pane.textContent).toContain("Who controls Acme Corp?");
      expect(pane.textContent).toContain("Claim c1 needs more evidence");
      expect(pane.textContent).toContain("Acme and PAC filings overlap");
      expect(pane.textContent).toContain("Acme Corp");
    });
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
});
