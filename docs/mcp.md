# MCP integration

The MCP process is a thin adapter over the SourceRecall HTTP API. It does not
index repositories, access Qdrant, or implement a second retrieval pipeline.

## Tools

- `search_codebase(repository, query, limit)` — hybrid and reranked retrieval
- `get_file(repository, path)` — bounded source-file read
- `list_repositories()` — repository discovery and index state
- `get_index_status()` — service/model/schema/index metadata

The initial MCP surface is read-only. Administrative indexing remains in the
CLI and HTTP API so an agent cannot silently mutate the index.

## Session model

The remote Streamable HTTP transport runs with `stateless_http=True`. The four
tools are independent API calls and do not require MCP session state, sampling,
resource subscriptions, or unsolicited server-to-client messages. Stateless
operation prevents a server or cluster restart from leaving clients with an
expired in-memory MCP session identifier.

The local `stdio` transport remains process-scoped and is unaffected by the
HTTP session setting.

## Client setup

The deployed Streamable HTTP endpoint is
`http://source-recall:8071/mcp/` by default. Replace `source-recall` in the
examples below with a hostname or IP address that the client can reach.

Connecting a client makes the four SourceRecall tools available. The optional
retrieval-policy files under [`contrib/`](../contrib/) are a separate step:
they teach the client when semantic or cross-repository retrieval is useful and
when the live workspace should remain authoritative.

## VS Code native agent

VS Code's native agent supports remote Streamable HTTP MCP servers. To add
SourceRecall through the UI:

1. Run **MCP: Add Server** from the Command Palette.
2. Select HTTP and enter `http://source-recall:8071/mcp/`.
3. Name the server `sourceRecall`.
4. Choose **Global** to make it available in every workspace, or **Workspace**
   to add it only to the current workspace.
5. Approve the server trust prompt, then run **MCP: List Servers** to confirm
   that SourceRecall is running and exposes its four tools.

You can instead add the server manually to the VS Code user MCP configuration
or to `.vscode/mcp.json` in a workspace:

```json
{
  "servers": {
    "sourceRecall": {
      "type": "http",
      "url": "http://source-recall:8071/mcp/"
    }
  }
}
```

