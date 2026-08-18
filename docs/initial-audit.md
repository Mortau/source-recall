# Initial prototype audit

The imported Node 4 prototype contained four Python files, one YAML file, and a
systemd unit. Its overall separation of API, indexer, CLI, and MCP concerns was
a useful starting point, and its embedding payload matched Jetson NLP.

The first production refactor was driven by these release blockers:

- Unvalidated repository input could escape the managed repository root.
- Re-indexing upserted current chunks without deleting obsolete Qdrant points.
- Two Uvicorn workers used independent in-memory job registries.
- Indexing failures were swallowed, causing the CLI to report success.
- Collection dimensions, embedding identity, chunker, and schema were not
  validated or recorded.
- Vector chunks and lexical lines almost never shared the original RRF key.
- The validated Jetson reranker was not used.
- The YAML configuration was unused while Python and systemd duplicated values.
- Blocking Qdrant and ripgrep work ran directly in async request handlers.
- There were no tests, dependency manifests, license, or public documentation.

The prototype files were replaced rather than retained as a second runtime
path. This audit preserves the original findings while the repository starts
with one supported SourceRecall implementation.
