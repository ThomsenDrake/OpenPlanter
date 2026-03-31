/** Chat pane: terminal-style messages, streaming, markdown rendering. */
import { appState, type ChatMessage, type StepToolCall } from "../state/store";
import { createInputBar } from "./InputBar";
import { parseAgentContent, stripToolXml, type ContentSegment } from "./contentParser";
import { extractToolCallKeyArg, KEY_ARGS } from "./toolArgs";
import { OPEN_WIKI_DRAWER_EVENT, type OpenWikiDrawerDetail } from "../wiki/drawerEvents";
import { resolveWikiMarkdownHref } from "../wiki/linkResolution";
import MarkdownIt from "markdown-it";
import hljs from "highlight.js";

const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: false,
  highlight(str: string, lang: string) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch { /* fallback */ }
    }
    return "";
  },
});

/** Format elapsed milliseconds as a readable string. */
function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Get last N lines of text for preview. */
function lastLines(text: string, n: number): string {
  const lines = text.split("\n").filter((l) => l.trim());
  return lines.slice(-n).join("\n");
}

type ActivityMode = "thinking" | "streaming" | "tool_args" | "tool";
const ROOT_CONVERSATION_PATH = "0";
let activeChatPaneCleanup: (() => void) | null = null;

interface PendingStepToolCall {
  name: string;
  keyArg: string;
  startTime: number;
  elapsed?: number;
}

interface StepBufferState {
  thinkingBuf: string;
  streamingBuf: string;
  toolArgsBuf: string;
  currentToolName: string;
  stepToolCalls: PendingStepToolCall[];
  stepStartTime: number;
}

function createStepBufferState(): StepBufferState {
  return {
    thinkingBuf: "",
    streamingBuf: "",
    toolArgsBuf: "",
    currentToolName: "",
    stepToolCalls: [],
    stepStartTime: Date.now(),
  };
}

/**
 * Manages the transient activity indicator shown during streaming.
 * A single DOM element updated in-place, removed when the step completes.
 */
class ActivityIndicator {
  private el: HTMLElement;
  private iconEl: HTMLElement;
  private labelEl: HTMLElement;
  private elapsedEl: HTMLElement;
  private stepEl: HTMLElement;
  private previewEl: HTMLElement;
  private mode: ActivityMode = "thinking";
  private startTime: number = Date.now();
  private timerId: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.el = document.createElement("div");
    this.el.className = "activity-indicator";

    const row = document.createElement("div");
    row.className = "activity-row";

    this.iconEl = document.createElement("span");
    this.iconEl.className = "activity-icon";

    this.labelEl = document.createElement("span");
    this.labelEl.className = "activity-label";

    this.elapsedEl = document.createElement("span");
    this.elapsedEl.className = "activity-elapsed";

    this.stepEl = document.createElement("span");
    this.stepEl.className = "activity-step";

    row.appendChild(this.iconEl);
    row.appendChild(this.labelEl);
    row.appendChild(this.elapsedEl);
    row.appendChild(this.stepEl);

    this.previewEl = document.createElement("div");
    this.previewEl.className = "activity-preview";

    this.el.appendChild(row);
    this.el.appendChild(this.previewEl);

    this.setMode("thinking");
    this.startTimer();
  }

  get element(): HTMLElement {
    return this.el;
  }

  private startTimer() {
    this.startTime = Date.now();
    this.updateElapsed();
    this.timerId = setInterval(() => this.updateElapsed(), 100);
  }

  private updateElapsed() {
    const ms = Date.now() - this.startTime;
    this.elapsedEl.textContent = formatElapsed(ms);
  }

  setMode(mode: ActivityMode, toolName?: string) {
    this.mode = mode;
    this.el.dataset.mode = mode;
    switch (mode) {
      case "thinking":
        this.labelEl.textContent = "Thinking...";
        break;
      case "streaming":
        this.labelEl.textContent = "Responding...";
        break;
      case "tool_args":
        this.labelEl.textContent = `Generating ${toolName || "tool"}...`;
        break;
      case "tool":
        this.labelEl.textContent = `Running ${toolName || "tool"}...`;
        break;
    }
  }

  setStep(step: number) {
    this.stepEl.textContent = step > 0 ? `Step ${step}` : "";
  }

  setPreview(text: string) {
    this.previewEl.textContent = lastLines(text, 3);
  }

  /** Transition to tool mode with key arg as preview. */
  setToolRunning(toolName: string, keyArg: string) {
    this.setMode("tool", toolName);
    this.previewEl.textContent = keyArg;
  }

  destroy() {
    if (this.timerId !== null) {
      clearInterval(this.timerId);
      this.timerId = null;
    }
    this.el.remove();
  }
}

