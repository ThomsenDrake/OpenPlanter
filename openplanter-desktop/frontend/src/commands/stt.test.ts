import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { __setHandler, __clearHandlers } from "../__mocks__/tauri";

vi.mock("@tauri-apps/api/core", async () => {
  const mock = await import("../__mocks__/tauri");
  return { invoke: mock.invoke };
});

import { handleSttCommand } from "./stt";
import { appState } from "../state/store";

describe("handleSttCommand", () => {
  const originalState = appState.get();

  beforeEach(() => {
    appState.set({
      ...originalState,
      sttProvider: "mistral",
      sttModel: "voxtral-mini-latest",
      sttProfileId: null,
      sttProfileName: null,
    });
  });

  afterEach(() => {
    __clearHandlers();
    appState.set(originalState);
  });

  it("saves the current STT endpoint and limits into profiles", async () => {
    __setHandler("update_config", ({ partial }: { partial: Record<string, string> }) => {
      expect(partial.stt_model).toBe("voxtral-large-latest");
      return {
        stt_provider: "mistral",
        stt_model: "voxtral-large-latest",
        stt_base_url: "https://stt.example/v1",
        stt_max_bytes: 123456,
        stt_chunk_max_seconds: 450,
        stt_chunk_overlap_seconds: 1.5,
        stt_max_chunks: 12,
        stt_request_timeout_sec: 90,
        stt_profile_id: null,
        stt_profile_name: null,
      };
    });
    __setHandler("save_settings", ({ settings }: { settings: any }) => {
      const profile = settings.profiles.stt["mistral-voxtral-large-latest"];
      expect(settings.active_profiles.stt).toBe("mistral-voxtral-large-latest");
      expect(profile.base_url).toBe("https://stt.example/v1");
      expect(profile.options).toEqual({
        max_bytes: 123456,
        chunk_max_seconds: 450,
        chunk_overlap_seconds: 1.5,
        max_chunks: 12,
        request_timeout_sec: 90,
      });
      expect(settings.mistral_transcription_base_url).toBe("https://stt.example/v1");
      expect(settings.mistral_transcription_max_chunks).toBe(12);
    });

    const result = await handleSttCommand("voxtral-large-latest --save");

    expect(result.lines).toContain("(Saved STT profile: mistral-voxtral-large-latest)");
    expect(appState.get().sttProfileId).toBe("mistral-voxtral-large-latest");
  });
});
