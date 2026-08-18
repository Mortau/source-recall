# Configuration

SourceRecall reads one YAML file. The systemd units set only
`SOURCE_RECALL_CONFIG=/etc/source-recall/source-recall.yaml`; operational values
do not live in the unit files.

Start from `config/source-recall.yaml.example`. Unknown sections and keys are
rejected so misspellings cannot silently select defaults.

## Service and repositories

| Key | Default | Purpose |
|---|---|---|
| `service.host` | `0.0.0.0` | API bind address |
| `service.port` | `8070` | API port |
| `repositories.root` | `/opt/source-recall/repositories` | Parent of managed checkouts |
| `repositories.git_tracked_only` | `true` | Index only `git ls-files --cached` paths |
| `repositories.require_clean_git` | `true` | Reject uncommitted working trees |
| `repositories.max_file_bytes` | `1048576` | Per-file read limit |
| `repositories.include_extensions` | See template | Indexed/searchable text extensions |
| `repositories.exclude_dirs` | See template | Always-excluded relative directories |

The default extension set includes Ruby (`.rb`), Puppet manifests (`.pp`),
Embedded Puppet templates (`.epp`), ERB templates (`.erb`), and shell scripts
(`.sh`) alongside the other languages shown in the template.

Repository names are one folder component. Nested or absolute paths are never
accepted through the API.

## Qdrant and Jetson NLP

| Key | Default | Purpose |
|---|---|---|
| `qdrant.url` | `http://127.0.0.1:6333` | Qdrant service URL |
| `qdrant.collection` | `source_recall_v1` | Versioned collection name |
| `qdrant.api_key` | `null` | Optional Qdrant credential |
| `qdrant.timeout_seconds` | `30` | Qdrant request timeout |
| `qdrant.embedding_dimensions` | `384` | Required vector dimensions |
| `jetson_nlp.base_url` | Jetson NLP address | Jetson NLP base URL |
| `jetson_nlp.embedding_model` | BGE small identifier | Index/search contract identifier |
| `jetson_nlp.request_timeout_seconds` | `30` | Interactive timeout |
| `jetson_nlp.index_timeout_seconds` | `120` | Batch embedding timeout |
| `jetson_nlp.rerank_enabled` | `true` | Enable cross-encoder reranking |

The model identifier is provenance, not a download instruction. SourceRecall
never loads model artifacts.

## Indexing and retrieval

| Key | Default | Purpose |
|---|---|---|
| `indexing.batch_size` | `16` | Texts per embedding request; maximum 32 |
| `indexing.chunk_max_characters` | `2000` | Target chunk bound; maximum 16000 |
| `indexing.chunk_overlap_lines` | `5` | Context repeated between chunks |
| `indexing.schema_version` | `1` | Payload schema contract |
| `indexing.chunker_version` | `line-v1` | Chunk identity contract |
| `retrieval.default_limit` | `8` | Default returned results |
| `retrieval.max_limit` | `20` | Maximum returned results |
| `retrieval.vector_candidates` | `20` | Qdrant candidates |
| `retrieval.lexical_candidates` | `20` | Bounded ripgrep candidates |
| `retrieval.rerank_candidates` | `20` | Documents sent to Jetson reranking |
| `retrieval.rrf_k` | `60` | Reciprocal-rank-fusion constant |
| `retrieval.lexical_context_lines` | `20` | Context around lexical matches |
| `retrieval.lexical_timeout_seconds` | `10` | Hard ripgrep deadline |

Changing dimensions, embedding model, schema version, or chunker version
requires a new collection name and complete re-index. Do not write incompatible
vectors into an existing collection.

## State, logging, security, and MCP

| Key | Default | Purpose |
|---|---|---|
| `state.database_path` | `/var/lib/source-recall/source-recall.db` | SQLite state |
| `state.job_history_limit` | `100` | Jobs returned by status listing |
| `logging.level` | `INFO` | Application level |
| `logging.file` | `/var/log/source-recall/source-recall.log` | Rotating JSON log; `null` disables file output |
| `logging.max_bytes` | `10485760` | Rotation threshold |
| `logging.backup_count` | `5` | Rotated files retained |
| `security.api_token` | `null` | Optional direct-API Bearer token |
| `mcp.api_url` | `http://127.0.0.1:8070` | API URL used by MCP |
| `mcp.transport` | `http` | `http` or local `stdio` |
| `mcp.host` | `0.0.0.0` | HTTP MCP bind address |
| `mcp.port` | `8071` | HTTP MCP port |
| `mcp.path` | `/mcp/` | Streamable HTTP endpoint |

The production configuration may contain credentials. Install it as
`root:aiadmin` with mode `0640` and never commit it.
