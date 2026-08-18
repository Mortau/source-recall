# Development

## Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the normal checks with:

```bash
ruff check .
pytest
```

The unit suite uses temporary Git repositories, SQLite, mocked HTTP transports,
and fake Qdrant clients. It does not call Node 2 or Node 4 services.

## Local configuration

Copy `config/source-recall.yaml.example` to the ignored
`config/source-recall.yaml` and replace production paths with writable local
directories. Then set:

```bash
export SOURCE_RECALL_CONFIG="$PWD/config/source-recall.yaml"
```

On PowerShell:

```powershell
$env:SOURCE_RECALL_CONFIG = "$PWD\config\source-recall.yaml"
```

## Design rules

- Keep HTTP concerns in `api.py` and MCP concerns in `mcp_server.py`.
- Keep repository semantics out of Jetson NLP.
- Never construct repository paths without `RepositoryManager`.
- Do not log query text, source content, vectors, tokens, or credentials.
- Treat model, dimensions, schema, and chunker changes as index migrations.
- Keep indexing failures visible to the caller and durable job state.
- Add tests before expanding indexing or retrieval behavior.

## Release validation

Before a release, run lint and tests, build a wheel/sdist, install the wheel in a
clean virtual environment, verify both console entry points, deploy to Node 4,
and run `diags/validate_deployment.py` against a representative repository.