User configuration is a good fit when one SourceRecall deployment serves many
repositories. Workspace configuration is useful when the endpoint should be
shared with that repository's contributors. See the official
[VS Code MCP guide](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
for configuration locations and server-management commands.

### Install the VS Code retrieval policy

Copy
[`contrib/vscode/source-recall.instructions.md`](../contrib/vscode/source-recall.instructions.md)
to one of VS Code's instruction locations:

- User-wide: `~/.copilot/instructions/source-recall.instructions.md`
- Current workspace:
  `.github/instructions/source-recall.instructions.md`

The template has `applyTo: '**'`, so VS Code applies it throughout the selected
scope. It directs the agent to use SourceRecall for semantic, architectural,
and cross-repository discovery, then switch to native workspace tools before
making claims about or editing the current working tree.

Run **Chat: Open Customizations** to confirm that the instruction is detected.
If it does not appear in a response, use the Chat customization diagnostics to
check its location and frontmatter. See the official
[VS Code custom-instructions guide](https://code.visualstudio.com/docs/agent-customization/custom-instructions)
for details.

### VS Code workflow

The native VS Code policy routes known locations and current changes directly
to editor-native tools. Conceptual or cross-repository questions begin with
SourceRecall discovery. Both paths converge on the live workspace before any
edit, test, or debugging work:

```text
                     CODE QUESTION
                          │
              ┌───────────┴───────────┐
              │                       │
       Known location?          Unknown/conceptual?
       Current changes?         Cross-repository?
              │                       │
             YES                     YES
              │                       │
              ▼                       ▼
       VS Code native             SourceRecall
           tools                     MCP
              │                       │
              │                 discover candidates
              │                       │
              └───────────┬───────────┘
                          ▼
                Live workspace read
                          │
                          ▼
                  edit / test / debug
```

## Codex IDE extension

The Codex IDE extension uses Codex MCP configuration rather than VS Code's
native `.vscode/mcp.json` configuration. To add SourceRecall through the
extension:

1. Open the Codex gear menu and select **MCP servers**.
2. Select **Add server**.
3. Name the server `source_recall`, choose **Streamable HTTP**, and enter
   `http://source-recall:8071/mcp/`.
4. Save the server and select **Restart extension**.
5. Reopen the MCP server list and confirm that SourceRecall is enabled.

For manual configuration, add the following to `~/.codex/config.toml`:

```toml
[mcp_servers.source_recall]
url = "http://source-recall:8071/mcp/"
```

Codex also supports project-scoped MCP configuration in `.codex/config.toml`
for trusted projects. The Codex IDE extension and CLI share this configuration,
so `codex mcp list` can also verify the server. See the official
[Codex MCP guide](https://learn.chatgpt.com/docs/extend/mcp) for configuration
and server-management details.

### Install the Codex retrieval policy

The Codex policy is
[`contrib/codex/AGENTS.md`](../contrib/codex/AGENTS.md). Install its contents at
one of these scopes:

- All repositories: merge it into the Codex-home `AGENTS.md`, normally
  `~/.codex/AGENTS.md`. If `CODEX_HOME` is set, use `AGENTS.md` in that
  directory instead.
- Current repository: merge it into `AGENTS.md` at the repository root.

If the destination does not exist, copy the contributed file there. If it
already exists, append or merge the SourceRecall policy instead of replacing
unrelated instructions. An `AGENTS.override.md` file takes precedence over
`AGENTS.md` at the same scope; when one exists, merge the policy into the
override or reconcile the two files deliberately.

Start a new Codex chat after installing or changing the policy because Codex
loads its `AGENTS.md` instruction chain once per run. See the official
[Codex AGENTS.md guide](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
for discovery order and override behavior.

### Codex workflow

The Codex policy explicitly treats local shell, Git, and file tools as the
current-working-tree path, while SourceRecall supplies semantic and
cross-repository retrieval. Evidence from either branch converges on local
verification before editing or testing:

```text
                     User request
                          │
             ┌────────────┴────────────┐
             │                         │
     Current/local code?        Semantic/broad search?
     Known symbol/file?         Cross repository?
     Editing/debugging?         Unknown implementation?
             │                         │
             ▼                         ▼
      Codex local tools           SourceRecall MCP
             │                         │
     shell / git / files         semantic retrieval
     live working tree           indexed repositories
             │                         │
             └────────────┬────────────┘
                          ▼
                  live verification
                          │
                          ▼
                    edit / test
```

## Continue

Continue supports remote Streamable HTTP MCP servers in agent mode. Add this to
the relevant Continue configuration, replacing the host address:

```yaml
mcpServers:
  - name: SourceRecall
    type: streamable-http
    url: http://source-recall:8071/mcp/
```

The official Continue MCP guide is maintained at
<https://docs.continue.dev/customize/deep-dives/mcp>.

### Install the Continue retrieval policy

Copy [`contrib/continue/10-source-recall.md`](../contrib/continue/10-source-recall.md)
to `.continue/rules/10-source-recall.md` in each workspace where Continue should
use SourceRecall. The `alwaysApply: true` frontmatter makes the rule available
in Continue's Agent, Chat, and Edit modes; MCP tools themselves are available
only in Agent mode. The `10-` prefix gives the policy an explicit position in
Continue's lexicographical rule order.

The rule retains Continue's built-in workspace tools as the source of truth for
current files, changes, debugging, and edits. It uses SourceRecall as the first
retrieval path for conceptual discovery and cross-repository questions. See the
official [Continue rules guide](https://docs.continue.dev/customize/deep-dives/rules)
for rule management and troubleshooting.

## Retrieval policy behavior

All three contributed policies share the same safety boundary while adapting
tool selection to each client:

- Use SourceRecall when the implementation location or terminology is unknown,
  the question spans a subsystem, or evidence is needed across repositories.
- Prefer the client's live local tools for a known file or symbol, current
  edits, exact lookups, diagnostics, testing, and code changes.
- Treat SourceRecall as an indexed clean-commit view that can lag behind staged,
  unstaged, and untracked workspace changes.
- Use SourceRecall to discover relevant code, then inspect and edit the live
  workspace copy.

Installing a policy does not configure or start the MCP server. Likewise,
configuring the server without a policy leaves tool selection to the client and
model defaults.

## Transport security

The stateless FastMCP endpoint is unauthenticated in the initial trusted-network
design.
Do not route port 8071 to the public internet. Use firewall restrictions or an
authenticated TLS reverse proxy if the trust boundary expands.

For a local client, set `mcp.transport: stdio` and launch
`source-recall-mcp`; HTTP host, port, and path settings are then ignored.
