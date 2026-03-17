/** Simple observable state store. */
import type {
  CompletionMeta,
  InitStatusView,
  InvestigationOverviewView,
  LoopMetrics,
  LoopHealthEvent,
  MigrationInitResultView,
  MigrationProgressEvent,
} from "../api/types";

type Listener<T> = (value: T) => void;

export class Store<T> {
  private value: T;
  private listeners: Set<Listener<T>> = new Set();

  constructor(initial: T) {
    this.value = initial;
  }

  get(): T {
    return this.value;
  }

  set(newValue: T): void {
    this.value = newValue;
    for (const listener of this.listeners) {
      listener(this.value);
    }
  }

  update(fn: (current: T) => T): void {
    this.set(fn(this.value));
  }

  subscribe(listener: Listener<T>): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export interface ToolCallDisplay {
  name: string;
  args: string;
}

export interface StepToolCall {
  name: string;
  keyArg: string;
  elapsed: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool" | "system" | "thinking" | "step-header" | "step-summary" | "tool-tree" | "splash";
  content: string;
  toolName?: string;
  timestamp: number;
  isRendered?: boolean;
  toolCalls?: ToolCallDisplay[];
  /** Step summary data (only for role "step-summary") */
  stepNumber?: number;
  stepTokensIn?: number;
  stepTokensOut?: number;
  stepElapsed?: number;
  stepToolCalls?: StepToolCall[];
  stepModelPreview?: string;
}

export interface AppState {
  provider: string;
  model: string;
  zaiPlan: string;
  webSearchProvider: string;
  chromeMcpEnabled: boolean;
  chromeMcpAutoConnect: boolean;
  chromeMcpBrowserUrl: string | null;
  chromeMcpChannel: string;
  chromeMcpConnectTimeoutSec: number;
  chromeMcpRpcTimeoutSec: number;
  chromeMcpStatus: string;
  chromeMcpStatusDetail: string;
  sessionId: string | null;
  inputTokens: number;
  outputTokens: number;
  isRunning: boolean;
  messages: ChatMessage[];
  reasoningEffort: string | null;
  recursive: boolean;
  workspace: string;
  maxDepth: number;
  maxStepsPerCall: number;
  currentStep: number;
  currentDepth: number;
  loopHealth: LoopHealthEvent | null;
  lastLoopMetrics: LoopMetrics | null;
  lastCompletion: CompletionMeta | null;
  inputHistory: string[];
  inputQueue: string[];
  initGateState: "ready" | "requires_action" | "blocked";
  initStatus: InitStatusView | null;
  isInitBusy: boolean;
  initGateVisible: boolean;
  initGateMode: "standard" | "migration";
  migrationProgress: MigrationProgressEvent | null;
  migrationResult: MigrationInitResultView | null;
  investigationViewTab: "overview" | "graph";
  overviewStatus: "idle" | "loading" | "ready" | "error";
  overviewData: InvestigationOverviewView | null;
  overviewError: string | null;
  overviewSelectedWikiPath: string | null;
}

export const appState = new Store<AppState>({
  provider: "",
  model: "",
  zaiPlan: "paygo",
  webSearchProvider: "exa",
  chromeMcpEnabled: false,
  chromeMcpAutoConnect: true,
  chromeMcpBrowserUrl: null,
  chromeMcpChannel: "stable",
  chromeMcpConnectTimeoutSec: 15,
  chromeMcpRpcTimeoutSec: 45,
  chromeMcpStatus: "disabled",
  chromeMcpStatusDetail: "Chrome DevTools MCP is disabled.",
  sessionId: null,
  inputTokens: 0,
  outputTokens: 0,
  isRunning: false,
  messages: [],
  reasoningEffort: null,
  recursive: true,
  workspace: "",
  maxDepth: 4,
  maxStepsPerCall: 100,
  currentStep: 0,
  currentDepth: 0,
  loopHealth: null,
  lastLoopMetrics: null,
  lastCompletion: null,
  inputHistory: [],
  inputQueue: [],
  initGateState: "ready",
  initStatus: null,
  isInitBusy: false,
  initGateVisible: false,
  initGateMode: "standard",
  migrationProgress: null,
  migrationResult: null,
  investigationViewTab: "overview",
  overviewStatus: "idle",
  overviewData: null,
  overviewError: null,
  overviewSelectedWikiPath: null,
});
