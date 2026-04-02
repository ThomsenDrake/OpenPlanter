import {
  getGraphData,
  readSessionArtifact,
  writeSessionArtifact,
} from "../api/invoke";

export type GraphSessionChangeSetVersion = "graph-session-change-set/v0";

const CHANGE_SET_FILENAME = "graph_session_change_set.json";

/**
 * Frontend-only scaffolding for future durable session change sets.
 *
 * This v0 shape is still derived from the current baseline heuristic, but it
 * gives the graph/session layer a stable envelope that can later be backed by
 * ontology-native, provenance-linked deltas.
 */
export interface GraphSessionChangeSet {
  id: string;
  version: GraphSessionChangeSetVersion;
  kind: "baseline-diff";
  generation: number;
  capturedAtIso: string;
  baselineNodeIds: string[];
  currentNodeIds: string[];
  addedNodeIds: string[];
  removedNodeIds: string[];
}

let baselineNodeIds = new Set<string>();
let baselineCaptured = false;
let sessionFilterActive = true;
let baselineGeneration = 0;
let latestChangeSet: GraphSessionChangeSet | null = null;

function toSortedNodeIdList(nodeIds: Iterable<string>): string[] {
  return Array.from(new Set(nodeIds)).sort();
}

function cloneGraphSessionChangeSet(changeSet: GraphSessionChangeSet): GraphSessionChangeSet {
  return {
    ...changeSet,
    baselineNodeIds: [...changeSet.baselineNodeIds],
    currentNodeIds: [...changeSet.currentNodeIds],
    addedNodeIds: [...changeSet.addedNodeIds],
    removedNodeIds: [...changeSet.removedNodeIds],
  };
}

function buildGraphSessionChangeSet(
  nodeIds: Iterable<string>,
  capturedAtIso = new Date().toISOString(),
): GraphSessionChangeSet {
  const currentNodeIds = new Set(nodeIds);
  const addedNodeIds = new Set<string>();
  const removedNodeIds = new Set<string>();

  for (const nodeId of currentNodeIds) {
    if (!baselineNodeIds.has(nodeId)) {
      addedNodeIds.add(nodeId);
    }
  }

  for (const nodeId of baselineNodeIds) {
    if (!currentNodeIds.has(nodeId)) {
      removedNodeIds.add(nodeId);
    }
  }

  return {
    id: `graph-session-change-set-${baselineGeneration}`,
    version: "graph-session-change-set/v0",
    kind: "baseline-diff",
    generation: baselineGeneration,
    capturedAtIso,
    baselineNodeIds: toSortedNodeIdList(baselineNodeIds),
    currentNodeIds: toSortedNodeIdList(currentNodeIds),
    addedNodeIds: toSortedNodeIdList(addedNodeIds),
    removedNodeIds: toSortedNodeIdList(removedNodeIds),
  };
}

function cacheGraphSessionChangeSet(nodeIds: Iterable<string>): GraphSessionChangeSet | null {
  if (!baselineCaptured) {
    latestChangeSet = null;
    return null;
  }

  latestChangeSet = buildGraphSessionChangeSet(nodeIds);
  return cloneGraphSessionChangeSet(latestChangeSet);
}

export function getGraphSessionBaselineIds(): Set<string> {
  return new Set(baselineNodeIds);
}

export function hasGraphSessionBaseline(): boolean {
  return baselineCaptured;
}

export function captureGraphSessionBaseline(nodeIds: Iterable<string>): void {
  if (baselineCaptured) {
    return;
  }
  baselineNodeIds = new Set(nodeIds);
  baselineCaptured = true;
  latestChangeSet = buildGraphSessionChangeSet(baselineNodeIds);
}

/**
 * Persist the current change set to the session directory.
 */
