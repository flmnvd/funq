# Funq MCP server

A local stdio MCP server for inspecting and exercising an already running
Funq-enabled Qt application. It uses the Python client in `../client`; the Qt
plugin and the application do not need MCP-specific changes.

The same server supports Codex, Claude Desktop, Claude Code, and DeepSeek
Harness through standard MCP over stdio. All 16 tools, error results, and native
PNG screenshots are available to each client. No provider API key is required by
this server.

## Setup

Use Python 3.10 or newer. From this directory on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The MCP SDK is the v1 `mcp` package, not the separate `fastmcp` distribution.
Installing Funq's legacy `nose` runner is unnecessary: the server imports the
client directly from the sibling checkout.

Run the server with:

```powershell
.\.venv\Scripts\python.exe -B .\run_server.py
```

The process speaks MCP on stdin/stdout. Diagnostic logging goes to stderr.
Do not expect a GUI or an interactive console prompt. `run_server.cmd` is a
convenience launcher. To use a different Funq checkout or artifact location:

```powershell
.\.venv\Scripts\python.exe -B .\run_server.py --funq-root Z:\rapps3\Tests\funq --artifact-dir Z:\rapps3\Tests\funq\mcp\artifacts
```

On Linux/macOS use `.venv/bin/python` in the commands above. Installation as a
package is also supported with `python -m pip install .`; run `funq-mcp` with
an explicit `--funq-root` and `--artifact-dir` when installed outside this checkout.

## Connect Codex

Copy the table in `codex-config.example.toml` into the user or trusted project
Codex `config.toml`, or register it through the CLI:

```powershell
codex mcp add funq -- Z:\rapps3\Tests\funq\mcp\.venv\Scripts\python.exe -B Z:\rapps3\Tests\funq\mcp\run_server.py
```

Restart/reconnect the MCP client after changing configuration. This project does
not edit your Codex configuration automatically.

## Connect Claude Desktop

Open Claude Desktop's **Settings > Developer > Edit Config**. On Windows the
file is `%APPDATA%\Claude\claude_desktop_config.json`; on macOS it is
`~/Library/Application Support/Claude/claude_desktop_config.json`.

Merge the `funq` entry from [claude-desktop-config.example.json](claude-desktop-config.example.json)
into that file's `mcpServers` object, preserving any existing entries. The example
uses this checkout's absolute Windows paths. Update them for a different checkout
or platform; on macOS/Linux use the virtual environment's `bin/python` executable.
The JSON backslashes in Windows paths must remain doubled.

Completely quit and restart Claude Desktop after saving. The Python executable,
script, Funq checkout, and artifact directory are specified explicitly, so the
server does not depend on Claude's working directory or shell activation.
If the `Z:` drive is unavailable to Claude, use paths visible to the Windows
account running Claude.

