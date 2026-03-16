/** Completion tree for slash command autocomplete. */
import { MODEL_ALIASES } from "./model";

export interface CompletionItem {
  value: string;
  description: string;
  children?: CompletionItem[];
}

const PROVIDER_FILTERS: CompletionItem[] = [
  { value: "all", description: "All providers" },
  { value: "openai", description: "OpenAI models" },
  { value: "anthropic", description: "Anthropic models" },
  { value: "ollama", description: "Local Ollama models" },
  { value: "cerebras", description: "Cerebras models" },
  { value: "openrouter", description: "OpenRouter models" },
];

const SAVE_FLAG: CompletionItem[] = [
  { value: "--save", description: "Persist to settings" },
];

const MODEL_ALIAS_ITEMS: CompletionItem[] = Object.keys(MODEL_ALIASES).map(
  (alias) => ({
    value: alias,
    description: MODEL_ALIASES[alias],
    children: SAVE_FLAG,
  }),
);

const REASONING_LEVELS: CompletionItem[] = [
  { value: "low", description: "Low reasoning effort", children: SAVE_FLAG },
  { value: "medium", description: "Medium reasoning effort", children: SAVE_FLAG },
  { value: "high", description: "High reasoning effort", children: SAVE_FLAG },
  { value: "off", description: "Disable reasoning", children: SAVE_FLAG },
];

const CHROME_CHANNELS: CompletionItem[] = [
  { value: "stable", description: "Target Chrome Stable", children: SAVE_FLAG },
  { value: "beta", description: "Target Chrome Beta", children: SAVE_FLAG },
  { value: "dev", description: "Target Chrome Dev", children: SAVE_FLAG },
  { value: "canary", description: "Target Chrome Canary", children: SAVE_FLAG },
];

export const COMMAND_COMPLETIONS: CompletionItem[] = [
  { value: "/help", description: "Show available commands" },
  { value: "/new", description: "Start a new session" },
  { value: "/clear", description: "Clear chat messages" },
  { value: "/quit", description: "Quit the application" },
  { value: "/exit", description: "Quit the application" },
  { value: "/status", description: "Show current status" },
  {
    value: "/model",
    description: "Show or switch model",
    children: [
      { value: "list", description: "List available models", children: PROVIDER_FILTERS },
      ...MODEL_ALIAS_ITEMS,
    ],
  },
  {
    value: "/reasoning",
    description: "Set reasoning effort",
    children: REASONING_LEVELS,
  },
  {
    value: "/chrome",
    description: "Show or configure Chrome DevTools MCP",
    children: [
      { value: "status", description: "Show Chrome MCP status" },
      { value: "on", description: "Enable Chrome MCP", children: SAVE_FLAG },
      { value: "off", description: "Disable Chrome MCP", children: SAVE_FLAG },
      { value: "auto", description: "Enable auto-connect mode", children: SAVE_FLAG },
      {
        value: "url",
        description: "Set an explicit Chrome browser URL",
        children: [
          {
            value: "<endpoint>",
            description: "Remote debugging endpoint URL",
            children: SAVE_FLAG,
          },
        ],
      },
      {
        value: "channel",
        description: "Set the Chrome release channel",
        children: CHROME_CHANNELS,
      },
    ],
  },
  {
    value: "/init",
    description: "Workspace initialization and migration",
    children: [
      { value: "status", description: "Show init status" },
      { value: "standard", description: "Initialize the current workspace" },
      { value: "migrate", description: "Open the migration init panel" },
      { value: "open", description: "Open the init panel" },
      { value: "done", description: "Mark the first-run gate complete" },
    ],
  },
];
