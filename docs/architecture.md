# Architecture

SourceRecall separates repository intelligence from model inference.

```text
IDE / agent
    |
    v
MCP adapter (read-only tools)
    |
    v
FastAPI
    +--> retrieval service
    |      +--> Jetson embedding
    |      +--> Qdrant vector search
    |      +--> ripgrep lexical search
    |      +--> reciprocal-rank fusion
    |      +--> Jetson reranking
    |
    +--> serialized indexing jobs
           +--> clean Git checkout discovery
           +--> bounded line-aware chunking
           +--> Jetson batch embeddings
           +--> Qdrant upserts and stale-point removal
           +--> SQLite job/index metadata
```

## Ownership boundaries

SourceRecall owns repository names, roots, paths, commits, chunks, collections,
search policy, and provenance. Jetson NLP owns embedding and reranking model
execution. Qdrant owns vector persistence and nearest-neighbor queries. MCP is a
thin adapter and contains no retrieval logic.

The remote Streamable HTTP adapter is stateless. Every MCP tool call maps to an
independent SourceRecall API request, so the service does not retain per-client
session data. This allows MCP clients to continue after service or host restarts
without presenting an in-memory session identifier from the previous process.

## Index integrity

The default policy indexes only Git-tracked files from a clean working tree.
Every point records the commit, file checksum, content checksum, embedding
model, vector dimensions, schema version, and chunker version.

Before each search, SourceRecall compares the active indexed commit with the
current checkout and rejects dirty or advanced clean checkouts. This prevents
lexical evidence from the working tree being mixed with vectors from a different
commit. Indexes deliberately created with `require_clean_git: false` are marked
`unverifiable_working_tree` because commit identity alone cannot prove their
contents remain unchanged.

Each pass writes a new index generation. Search continues using the prior
generation until all new chunks are embedded and persisted; the new generation
is then activated in SQLite and prior points are removed. A failed pass is never
made visible. Point identifiers are deterministic within a generation.

Qdrant collection dimensions and cosine distance are validated before writes.
Search filters also require the active model, schema, and chunker contract.
Changing any of those contracts requires a new versioned collection and full
re-index.

## Process model

The API uses exactly one Uvicorn worker. One `ThreadPoolExecutor` serializes
indexing work so simultaneous jobs do not contend for Jetson capacity or mutate
the same repository index concurrently. SQLite makes status durable and marks
interrupted jobs failed after restart.

This is deliberately not a distributed queue. Move indexing to a dedicated
worker/queue before scaling the API horizontally.

## Retrieval

The query is embedded first. Vector search and bounded ripgrep search then run
concurrently. Lexical line hits are fused into vector chunks that contain the
matching line, correcting the granularity mismatch in the original prototype.
The best fused candidates are sent to Jetson NLP's cross-encoder reranker. If
reranking is temporarily unavailable, SourceRecall returns fused results and
marks `reranked` false.

## Current limitations

- Chunking is line-aware, not syntax-aware.
- Indexing is authoritative full indexing, not incremental indexing.
- Symbol definitions, references, callers, and test relationships are not yet
  modeled.
- API authentication is a shared optional Bearer token.
- MCP transport authentication must be supplied by the network or proxy layer.
