# SourceRecall

SourceRecall is a self-hosted repository intelligence service for AI coding
assistants. It indexes clean Git working trees into Qdrant, combines semantic
and lexical retrieval, reranks candidates through a separate Jetson NLP
service, and exposes the results through HTTP and Model Context Protocol (MCP).

It is designed for a small trusted-network deployment where repository data
must remain under the operator's control.

## Highlights

- Safe repository containment beneath one managed root
- Clean-commit indexing with file, chunk, model, and schema provenance
- Authoritative full re-indexing that removes obsolete Qdrant points
- Hybrid vector and ripgrep retrieval with chunk-aware reciprocal-rank fusion
- Optional cross-encoder reranking through Jetson NLP
- Thin stateless Streamable HTTP MCP integration with structured tool responses
- Durable SQLite job and index status
- Validated YAML configuration and structured rotating-file logs
- Single-worker, serialized indexing model with explicit resource bounds

## Architecture

```text
VS Code / Codex / Continue agent
    |
    | Streamable HTTP MCP
    v
SourceRecall MCP :8071
    |
    v
SourceRecall API :8070
    |                 |
    |                 +--> managed Git repositories
    |                      + ripgrep lexical retrieval
    |
    +--> Qdrant :6333
    +--> Jetson NLP :8091 (/v1/embeddings and /v1/rerank)
```

SourceRecall owns repository, path, commit, chunk, and retrieval semantics.
Jetson NLP remains a stateless inference service that only knows text, vectors,
and scores.

## Repository layout

```text
config/             Versioned configuration template
contrib/            Client-specific SourceRecall retrieval policies
deploy/systemd/     API and MCP systemd units
diags/              Deployment validation utilities
docs/               Architecture, API, deployment, and operations guides
src/source_recall/  Installable Python package
tests/              Automated tests
```

## API at a glance

```bash
curl http://source-recall:8070/live

curl -X POST http://source-recall:8070/index \
  -H 'Content-Type: application/json' \
  -d '{"repository":"episode-tracker"}'

curl -X POST http://source-recall:8070/search \
  -H 'Content-Type: application/json' \
  -d '{
    "repository":"episode-tracker",
    "query":"where are TV episode credits normalized?",
    "limit":8
  }'
```

When `security.api_token` is configured, add
`Authorization: Bearer <token>` to all non-health API requests.

## Production paths

| Purpose | Path |
|---|---|
| Application | `/opt/source-recall` |
| Virtual environment | `/opt/source-recall/.venv` |
| Configuration | `/etc/source-recall/source-recall.yaml` |
| Managed repositories | `/opt/source-recall/repositories` |
| Durable state | `/var/lib/source-recall/source-recall.db` |
| Application logs | `/var/log/source-recall/source-recall.log` |
| API service | `/etc/systemd/system/source-recall-api.service` |
| MCP service | `/etc/systemd/system/source-recall-mcp.service` |

See [Deployment](docs/deployment.md) for the complete installation procedure.

## Documentation

- [Architecture](docs/architecture.md)
- [API reference](docs/api.md)
- [Configuration](docs/configuration.md)
- [Deployment](docs/deployment.md)
- [Development](docs/development.md)
- [MCP client setup and retrieval policies](docs/mcp.md)
- [Operations](docs/operations.md)
- [Initial audit](docs/initial-audit.md)

The MCP guide includes native VS Code, the Codex IDE extension, and Continue
configuration, plus the client-specific instruction files under `contrib/`
that teach each agent when to use SourceRecall instead of its live workspace
tools.

## Current scope

The initial release performs authoritative full indexing. Incremental Git
indexing, webhook ingestion, syntax-aware chunking, symbol graphs, and reference
analysis are planned extensions rather than claimed features. Indexing jobs are
durable for status reporting but execute in one local process; this is not a
distributed job queue.

The services do not terminate TLS, and the MCP endpoint does not implement
client authentication. Keep them on a trusted private network or place them
behind an authenticated reverse proxy. See [Security](SECURITY.md).

## License

SourceRecall is available under the [MIT License](LICENSE).
