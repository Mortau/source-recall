# Changelog

All notable changes to SourceRecall will be documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project intends to use semantic versioning after the initial alpha.

## [Unreleased]

### Added

- Installable `source_recall` package and production repository structure
- Validated YAML configuration and structured rotating-file logging
- Safe managed-repository and file resolution
- Clean Git working-tree validation and authoritative full indexing
- Generation-based index activation that keeps failed refreshes invisible
- Qdrant vector, model, chunker, and schema contract checks
- Durable SQLite indexing status and serialized background jobs
- Hybrid retrieval with chunk-aware reciprocal-rank fusion
- Jetson NLP embedding and reranking contract validation
- FastAPI and Streamable HTTP MCP services
- VS Code, Codex, and Continue MCP setup and retrieval-policy templates
- Unit tests, deployment assets, and public documentation

### Changed

- Use `/opt/source-recall/repositories` as the managed checkout root
- Include Ruby, Puppet, EPP, ERB, and shell files in default indexing
- Use infrastructure-neutral hostnames and wording in public examples
- Run the remote MCP transport statelessly so service restarts do not invalidate
  client sessions