/** Render a tool call as a compact inline block: ├─ tool_name "key arg" */
function renderToolCallBlock(seg: Extract<ContentSegment, { type: "tool_call" }>): HTMLElement {
  const block = document.createElement("div");
  block.className = "tool-call-block";

  const connector = document.createTextNode("\u251C\u2500 ");
  block.appendChild(connector);

  const fn = document.createElement("span");
  fn.className = "tool-fn";
  fn.textContent = seg.name;
  block.appendChild(fn);

  if (seg.keyArg) {
    const arg = document.createElement("span");
    arg.className = "tool-arg";
    arg.textContent = ` "${seg.keyArg}"`;
    block.appendChild(arg);
  }

  return block;
}

/** Render a tool result as a collapsible output block. */
function renderToolResultBlock(seg: Extract<ContentSegment, { type: "tool_result" }>): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "tool-result-wrapper";

  const output = seg.stdout || seg.stderr || "";
  const lines = output.split("\n").filter((l) => l !== "");
  const hasError = seg.stderr.length > 0 || (seg.returncode !== null && seg.returncode !== 0);
  const collapsible = lines.length > 4;

  // Toggle header
  const toggle = document.createElement("div");
  toggle.className = "tool-result-toggle";
  toggle.textContent = collapsible
    ? `\u25B6 Output (${lines.length} lines)`
    : `\u25BC Output`;
  wrapper.appendChild(toggle);

  // Output block
  const block = document.createElement("div");
  block.className = "tool-result-block";
  if (hasError) block.classList.add("has-error");
  if (collapsible) {
    // Collapsed by default
  } else {
    block.classList.add("expanded");
  }

  // Build content with │ prefix
  const prefixed = lines.map((l) => `\u2502 ${l}`).join("\n");
  block.textContent = prefixed;
  wrapper.appendChild(block);

  // Toggle click handler
  if (collapsible) {
    toggle.addEventListener("click", () => {
      const isExpanded = block.classList.toggle("expanded");
      toggle.textContent = isExpanded
        ? `\u25BC Output (${lines.length} lines)`
        : `\u25B6 Output (${lines.length} lines)`;
    });
  }

  return wrapper;
}

