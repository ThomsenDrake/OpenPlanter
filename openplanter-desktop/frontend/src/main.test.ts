// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => {
  const handlers: Record<string, Function | undefined> = {};
  return {
    handlers,
    createApp: vi.fn(),
    getConfig: vi.fn(),
    getInitStatus: vi.fn(),
  };
});

vi.mock("./components/App", () => ({
  createApp: mocks.createApp,
}));

vi.mock("./api/invoke", () => ({
  getConfig: mocks.getConfig,
  getInitStatus: mocks.getInitStatus,
}));

vi.mock("./api/events", () => ({
  onAgentTrace: async (cb: Function) => {
    mocks.handlers.trace = cb;
    return () => {};
  },
  onAgentDelta: async (cb: Function) => {
    mocks.handlers.delta = cb;
    return () => {};
  },
  onAgentCompleteEvent: async (cb: Function) => {
    mocks.handlers.complete = cb;
    return () => {};
  },
  onAgentError: async (cb: Function) => {
    mocks.handlers.error = cb;
    return () => {};
  },
  onAgentStep: async (cb: Function) => {
    mocks.handlers.step = cb;
    return () => {};
  },
  onWikiUpdated: async (cb: Function) => {
    mocks.handlers.wiki = cb;
    return () => {};
  },
  onCuratorUpdate: async (cb: Function) => {
    mocks.handlers.curator = cb;
    return () => {};
  },
  onLoopHealth: async (cb: Function) => {
    mocks.handlers.loopHealth = cb;
    return () => {};
  },
  onMigrationProgress: async (cb: Function) => {
    mocks.handlers.migration = cb;
    return () => {};
  },
}));

