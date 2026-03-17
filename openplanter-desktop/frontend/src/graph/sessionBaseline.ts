import { getGraphData } from "../api/invoke";

let baselineNodeIds = new Set<string>();
let baselineCaptured = false;
let sessionFilterActive = true;
let baselineGeneration = 0;

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
}

export function resetGraphSessionState(isNew: boolean): void {
  baselineNodeIds = new Set<string>();
  baselineCaptured = false;
  sessionFilterActive = isNew;
  baselineGeneration += 1;
}

export function isGraphSessionFilterActive(): boolean {
  return sessionFilterActive;
}

export function setGraphSessionFilterActive(active: boolean): void {
  sessionFilterActive = active;
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
  } catch {
    // Best-effort: the graph can still capture a baseline once it mounts.
  }
}
