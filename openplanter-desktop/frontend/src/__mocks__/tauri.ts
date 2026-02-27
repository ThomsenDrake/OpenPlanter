/** Mock for @tauri-apps/api/core used in tests. */

const handlers: Record<string, Function> = {};

export function invoke(cmd: string, args?: any): Promise<any> {
  if (handlers[cmd]) return Promise.resolve(handlers[cmd](args));
  return Promise.reject(new Error(`No mock for command: ${cmd}`));
}

export function __setHandler(cmd: string, fn: Function): void {
  handlers[cmd] = fn;
}

export function __clearHandlers(): void {
  for (const k in handlers) delete handlers[k];
}
