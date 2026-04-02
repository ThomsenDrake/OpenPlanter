# Terminal User Interface

<cite>
**Referenced Files in This Document**
- [textual_tui.py](file://agent/textual_tui.py)
- [tui.py](file://agent/tui.py)
- [demo.py](file://agent/demo.py)
- [wiki_graph.py](file://agent/wiki_graph.py)
- [__main__.py](file://agent/__main__.py)
- [test_textual_tui.py](file://tests/test_textual_tui.py)
- [test_tui_repl.py](file://tests/test_tui_repl.py)
- [README.md](file://README.md)
- [DEMO.md](file://DEMO.md)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document explains the terminal user interface (TUI) functionality for OpenPlanter, focusing on:
- The Rich REPL (with colors and spinners)
- The Textual-based TUI with a wiki knowledge graph panel
- Interactive chat interface and slash command system
- Real-time conversation flow and session management
- Demo mode for anonymized output
- Terminal compatibility and performance considerations
- Troubleshooting guidance for terminal rendering issues

## Project Structure
The terminal UI is implemented primarily in the agent package:
- Rich REPL and plain REPL: [tui.py](file://agent/tui.py)
- Textual TUI with wiki graph: [textual_tui.py](file://agent/textual_tui.py)
- Wiki knowledge graph model and renderer: [wiki_graph.py](file://agent/wiki_graph.py)
- Demo mode output censoring: [demo.py](file://agent/demo.py)
- CLI entry point and mode selection: [__main__.py](file://agent/__main__.py)
- Tests validating TUI behavior: [test_textual_tui.py](file://tests/test_textual_tui.py), [test_tui_repl.py](file://tests/test_tui_repl.py)

```mermaid
graph TB
subgraph "CLI Entrypoint"
MAIN["agent/__main__.py<br/>Mode selection (--no-tui, --textual, --demo)"]
end
subgraph "Rich REPL"
TUI["agent/tui.py<br/>RichREPL, dispatch_slash_command"]
end
subgraph "Textual TUI"
TEXTUAL["agent/textual_tui.py<br/>OpenPlanterApp, ActivityIndicator,<br/>WikiGraphCanvas, message bus"]
WIKI["agent/wiki_graph.py<br/>WikiGraphModel, WikiWatcher"]
DEMO["agent/demo.py<br/>DemoCensor"]
end
MAIN --> TUI
MAIN --> TEXTUAL
TEXTUAL --> WIKI
TEXTUAL --> DEMO
```

**Diagram sources**
- [__main__.py:708-800](file://agent/__main__.py#L708-L800)
- [tui.py:940-1317](file://agent/tui.py#L940-L1317)
- [textual_tui.py:341-789](file://agent/textual_tui.py#L341-L789)
- [wiki_graph.py:243-495](file://agent/wiki_graph.py#L243-L495)
- [demo.py:29-111](file://agent/demo.py#L29-L111)

**Section sources**
- [__main__.py:708-800](file://agent/__main__.py#L708-L800)
- [README.md:55-90](file://README.md#L55-L90)

## Core Components
- Rich REPL: A colorful, spinner-enhanced terminal interface powered by Rich and prompt_toolkit. Supports slash commands, live step rendering, and queued inputs while an agent is running.
- Textual TUI: A widget-based terminal UI using Textual, featuring a chat pane, an activity indicator, a prompt input, and a wiki knowledge graph panel with live updates.
- Slash Command System: A unified dispatcher for commands like /help, /quit, /exit, /status, /clear, /model, /reasoning, /embeddings, and /chrome.
- Demo Mode: Anonymizes workspace paths in TUI output for safe demonstrations.
- Wiki Knowledge Graph: Parses wiki entries, extracts cross-references, and renders a character-cell graph with live filesystem watching.

**Section sources**
- [tui.py:20-31](file://agent/tui.py#L20-L31)
- [tui.py:505-567](file://agent/tui.py#L505-L567)
- [textual_tui.py:341-789](file://agent/textual_tui.py#L341-L789)
- [demo.py:29-111](file://agent/demo.py#L29-L111)
- [wiki_graph.py:243-495](file://agent/wiki_graph.py#L243-L495)

## Architecture Overview
The terminal UI architecture separates concerns between:
- CLI mode selection and runtime configuration
- Rich REPL for immediate, non-blocking interaction
- Textual TUI for advanced visualization and real-time graph updates
- Slash command dispatch and session management
- Demo mode censorship for anonymization

```mermaid
sequenceDiagram
participant User as "User"
participant CLI as "agent/__main__.py"
participant Rich as "RichREPL (tui.py)"
participant Textual as "OpenPlanterApp (textual_tui.py)"
participant Engine as "RLMEngine"
participant Wiki as "WikiGraphModel (wiki_graph.py)"
User->>CLI : "openplanter-agent [--no-tui | --textual | --demo]"
CLI->>CLI : "Resolve workspace, credentials, settings"
alt Rich REPL
CLI->>Rich : "run_rich_repl()"
Rich->>Rich : "dispatch_slash_command()"
Rich->>Engine : "solve(objective, callbacks)"
Engine-->>Rich : "on_event/on_step/on_content_delta"
Rich->>Rich : "render activity/spinner"
else Textual TUI
CLI->>Textual : "run_textual_app()"
Textual->>Wiki : "WikiGraphModel.rebuild()"
Textual->>Engine : "solve(objective, callbacks)"
Engine-->>Textual : "AgentEvent/AgentStepEvent/AgentContentDelta"
Textual->>Textual : "render chat + activity + graph"
end
```

**Diagram sources**
- [__main__.py:708-800](file://agent/__main__.py#L708-L800)
- [tui.py:940-1317](file://agent/tui.py#L940-L1317)
- [textual_tui.py:547-693](file://agent/textual_tui.py#L547-L693)
- [wiki_graph.py:264-302](file://agent/wiki_graph.py#L264-L302)

## Detailed Component Analysis

### Rich REPL (with colors and spinners)
The Rich REPL provides a fully interactive terminal experience with:
- Colorful output via Rich
- Spinner-like activity display for thinking, streaming, tool execution, and tool argument generation
- Slash command handling and queued input processing
- Demo mode integration for anonymized output

Key behaviors:
- Slash commands are dispatched before launching the agent
- While an agent is running, non-slash inputs are queued and executed after completion
- Activity transitions from thinking to streaming when text deltas arrive
- Tool calls are tracked and rendered with elapsed time and error flags

```mermaid
classDiagram
class RichREPL {
+ChatContext ctx
+Console console
+dict _startup_info
+_StepState _current_step
+Thread _agent_thread
+run()
+dispatch_slash_command()
+_on_event()
+_on_step()
+_on_content_delta()
}
class ActivityDisplay {
+start(mode, step_label)
+feed(delta_type, text)
+set_tool(tool_name, key_arg, step_label)
+stop()
}
RichREPL --> ActivityDisplay : "uses"
```

**Diagram sources**
- [tui.py:940-1317](file://agent/tui.py#L940-L1317)
- [tui.py:698-939](file://agent/tui.py#L698-L939)

**Section sources**
- [tui.py:940-1317](file://agent/tui.py#L940-L1317)
- [tui.py:698-939](file://agent/tui.py#L698-L939)
- [test_tui_repl.py:231-333](file://tests/test_tui_repl.py#L231-L333)

### Textual-based TUI with wiki knowledge graph panel
The Textual TUI offers a widget-based layout with:
- Chat pane: RichLog for message history, ActivityIndicator for live status, Input for prompts
- Graph pane: WikiGraphCanvas rendering a force-directed graph of wiki sources
- Message bus: AgentEvent, AgentStepEvent, AgentContentDelta, AgentComplete, WikiChanged
- Live graph updates via WikiWatcher polling the wiki directory

```mermaid
classDiagram
class OpenPlanterApp {
+ChatContext ctx
+bool _agent_running
+list _queued_inputs
+compose()
+on_input_submitted()
+_run_agent(objective)
+on_agent_event()
+on_agent_step_event()
+on_agent_content_delta()
+on_agent_complete()
+on_wiki_changed()
+action_cancel_agent()
}
class ActivityIndicator {
+reactive mode
+start_activity(mode, step_label)
+feed(delta_type, text)
+set_tool(tool_name, key_arg, step_label)
+stop_activity()
+render() Text
}
class WikiGraphCanvas {
+Path _wiki_dir
+WikiGraphModel _model
+on_mount()
+rebuild()
+render() Text
+node_count() int
+edge_count() int
}
OpenPlanterApp --> ActivityIndicator : "uses"
OpenPlanterApp --> WikiGraphCanvas : "uses"
```

**Diagram sources**
- [textual_tui.py:341-789](file://agent/textual_tui.py#L341-L789)
- [textual_tui.py:106-257](file://agent/textual_tui.py#L106-L257)
- [textual_tui.py:279-335](file://agent/textual_tui.py#L279-L335)

**Section sources**
- [textual_tui.py:341-789](file://agent/textual_tui.py#L341-L789)
- [test_textual_tui.py:176-250](file://tests/test_textual_tui.py#L176-L250)

### Slash Command System
The slash command system supports:
- /help: Displays available commands and usage
- /status: Shows provider, model, reasoning effort, embeddings, tokens, and Chrome MCP status
- /clear: Clears the chat log
- /quit /exit: Exits the application
- /model: Switch models, list providers/models, persist defaults
- /reasoning: Adjust reasoning effort and persist
- /embeddings: Switch embeddings provider and persist
- /chrome: Control Chrome DevTools MCP (status, on/off/auto/url/channel) and persist

```mermaid
flowchart TD
Start(["Input received"]) --> CheckSlash{"Starts with '/'?"}
CheckSlash --> |No| PassThrough["Pass to agent solver"]
CheckSlash --> |Yes| Dispatch["dispatch_slash_command()"]
Dispatch --> Quit{"Is '/quit' or '/exit'?"}
Quit --> |Yes| ExitApp["Exit application"]
Quit --> |No| Help{"Is '/help'?"}
Help --> |Yes| ShowHelp["Emit help lines"]
Help --> |No| Status{"Is '/status'?"}
Status --> |Yes| ShowStatus["Emit status info"]
Status --> |No| Clear{"Is '/clear'?"}
Clear --> |Yes| ClearLog["Clear message log"]
Clear --> |No| Model{"Is '/model'?"}
Model --> |Yes| HandleModel["handle_model_command()"]
Model --> |No| Reasoning{"Is '/reasoning'?"}
Reasoning --> |Yes| HandleReasoning["handle_reasoning_command()"]
Reasoning --> |No| Embeddings{"Is '/embeddings'?"}
Embeddings --> |Yes| HandleEmbeddings["handle_embeddings_command()"]
Embeddings --> |No| Chrome{"Is '/chrome'?"}
Chrome --> |Yes| HandleChrome["handle_chrome_command()"]
Chrome --> |No| Unknown["Unknown command"]
ShowHelp --> End(["Handled"])
ShowStatus --> End
ClearLog --> End
HandleModel --> End
HandleReasoning --> End
HandleEmbeddings --> End
HandleChrome --> End
ExitApp --> End
PassThrough --> End
Unknown --> End
```

**Diagram sources**
- [tui.py:505-567](file://agent/tui.py#L505-L567)
- [tui.py:222-316](file://agent/tui.py#L222-L316)
- [tui.py:319-357](file://agent/tui.py#L319-L357)
- [tui.py:414-438](file://agent/tui.py#L414-L438)
- [tui.py:441-502](file://agent/tui.py#L441-L502)

**Section sources**
- [tui.py:20-31](file://agent/tui.py#L20-L31)
- [tui.py:114-124](file://agent/tui.py#L114-L124)
- [tui.py:505-567](file://agent/tui.py#L505-L567)

### Real-time Conversation Flow
The conversation flow integrates agent callbacks with UI rendering:
- AgentEvent: Parses trace prefixes and transitions activity modes
- AgentStepEvent: Builds step state, tracks tool calls, and flags errors
- AgentContentDelta: Feeds text deltas to the activity indicator
- AgentComplete: Renders final markdown result, token summary, and processes queued inputs

```mermaid
sequenceDiagram
participant UI as "OpenPlanterApp"
participant Engine as "RLMEngine"
participant Log as "RichLog"
participant Act as "ActivityIndicator"
UI->>Engine : "solve(objective, on_event, on_step, on_content_delta)"
Engine-->>UI : "AgentEvent('calling model')"
UI->>Act : "start_activity('thinking')"
Engine-->>UI : "AgentEvent('>> entering subtask/executing leaf')"
UI->>Act : "stop_activity()"
Engine-->>UI : "AgentEvent('tool_name(args)')"
UI->>Act : "set_tool(tool_name, key_arg)"
Engine-->>UI : "AgentContentDelta('text'|'thinking'|'tool_call_args')"
UI->>Act : "feed(delta_type, text)"
Engine-->>UI : "AgentComplete(result)"
UI->>Log : "render markdown result"
UI->>Log : "emit token summary"
UI->>UI : "process _queued_inputs"
```

**Diagram sources**
- [textual_tui.py:575-693](file://agent/textual_tui.py#L575-L693)
- [textual_tui.py:709-770](file://agent/textual_tui.py#L709-L770)

**Section sources**
- [textual_tui.py:575-693](file://agent/textual_tui.py#L575-L693)
- [textual_tui.py:709-770](file://agent/textual_tui.py#L709-L770)

### Wiki Knowledge Graph Integration
The wiki graph panel:
- Parses wiki/index.md and individual markdown files to extract cross-references
- Builds a NetworkX graph and computes a spring layout scaled to character cells
- Renders a character-cell visualization with node colors by category
- Watches the wiki directory for changes and rebuilds the graph live

```mermaid
flowchart TD
Start(["WikiGraphCanvas.render()"]) --> CheckModel{"Has WikiGraphModel?"}
CheckModel --> |No| NoData["Return 'No wiki data'"]
CheckModel --> |Yes| ComputeLayout["Compute spring layout"]
ComputeLayout --> InitBuf["Initialize buffer"]
InitBuf --> DrawEdges["Draw edges with Bresenham"]
DrawEdges --> DrawNodes["Draw nodes and labels"]
DrawNodes --> ReturnBuf["Return 2D buffer of (char, color)"]
```

**Diagram sources**
- [wiki_graph.py:348-406](file://agent/wiki_graph.py#L348-L406)
- [textual_tui.py:279-335](file://agent/textual_tui.py#L279-L335)

**Section sources**
- [wiki_graph.py:243-495](file://agent/wiki_graph.py#L243-L495)
- [textual_tui.py:279-335](file://agent/textual_tui.py#L279-L335)

### Demo Mode for Anonymized Output
Demo mode censors workspace path segments in TUI output:
- Builds replacement tables from the workspace path
- Preserves Rich Text style spans by replacing characters with block characters of equal length
- Applies to text, markdown, and rules before display

```mermaid
flowchart TD
Start(["DemoCensor.censor_text(text)"]) --> Decompose["Decompose workspace path into parts"]
Decompose --> Filter["Filter out generic path parts"]
Filter --> Sort["Sort by length (longest first)"]
Sort --> Replace["Replace each segment with block chars"]
Replace --> Return["Return censored text"]
```

**Diagram sources**
- [demo.py:29-111](file://agent/demo.py#L29-L111)

**Section sources**
- [demo.py:29-111](file://agent/demo.py#L29-L111)
- [__main__.py:517-519](file://agent/__main__.py#L517-L519)

## Dependency Analysis
The terminal UI components depend on:
- Rich and prompt_toolkit for Rich REPL
- Textual for the TUI widgets and message bus
- NetworkX for the wiki graph layout
- Engine callbacks for real-time agent events

```mermaid
graph TB
TUI["agent/tui.py"] --> ENGINE["RLMEngine"]
TEXTUAL["agent/textual_tui.py"] --> ENGINE
TEXTUAL --> WIKI["agent/wiki_graph.py"]
TEXTUAL --> DEMO["agent/demo.py"]
MAIN["agent/__main__.py"] --> TUI
MAIN --> TEXTUAL
```

**Diagram sources**
- [tui.py:13-16](file://agent/tui.py#L13-L16)
- [textual_tui.py:25-42](file://agent/textual_tui.py#L25-L42)
- [wiki_graph.py:17-21](file://agent/wiki_graph.py#L17-L21)
- [__main__.py:35](file://agent/__main__.py#L35)

**Section sources**
- [tui.py:13-16](file://agent/tui.py#L13-L16)
- [textual_tui.py:25-42](file://agent/textual_tui.py#L25-L42)
- [wiki_graph.py:17-21](file://agent/wiki_graph.py#L17-L21)
- [__main__.py:35](file://agent/__main__.py#L35)

## Performance Considerations
- Rich REPL: Uses a Live renderer at 8fps for smooth spinner updates; minimal overhead for small terminal sizes.
- Textual TUI: Character-cell rendering scales with terminal dimensions; layout recomputation occurs on resize and graph rebuild.
- Wiki graph: Spring layout computation is O(N^2) in worst case; caching and incremental rebuilds reduce cost.
- Demo mode: String replacement operations scale linearly with output length; minimal impact on agent throughput.
- Terminal compatibility: Rich REPL requires ANSI-capable terminals; Textual relies on Textual’s rendering pipeline.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common terminal rendering issues and resolutions:
- Rich REPL spinner not updating:
  - Ensure the terminal supports ANSI sequences and cursor control.
  - Verify Rich and prompt_toolkit are installed.
- Textual TUI not displaying:
  - Confirm Textual is installed and the terminal supports Unicode block characters.
  - Check that the terminal size is sufficient for the layout.
- Wiki graph not appearing:
  - Ensure the wiki directory exists and contains index.md and markdown files.
  - Verify NetworkX is installed for graph layout calculations.
- Demo mode not censoring:
  - Confirm demo mode is enabled via CLI flag.
  - Verify workspace path resolution is correct.

**Section sources**
- [README.md:444](file://README.md#L444)
- [__main__.py:517-519](file://agent/__main__.py#L517-L519)

## Conclusion
OpenPlanter’s terminal UI provides two complementary experiences:
- Rich REPL for quick, colorful interaction with live activity feedback
- Textual TUI for advanced visualization with a live wiki knowledge graph

Both integrate a robust slash command system, real-time conversation flow, and demo mode for anonymized output. Choose Rich REPL for simplicity and speed, or Textual TUI for richer visual context and graph exploration.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### Practical Examples
- Interactive investigations:
  - Use /help to explore available commands.
  - Use /status to verify model and provider configuration.
  - Use /model and /reasoning to adjust agent behavior.
  - Use /embeddings and /chrome to configure retrieval and browser tools.
- Session management:
  - Use /clear to reset the conversation.
  - Use /quit or /exit to terminate the session.
- Real-time flow:
  - Observe thinking, streaming, and tool execution phases in the activity indicator.
  - Review step headers, model previews, and tool call trees after completion.

**Section sources**
- [tui.py:114-124](file://agent/tui.py#L114-L124)
- [textual_tui.py:575-693](file://agent/textual_tui.py#L575-L693)
- [DEMO.md:9-120](file://DEMO.md#L9-L120)