export function createChatPane(): HTMLElement {
  activeChatPaneCleanup?.();
  activeChatPaneCleanup = null;

  const pane = document.createElement("div");
  pane.className = "chat-pane";

  const messagesEl = document.createElement("div");
  messagesEl.className = "chat-messages";
  pane.appendChild(messagesEl);

  pane.appendChild(createInputBar());

  function handleWikiLinkClick(event: Event) {
    if (event.defaultPrevented) return;

    const rawTarget = event.target;
    const target =
      rawTarget instanceof Element
        ? rawTarget
        : rawTarget instanceof Node
          ? rawTarget.parentElement
          : null;
    if (!target) return;

    const link = target.closest("a");
    if (!link || !messagesEl.contains(link)) return;
    if (!link.closest(".message.assistant.rendered")) return;

    const href = link.getAttribute("href");
    if (!href) return;

    const wikiPath = resolveWikiMarkdownHref(href);
    if (!wikiPath) return;

    event.preventDefault();
    const requestedTitle = link.textContent?.trim() || undefined;
    window.dispatchEvent(new CustomEvent<OpenWikiDrawerDetail>(OPEN_WIKI_DRAWER_EVENT, {
      detail: {
        wikiPath,
        source: "chat",
        requestedTitle,
      },
    }));
  }

  messagesEl.addEventListener("click", handleWikiLinkClick);

  let renderedCount = 0;

  // ── Auto-scroll with proximity check ──
  function autoScroll() {
    // Don't scroll until the first step completes — prevents the activity
    // indicator from pushing the splash text out of view during the first step.
    const msgs = appState.get().messages;
    if (!msgs.some((m) => m.role === "step-summary")) return;

    const isNearBottom =
      messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 40;
    if (isNearBottom) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  }

  // ── Streaming state ──
  let activity: ActivityIndicator | null = null;
  let wasRunning = appState.get().isRunning;
  const stepBuffers = new Map<string, StepBufferState>();

  function getStepBuffer(path: string): StepBufferState {
    let buffer = stepBuffers.get(path);
    if (!buffer) {
      buffer = createStepBufferState();
      stepBuffers.set(path, buffer);
    }
    return buffer;
  }

  function resetBuffer(path: string) {
    stepBuffers.delete(path);
  }

  function resetBuffers() {
    stepBuffers.clear();
  }

  function ensureActivity(): ActivityIndicator {
    if (!activity) {
      activity = new ActivityIndicator();
      const step = appState.get().currentStep;
      activity.setStep(step);
      messagesEl.appendChild(activity.element);
    }
    return activity;
  }

  function removeActivity() {
    if (activity) {
      activity.destroy();
      activity = null;
    }
  }

  // ── Message rendering (state-driven) ──

  function renderMessage(msg: ChatMessage): HTMLElement {
    const el = document.createElement("div");
    el.className = `message ${msg.role}`;

    switch (msg.role) {
      case "splash":
        el.textContent = msg.content;
        break;

      case "step-header":
        el.textContent = msg.content;
        break;

      case "step-summary":
        renderStepSummaryEl(el, msg);
        break;

      case "tool-tree": {
        if (msg.toolCalls && msg.toolCalls.length > 0) {
          for (const tc of msg.toolCalls) {
            const line = document.createElement("div");
            line.className = "tool-tree-line";
            const fn = document.createElement("span");
            fn.className = "tool-fn";
            fn.textContent = tc.name;
            line.appendChild(fn);
            if (tc.args) {
              const arg = document.createElement("span");
              arg.className = "tool-arg";
              arg.textContent = ` ${tc.args}`;
              line.appendChild(arg);
            }
            el.appendChild(line);
          }
        } else {
          el.textContent = msg.content;
        }
        break;
      }

      case "thinking":
        el.textContent = msg.content;
        break;

      case "user":
      case "system":
        el.textContent = msg.content;
        break;

      case "tool":
        if (msg.toolName) {
          const toolLabel = document.createElement("div");
          toolLabel.className = "tool-name";
          toolLabel.textContent = msg.toolName;
          el.appendChild(toolLabel);
        }
        el.appendChild(document.createTextNode(msg.content));
        break;

      case "assistant":
        if (msg.isRendered) {
          el.classList.add("rendered");
          const segments = parseAgentContent(msg.content);
          if (segments.length === 1 && segments[0].type === "text") {
            // Fast path: no tool XML
            el.innerHTML = md.render(msg.content);
          } else {
            for (const seg of segments) {
              if (seg.type === "text" && seg.text.trim()) {
                const textEl = document.createElement("div");
                textEl.innerHTML = md.render(seg.text);
                el.appendChild(textEl);
              } else if (seg.type === "tool_call") {
                el.appendChild(renderToolCallBlock(seg));
              } else if (seg.type === "tool_result") {
                el.appendChild(renderToolResultBlock(seg));
              }
            }
          }
          el.addEventListener("click", handleWikiLinkClick);
        } else {
          el.textContent = msg.content;
        }
        break;

      default:
        el.textContent = msg.content;
    }

    return el;
  }

  function renderStepSummaryEl(el: HTMLElement, msg: ChatMessage) {
    // Header line: timestamp  Depth N  ·  Path X  ·  Step N  ·  Xk in / Yk out
    const header = document.createElement("div");
    header.className = "step-header-line";
    const ts = new Date(msg.timestamp);
    const timeStr = [
      ts.getHours().toString().padStart(2, "0"),
      ts.getMinutes().toString().padStart(2, "0"),
      ts.getSeconds().toString().padStart(2, "0"),
    ].join(":");
    const inK = ((msg.stepTokensIn || 0) / 1000).toFixed(1);
    const outK = ((msg.stepTokensOut || 0) / 1000).toFixed(1);
    const stepDepth = msg.stepDepth ?? 0;
    const conversationPath = msg.conversationPath ?? "0";
    header.textContent =
      `${timeStr}  Depth ${stepDepth}  ·  Path ${conversationPath}  ·  ` +
      `Step ${msg.stepNumber || "?"}  ·  ${inK}k in / ${outK}k out`;
    el.appendChild(header);

    // Model text preview (if any)
    if (msg.stepModelPreview) {
      const cleanPreview = stripToolXml(msg.stepModelPreview);
      if (cleanPreview.trim()) {
        const preview = document.createElement("div");
        preview.className = "step-model-text";
        const elapsedStr = msg.stepElapsed ? `(${formatElapsed(msg.stepElapsed)}) ` : "";
        // Truncate to ~200 chars
        const truncated =
          cleanPreview.length > 200
            ? cleanPreview.slice(0, 200) + "..."
            : cleanPreview;
        preview.textContent = elapsedStr + truncated;
        el.appendChild(preview);
      }
    }

    // Tool tree
    const tools = msg.stepToolCalls;
    if (tools && tools.length > 0) {
      const tree = document.createElement("div");
      tree.className = "step-tool-tree";
      for (let i = 0; i < tools.length; i++) {
        const tc = tools[i];
        const isLast = i === tools.length - 1;
        const line = document.createElement("div");
        line.className = "step-tool-line";
        if (isLast) line.classList.add("last");

        const connector = isLast ? "\u2514\u2500 " : "\u251C\u2500 ";
        const fnSpan = document.createElement("span");
        fnSpan.className = "tool-fn";
        fnSpan.textContent = tc.name;

        const argSpan = document.createElement("span");
        argSpan.className = "tool-arg";
        argSpan.textContent = tc.keyArg ? ` "${tc.keyArg}"` : "";

        const elSpan = document.createElement("span");
        elSpan.className = "tool-elapsed";
        elSpan.textContent = tc.elapsed > 0 ? ` ${formatElapsed(tc.elapsed)}` : "";

        line.appendChild(document.createTextNode(connector));
        line.appendChild(fnSpan);
        line.appendChild(argSpan);
        line.appendChild(elSpan);
        tree.appendChild(line);
      }
      el.appendChild(tree);
    }
  }

  function render() {
    const messages = appState.get().messages;
    while (renderedCount < messages.length) {
      const msgEl = renderMessage(messages[renderedCount]);
      // Insert before activity indicator if it exists
      if (activity) {
        messagesEl.insertBefore(msgEl, activity.element);
      } else {
        messagesEl.appendChild(msgEl);
      }
      renderedCount++;
    }
    autoScroll();
  }

  const unsubscribeRender = appState.subscribe(render);

  // ── Handle streaming deltas ──

  const onAgentDelta = ((e: CustomEvent) => {
    const {
      kind,
      text,
      conversation_path: conversationPath = ROOT_CONVERSATION_PATH,
    } = e.detail;
    const buffer = getStepBuffer(conversationPath);
    const isRootConversation = conversationPath === ROOT_CONVERSATION_PATH;

    if (kind === "thinking") {
      buffer.thinkingBuf += text;
      if (isRootConversation) {
        const ai = ensureActivity();
        ai.setMode("thinking");
        ai.setPreview(buffer.thinkingBuf);
        autoScroll();
      }
    } else if (kind === "text") {
      // Transition from thinking to streaming
      if (buffer.thinkingBuf && !buffer.streamingBuf) {
        // First text delta after thinking — switch mode
      }
      buffer.streamingBuf += text;
      if (isRootConversation) {
        const ai = ensureActivity();
        ai.setMode("streaming");
        ai.setPreview(stripToolXml(buffer.streamingBuf));
        autoScroll();
      }
    } else if (kind === "tool_call_start") {
      buffer.currentToolName = text;
      buffer.toolArgsBuf = "";
      buffer.stepToolCalls.push({
        name: text,
        keyArg: "",
        startTime: Date.now(),
      });

      if (isRootConversation) {
        const ai = ensureActivity();
        ai.setMode("tool_args", text);
        ai.setPreview("");
        autoScroll();
      }
    } else if (kind === "tool_call_args") {
      buffer.toolArgsBuf += text;

      // Always re-extract key arg as more chunks arrive — partial JSON
      // grows with each chunk so the extracted value gets more complete.
      const keyArg = extractToolCallKeyArg(buffer.currentToolName, buffer.toolArgsBuf);
      if (keyArg) {
        const current = buffer.stepToolCalls[buffer.stepToolCalls.length - 1];
        if (current) current.keyArg = keyArg;
        if (isRootConversation) {
          const ai = ensureActivity();
          ai.setToolRunning(buffer.currentToolName, keyArg);
          autoScroll();
        }
      } else if (isRootConversation) {
        const ai = ensureActivity();
        ai.setPreview(buffer.toolArgsBuf.slice(-120));
        autoScroll();
      }
    }
  }) as EventListener;
  window.addEventListener("agent-delta", onAgentDelta);

  // ── Handle step events — render step summary ──

  const onAgentStep = ((e: CustomEvent) => {
    const event = e.detail;
    const now = Date.now();
    const conversationPath = event.conversation_path ?? ROOT_CONVERSATION_PATH;
    const buffer = stepBuffers.get(conversationPath) ?? createStepBufferState();

    // Finalize elapsed times for tool calls in this step
    for (const tc of buffer.stepToolCalls) {
      if (tc.elapsed === undefined || tc.elapsed === 0) {
        tc.elapsed = now - tc.startTime;
      }
    }

    // Build step summary tool calls
    const summaryTools: StepToolCall[] = buffer.stepToolCalls.map((tc) => ({
      name: tc.name,
      keyArg: tc.keyArg,
      elapsed: tc.elapsed || now - tc.startTime,
    }));

    if (conversationPath === ROOT_CONVERSATION_PATH) {
      removeActivity();
    }

    // Create step summary message
    const stepElapsed = stepBuffers.has(conversationPath)
      ? now - buffer.stepStartTime
      : event.elapsed_ms;
    const modelPreview = buffer.streamingBuf.trim();

    appState.update((s) => ({
      ...s,
      messages: [
        ...s.messages,
        {
          id: crypto.randomUUID(),
          role: "step-summary" as const,
          content: "",
          timestamp: now,
          stepNumber: event.step,
          stepDepth: event.depth,
          conversationPath,
          stepTokensIn: event.tokens.input_tokens,
          stepTokensOut: event.tokens.output_tokens,
          stepElapsed: stepElapsed,
          stepToolCalls: summaryTools,
          stepModelPreview: modelPreview,
        },
      ],
    }));

    // Reset buffers for next step
    resetBuffer(conversationPath);
  }) as EventListener;
  window.addEventListener("agent-step", onAgentStep);

  // ── When complete event fires, clean up ──
  const unsubscribeCompletion = appState.subscribe(() => {
    const isRunning = appState.get().isRunning;
    if (wasRunning && !isRunning) {
      removeActivity();
      resetBuffers();
    }
    wasRunning = isRunning;
  });

  // ── Clear messages DOM when session changes ──
  const onSessionChanged = () => {
    messagesEl.innerHTML = "";
    renderedCount = 0;
    removeActivity();
    resetBuffers();
    render(); // re-render current messages (e.g. splash + user msg on lazy session create)
  };
  window.addEventListener("session-changed", onSessionChanged);

  activeChatPaneCleanup = () => {
    window.removeEventListener("agent-delta", onAgentDelta);
    window.removeEventListener("agent-step", onAgentStep);
    window.removeEventListener("session-changed", onSessionChanged);
    messagesEl.removeEventListener("click", handleWikiLinkClick);
    unsubscribeRender();
    unsubscribeCompletion();
    removeActivity();
    resetBuffers();
    if (activeChatPaneCleanup) {
      activeChatPaneCleanup = null;
    }
  };

  return pane;
}
export { KEY_ARGS };
