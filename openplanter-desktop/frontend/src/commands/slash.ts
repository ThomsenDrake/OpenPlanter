/** Slash command dispatcher. */
import { appState } from "../state/store";
import { openSession } from "../api/invoke";
import { handleModelCommand, type CommandResult } from "./model";
import { CHROME_USAGE, formatChromeStatusLines, handleChromeCommand } from "./chrome";
import { handleReasoningCommand } from "./reasoning";
import { handleEmbeddingsCommand } from "./embeddings";
import { handleWebSearchCommand } from "./webSearch";
import { handleZaiPlanCommand } from "./zaiPlan";
import { handleInitCommand } from "./init";
import { handleContinuityCommand } from "./continuity";
import { handleRecursionCommand } from "./recursion";
import { handleMistralCommand, MISTRAL_USAGE } from "./mistral";

/** Dispatch a slash command. Returns null if not a slash command. */
export async function dispatchSlashCommand(input: string): Promise<CommandResult | null> {
  const trimmed = input.trim();
  if (!trimmed.startsWith("/")) return null;

  const spaceIdx = trimmed.indexOf(" ");
  const cmd = spaceIdx === -1 ? trimmed.toLowerCase() : trimmed.slice(0, spaceIdx).toLowerCase();
  const args = spaceIdx === -1 ? "" : trimmed.slice(spaceIdx + 1);

  switch (cmd) {
    case "/help":
      return {
        action: "handled",
        lines: [
          "Available commands:",
          "  /help               Show this help",
          "  /new                Start a new session",
          "  /clear              Clear chat messages",
          "  /quit, /exit        Quit the application",
          "  /status             Show current status",
          "  /model              Show/switch model (aliases: opus, sonnet, haiku, gpt5, ...)",
          "  /model <name>       Switch model (auto-detects provider)",
          "  /model <name> --save  Switch and persist",
          "  /model list [provider]  List available models",
          "  /zai-plan          Show current Z.AI endpoint family",
          "  /zai-plan <plan>   Set Z.AI endpoint family (paygo, coding)",
          "  /zai-plan <plan> --save  Set and persist",
          "  /embeddings        Show current embeddings provider and retrieval status",
          "  /embeddings <provider>  Set embeddings provider (voyage, mistral)",
          "  /embeddings <provider> --save  Set and persist",
          "  /web-search        Show current web search provider",
          "  /web-search <provider>  Set web search provider (exa, firecrawl, brave, tavily)",
          "  /web-search <provider> --save  Set and persist",
          "  /continuity       Show current follow-up continuity mode",
          "  /continuity <mode>  Set mode (auto, fresh, continue)",
          "  /continuity <mode> --save  Set and persist",
          "  /recursion         Show current recursion settings",
          "  /recursion <mode>  Set mode (flat, auto, force-max)",
          "  /recursion <mode> --min <N> --max <N> [--save]  Configure recursion depth policy",
          "  /reasoning          Show/set reasoning effort",
          "  /reasoning <level>  Set level (low, medium, high, off)",
          `  ${MISTRAL_USAGE.slice(6)}`,
          "  /chrome             Show current Chrome DevTools MCP status",
          `  ${CHROME_USAGE.slice(6)}`,
          "  /init status        Show workspace init status",
          "  /init standard      Initialize the current workspace",
          "  /init migrate       Open the migration init panel",
        ],
      };

    case "/new": {
      try {
        const investigationId = appState.get().activeInvestigationId;
        const session = await openSession(undefined, false, investigationId);
        appState.update((s) => ({
          ...s,
          sessionId: session.id,
          messages: [],
          inputTokens: 0,
          outputTokens: 0,
          currentStep: 0,
          currentDepth: 0,
          currentConversationPath: null,
          loopHealth: null,
          lastLoopMetrics: null,
          lastCompletion: null,
          inputQueue: [],
        }));
        window.dispatchEvent(new CustomEvent("session-changed", { detail: { isNew: true } }));
        return {
          action: "handled",
          lines: [`New session: ${session.id.slice(0, 8)}`],
        };
      } catch (e) {
        return {
          action: "handled",
          lines: [`Failed to create session: ${e}`],
        };
      }
    }

    case "/clear":
      return { action: "clear", lines: [] };

    case "/quit":
    case "/exit":
      return { action: "quit", lines: ["Goodbye."] };

    case "/status": {
      const s = appState.get();
      const inK = (s.inputTokens / 1000).toFixed(1);
      const outK = (s.outputTokens / 1000).toFixed(1);
      return {
        action: "handled",
        lines: [
          `Provider:    ${s.provider || "auto"}`,
          `Model:       ${s.model || "—"}`,
          `Z.AI plan:   ${s.zaiPlan || "paygo"}`,
          `Embeddings:  ${s.embeddingsProvider || "voyage"} (${s.embeddingsStatus || "disabled"})`,
          `Retrieval:   ${s.embeddingsStatusDetail}`,
          `Hybrid:      ${s.embeddingsMode || "documents+ontology"} (${s.embeddingsPacketVersion || "retrieval-v3"})`,
          `Vectorize:   ${s.retrievalProgressActive ? (s.retrievalProgressLabel || "in progress") : "idle"}`,
          `Web search:  ${s.webSearchProvider || "exa"}`,
          `Continuity:  ${s.continuityMode || "auto"}`,
          `Reasoning:   ${s.reasoningEffort ?? "off"}`,
          `DocAI key mode: ${s.mistralDocumentAiUseSharedKey ? "shared" : "override"}`,
          ...formatChromeStatusLines(s),
          `Mode:        ${s.recursive ? "recursive" : "flat"}`,
          `Policy:      ${s.recursionPolicy.replace(/_/g, "-")}`,
          `Min depth:   ${s.minSubtaskDepth}`,
          `Max depth:   ${s.maxDepth}`,
          `Max steps:   ${s.maxStepsPerCall}`,
          `Workspace:   ${s.workspace || "."}`,
          `Session:     ${s.sessionId ? s.sessionId.slice(0, 8) : "—"}`,
          `Tokens:      ${inK}k in / ${outK}k out`,
          `Running:     ${s.isRunning ? "yes" : "no"}`,
          `Queue:       ${s.inputQueue.length} item(s)`,
        ],
      };
    }

    case "/model":
      return handleModelCommand(args);

    case "/zai-plan":
      return handleZaiPlanCommand(args);

    case "/embeddings":
      return handleEmbeddingsCommand(args);

    case "/web-search":
      return handleWebSearchCommand(args);

    case "/continuity":
      return handleContinuityCommand(args);

    case "/recursion":
      return handleRecursionCommand(args);

    case "/reasoning":
      return handleReasoningCommand(args);

    case "/mistral":
      return handleMistralCommand(args);

    case "/chrome":
      return handleChromeCommand(args);

    case "/init":
      return handleInitCommand(args);

    default:
      return {
        action: "handled",
        lines: [`Unknown command: ${cmd}. Type /help for available commands.`],
      };
  }
}
