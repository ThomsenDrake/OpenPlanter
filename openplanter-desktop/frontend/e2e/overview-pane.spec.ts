import { expect, test, type Page } from "@playwright/test";
import {
  MOCK_CREDENTIALS,
  MOCK_CONFIG,
  MOCK_GRAPH_DATA,
  MOCK_INVESTIGATION_OVERVIEW,
  MOCK_SESSIONS,
} from "./fixtures/graph-data";

async function injectTauriMocks(page: Page) {
  await page.addInitScript(
    ({ graphData, overview, config, sessions, credentials }) => {
      (window as any).__TAURI_INTERNALS__ = {
        invoke: async (cmd: string, args?: any) => {
          switch (cmd) {
            case "get_graph_data":
              return graphData;
            case "get_investigation_overview":
              return overview;
            case "get_config":
              return config;
            case "list_sessions":
              return sessions;
            case "get_credentials_status":
              return credentials;
            case "read_wiki_file":
              return `# ${args?.path?.replace(/.*\//, "").replace(".md", "")}\n\nOverview wiki content.`;
            case "open_session":
              return {
                id: "new-session-id",
                created_at: new Date().toISOString(),
                turn_count: 0,
                last_objective: null,
              };
            case "get_session_history":
              return [];
            case "debug_log":
            case "save_settings":
            case "solve":
              return;
            case "list_models":
              return [];
            default:
              return;
          }
        },
        transformCallback: (callback: Function) => {
          const id = Math.floor(Math.random() * 1000000);
          (window as any).__TAURI_CB__ = (window as any).__TAURI_CB__ || {};
          (window as any).__TAURI_CB__[id] = callback;
          return id;
        },
        convertFileSrc: (path: string) => path,
        metadata: {
          currentWindow: { label: "main" },
          currentWebview: { windowLabel: "main", label: "main" },
        },
      };

      (window as any).__TAURI_EVENT_PLUGIN_INTERNALS__ = {
        unregisterListener: () => {},
      };
    },
    {
      graphData: MOCK_GRAPH_DATA,
      overview: MOCK_INVESTIGATION_OVERVIEW,
      config: MOCK_CONFIG,
      sessions: MOCK_SESSIONS,
      credentials: MOCK_CREDENTIALS,
    },
  );
}

test.describe("Overview Pane", () => {
  test.beforeEach(async ({ page }) => {
    await injectTauriMocks(page);
    await page.goto("/");
    await page.waitForSelector(".investigation-pane", { timeout: 5000 });
  });

  test("overview is the default investigation tab", async ({ page }) => {
    await expect(page.locator(".investigation-tab.active")).toHaveText("Overview");
    await expect(page.locator(".overview-pane")).toBeVisible();
    await expect(page.locator(".overview-pane")).toContainText("Who controls Acme Corp?");
    await expect(page.locator(".overview-pane")).toContainText("Outstanding Gaps");
    await expect(page.locator(".overview-pane")).toContainText("Recent Revelations");
  });

  test("users can switch from overview to graph", async ({ page }) => {
    await page.locator(".investigation-tab", { hasText: "Graph" }).click();
    await expect(page.locator(".investigation-tab.active")).toHaveText("Graph");
    await expect(page.locator(".graph-pane")).toBeVisible();
    await expect(page.locator(".graph-toolbar")).toBeVisible();
  });
});
