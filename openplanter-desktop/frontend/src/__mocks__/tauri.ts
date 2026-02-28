/** Test utilities for controlling the Tauri invoke mock.
 *
 * The actual mock is set up in setup.ts via vi.mock.
 * This file provides helpers for tests to register/clear handlers.
 */

const GLOBAL_KEY = "__tauri_mock_handlers__";

function getHandlers(): Record<string, Function> {
  if (!(globalThis as any)[GLOBAL_KEY]) {
    (globalThis as any)[GLOBAL_KEY] = {};
  }
  return (globalThis as any)[GLOBAL_KEY];
}

export function invoke(cmd: string, args?: any): Promise<any> {
  const handlers = getHandlers();
  if (handlers[cmd]) {
    try {
      return Promise.resolve(handlers[cmd](args));
    } catch (e) {
      return Promise.reject(e);
    }
  }
  return Promise.reject(new Error(`No mock for command: ${cmd}`));
}

export function __setHandler(cmd: string, fn: Function): void {
  getHandlers()[cmd] = fn;
}

export function __clearHandlers(): void {
  const handlers = getHandlers();
  for (const k in handlers) delete handlers[k];
}
