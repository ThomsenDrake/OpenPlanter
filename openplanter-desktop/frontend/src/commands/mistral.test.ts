import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { __setHandler, __clearHandlers } from "../__mocks__/tauri";

vi.mock("@tauri-apps/api/core", async () => {
  const mock = await import("../__mocks__/tauri");
  return { invoke: mock.invoke };
});

import { appState } from "../state/store";
import { handleMistralCommand, MISTRAL_USAGE } from "./mistral";

function makeConfig(overrides: Record<string, unknown> = {}) {
  return {
    provider: "anthropic",
    model: "claude-opus-4-6",
    reasoning_effort: "medium",
    zai_plan: "paygo",
    web_search_provider: "exa",
    continuity_mode: "auto",
    mistral_document_ai_use_shared_key: true,
    chrome_mcp_enabled: false,
    chrome_mcp_auto_connect: true,
    chrome_mcp_browser_url: null,
    chrome_mcp_channel: "stable",
    chrome_mcp_connect_timeout_sec: 15,
    chrome_mcp_rpc_timeout_sec: 45,
    chrome_mcp_status: "disabled",
    chrome_mcp_status_detail: "disabled",
    workspace: ".",
    session_id: null,
    recursive: true,
    recursion_policy: "auto",
    min_subtask_depth: 0,
    max_depth: 4,
    max_steps_per_call: 100,
    demo: false,
    ...overrides,
  };
}

describe("handleMistralCommand", () => {
  const originalState = appState.get();

  beforeEach(() => {
    appState.set({
      ...originalState,
      mistralDocumentAiUseSharedKey: true,
    });
  });

  afterEach(() => {
    __clearHandlers();
    appState.set(originalState);
  });

  it("shows status and usage when called without args", async () => {
    __setHandler("get_credentials_status", () => ({
      mistral: true,
      mistral_document_ai: false,
      mistral_transcription: true,
    }));

    const result = await handleMistralCommand("");
    expect(result.lines).toContain("Document AI key mode: shared");
    expect(result.lines).toContain("Mistral shared key: configured");
    expect(result.lines).toContain("Document AI override key: missing");
    expect(result.lines).toContain("Transcription key: configured");
    expect(result.lines).toContain(MISTRAL_USAGE);
  });

  it("updates key mode and persists when requested", async () => {
    __setHandler("update_config", ({ partial }: { partial: Record<string, unknown> }) => {
      expect(partial).toEqual({
        mistral_document_ai_use_shared_key: false,
      });
      return makeConfig({ mistral_document_ai_use_shared_key: false });
    });
    __setHandler("save_settings", ({ settings }: { settings: Record<string, unknown> }) => {
      expect(settings).toEqual({
        mistral_document_ai_use_shared_key: false,
      });
    });

    const result = await handleMistralCommand("key-mode override --save");
    expect(result.lines[0]).toContain("Document AI key mode set to: override");
    expect(result.lines).toContain("(Settings saved)");
    expect(appState.get().mistralDocumentAiUseSharedKey).toBe(false);
  });

  it("saves the shared key without echoing the secret", async () => {
    __setHandler("save_credential", ({ service, value }: any) => {
      expect(service).toBe("mistral");
      expect(value).toBe("super-secret");
      return {
        mistral: true,
        mistral_document_ai: false,
        mistral_transcription: false,
      };
    });

    const result = await handleMistralCommand("shared-key set super-secret");
    expect(result.sensitive).toBe(true);
    expect(result.lines[0]).toContain("Saved Mistral shared workspace key.");
    expect(result.lines.join("\n")).not.toContain("super-secret");
  });

  it("clears the Document AI override key and warns when env fallback remains", async () => {
    __setHandler("save_credential", ({ service, value }: any) => {
      expect(service).toBe("mistral_document_ai");
      expect(value).toBeNull();
      return {
        mistral: true,
        mistral_document_ai: true,
        mistral_transcription: false,
      };
    });

    const result = await handleMistralCommand("docai-key clear");
    expect(result.lines[0]).toContain("Cleared Mistral Document AI override workspace key.");
    expect(result.lines).toContain("This service is still configured from env or .env.");
  });

  it("saves the transcription key to the correct credential slot", async () => {
    __setHandler("save_credential", ({ service, value }: any) => {
      expect(service).toBe("mistral_transcription");
      expect(value).toBe("transcribe-me");
      return {
        mistral: false,
        mistral_document_ai: false,
        mistral_transcription: true,
      };
    });

    const result = await handleMistralCommand("transcription-key set transcribe-me");
    expect(result.sensitive).toBe(true);
    expect(result.lines[0]).toContain("Saved Mistral transcription workspace key.");
    expect(result.lines.join("\n")).not.toContain("transcribe-me");
  });

  it("rejects unknown actions", async () => {
    const result = await handleMistralCommand("banana");
    expect(result.lines[0]).toContain('Unknown /mistral action "banana".');
    expect(result.lines).toContain(MISTRAL_USAGE);
  });
});
