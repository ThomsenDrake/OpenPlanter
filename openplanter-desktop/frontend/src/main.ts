import { createApp } from "./components/App";
import { getConfig, getInitStatus } from "./api/invoke";
import {
  onAgentTrace,
  onAgentDelta,
  onAgentCompleteEvent,
  onAgentError,
  onAgentStep,
  onWikiUpdated,
  onCuratorUpdate,
  onLoopHealth,
  onMigrationProgress,
} from "./api/events";
import { appState } from "./state/store";

const SPLASH_ART = [
  " .oOo.      ___                   ____  _             _                .oOo. ",
  "oO.|.Oo    / _ \\ _ __   ___ _ __ |  _ \\| | __ _ _ __ | |_ ___ _ __    oO.|.Oo",
  "Oo.|.oO   | | | | '_ \\ / _ \\ '_ \\| |_) | |/ _` | '_ \\| __/ _ \\ '__|   Oo.|.oO",
  "  .|.     | |_| | |_) |  __/ | | |  __/| | (_| | | | | ||  __/ |        .|.  ",
  "[=====]    \\___/| .__/ \\___|_| |_|_|   |_|\\__,_|_| |_|\\__\\___|_|      [=====]",
  " \\___/          |_|                                                    \\___/ ",
].join("\n");

const RETRIEVAL_PROGRESS_PREFIX = "[retrieval:progress] ";

function formatRecursionMode(state: {
  recursive: boolean;
  recursionPolicy: string;
  minSubtaskDepth: number;
  maxDepth: number;
}): string {
  if (!state.recursive) return "flat";
  const policy = state.recursionPolicy.replace(/_/g, "-");
  return `recursive:${policy} min:${state.minSubtaskDepth} max:${state.maxDepth}`;
}

function parseRetrievalProgress(message: string): {
  corpus: string;
  phase: string;
  documents_done: number;
  documents_total: number;
  percent: number;
  message: string;
} | null {
  if (!message.startsWith(RETRIEVAL_PROGRESS_PREFIX)) {
    return null;
  }
  try {
    const parsed = JSON.parse(message.slice(RETRIEVAL_PROGRESS_PREFIX.length));
    if (!parsed || typeof parsed !== "object") return null;
    return {
      corpus: String((parsed as any).corpus || "all"),
      phase: String((parsed as any).phase || "scan"),
      documents_done: Number((parsed as any).documents_done || 0),
      documents_total: Number((parsed as any).documents_total || 0),
      percent: Number((parsed as any).percent || 0),
      message: String((parsed as any).message || ""),
    };
  } catch {
    return null;
  }
}

function formatRetrievalProgressLabel(progress: {
  corpus: string;
  phase: string;
  documents_done: number;
  documents_total: number;
  percent: number;
  message: string;
}): string {
  const corpus = progress.corpus === "all" ? "all corpora" : progress.corpus;
  const counts =
    progress.documents_total > 0
      ? `${progress.phase} ${progress.percent}% (${progress.documents_done}/${progress.documents_total} docs)`
      : progress.phase;
  return progress.message ? `${corpus}: ${counts} - ${progress.message}` : `${corpus}: ${counts}`;
}

function isTerminalRetrievalPhase(phase: string): boolean {
  return phase === "done" || phase === "failed";
}