See the [official local MCP setup guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
for configuration and connection troubleshooting.

## Connect Claude Code

From the project where you want to use Funq, register the local stdio server:

```powershell
claude mcp add --transport stdio --scope local funq -- Z:\rapps3\Tests\funq\mcp\.venv\Scripts\python.exe -B Z:\rapps3\Tests\funq\mcp\run_server.py --funq-root Z:\rapps3\Tests\funq --artifact-dir Z:\rapps3\Tests\funq\mcp\artifacts
claude mcp get funq
```

Use `--scope user` to make it available across your projects. For a shared project
configuration, merge [claude-code-config.example.json](claude-code-config.example.json)
into `.mcp.json` at your project root, adapting its paths for the machines using it.
In an interactive Claude Code session, approve the project server when prompted.
Restart an existing session after registration and use `/mcp` to check the
connection. These examples do not change your Claude configuration automatically.

See [Claude Code's MCP documentation](https://code.claude.com/docs/en/mcp)
for scopes and configuration details.

## Connect DeepSeek Harness

DSH (DeepSeek Harness) uses its bundled MCP client plugin,
`@deepseek-ai/dsh-mcp-client`. MCP servers are not configured in a separate JSON
file: each server is a row in the active profile's `cordis.patch.yml`, next to
the harness's other plugin settings.

Find the profile directory first. The desktop app uses
`%USERPROFILE%\.dsh\profiles\<profile>\` (the name is in `DSH_PROFILE`; the
shipped desktop profile is `desktop`). Append this block to that profile's
`cordis.patch.yml`:

```yaml
- insert:
    - id: mcp-funq
      name: "@deepseek-ai/dsh-mcp-client"
      config:
        serverName: funq
        transport: stdio
        command: 'Z:\rapps3\Tests\funq\mcp\.venv\Scripts\python.exe'
        args:
          - '-B'
          - 'Z:\rapps3\Tests\funq\mcp\run_server.py'
          - '--funq-root'
          - 'Z:\rapps3\Tests\funq'
          - '--artifact-dir'
          - 'Z:\rapps3\Tests\funq\mcp\artifacts'
        cwd: 'Z:\rapps3\Tests\funq\mcp'
        toolCallTimeoutMs: 60000
```

Use the `insert:` form for a new row; a bare `- id:` entry only overrides a row
that a bundle already defines. Single-quoted YAML keeps Windows backslashes
literal. Adjust the paths for another checkout or platform; on macOS/Linux use
the virtual environment's `bin/python`.

Save the file. Profiles with HMR enabled — including the shipped web and desktop
compositions — reload the patch and start the server immediately; otherwise
restart DSH. The tools then appear as `mcp__funq__funq_attach`,
`mcp__funq__funq_snapshot`, and so on, and the server's instructions are added to
the harness prompt. Remove the inserted block (or set `disabled: true` on the
row) to unload the server the same way.

Notes:

- `serverName` becomes the tool namespace and must match
  `[A-Za-z0-9_-]{1,32}`; keep `funq`.
- DSH scrubs ambient `*KEY*`, `*PASSWORD*`, `*SECRET*`, `*TOKEN*`, and `DSH_*`
  variables from stdio children; this server needs none of them.
- The plugin ships with current DSH builds. If DSH reports that the package
  cannot be resolved, the build predates the bundled MCP client; update DSH.
- The profile entry is global to that profile, not per project. Its 16 tool
  schemas and the server instructions are sent with every request.

## Start a GUI test

Start one Funq-enabled application using its normal test launch procedure and
record its port. For R-Studio, use the existing instructions in
`../../FunqTests/file_mask_runtime_runbook.md`. The MCP server neither launches
the application nor calls Funq's `quit` command. `funq_detach` closes only the
test socket. Match the Funq plugin to the application's Qt version, bitness,
compiler/runtime, and Debug/Release build as required by the existing setup.

Suggested first request to Codex, Claude, or DeepSeek Harness:

> Use Funq on the explicit port 52777. Attach with expected_class CMainWindow,
> inspect visible widgets, and capture a screenshot. Report any startup dialog
> before proceeding with the requested test.

Keep the Funq listener on loopback for local testing. Remote hosts can be passed
to `funq_attach`; Funq's TCP protocol itself has no authentication or encryption.

## Tools

| Tool | Behavior |
| --- | --- |
| `funq_attach` | Require `port`; optionally specify `host`, `expected_class`, and connection/handshake `timeout`. |
| `funq_sessions` | List session IDs and connection state. |
| `funq_detach` | Close and discard one connection, leaving the application running. |
| `funq_snapshot` | Compact widget records with properties, classes, and paths; optional subtree, visibility filtering, and output pagination. |
| `funq_find` | Resolve one object immediately; fail on absent or ambiguous selectors. |
| `funq_inspect` | Read Qt properties; save full values when their summaries are truncated. |
| `funq_click` | Click a widget center; support left/middle/right and left double-click. |
| `funq_trigger` | Schedule a QAction with `blocking=false`, allowing modal dialogs to open. |
| `funq_type` | Focus a widget and send text; `replace=true` uses Ctrl+A and Backspace. |
| `funq_shortcut` | Send a Qt key sequence to a widget. |
| `funq_set_properties` | Assign properties for fixture setup and read them back for verification. |
| `funq_close_widget` | Schedule a widget close; verify disappearance or visibility with `funq_wait`. |
| `funq_wait` | Poll for existence, absence, or exact property values. |
| `funq_model_read` | Return tree/table model cells and their parent index paths. |
| `funq_model_select` | Select, edit, click, or double-click a view cell. |
| `funq_screenshot` | Return native MCP PNG image content plus a saved file path. |

GUI tools take a `session_id` returned by `funq_attach`. Selectors contain exactly
one of `path` or `object_name`:

```json
{"object_name": "Tools::s_pSettings", "class_name": "QAction"}
```

```json
{"path": "main/settingsDialog/nameEdit"}
```

Paths are the real values returned by Funq, not invented widget labels. Names
are exact Qt `objectName` values, including any namespace prefix. `class_name`
is available for object-name lookups. Reuse selectors, not pointer-derived
object IDs: every operation resolves its selector again. Missing objects return
`ObjectNotFound`; ambiguous matches return `AmbiguousObjectMatch`.

A typical interaction is:

1. `funq_attach(port=<reported port>, expected_class="CMainWindow")`.
2. `funq_snapshot(session_id=...)` and `funq_inspect` to identify the intended action.
3. `funq_trigger(session_id=..., selector={"object_name": "<action objectName>"})`.
4. `funq_wait` for the expected dialog with `properties={"visible": true}`.
5. Perform input and inspect or wait for the expected outcome.
6. Capture a screenshot; close the test dialog and verify it is hidden.
7. Detach when finished.

For model operations, `itempath` identifies the item's **parent** index chain:
`2-0/4-0` means parent row 2 column 0, then parent row 4 column 0.
The target item's own `row` and `column` are separate arguments. Omit `itempath`
for top-level cells.

## Results and failure behavior

Tools return both JSON text and MCP `structuredContent`:

```json
{"ok": true, "data": {"status": "dispatched", "verification_required": true}}
```

Application actions return **dispatched**, not a test pass. Wait for or inspect the
observable GUI result before declaring success. Direct property assignment is
fixture setup and does not exercise keyboard validation; typing does.

Errors set MCP `isError=true` and include `ok=false`, `error.code`, and
`error.message`. Operation errors also include saved diagnostic artifact paths.
Events are always attempted; a full widget tree and desktop PNG are captured
when the connection is still usable and operation time remains. Evidence cannot
be fetched through a disconnected or unresponsive application.

Requests on one GUI session are serialized, including multi-command operations.
The same endpoint cannot be attached twice through host aliases within one MCP
server. Each independent MCP server process still needs its own application or
external coordination; this server does not lock out other Funq clients.

A network timeout, EOF, invalid frame, or unsolicited event closes the socket.
After `RequestTimeout` or `ConnectionLost`, a mutating operation may already have
run. It is never automatically replayed. Detach the broken session, attach again,
inspect the GUI state, and then decide whether further action is needed.
`ConditionTimeout` means an observable wait failed; it normally leaves the
connection usable. Unsupported plugin commands fail before sending a request.

Tool deadlines are at most 50 seconds and default to 10. A deadline covers the
session queue and all requests within the operation. TCP connect uses a bounded
socket timeout; OS hostname resolution can have its own timing. For longer GUI
tasks, dispatch the action and inspect its progress in subsequent calls.

Artifacts are saved in `artifacts/<session_id>/` by default. Large widget/property
values are summarized in tool output, with full JSON saved when truncated.
Snapshot/model pages have a roughly 32k-character output budget. Response frames
are capped at 32 MiB; use `--max-frame-mb` to configure the limit.

## Current scope

- Qt Widgets and QAction operations supported by the local Funq plugin.
- Model pagination limits **MCP output only**: the plugin currently traverses the
  complete model before responding. Use bounded test fixtures. True pagination
  would need a separate plugin change.
- Native OS dialogs and dedicated QML/Qt Quick item discovery are not exposed by
  this first adapter. Discovering a Qt Quick window does not imply item support.
- Click handlers can themselves block on a modal dialog; prefer nonblocking
  QAction triggers where available.
- Keyboard text behavior, focus, and shortcuts depend on the application and
  platform. Verify text after entry, especially with Unicode or custom editors.
- Registered test execution, application launching, and arbitrary slot/Python
  execution are outside this adapter's current tool set.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install "pytest>=8"
.\.venv\Scripts\python.exe -B -m pytest -q
```

Tests use the real sibling Funq Python client and a fake TCP endpoint; they never
launch or interact with R-Studio. They cover TCP framing and deadlines, ambiguous
selectors, changing object IDs, modal action dispatch, Unicode payloads, property
verification, serialized operations, pagination, diagnostics, and an end-to-end
MCP stdio client session including native image content. The stdio checks also
launch both Claude configuration examples from an unrelated working directory
and verify that JSON text results agree with `structuredContent`.

Claude Code 2.1.117 also connected successfully using the supplied `.mcp.json`
entry and `claude mcp get funq` in an isolated temporary project. This checks the
host connection without a model request. The Claude Desktop application itself
has not been exercised by these checks.

DeepSeek Harness 0.2.1-rc.3 connected successfully through the profile entry
above: the server hot-reloaded as `mcp__funq__*` tools, `mcp__funq__funq_sessions`
returned `{"ok": true, "data": []}`, and a live R-Studio build was driven through
attach, dialog click, snapshot, and native PNG screenshot.

Set `FUNQ_ROOT` when running tests outside the Funq checkout. Live application
validation remains a separate step requiring a running Funq-enabled application
and its explicitly supplied port.
