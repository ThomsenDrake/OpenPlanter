/**
 * Event Inspector: A slide-out panel for viewing raw v2 event envelopes.
 *
 * Listens for the `show-event-detail` custom event dispatched from OverviewPane
 * when users click on event links in evidence trails.
 */

import {
  getSessionDirectory,
  readSessionArtifact,
  readSessionEvent,
} from "../api/invoke";
import { appState } from "../state/store";

const EVENT_INSPECTOR_ID = "event-inspector-panel";
const SHOW_EVENT_DETAIL_EVENT = "show-event-detail";
const OPEN_ARTIFACT_EVENT = "open-artifact";

interface ShowEventDetailPayload {
  eventId: string;
  source: string;
}

interface OpenArtifactPayload {
  path: string;
  source: string;
}

// Key provenance fields to highlight in JSON display
const HIGHLIGHT_KEYS = new Set([
  "event_id",
  "turn_id",
  "source_refs",
  "evidence_refs",
  "generated_from",
  "schema_version",
  "envelope",
  "timestamp",
  "kind",
  "role",
]);

interface EventEnvelope {
  event_id: string;
  turn_id?: string;
  timestamp?: string;
  kind?: string;
  role?: string;
  event_type?: string;
  [key: string]: unknown;
}

let panelInstance: HTMLElement | null = null;
let cleanupFn: (() => void) | null = null;

/**
 * Create the event inspector panel element.
 */
function createPanel(): HTMLElement {
  const el = document.createElement("div");
  el.id = EVENT_INSPECTOR_ID;
  el.className = "event-inspector-panel";
  el.innerHTML = `
    <div class="event-inspector-header">
      <span class="event-inspector-title">Event Inspector</span>
      <div class="event-inspector-actions">
        <button type="button" class="event-inspector-btn event-inspector-copy-btn">Copy ID</button>
        <button type="button" class="event-inspector-btn event-inspector-close-btn">Close</button>
      </div>
    </div>
    <div class="event-inspector-body">
      <div class="event-inspector-placeholder">Select an event to inspect its envelope.</div>
    </div>
  `;

  // Apply styles
  Object.assign(el.style, {
    position: "fixed",
    right: "0",
    top: "0",
    bottom: "0",
    width: "480px",
    maxWidth: "90vw",
    background: "var(--bg-secondary, #1e1e2e)",
    borderLeft: "1px solid var(--border-color, #333)",
    zIndex: "1000",
    display: "none",
    flexDirection: "column",
    fontFamily: "var(--font-mono, monospace)",
    fontSize: "13px",
    overflow: "hidden",
    boxShadow: "-4px 0 16px rgba(0, 0, 0, 0.3)",
  });

  // Style header
  const header = el.querySelector(".event-inspector-header") as HTMLElement;
  Object.assign(header.style, {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "12px 16px",
    borderBottom: "1px solid var(--border-color, #333)",
    flexShrink: "0",
    background: "var(--bg-tertiary, #252535)",
  });

  // Style title
  const title = el.querySelector(".event-inspector-title") as HTMLElement;
  Object.assign(title.style, {
    fontWeight: "600",
    fontSize: "14px",
    color: "var(--text-primary, #e0e0e0)",
  });

  // Style actions
  const actions = el.querySelector(".event-inspector-actions") as HTMLElement;
  Object.assign(actions.style, {
    display: "flex",
    gap: "8px",
  });

  // Style buttons
  for (const btn of el.querySelectorAll(".event-inspector-btn")) {
    const button = btn as HTMLButtonElement;
    Object.assign(button.style, {
      padding: "4px 10px",
      border: "1px solid var(--border-color, #555)",
      background: "transparent",
      color: "var(--text-primary, #e0e0e0)",
      borderRadius: "4px",
      cursor: "pointer",
      fontSize: "12px",
      transition: "background 0.15s ease",
    });

    button.addEventListener("mouseenter", () => {
      button.style.background = "var(--bg-hover, #333)";
    });
    button.addEventListener("mouseleave", () => {
      button.style.background = "transparent";
    });
  }

  // Style body
  const body = el.querySelector(".event-inspector-body") as HTMLElement;
  Object.assign(body.style, {
    flex: "1",
    overflowY: "auto",
    padding: "16px",
    color: "var(--text-primary, #e0e0e0)",
  });

  // Close button handler
  const closeBtn = el.querySelector(".event-inspector-close-btn") as HTMLButtonElement;
  closeBtn.addEventListener("click", () => hidePanel());

  // Click outside to close
  el.addEventListener("click", (e) => {
    if (e.target === el) {
      hidePanel();
    }
  });

  return el;
}

