import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { __setHandler, __clearHandlers } from "../__mocks__/tauri";

vi.mock("@tauri-apps/api/core", async () => {
  const mock = await import("../__mocks__/tauri");
  return { invoke: mock.invoke };
});

import { handleRecursionCommand } from "./recursion";
import { appState } from "../state/store";

describe("handleRecursionCommand", () => {
  const originalState = appState.get();

  beforeEach(() => {
    appState.set({
      ...originalState,
      recursive: true,
      recursionPolicy: "auto",
      minSubtaskDepth: 0,
      maxDepth: 4,
    });
  });

  afterEach(() => {
    __clearHandlers();
    appState.set(originalState);
  });

  it("shows current recursion status with no args", async () => {
    const result = await handleRecursionCommand("");
    expect(result.action).toBe("handled");
    expect(result.lines).toContain("Recursion mode: recursive");
    expect(result.lines).toContain("Recursion policy: auto");
  });

  it("sets flat mode", async () => {
    __setHandler("update_config", ({ partial }: any) => {
      expect(partial.recursive).toBe(false);
      expect(partial.recursion_policy).toBe("auto");
      return {
        recursive: false,
        recursion_policy: "auto",
        min_subtask_depth: 0,
        max_depth: 4,
      };
    });

    const result = await handleRecursionCommand("flat");
    expect(result.lines).toContain("Recursion mode set to: flat");
    expect(appState.get().recursive).toBe(false);
  });

  it("normalizes force-max and forwards min/max overrides", async () => {
    __setHandler("update_config", ({ partial }: any) => {
      expect(partial.recursive).toBe(true);
      expect(partial.recursion_policy).toBe("force_max");
      expect(partial.min_subtask_depth).toBe(2);
      expect(partial.max_depth).toBe(5);
      return {
        recursive: true,
        recursion_policy: "force_max",
        min_subtask_depth: 2,
        max_depth: 5,
      };
    });

    const result = await handleRecursionCommand("force-max --min 2 --max 5");
    expect(result.lines).toContain("Recursion policy: force-max");
    expect(result.lines).toContain("Min subtask depth: 2");
    expect(result.lines).toContain("Max depth: 5");
  });

  it("saves settings when requested", async () => {
    __setHandler("update_config", () => ({
      recursive: true,
      recursion_policy: "auto",
      min_subtask_depth: 1,
      max_depth: 6,
    }));
    __setHandler("save_settings", ({ settings }: any) => {
      expect(settings.recursive).toBe(true);
      expect(settings.recursion_policy).toBe("auto");
      expect(settings.min_subtask_depth).toBe(1);
      expect(settings.max_depth).toBe(6);
    });

    const result = await handleRecursionCommand("auto --min 1 --max 6 --save");
    expect(result.lines).toContain("(Settings saved)");
  });

  it("rejects invalid modes", async () => {
    const result = await handleRecursionCommand("deeper");
    expect(result.lines[0]).toContain('Invalid recursion mode "deeper"');
  });

  it("rejects missing flag values", async () => {
    const result = await handleRecursionCommand("auto --min");
    expect(result.lines[0]).toContain("Missing value for --min");
  });
});
