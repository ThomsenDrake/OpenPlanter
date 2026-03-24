/** TypeScript interfaces matching Rust event types. */

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
}

export interface TraceEvent {
  message: string;
}

export type LoopPhase = "investigate" | "build" | "iterate" | "finalize";

export interface LoopMetrics {
  steps: number;
  model_turns: number;
  tool_calls: number;
  investigate_steps: number;
  build_steps: number;
  iterate_steps: number;
  finalize_steps: number;
  recon_streak: number;
  max_recon_streak: number;
  guardrail_warnings: number;
  final_rejections: number;
  extensions_granted: number;
  extension_eligible_checks: number;
  extension_denials_no_progress: number;
  extension_denials_cap: number;
  termination_reason: string;
}

export interface StepEvent {
  depth: number;
  step: number;
  conversation_path?: string;
  tool_name: string | null;
  tokens: TokenUsage;
  elapsed_ms: number;
  is_final: boolean;
  loop_phase?: LoopPhase;
  loop_metrics?: LoopMetrics;
}

export type DeltaKind = "text" | "thinking" | "tool_call_start" | "tool_call_args";

export interface DeltaEvent {
  kind: DeltaKind;
  text: string;
}

export interface CompletionMeta {
  kind: string;
  reason: string;
  steps_used: number;
  max_steps: number;
  extensions_granted: number;
  extension_block_steps: number;
  extension_max_blocks: number;
}

export interface CompleteEvent {
  result: string;
  loop_metrics?: LoopMetrics;
  completion?: CompletionMeta;
}

export interface LoopHealthEvent {
  depth: number;
  step: number;
  conversation_path?: string;
  phase: LoopPhase;
  metrics: LoopMetrics;
  is_final: boolean;
}

export interface ErrorEvent {
  message: string;
}

export interface CuratorUpdateEvent {
  summary: string;
  files_changed: number;
}

export type NodeType = "source" | "section" | "fact";