export async function saveGraphSessionChangeSet(sessionDir: string): Promise<void> {
  if (!latestChangeSet) return;

  try {
    const payload = JSON.stringify(latestChangeSet, null, 2);
    await writeSessionArtifact(sessionDir, CHANGE_SET_FILENAME, payload);
  } catch (err) {
    console.warn("[sessionBaseline] failed to save change set:", err);
  }
}

/**
 * Load a persisted change set from the session directory.
 * Returns true if a change set was loaded successfully.
 */
export async function loadGraphSessionChangeSet(sessionDir: string): Promise<boolean> {
  try {
    const content = await readSessionArtifact(sessionDir, CHANGE_SET_FILENAME);

    if (!content) return false;

    const parsed = JSON.parse(content) as GraphSessionChangeSet;
    if (parsed.version !== "graph-session-change-set/v0") return false;

    // Restore state from persisted change set
    baselineNodeIds = new Set(parsed.baselineNodeIds);
    baselineCaptured = true;
    baselineGeneration = parsed.generation;
    latestChangeSet = parsed;

    return true;
  } catch {
    return false;
  }
}

/**
 * Capture baseline and persist it to the session directory.
 * This is an async version that persists the change set.
 */
export async function captureAndPersistGraphSessionBaseline(
  nodeIds: Iterable<string>,
  sessionDir?: string,
): Promise<void> {
  if (baselineCaptured) {
    return;
  }
  baselineNodeIds = new Set(nodeIds);
  baselineCaptured = true;
  latestChangeSet = buildGraphSessionChangeSet(baselineNodeIds);

  if (sessionDir) {
    await saveGraphSessionChangeSet(sessionDir);
  }
}

/**
 * Capture the current change set and optionally persist it.
 */
export async function captureAndPersistChangeSet(
  nodeIds: Iterable<string>,
  sessionDir?: string,
): Promise<GraphSessionChangeSet | null> {
  const changeSet = cacheGraphSessionChangeSet(nodeIds);
  if (changeSet && sessionDir) {
    await saveGraphSessionChangeSet(sessionDir);
  }
  return changeSet;
}

export function resetGraphSessionState(isNew: boolean): void {
  baselineNodeIds = new Set<string>();
  baselineCaptured = false;
  sessionFilterActive = isNew;
  baselineGeneration += 1;
  latestChangeSet = null;
}

export function isGraphSessionFilterActive(): boolean {
  return sessionFilterActive;
}

export function setGraphSessionFilterActive(active: boolean): void {
  sessionFilterActive = active;
}

/**
 * Compute a v0 change set from the current baseline and a graph snapshot.
 *
 * Callers can use this immediately for in-memory UX, then later swap to a
 * backend-provided change set without changing higher-level semantics.
 */
export function computeGraphSessionChangeSet(nodeIds: Iterable<string>): GraphSessionChangeSet | null {
  if (!baselineCaptured) {
    return null;
  }
  return buildGraphSessionChangeSet(nodeIds);
}

/**
 * Cache the latest derived change set for the current session generation.
 *
 * This is intentionally additive scaffolding and is not yet required by the
 * current GraphPane call sites.
 */
export function captureGraphSessionChangeSet(nodeIds: Iterable<string>): GraphSessionChangeSet | null {
  return cacheGraphSessionChangeSet(nodeIds);
}

export function getGraphSessionChangeSet(): GraphSessionChangeSet | null {
  if (!latestChangeSet) {
    return null;
  }
  return cloneGraphSessionChangeSet(latestChangeSet);
}

export async function primeGraphSessionBaseline(): Promise<void> {
  if (baselineCaptured) {
    return;
  }

  const generation = baselineGeneration;
  try {
    const data = await getGraphData();
    if (generation !== baselineGeneration || baselineCaptured) {
      return;
    }

    baselineNodeIds = new Set(data.nodes.map((node) => node.id));
    baselineCaptured = true;
    latestChangeSet = buildGraphSessionChangeSet(baselineNodeIds);
  } catch {
    // Best-effort: the graph can still capture a baseline once it mounts.
  }
}