/**
 * Apply syntax highlighting to JSON string.
 */
function syntaxHighlightJSON(obj: unknown): string {
  const json = JSON.stringify(obj, null, 2);
  return json
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"([^"]+)":/g, (match, key) => {
      const color = HIGHLIGHT_KEYS.has(key)
        ? "color: var(--accent, #f9e2af); font-weight: 600;"
        : "color: var(--syntax-key, #89b4fa);";
      return `<span style="${color}">"${key}"</span>:`;
    })
    .replace(/: "([^"]*)"/g, ': <span style="color: var(--syntax-string, #a6e3a1);">"$1"</span>')
    .replace(/: (-?\d+\.?\d*)/g, ': <span style="color: var(--syntax-number, #fab387);">$1</span>')
    .replace(/: (null)/g, ': <span style="color: var(--syntax-null, #6c7086);">$1</span>')
    .replace(/: (true|false)/g, ': <span style="color: var(--syntax-bool, #cba6f7);">$1</span>');
}

/**
 * Format a timestamp for display.
 */
function formatTimestamp(value?: string): string {
  if (!value) return "Unknown";
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return value;
  }
}

/**
 * Truncate a string for display.
 */
function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1)}…`;
}

function ensurePanel(
  title: string,
  copyValue: string,
  copyLabel: string,
): { panel: HTMLElement; body: HTMLElement } {
  if (!panelInstance) {
    panelInstance = createPanel();
    document.body.appendChild(panelInstance);
  }

  const body = panelInstance.querySelector(".event-inspector-body") as HTMLElement;
  const titleEl = panelInstance.querySelector(".event-inspector-title") as HTMLElement;
  const copyBtn = panelInstance.querySelector(".event-inspector-copy-btn") as HTMLButtonElement;

  titleEl.textContent = title;
  titleEl.title = copyValue;
  copyBtn.textContent = copyLabel;
  copyBtn.style.background = "transparent";
  copyBtn.style.color = "var(--text-primary, #e0e0e0)";
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(copyValue).then(() => {
      copyBtn.textContent = "Copied!";
      copyBtn.style.color = "var(--success, #a6e3a1)";
      setTimeout(() => {
        copyBtn.textContent = copyLabel;
        copyBtn.style.color = "var(--text-primary, #e0e0e0)";
      }, 1500);
    }).catch((err) => {
      console.error("[EventInspector] Failed to copy:", err);
      copyBtn.textContent = "Failed";
      setTimeout(() => {
        copyBtn.textContent = copyLabel;
      }, 1500);
    });
  };

  return { panel: panelInstance, body };
}

function revealPanel(): void {
  if (!panelInstance) return;
  panelInstance.style.display = "flex";
  requestAnimationFrame(() => {
    if (panelInstance) {
      panelInstance.style.transform = "translateX(0)";
    }
  });
}

function showLoading(body: HTMLElement, message: string): void {
  body.innerHTML = `
    <div class="event-inspector-loading" style="color: var(--text-muted, #888); padding: 24px; text-align: center;">
      ${message}
    </div>
  `;
}

/**
 * Show the panel with event data.
 */
async function showEventPanel(eventId: string): Promise<void> {
  const shortId = eventId.length > 24 ? truncate(eventId, 24) : eventId;
  const { body } = ensurePanel(`Event: ${shortId}`, eventId, "Copy ID");
  showLoading(body, "Loading event data...");
  revealPanel();

  try {
    const sessionId = appState.get().sessionId;
    if (!sessionId) {
      showInspectorMessage(
        body,
        `Event ${truncate(eventId, 20)}`,
        "No active session.",
        "The event inspector reads from the session's events.jsonl file.",
      );
      return;
    }

    const eventData = await readSessionEvent(sessionId, eventId);

    if (eventData) {
      renderEventData(body, eventData as EventEnvelope);
    } else {
      showInspectorMessage(
        body,
        `Event ${truncate(eventId, 20)}`,
        "Event not found in session events.",
        "The event inspector reads from the session's events.jsonl file.",
      );
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    showInspectorMessage(
      body,
      `Event ${truncate(eventId, 20)}`,
      `Error loading event: ${errorMsg}`,
      "The event inspector reads from the session's events.jsonl file.",
    );
  }
}

async function showArtifactPanel(path: string): Promise<void> {
  const shortPath = truncate(path, 32);
  const { body } = ensurePanel(`Artifact: ${shortPath}`, path, "Copy Path");
  showLoading(body, "Loading artifact...");
  revealPanel();

  try {
    const sessionId = appState.get().sessionId;
    if (!sessionId) {
      showInspectorMessage(
        body,
        `Artifact ${truncate(path, 20)}`,
        "No active session.",
        "Artifacts are loaded from the active session directory.",
      );
      return;
    }

    const sessionDir = await getSessionDirectory(sessionId);
    const content = await readSessionArtifact(sessionDir, path);
    if (content == null) {
      showInspectorMessage(
        body,
        `Artifact ${truncate(path, 20)}`,
        "Artifact not found in the session.",
        "Artifacts are loaded from the active session directory.",
      );
      return;
    }

    renderArtifactData(body, path, content);
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    showInspectorMessage(
      body,
      `Artifact ${truncate(path, 20)}`,
      `Error loading artifact: ${errorMsg}`,
      "Artifacts are loaded from the active session directory.",
    );
  }
}

/**
 * Render event data in the panel body.
 */
function renderEventData(body: HTMLElement, eventData: EventEnvelope): void {
  body.innerHTML = "";

  // Create meta section
  const meta = document.createElement("div");
  meta.className = "event-inspector-meta";
  Object.assign(meta.style, {
    marginBottom: "16px",
    padding: "12px",
    background: "var(--bg-tertiary, #252535)",
    borderRadius: "6px",
    border: "1px solid var(--border-color, #333)",
  });

  // Timestamp
  if (eventData.timestamp) {
    const tsRow = document.createElement("div");
    Object.assign(tsRow.style, {
      marginBottom: "4px",
      fontSize: "12px",
      color: "var(--text-muted, #888)",
    });
    tsRow.innerHTML = `<strong>Timestamp:</strong> ${formatTimestamp(eventData.timestamp)}`;
    meta.appendChild(tsRow);
  }

  // Kind/Role
  if (eventData.kind || eventData.role || eventData.event_type) {
    const kindRow = document.createElement("div");
    Object.assign(kindRow.style, {
      marginBottom: "4px",
      fontSize: "12px",
      color: "var(--text-muted, #888)",
    });
    kindRow.innerHTML = `<strong>Kind:</strong> ${eventData.event_type || eventData.kind || eventData.role || "unknown"}`;
    meta.appendChild(kindRow);
  }

  // Turn ID
  if (eventData.turn_id) {
    const turnRow = document.createElement("div");
    Object.assign(turnRow.style, {
      fontSize: "12px",
      color: "var(--text-muted, #888)",
    });
    turnRow.innerHTML = `<strong>Turn:</strong> ${truncate(eventData.turn_id, 32)}`;
    meta.appendChild(turnRow);
  }

  body.appendChild(meta);

  // Create JSON viewer
  const pre = document.createElement("pre");
  Object.assign(pre.style, {
    margin: "0",
    padding: "12px",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    lineHeight: "1.5",
    background: "var(--bg-primary, #1a1a2a)",
    borderRadius: "6px",
    border: "1px solid var(--border-color, #333)",
    overflow: "auto",
    maxHeight: "60vh",
  });
  pre.innerHTML = syntaxHighlightJSON(eventData);
  body.appendChild(pre);
}

/**
 * Render a text/patch artifact in the panel body.
 */
function renderArtifactData(body: HTMLElement, path: string, content: string): void {
  body.innerHTML = "";

  const meta = document.createElement("div");
  meta.className = "event-inspector-meta";
  Object.assign(meta.style, {
    marginBottom: "16px",
    padding: "12px",
    background: "var(--bg-tertiary, #252535)",
    borderRadius: "6px",
    border: "1px solid var(--border-color, #333)",
  });

  const typeRow = document.createElement("div");
  Object.assign(typeRow.style, {
    marginBottom: "4px",
    fontSize: "12px",
    color: "var(--text-muted, #888)",
  });
  typeRow.innerHTML = `<strong>Type:</strong> ${path.endsWith(".patch") ? "Patch artifact" : "Text artifact"}`;
  meta.appendChild(typeRow);

  const pathRow = document.createElement("div");
  Object.assign(pathRow.style, {
    fontSize: "12px",
    color: "var(--text-muted, #888)",
  });
  pathRow.innerHTML = `<strong>Path:</strong> ${path}`;
  meta.appendChild(pathRow);

  body.appendChild(meta);

  const pre = document.createElement("pre");
  Object.assign(pre.style, {
    margin: "0",
    padding: "12px",
    whiteSpace: "pre-wrap",
    wordBreak: "break-word",
    lineHeight: "1.5",
    background: "var(--bg-primary, #1a1a2a)",
    borderRadius: "6px",
    border: "1px solid var(--border-color, #333)",
    overflow: "auto",
    maxHeight: "60vh",
  });
  pre.textContent = content;
  body.appendChild(pre);
}

/**
 * Show a no-data or error message.
 */
function showInspectorMessage(
  body: HTMLElement,
  subject: string,
  message: string,
  helpText: string,
): void {
  body.innerHTML = `
    <div class="event-inspector-nodata" style="color: var(--text-muted, #888); padding: 24px; text-align: center;">
      <div style="font-size: 48px; margin-bottom: 16px; opacity: 0.5;">📋</div>
      <div style="font-weight: 600; margin-bottom: 8px; color: var(--text-primary, #e0e0e0);">
        ${subject}
      </div>
      <div style="font-size: 12px;">${message}</div>
      <div style="font-size: 11px; margin-top: 12px; opacity: 0.7;">
        ${helpText}
      </div>
    </div>
  `;
}

/**
 * Hide the panel.
 */
function hidePanel(): void {
  if (panelInstance) {
    panelInstance.style.display = "none";
  }
}

/**
 * Handle show-event-detail custom event.
 */
function handleShowEvent(e: Event): void {
  const detail = (e as CustomEvent<ShowEventDetailPayload>).detail;
  if (!detail?.eventId) {
    console.warn("[EventInspector] show-event-detail event missing eventId");
    return;
  }

  console.log(`[EventInspector] Showing event: ${detail.eventId} (source: ${detail.source})`);
  void showEventPanel(detail.eventId);
}

/**
 * Handle open-artifact custom event.
 */
async function handleOpenArtifact(e: Event): Promise<void> {
  const detail = (e as CustomEvent<OpenArtifactPayload>).detail;
  if (!detail?.path) {
    console.warn("[EventInspector] open-artifact event missing path");
    return;
  }

  console.log(`[EventInspector] Opening artifact: ${detail.path} (source: ${detail.source})`);
  await showArtifactPanel(detail.path);
}

/**
 * Mount the event inspector to the DOM and set up event listeners.
 * Returns a cleanup function to remove the panel and listeners.
 */
export function mountEventInspector(): () => void {
  // Add event listeners
  window.addEventListener(SHOW_EVENT_DETAIL_EVENT, handleShowEvent);
  window.addEventListener(OPEN_ARTIFACT_EVENT, handleOpenArtifact);

  // Keyboard handler to close on Escape
  const handleKeydown = (e: KeyboardEvent) => {
    if (e.key === "Escape" && panelInstance?.style.display === "flex") {
      hidePanel();
    }
  };
  window.addEventListener("keydown", handleKeydown);

  // Return cleanup function
  cleanupFn = () => {
    window.removeEventListener(SHOW_EVENT_DETAIL_EVENT, handleShowEvent);
    window.removeEventListener(OPEN_ARTIFACT_EVENT, handleOpenArtifact);
    window.removeEventListener("keydown", handleKeydown);
    if (panelInstance) {
      panelInstance.remove();
      panelInstance = null;
    }
  };

  return cleanupFn;
}

/**
 * Create and return the event inspector panel element.
 * This is an alternative API that returns the element for manual mounting.
 */
export function createEventInspector(): HTMLElement {
  if (!panelInstance) {
    panelInstance = createPanel();
  }
  return panelInstance;
}

/**
 * Show the event inspector with the given event ID.
 * Public API for programmatic access.
 */
export function inspectEvent(eventId: string): void {
  void showEventPanel(eventId);
}

/**
 * Close the event inspector panel.
 * Public API for programmatic access.
 */
export function closeEventInspector(): void {
  hidePanel();
}
