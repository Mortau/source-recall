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

Do not enable both Continue-native repository indexing and SourceRecall retrieval
for the initial rollout. A single retrieval path makes relevance problems
observable and reproducible.

## Transport security

The FastMCP endpoint is unauthenticated in the initial trusted-network design.
Do not route port 8071 to the public internet. Use firewall restrictions or an
authenticated TLS reverse proxy if the trust boundary expands.

For a local client, set `mcp.transport: stdio` and launch
`source-recall-mcp`; HTTP host, port, and path settings are then ignored.
