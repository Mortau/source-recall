# HTTP API reference

The example base URL is `http://source-recall:8070`. FastAPI publishes OpenAPI
documentation at `/docs` and `/openapi.json`.

If `security.api_token` is set, all routes except `/live`, `/ready`, `/health`,
`/docs`, and `/openapi.json` require:

```text
Authorization: Bearer <configured-token>
```

Clients may provide a printable `X-Request-ID` of at most 128 characters. The
API returns it, or a generated identifier, in every response.

## `GET /live`

Process liveness only:

```json
{"status":"alive"}
```

## `GET /ready` and `GET /health`

Checks Qdrant, Jetson NLP's `/ready` route, and ripgrep availability. Returns
HTTP 200 only when all three are ready; otherwise returns HTTP 503.

## `GET /status`

Returns the active Qdrant collection, embedding model and dimensions, schema and
chunker versions, repository root, and durable metadata for indexed
repositories.

## `GET /repositories`

Lists safe repository directories immediately beneath the configured root and
attaches index metadata where available.

## `GET /file/{repository}/{path}`

Returns one bounded UTF-8 file from a managed repository:

```json
{
  "repository": "episode-tracker",
  "path": "src/episode_tracker/scanner.py",
  "content": "..."
}
```

Absolute paths, parent traversal, backslashes, files outside the repository,
oversized files, and non-UTF-8 files are rejected.

## `POST /search`

Request:

```json
{
  "repository": "episode-tracker",
  "query": "where are credits normalized?",
  "limit": 8
}
```

`repository` is required and must be one immediate managed folder. `query` must
be nonblank and at most 16,000 characters. `limit` defaults to the configured
value and cannot exceed `retrieval.max_limit`.

Response results include repository, path, line range, content, contributing
retrieval sources, vector/fusion/rerank scores, and indexed provenance. The
top-level response also reports `indexed_commit` and `freshness`. Search rejects
a dirty working tree or changed commit when the index was created from a clean
commit. `reranked` is false when reranking is disabled or the Jetson reranker was
temporarily unavailable.

## `POST /index`

Queues authoritative full indexing and returns HTTP 202:

```json
{
  "status": "accepted",
  "job_id": "f85c...",
  "repository": "episode-tracker"
}
```

Only one active job per repository is accepted. A second request returns HTTP
409. The repository must be a clean Git working tree by default.

## `GET /index-status`

Returns recent durable job records, newest first.

## `GET /index-status/{job_id}`

Returns one job, including timestamps, file and chunk counts, stale-point count,
and any bounded error message.

## Error behavior

- HTTP 400: request exceeds configured policy
- HTTP 401: missing or invalid optional API Bearer token
- HTTP 404: repository, file, or job is unavailable
- HTTP 409: repository has an active indexing job or no completed current index
- HTTP 422: malformed request schema
- HTTP 502: Jetson NLP or Qdrant dependency unavailable
- HTTP 503: readiness dependency unavailable
- HTTP 500: unexpected internal failure

Internal exception details are written to logs rather than returned by search.
