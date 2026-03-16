# OpenPlanter

A recursive-language-model investigation agent with a desktop GUI and terminal interface. OpenPlanter ingests heterogeneous datasets — corporate registries, campaign finance records, lobbying disclosures, government contracts, and more — resolves entities across them, and surfaces non-obvious connections through evidence-backed analysis. It operates autonomously with file I/O, shell execution, web search, and recursive sub-agent delegation.

![OpenPlanter Desktop](screenshot.png)

## Download

Pre-built binaries are available on the [Releases page](https://github.com/ShinMegamiBoson/OpenPlanter/releases/latest):

- **macOS** — `.dmg`
- **Windows** — `.msi`
- **Linux** — `.AppImage`

## Desktop App

The desktop app (`openplanter-desktop/`) is a Tauri 2 application with a three-pane layout:

- **Sidebar** — Session management, provider/model settings, and API credential status
- **Chat pane** — Conversational interface showing the agent's objectives, reasoning steps, tool calls, and findings with syntax-highlighted code blocks
- **Knowledge graph** — Interactive Cytoscape.js visualization of entities and relationships discovered during investigation. Nodes are color-coded by category (corporate, campaign-finance, lobbying, contracts, sanctions, etc.). Click a source node to open a slide-out drawer with the full rendered wiki document.

### Features

- **Live knowledge graph** — Entities and connections render in real time as the agent works. Switch between force-directed, hierarchical, and circular layouts. Search and filter by category.
- **Wiki source drawer** — Click any source node to read the full markdown document in a slide-out panel. Internal wiki links navigate between documents and focus the corresponding graph node.
- **Session persistence** — Investigations are saved automatically. Resume previous sessions or start new ones from the sidebar.
- **Background wiki curator** — A lightweight agent runs in the background to keep wiki documents consistent and cross-linked.
- **Multi-provider support** — Switch between OpenAI, Anthropic, OpenRouter, Cerebras, and Ollama (local) from the sidebar.

### Building from Source

```bash
cd openplanter-desktop

# Install frontend dependencies
cd frontend && npm install && cd ..

# Run in development mode
cargo tauri dev

# Build distributable binary
cargo tauri build
```

Requires: Rust stable, Node.js 20+, and platform-specific Tauri dependencies ([see Tauri prerequisites](https://v2.tauri.app/start/prerequisites/)).

If you want the desktop app to control a live Chrome session through Chrome DevTools MCP, keep a local Node/npm install available at runtime. OpenPlanter shells out to `npx -y chrome-devtools-mcp@latest`; it does not bundle the server or launch Chrome for you.

## CLI Agent

The Python CLI agent can be used independently of the desktop app.

### Quickstart

```bash
# Install
pip install -e .

# Configure API keys (interactive prompt)
openplanter-agent --configure-keys

# In this repo, point OpenPlanter at the live workspace from the repo-root .env
echo 'OPENPLANTER_WORKSPACE=workspace' >> .env

# Launch the TUI
openplanter-agent
```

Or run a single task headlessly:

```bash
openplanter-agent --task "Cross-reference vendor payments against lobbying disclosures and flag overlaps" --workspace ./data
```

Chrome DevTools MCP support in the CLI/TUI also uses local `npx`, so install Node.js 20+ if you want to enable Chrome tools there.

### Docker

```bash
# Add your API keys to .env, then:
docker compose up
```

The container mounts `./workspace` as the agent's working directory.

## Supported Providers

| Provider | Default Model | Env Var |
|----------|---------------|---------|
| OpenAI | `gpt-5.2` | `OPENAI_API_KEY` or `OPENAI_OAUTH_TOKEN` |
| Anthropic | `claude-opus-4-6` | `ANTHROPIC_API_KEY` |
| OpenRouter | `anthropic/claude-sonnet-4-5` | `OPENROUTER_API_KEY` |
| Cerebras | `qwen-3-235b-a22b-instruct-2507` | `CEREBRAS_API_KEY` |
| Ollama | `llama3.2` | (none — local) |

### Local Models (Ollama)

[Ollama](https://ollama.com) runs models locally with no API key. Install Ollama, pull a model (`ollama pull llama3.2`), then:

```bash
openplanter-agent --provider ollama
openplanter-agent --provider ollama --model mistral
openplanter-agent --provider ollama --list-models
```

The base URL defaults to `http://localhost:11434/v1` and can be overridden with `OPENPLANTER_OLLAMA_BASE_URL` or `--base-url`. The first request may be slow while Ollama loads the model into memory; a 120-second first-byte timeout is used automatically.

Additional service keys: `EXA_API_KEY` (web search), `VOYAGE_API_KEY` (embeddings), `MISTRAL_TRANSCRIPTION_API_KEY` or `MISTRAL_API_KEY` (audio transcription).

### Audio Transcription

OpenPlanter includes an `audio_transcribe` tool backed by Mistral's offline transcription API. It accepts local workspace audio or video files, returns transcript text plus any timestamps or diarization metadata Mistral provides, and automatically falls back to overlapping chunked transcription for long recordings when `chunking` is left at `auto`.

Useful overrides:

```bash
export MISTRAL_API_KEY=...
export OPENPLANTER_MISTRAL_TRANSCRIPTION_MODEL=voxtral-mini-latest
export OPENPLANTER_MISTRAL_TRANSCRIPTION_MAX_BYTES=104857600
export OPENPLANTER_MISTRAL_TRANSCRIPTION_CHUNK_MAX_SECONDS=900
export OPENPLANTER_MISTRAL_TRANSCRIPTION_CHUNK_OVERLAP_SECONDS=2.0
```

Notes:
- The tool only accepts local workspace files.
- Long-form chunking requires `ffmpeg` and `ffprobe` to be available at runtime.
- `chunking: "force"` always chunks, and `chunking: "off"` keeps the single-upload path.
- Video inputs are audio-extracted with `ffmpeg` before transcription.

All keys can also be set with an `OPENPLANTER_` prefix (e.g. `OPENPLANTER_OPENAI_API_KEY` or `OPENPLANTER_OPENAI_OAUTH_TOKEN`), via `.env` files in the workspace, or via CLI flags.

## Agent Tools

The agent has access to 20 tools, organized around its investigation workflow:

**Dataset ingestion & workspace** — `list_files`, `search_files`, `repo_map`, `read_file`, `write_file`, `edit_file`, `hashline_edit`, `apply_patch` — load, inspect, and transform source datasets; write structured findings.

**Shell execution** — `run_shell`, `run_shell_bg`, `check_shell_bg`, `kill_shell_bg` — run analysis scripts, data pipelines, and validation checks.

**Web** — `web_search` (Exa), `fetch_url` — pull public records, verify entities, and retrieve supplementary data.

**Audio** — `audio_transcribe` — transcribe local audio or video with Mistral, including optional timestamps, diarization, and automatic chunking for long recordings.

**Planning & delegation** — `think`, `subtask`, `execute`, `list_artifacts`, `read_artifact` — decompose investigations into focused sub-tasks, each with acceptance criteria and independent verification.

In **recursive mode** (the default), the agent spawns sub-agents via `subtask` and `execute` to parallelize entity resolution, cross-dataset linking, and evidence-chain construction across large investigations.

When Chrome DevTools MCP is enabled, OpenPlanter discovers Chrome's published MCP tools at solve start and appends them natively to the built-in tool set for the main agent, recursive subtasks, and execute flows.

## Chrome DevTools MCP

OpenPlanter can attach to the official Chrome DevTools MCP server and reuse an active Chrome debugging session. The integration is native in both runtimes, but the server itself is still the upstream package started locally through `npx`.

### Requirements

- Node.js and npm available on your `PATH`
- Chrome 144 or newer
- Remote debugging enabled in Chrome at `chrome://inspect/#remote-debugging`

### How OpenPlanter Connects

- Auto-connect mode: OpenPlanter starts `chrome-devtools-mcp` with `--autoConnect` and reuses a running Chrome session after you approve Chrome's debugging prompt.
- Browser URL mode: OpenPlanter passes `--browserUrl <endpoint>` to attach to an existing remote debugging endpoint. This takes precedence over auto-connect when configured.
- Channel selection: `stable` is the default channel; you can switch to `beta`, `dev`, or `canary` when needed.

If Chrome MCP cannot start because Node/npm is missing, Chrome remote debugging is disabled, or Chrome is not available, OpenPlanter keeps running with its built-in tools and reports Chrome MCP as `unavailable`.

### Desktop Usage

Use the desktop slash command:

```text
/chrome status
/chrome on
/chrome off
/chrome auto --save
/chrome url http://127.0.0.1:9222 --save
/chrome channel beta --save
```

The sidebar and `/status` output both show the current Chrome MCP runtime state.

### CLI Usage

Use per-run flags:

```bash
openplanter-agent --chrome-mcp --chrome-auto-connect
openplanter-agent --chrome-mcp --chrome-browser-url http://127.0.0.1:9222
openplanter-agent --chrome-mcp --chrome-channel beta
```

The TUI also supports `/chrome status|on|off|auto|url <endpoint>|channel <stable|beta|dev|canary> [--save]`.

## CLI Reference

```
openplanter-agent [options]
```

### Workspace & Session

| Flag | Description |
|------|-------------|
| `--workspace DIR` | Explicit non-root workspace override. Repo root is rejected. |
| `--session-id ID` | Use a specific session ID |
| `--resume` | Resume the latest (or specified) session |
| `--list-sessions` | List saved sessions and exit |

### Startup Workspace Resolution

Startup resolves the runtime workspace in this order:

1. Explicit CLI `--workspace` for the Python agent, if provided
2. Process env `OPENPLANTER_WORKSPACE`
3. `OPENPLANTER_WORKSPACE` from the nearest ancestor `.env`
4. Entry-point fallback, followed by repo-root guardrails

Both the CLI and the desktop app refuse to operate directly in repo root. If startup would land on repo root and `<repo>/workspace` exists, OpenPlanter redirects there. Otherwise it exits with an actionable error.

For this repository, the intended local setup is:

```dotenv
OPENPLANTER_WORKSPACE=workspace
```

### Model Selection

| Flag | Description |
|------|-------------|
| `--provider NAME` | `auto`, `openai`, `anthropic`, `openrouter`, `cerebras`, `ollama` |
| `--model NAME` | Model name or `newest` to auto-select |
| `--openai-oauth-token TOKEN` | ChatGPT/OpenAI OAuth token override for OpenAI-compatible models |
| `--reasoning-effort LEVEL` | `low`, `medium`, `high`, or `none` |
| `--chrome-mcp` / `--no-chrome-mcp` | Enable or disable native Chrome DevTools MCP tools |
| `--chrome-auto-connect` / `--no-chrome-auto-connect` | Use Chrome MCP auto-connect or require an explicit browser URL |
| `--chrome-browser-url URL` | Attach Chrome MCP to an existing remote debugging browser URL |
| `--chrome-channel CHANNEL` | Chrome release channel for auto-connect: `stable`, `beta`, `dev`, `canary` |
| `--list-models` | Fetch available models from the provider API |

### Execution

| Flag | Description |
|------|-------------|
| `--task OBJECTIVE` | Run a single task and exit (headless) |
| `--recursive` | Enable recursive sub-agent delegation |
| `--acceptance-criteria` | Judge subtask results with a lightweight model |
| `--max-depth N` | Maximum recursion depth (default: 4) |
| `--max-steps N` | Maximum steps per call (default: 100) |
| `--timeout N` | Shell command timeout in seconds (default: 45) |

### UI

| Flag | Description |
|------|-------------|
| `--no-tui` | Plain REPL (no colors or spinner) |
| `--headless` | Non-interactive mode (for CI) |
| `--demo` | Censor entity names and workspace paths in output |

### Persistent Defaults

Use `--default-model`, `--default-reasoning-effort`, Chrome MCP slash commands with `--save`, or per-provider variants like `--default-model-openai` to save workspace defaults to `.openplanter/settings.json`. View them with `--show-settings`.

## Configuration

Keys are resolved in this priority order (highest wins):

1. CLI flags (`--openai-api-key`, etc.)
2. Environment variables (`OPENAI_API_KEY`, `OPENPLANTER_OPENAI_API_KEY`, `OPENAI_OAUTH_TOKEN`, or `OPENPLANTER_OPENAI_OAUTH_TOKEN`)
3. Nearest ancestor `.env` discovered from the resolved workspace path
4. Workspace credential store (`.openplanter/credentials.json`)
5. User credential store (`~/.openplanter/credentials.json`)

All runtime settings can also be set via `OPENPLANTER_*` environment variables (e.g. `OPENPLANTER_MAX_DEPTH=8`).

## Project Structure

```
openplanter-desktop/         Tauri 2 desktop application
  crates/
    op-tauri/                 Tauri backend (Rust)
      src/commands/           IPC command handlers (agent, wiki, config)
    op-core/                  Shared core library
  frontend/                   TypeScript/Vite frontend
    src/components/           UI components (ChatPane, GraphPane, InputBar, Sidebar)
    src/graph/                Cytoscape.js graph rendering
    src/api/                  Tauri IPC wrappers
    e2e/                      Playwright E2E tests

agent/                        Python CLI agent
  __main__.py                 CLI entry point and REPL
  engine.py                   Recursive language model engine
  runtime.py                  Session persistence and lifecycle
  model.py                    Provider-agnostic LLM abstraction
  builder.py                  Engine/model factory
  tools.py                    Workspace tool implementations
  tool_defs.py                Tool JSON schemas
  prompts.py                  System prompt construction
  config.py                   Configuration dataclass
  credentials.py              Credential management
  tui.py                      Rich terminal UI
  demo.py                     Demo mode (output censoring)
  patching.py                 File patching utilities
  settings.py                 Persistent settings

tests/                        Unit and integration tests
```

## Development

### Desktop App

```bash
cd openplanter-desktop

# Development mode (hot-reload)
cargo tauri dev

# Frontend tests
cd frontend && npm test

# E2E tests (Playwright)
cd frontend && npm run test:e2e

# Backend tests
cargo test
```

### CLI Agent

```bash
# Install in editable mode
pip install -e .

# Run tests
python -m pytest tests/

# Skip live API tests
python -m pytest tests/ --ignore=tests/test_live_models.py --ignore=tests/test_integration_live.py
```

Requires Python 3.10+. Dependencies: `rich`, `prompt_toolkit`, `pyfiglet`.

## License

MIT — see [LICENSE](LICENSE) for details.