async function init() {
  const app = document.getElementById("app")!;
  createApp(app);

  // Load initial config
  let provider = "";
  let model = "";
  try {
    const config = await getConfig();
    provider = config.provider;
    model = config.model;
    const initStatus = await getInitStatus();
    appState.update((s) => ({
      ...s,
      provider: config.provider,
      model: config.model,
      zaiPlan: config.zai_plan,
      webSearchProvider: config.web_search_provider,
      embeddingsProvider: config.embeddings_provider,
      embeddingsStatus: config.embeddings_status,
      embeddingsStatusDetail: config.embeddings_status_detail,
      embeddingsMode: config.embeddings_mode,
      embeddingsPacketVersion: config.embeddings_packet_version,
      continuityMode: config.continuity_mode,
      mistralDocumentAiUseSharedKey: config.mistral_document_ai_use_shared_key,
      chromeMcpEnabled: config.chrome_mcp_enabled,
      chromeMcpAutoConnect: config.chrome_mcp_auto_connect,
      chromeMcpBrowserUrl: config.chrome_mcp_browser_url,
      chromeMcpChannel: config.chrome_mcp_channel,
      chromeMcpConnectTimeoutSec: config.chrome_mcp_connect_timeout_sec,
      chromeMcpRpcTimeoutSec: config.chrome_mcp_rpc_timeout_sec,
      chromeMcpStatus: config.chrome_mcp_status,
      chromeMcpStatusDetail: config.chrome_mcp_status_detail,
      sessionId: config.session_id,
      reasoningEffort: config.reasoning_effort,
      recursive: config.recursive,
      recursionPolicy: config.recursion_policy,
      workspace: config.workspace,
      minSubtaskDepth: config.min_subtask_depth,
      maxDepth: config.max_depth,
      maxStepsPerCall: config.max_steps_per_call,
      initStatus,
      initGateState: initStatus.gate_state,
      initGateVisible: initStatus.gate_state !== "ready",
    }));
  } catch (e) {
    console.error("Failed to load config:", e);
  }

  // Add splash art and startup info (session created lazily on first message)
  const state = appState.get();
  const reasoningLabel = state.reasoningEffort ?? "off";
  const modeLabel = formatRecursionMode(state);

  appState.update((s) => ({
    ...s,
    messages: [
      {
        id: crypto.randomUUID(),
        role: "splash" as const,
        content: SPLASH_ART,
        timestamp: Date.now(),
      },
      {
        id: crypto.randomUUID(),
        role: "system" as const,
        content: [
          `provider: ${provider || "auto"}`,
          `model: ${model || "—"}`,
          `z.ai plan: ${state.zaiPlan || "paygo"}`,
          `embeddings: ${state.embeddingsProvider || "voyage"} (${state.embeddingsStatus || "disabled"})`,
          `web search: ${state.webSearchProvider || "exa"}`,
          `continuity: ${state.continuityMode || "auto"}`,
          `chrome mcp: ${state.chromeMcpStatus}`,
          `reasoning: ${reasoningLabel}`,
          `mode: ${modeLabel}`,
          `workspace: ${state.workspace || "."}`,
        ].join("  |  "),
        timestamp: Date.now(),
      },
      {
        id: crypto.randomUUID(),
        role: "system" as const,
        content: "Type /help for commands. ESC to cancel a running task.",
        timestamp: Date.now(),
      },
      ...(state.initGateState !== "ready"
        ? [
            {
              id: crypto.randomUUID(),
              role: "system" as const,
              content:
                "Workspace initialization is required before running the agent. Use the setup panel or /init.",
              timestamp: Date.now(),
            },
          ]
        : []),
    ],
  }));

  // Subscribe to agent events — await each to ensure listeners are registered
  await onAgentTrace((msg) => {
    const retrievalProgress = parseRetrievalProgress(msg);
    if (retrievalProgress) {
      appState.update((s) => ({
        ...s,
        retrievalProgressActive: !isTerminalRetrievalPhase(retrievalProgress.phase),
        retrievalProgressLabel: formatRetrievalProgressLabel(retrievalProgress),
        retrievalProgressPercent: retrievalProgress.percent,
      }));
    }
    console.log("[trace]", msg);
  });

  await onAgentStep((event) => {
    appState.update((s) => ({
      ...s,
      inputTokens: s.inputTokens + event.tokens.input_tokens,
      outputTokens: s.outputTokens + event.tokens.output_tokens,
      currentStep: event.step,
      currentDepth: event.depth,
      currentConversationPath: event.conversation_path ?? s.currentConversationPath,
      lastLoopMetrics: event.loop_metrics ?? s.lastLoopMetrics,
    }));

    // Dispatch to ChatPane for rich step summary rendering
    window.dispatchEvent(new CustomEvent("agent-step", { detail: event }));
  });

  await onAgentDelta((event) => {
    const detail = new CustomEvent("agent-delta", { detail: event });
    window.dispatchEvent(detail);
  });

  await onAgentCompleteEvent((event) => {
    appState.update((s) => ({
      ...s,
      isRunning: false,
      currentStep: 0,
      currentDepth: 0,
      currentConversationPath: null,
      loopHealth: null,
      retrievalProgressActive: false,
      retrievalProgressLabel: null,
      retrievalProgressPercent: null,
      lastLoopMetrics: event.loop_metrics ?? s.lastLoopMetrics,
      lastCompletion: event.completion ?? null,
      messages: [
        ...s.messages,
        {
          id: crypto.randomUUID(),
          role: "assistant" as const,
          content: event.result,
          timestamp: Date.now(),
          isRendered: true,
        },
        ...(event.completion?.kind === "partial"
          ? [
              {
                id: crypto.randomUUID(),
                role: "system" as const,
                content:
                  "Partial completion: the run used its bounded step budget and stopped cleanly. Resume to continue from the saved state.",
                timestamp: Date.now(),
              },
            ]
          : []),
      ],
    }));

    window.dispatchEvent(new CustomEvent("agent-finished"));

    // Process input queue
    processQueue();
  });

  await onAgentError((message) => {
    appState.update((s) => ({
      ...s,
      isRunning: false,
      currentStep: 0,
      currentDepth: 0,
      currentConversationPath: null,
      loopHealth: null,
      retrievalProgressActive: false,
      retrievalProgressLabel: null,
      retrievalProgressPercent: null,
      lastCompletion: null,
      messages: [
        ...s.messages,
        {
          id: crypto.randomUUID(),
          role: "system" as const,
          content: `Error: ${message}`,
          timestamp: Date.now(),
        },
        ...(s.inputQueue.length > 0
          ? [
              {
                id: crypto.randomUUID(),
                role: "system" as const,
                content: `Run stopped after error; ${s.inputQueue.length} queued objective(s) were not started.`,
                timestamp: Date.now(),
              },
            ]
          : []),
      ],
    }));

    window.dispatchEvent(new CustomEvent("agent-finished"));
  });

  await onWikiUpdated((data) => {
    const detail = new CustomEvent("wiki-updated", { detail: data });
    window.dispatchEvent(detail);
  });

  await onCuratorUpdate(() => {
    // Notify graph pane to refresh with curator's wiki changes
    window.dispatchEvent(new CustomEvent("curator-done"));
  });

  await onLoopHealth((event) => {
    appState.update((s) => ({
      ...s,
      currentStep: event.step,
      currentDepth: event.depth,
      loopHealth: event,
      currentConversationPath: event.conversation_path ?? s.currentConversationPath,
      lastLoopMetrics: event.metrics,
    }));
  });

  await onMigrationProgress((event) => {
    appState.update((s) => ({
      ...s,
      migrationProgress: event,
      isInitBusy: event.stage !== "done",
    }));
  });
}

function processQueue() {
  const state = appState.get();
  if (state.inputQueue.length > 0) {
    const [next, ...rest] = state.inputQueue;
    appState.update((s) => ({ ...s, inputQueue: rest }));
    // Dispatch queued-submit event for InputBar to pick up
    window.dispatchEvent(
      new CustomEvent("queued-submit", { detail: { text: next } }),
    );
  }
}

init();
