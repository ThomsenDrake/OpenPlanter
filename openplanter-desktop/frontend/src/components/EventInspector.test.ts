// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";

const getSessionDirectoryMock = vi.fn();
const readSessionArtifactMock = vi.fn();
const readSessionEventMock = vi.fn();

vi.mock("../api/invoke", () => ({
  getSessionDirectory: (...args: unknown[]) => getSessionDirectoryMock(...args),
  readSessionArtifact: (...args: unknown[]) => readSessionArtifactMock(...args),
  readSessionEvent: (...args: unknown[]) => readSessionEventMock(...args),
}));

import { mountEventInspector } from "./EventInspector";
import { appState } from "../state/store";

describe("EventInspector", () => {
  afterEach(() => {
    getSessionDirectoryMock.mockReset();
    readSessionArtifactMock.mockReset();
    readSessionEventMock.mockReset();
    document.body.innerHTML = "";
    appState.set({ ...appState.get(), sessionId: null });
  });

  it("loads event envelopes through readSessionEvent", async () => {
    readSessionEventMock.mockResolvedValue({
      event_id: "evt:session-1:000001",
      event_type: "turn.completed",
      turn_id: "turn-000001",
      timestamp: "2026-04-01T12:00:00Z",
    });
    appState.set({ ...appState.get(), sessionId: "session-1" });

    const cleanup = mountEventInspector();
    window.dispatchEvent(
      new CustomEvent("show-event-detail", {
        detail: { eventId: "evt:session-1:000001", source: "test" },
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(readSessionEventMock).toHaveBeenCalledWith("session-1", "evt:session-1:000001");
    expect(document.body.textContent).toContain("turn.completed");
    expect(document.body.textContent).toContain("turn-000001");

    cleanup();
  });

  it("loads artifact text through session artifact APIs", async () => {
    getSessionDirectoryMock.mockResolvedValue("/tmp/session-1");
    readSessionArtifactMock.mockResolvedValue("diff --git a/file b/file");
    appState.set({ ...appState.get(), sessionId: "session-1" });

    const cleanup = mountEventInspector();
    window.dispatchEvent(
      new CustomEvent("open-artifact", {
        detail: { path: "artifacts/patches/example.patch", source: "test" },
      }),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(getSessionDirectoryMock).toHaveBeenCalledWith("session-1");
    expect(readSessionArtifactMock).toHaveBeenCalledWith(
      "/tmp/session-1",
      "artifacts/patches/example.patch",
    );
    expect(document.body.textContent).toContain("Patch artifact");
    expect(document.body.textContent).toContain("diff --git a/file b/file");

    cleanup();
  });
});