describe("main queue handling", () => {
  beforeEach(async () => {
    vi.resetModules();
    mocks.createApp.mockReset();
    mocks.getConfig.mockReset();
    mocks.getInitStatus.mockReset();
    Object.keys(mocks.handlers).forEach((key) => delete mocks.handlers[key]);

    document.body.innerHTML = '<div id="app"></div>';

    let uuidCounter = 0;
    vi.stubGlobal("crypto", {
      randomUUID: () => `uuid-${++uuidCounter}`,
    });

    mocks.getConfig.mockResolvedValue({
      provider: "anthropic",
      model: "anthropic-foundry/claude-opus-4-6",
      zai_plan: "paygo",
      web_search_provider: "exa",
      embeddings_provider: "voyage",
      embeddings_status: "enabled",
      embeddings_status_detail: "Retrieval enabled via voyage (voyage-4). Hybrid mode: documents+ontology (retrieval-v3).",
      embeddings_mode: "documents+ontology",
      embeddings_packet_version: "retrieval-v3",
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
      session_id: "session-1",
      reasoning_effort: "high",
      recursive: true,
      recursion_policy: "auto",
      workspace: ".",
      min_subtask_depth: 0,
      max_depth: 4,
      max_steps_per_call: 100,
    });
    mocks.getInitStatus.mockResolvedValue({
      gate_state: "ready",
    });

    const { appState } = await import("./state/store");
    appState.set({
      ...appState.get(),
      messages: [],
      inputQueue: [],
      isRunning: false,
      currentStep: 0,
      currentDepth: 0,
      currentConversationPath: null,
      loopHealth: null,
      lastLoopMetrics: null,
      lastCompletion: null,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("does not process queued objectives after agent errors", async () => {
    const queuedSubmitSpy = vi.fn();
    window.addEventListener("queued-submit", queuedSubmitSpy as EventListener);

    const { appState } = await import("./state/store");
    appState.update((s) => ({
      ...s,
      isRunning: true,
      inputQueue: ["queued one", "queued two"],
    }));

    await import("./main");
    await vi.waitFor(() => expect(typeof mocks.handlers.error).toBe("function"));

    mocks.handlers.error?.("SSE stream error: Invalid status code: 400 Bad Request");

    await vi.waitFor(() => {
      const state = appState.get();
      expect(state.isRunning).toBe(false);
      expect(state.inputQueue).toEqual(["queued one", "queued two"]);
      expect(queuedSubmitSpy).not.toHaveBeenCalled();
      const contents = state.messages.map((msg) => msg.content);
      expect(contents).toContain(
        "Error: SSE stream error: Invalid status code: 400 Bad Request"
      );
      expect(contents).toContain(
        "Run stopped after error; 2 queued objective(s) were not started."
      );
    });
  });

  it("still processes queued objectives after successful completion", async () => {
    const queuedSubmitSpy = vi.fn();
    window.addEventListener("queued-submit", queuedSubmitSpy as EventListener);

    const { appState } = await import("./state/store");
    appState.update((s) => ({
      ...s,
      isRunning: true,
      inputQueue: ["queued next", "queued later"],
    }));

    await import("./main");
    await vi.waitFor(() => expect(typeof mocks.handlers.complete).toBe("function"));

    mocks.handlers.complete?.({
      result: "done",
      loop_metrics: null,
      completion: null,
    });

    await vi.waitFor(() => {
      const state = appState.get();
      expect(state.isRunning).toBe(false);
      expect(state.inputQueue).toEqual(["queued later"]);
      expect(queuedSubmitSpy).toHaveBeenCalledTimes(1);
      expect(queuedSubmitSpy.mock.calls[0][0].detail).toEqual({
        text: "queued next",
      });
    });
  });

  it("tracks retrieval progress from trace events", async () => {
    const { appState } = await import("./state/store");

    await import("./main");
    await vi.waitFor(() => expect(typeof mocks.handlers.trace).toBe("function"));

    mocks.handlers.trace?.(
      '[retrieval:progress] {"corpus":"workspace","phase":"embedding","documents_done":12,"documents_total":48,"chunks_done":80,"chunks_total":320,"reused_documents":0,"percent":25,"message":"Embedding workspace retrieval index."}'
    );

    await vi.waitFor(() => {
      const state = appState.get();
      expect(state.retrievalProgressActive).toBe(true);
      expect(state.retrievalProgressPercent).toBe(25);
      expect(state.retrievalProgressLabel).toBe(
        "workspace: embedding 25% (12/48 docs) - Embedding workspace retrieval index."
      );
    });

    mocks.handlers.trace?.(
      '[retrieval:progress] {"corpus":"workspace","phase":"done","documents_done":48,"documents_total":48,"chunks_done":320,"chunks_total":320,"reused_documents":0,"percent":100,"message":"Workspace retrieval index ready."}'
    );

    await vi.waitFor(() => {
      const state = appState.get();
      expect(state.retrievalProgressActive).toBe(false);
      expect(state.retrievalProgressPercent).toBe(100);
      expect(state.retrievalProgressLabel).toBe(
        "workspace: done 100% (48/48 docs) - Workspace retrieval index ready."
      );
    });
  });

  it("treats failed retrieval progress as terminal", async () => {
    const { appState } = await import("./state/store");

    await import("./main");
    await vi.waitFor(() => expect(typeof mocks.handlers.trace).toBe("function"));

    mocks.handlers.trace?.(
      '[retrieval:progress] {"corpus":"workspace","phase":"failed","documents_done":12,"documents_total":48,"chunks_done":80,"chunks_total":320,"reused_documents":0,"percent":25,"message":"workspace retrieval indexing failed after retries; cached 12/48 docs for future runs."}'
    );

    await vi.waitFor(() => {
      const state = appState.get();
      expect(state.retrievalProgressActive).toBe(false);
      expect(state.retrievalProgressPercent).toBe(25);
      expect(state.retrievalProgressLabel).toBe(
        "workspace: failed 25% (12/48 docs) - workspace retrieval indexing failed after retries; cached 12/48 docs for future runs."
      );
    });
  });
});
