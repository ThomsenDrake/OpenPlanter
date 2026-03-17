import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { __setHandler, __clearHandlers } from "../__mocks__/tauri";

vi.mock("@tauri-apps/api/core", async () => {
  const mock = await import("../__mocks__/tauri");
  return { invoke: mock.invoke };
});

import { handleContinuityCommand } from "./continuity";
import { appState } from "../state/store";

describe("handleContinuityCommand", () => {
  const originalState = appState.get();

  beforeEach(() => {
    appState.set({
      ...originalState,
      continuityMode: "auto",
    });
  });

  afterEach(() => {
    __clearHandlers();
    appState.set(originalState);
  });

  it("no args shows current mode", async () => {
    const result = await handleContinuityCommand("");
    expect(result.action).toBe("handled");
    expect(result.lines).toContain("Continuity mode: auto");
  });

  it("updates continuity mode", async () => {
    __setHandler("update_config", ({ partial }: any) => {
      expect(partial.continuity_mode).toBe("continue");
      return {
        continuity_mode: "continue",
      };
    });

    const result = await handleContinuityCommand("continue");
    expect(result.action).toBe("handled");
    expect(result.lines).toContain("Continuity mode set to: continue");
    expect(appState.get().continuityMode).toBe("continue");
  });

  it("saves continuity mode when requested", async () => {
    __setHandler("update_config", () => ({
      continuity_mode: "fresh",
    }));
    __setHandler("save_settings", ({ settings }: any) => {
      expect(settings.continuity_mode).toBe("fresh");
    });

    const result = await handleContinuityCommand("fresh --save");
    expect(result.lines.some((line) => line.includes("(Settings saved)"))).toBe(true);
  });

  it("rejects invalid continuity mode", async () => {
    const result = await handleContinuityCommand("weird");
    expect(result.lines.some((line) => line.includes("Invalid continuity mode"))).toBe(true);
  });
});