export interface GraphNode {
  id: string;
  label: string;
  category: string;
  path: string;
  node_type?: NodeType;
  parent_id?: string;
  content?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  label: string | null;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface InvestigationSnapshotView {
  focus_question_count: number;
  supported_count: number;
  contested_count: number;
  outstanding_gap_count: number;
  candidate_action_count: number;
}

export interface OverviewQuestionView {
  id: string;
  text: string;
  priority: string;
  updated_at?: string;
}

export interface OverviewGapView {
  gap_id: string;
  label: string;
  status: string;
  kind: string;
  scope: string;
  related_action_ids: string[];
}

export interface OverviewActionView {
  action_id: string;
  label: string;
  rationale?: string;
  evidence_gap_refs: string[];
  priority: string;
}

export interface OverviewRevelationProvenanceView {
  source: string;
  step_index?: number;
  turn_id?: string;
  event_id?: string;
  replay_line?: number;
  source_refs?: string[];
  evidence_refs?: string[];
}

export interface OverviewRevelationView {
  revelation_id: string;
  occurred_at: string;
  title: string;
  summary: string;
  provenance: OverviewRevelationProvenanceView;
}

export interface WikiNavFactView {
  fact_id: string;
  label: string;
}

export interface WikiNavSectionView {
  section_id: string;
  title: string;
  facts: WikiNavFactView[];
}

export interface WikiNavSourceView {
  source_id: string;
  title: string;
  category: string;
  file_path: string;
  sections: WikiNavSectionView[];
}

export interface WikiNavTreeView {
  sources: WikiNavSourceView[];
}

export interface InvestigationOverviewView {
  session_id: string | null;
  generated_at: string;
  snapshot: InvestigationSnapshotView;
  focus_questions: OverviewQuestionView[];
  outstanding_gaps: OverviewGapView[];
  candidate_actions: OverviewActionView[];
  recent_revelations: OverviewRevelationView[];
  wiki_nav: WikiNavTreeView;
  warnings: string[];
}

export interface ConfigView {
  provider: string;
  model: string;
  reasoning_effort: string | null;
  zai_plan: string;
  web_search_provider: string;
  embeddings_provider: string;
  embeddings_status: string;
  embeddings_status_detail: string;
  continuity_mode: string;
  mistral_document_ai_use_shared_key: boolean;
  chrome_mcp_enabled: boolean;
  chrome_mcp_auto_connect: boolean;
  chrome_mcp_browser_url: string | null;
  chrome_mcp_channel: string;
  chrome_mcp_connect_timeout_sec: number;
  chrome_mcp_rpc_timeout_sec: number;
  chrome_mcp_status: string;
  chrome_mcp_status_detail: string;
  workspace: string;
  session_id: string | null;
  recursive: boolean;
  recursion_policy: string;
  min_subtask_depth: number;
  max_depth: number;
  max_steps_per_call: number;
  demo: boolean;
}

export interface PartialConfig {
  provider?: string;
  model?: string;
  reasoning_effort?: string;
  zai_plan?: string;
  web_search_provider?: string;
  embeddings_provider?: string;
  continuity_mode?: string;
  mistral_document_ai_use_shared_key?: boolean;
  chrome_mcp_enabled?: boolean;
  chrome_mcp_auto_connect?: boolean;
  chrome_mcp_browser_url?: string | null;
  chrome_mcp_channel?: string;
  chrome_mcp_connect_timeout_sec?: number;
  chrome_mcp_rpc_timeout_sec?: number;
  recursive?: boolean;
  recursion_policy?: string;
  min_subtask_depth?: number;
  max_depth?: number;
}

export interface ModelInfo {
  id: string;
  name: string | null;
  provider: string;
}

export interface SessionInfo {
  id: string;
  created_at: string;
  turn_count: number;
  last_objective: string | null;
}

export interface PersistentSettings {
  default_model?: string | null;
  default_reasoning_effort?: string | null;
  default_model_openai?: string | null;
  default_model_anthropic?: string | null;
  default_model_openrouter?: string | null;
  default_model_cerebras?: string | null;
  default_model_zai?: string | null;
  default_model_ollama?: string | null;
  zai_plan?: string | null;
  web_search_provider?: string | null;
  embeddings_provider?: string | null;
  continuity_mode?: string | null;
  mistral_document_ai_use_shared_key?: boolean | null;
  chrome_mcp_enabled?: boolean | null;
  chrome_mcp_auto_connect?: boolean | null;
  chrome_mcp_browser_url?: string | null;
  chrome_mcp_channel?: string | null;
  chrome_mcp_connect_timeout_sec?: number | null;
  chrome_mcp_rpc_timeout_sec?: number | null;
  recursive?: boolean | null;
  recursion_policy?: string | null;
  min_subtask_depth?: number | null;
  max_depth?: number | null;
}

export type CredentialService =
  | "openai"
  | "anthropic"
  | "openrouter"
  | "cerebras"
  | "zai"
  | "exa"
  | "firecrawl"
  | "brave"
  | "tavily"
  | "voyage"
  | "mistral"
  | "mistral_document_ai"
  | "mistral_transcription";

export type CredentialStatusMap = Record<string, boolean>;

export interface SlashResult {
  output: string;
  success: boolean;
}

export type InitGateState = "ready" | "requires_action" | "blocked";
export type MigrationSourceKind = "openplanter_workspace" | "manual_research" | "unknown";
export type MigrationProgressStage =
  | "inspect"
  | "copy"
  | "merge_sessions"
  | "merge_settings"
  | "merge_credentials"
  | "synthesize"
  | "rewrite"
  | "done";

export interface StandardInitReportView {
  workspace: string;
  created_paths: string[];
  copied_paths: string[];
  skipped_existing: number;
  errors: string[];
  onboarding_required: boolean;
}

export interface InitStatusView {
  runtime_workspace: string;
  gate_state: InitGateState;
  onboarding_completed: boolean;
  has_openplanter_root: boolean;
  has_runtime_wiki: boolean;
  has_runtime_index: boolean;
  init_state_path: string;
  last_migration_target: string | null;
  warnings: string[];
}

export interface MigrationSourceInspection {
  path: string;
  kind: MigrationSourceKind;
  has_sessions: boolean;
  has_settings: boolean;
  has_credentials: boolean;
  has_runtime_wiki: boolean;
  has_baseline_wiki: boolean;
  markdown_files: number;
  warnings: string[];
}

export interface MigrationSourceInput {
  path: string;
}

export interface MigrationInitRequest {
  target_workspace: string;
  sources: MigrationSourceInput[];
}

export interface MigrationProgressEvent {
  stage: MigrationProgressStage;
  message: string;
  current: number;
  total: number;
}

export interface MigrationInitResultView {
  target_workspace: string;
  sources: string[];
  sessions_copied: number;
  sessions_renamed: number;
  settings_merged_fields: string[];
  credentials_merged_fields: string[];
  wiki_files_synthesized: number;
  raw_preservation_root: string;
  rewrite_summary: string;
  restart_required: boolean;
  restart_message: string;
  warnings: string[];
}

export interface StepToolCallEntry {
  name: string;
  key_arg: string;
  elapsed: number;
}

export interface ReplayEntry {
  seq: number;
  timestamp: string;
  role: string;
  content: string;
  tool_name?: string;
  is_rendered?: boolean;
  step_number?: number;
  step_tokens_in?: number;
  step_tokens_out?: number;
  step_elapsed?: number;
  step_model_preview?: string;
  step_tool_calls?: StepToolCallEntry[];
  step_depth?: number;
  conversation_path?: string;
}

export type AgentEvent =
  | { type: "trace"; message: string }
  | {
      type: "step";
      depth: number;
      step: number;
      conversation_path?: string;
      tool_name: string | null;
      tokens: TokenUsage;
      elapsed_ms: number;
      is_final: boolean;
      loop_phase?: LoopPhase;
      loop_metrics?: LoopMetrics;
    }
  | { type: "delta"; kind: DeltaKind; text: string }
  | { type: "complete"; result: string; loop_metrics?: LoopMetrics; completion?: CompletionMeta }
  | { type: "error"; message: string }
  | { type: "wiki_updated"; nodes: GraphNode[]; edges: GraphEdge[] }
  | {
      type: "loop_health";
      depth: number;
      step: number;
      conversation_path?: string;
      phase: LoopPhase;
      metrics: LoopMetrics;
      is_final: boolean;
    };
