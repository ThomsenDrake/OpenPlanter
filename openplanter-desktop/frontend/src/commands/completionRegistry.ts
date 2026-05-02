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
  { value: "zai", description: "Z.AI models" },
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

const WEB_SEARCH_PROVIDERS: CompletionItem[] = [
  { value: "exa", description: "Use Exa for web search", children: SAVE_FLAG },
  { value: "firecrawl", description: "Use Firecrawl for web search", children: SAVE_FLAG },
  { value: "brave", description: "Use Brave Search for web search", children: SAVE_FLAG },
  { value: "tavily", description: "Use Tavily for web search", children: SAVE_FLAG },
];

const EMBEDDINGS_PROVIDERS: CompletionItem[] = [
  { value: "voyage", description: "Use Voyage embeddings", children: SAVE_FLAG },
  { value: "mistral", description: "Use Mistral embeddings", children: SAVE_FLAG },
];

const CONTINUITY_MODES: CompletionItem[] = [
  { value: "auto", description: "Infer follow-ups automatically", children: SAVE_FLAG },
  { value: "fresh", description: "Force a fresh turn context", children: SAVE_FLAG },
  { value: "continue", description: "Force prior-turn continuity", children: SAVE_FLAG },
];

const RECURSION_FLAGS: CompletionItem[] = [
  {
    value: "--min",
    description: "Require delegation down to at least this depth",
    children: [{ value: "<n>", description: "Non-negative minimum depth", children: SAVE_FLAG }],
  },
  {
    value: "--max",
    description: "Set the maximum recursion depth",
    children: [{ value: "<n>", description: "Non-negative maximum depth", children: SAVE_FLAG }],
  },
  ...SAVE_FLAG,
];

const RECURSION_MODES: CompletionItem[] = [
  { value: "flat", description: "Disable recursion", children: RECURSION_FLAGS },
  { value: "auto", description: "Use heuristic recursion", children: RECURSION_FLAGS },
  { value: "force-max", description: "Force delegation to max depth", children: RECURSION_FLAGS },
];

const ZAI_PLANS: CompletionItem[] = [
  { value: "paygo", description: "Use the Z.AI PAYGO endpoint", children: SAVE_FLAG },
  { value: "coding", description: "Use the Z.AI Coding Plan endpoint", children: SAVE_FLAG },
];

const CHROME_CHANNELS: CompletionItem[] = [
  { value: "stable", description: "Target Chrome Stable", children: SAVE_FLAG },
  { value: "beta", description: "Target Chrome Beta", children: SAVE_FLAG },
  { value: "dev", description: "Target Chrome Dev", children: SAVE_FLAG },
  { value: "canary", description: "Target Chrome Canary", children: SAVE_FLAG },
];

const OBSIDIAN_MODES: CompletionItem[] = [
  { value: "fresh-vault", description: "Export directly into a fresh Obsidian vault" },
  { value: "existing-vault-folder", description: "Export into a folder inside an existing vault" },
];

const OBSIDIAN_ENABLE_ARGS: CompletionItem[] = [
  {
    value: "<vault-path>",
    description: "Path to a fresh vault or existing vault root",
    children: [
      { value: "--mode", description: "Choose the export mode", children: OBSIDIAN_MODES },
      { value: "--subdir", description: "Folder name inside an existing vault", children: [{ value: "OpenPlanter", description: "Default export folder" }] },
      { value: "--no-canvas", description: "Skip JSON Canvas generation" },
    ],
  },
];

const MISTRAL_VALUE: CompletionItem[] = [
  { value: "<value>", description: "Workspace API key value" },
];

function createMistralKeyActions(label: string): CompletionItem[] {
  return [
    {
      value: "set",
      description: `Save the ${label} workspace key`,
      children: MISTRAL_VALUE,
    },
    {
      value: "clear",
      description: `Clear the ${label} workspace key`,
    },
  ];
}

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
    value: "/zai-plan",
    description: "Show or switch the Z.AI endpoint family",
    children: ZAI_PLANS,
  },
  {
    value: "/embeddings",
    description: "Show or switch the embeddings provider",
    children: EMBEDDINGS_PROVIDERS,
  },
  {
    value: "/web-search",
    description: "Show or switch the web search provider",
    children: WEB_SEARCH_PROVIDERS,
  },
  {
    value: "/continuity",
    description: "Show or switch follow-up continuity mode",
    children: CONTINUITY_MODES,
  },
  {
    value: "/recursion",
    description: "Show or configure recursion behavior",
    children: RECURSION_MODES,
  },
  {
    value: "/reasoning",
    description: "Set reasoning effort",
    children: REASONING_LEVELS,
  },
  {
    value: "/mistral",
    description: "Show or configure Mistral tool credentials",
    children: [
      { value: "status", description: "Show Mistral key status" },
      {
        value: "key-mode",
        description: "Choose which key Document AI uses",
        children: [
          {
            value: "shared",
            description: "Use the shared Mistral key for Document AI",
            children: SAVE_FLAG,
          },
          {
            value: "override",
            description: "Use the Document AI override key",
            children: SAVE_FLAG,
          },
        ],
      },
      {
        value: "shared-key",
        description: "Manage the shared Mistral key",
        children: createMistralKeyActions("shared Mistral"),
      },
      {
        value: "docai-key",
        description: "Manage the Document AI override key",
        children: createMistralKeyActions("Document AI override"),
      },
      {
        value: "transcription-key",
        description: "Manage the transcription key",
        children: createMistralKeyActions("transcription"),
      },
    ],
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
    value: "/obsidian",
    description: "Show, configure, export, or open Obsidian investigation packs",
    children: [
      { value: "status", description: "Show Obsidian export status" },
      { value: "enable", description: "Enable generated Obsidian exports", children: OBSIDIAN_ENABLE_ARGS },
      { value: "disable", description: "Disable generated Obsidian exports" },
      { value: "export", description: "Export the active investigation pack" },
      { value: "open", description: "Export and open the active investigation in Obsidian" },
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
