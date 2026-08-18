# Operations

## Routine checks

```bash
systemctl status source-recall-api source-recall-mcp
curl --fail http://127.0.0.1:8070/live
curl --fail http://127.0.0.1:8070/ready
journalctl -u source-recall-api -n 100 --no-pager
tail -n 100 /var/log/source-recall/source-recall.log
```

`/live` proves only that the API process responds. `/ready` checks Qdrant,
Jetson NLP, and ripgrep. `/status` records which commit and index contract each
repository currently exposes.

## Indexing

Use the API while the services are online so indexing remains serialized in the
single API process:

```bash
curl --fail -X POST http://127.0.0.1:8070/index \
  -H 'Content-Type: application/json' \
  -d '{"repository":"<repository>"}'
```

The CLI is intended for offline maintenance. Stop both services first so a CLI
process cannot compete with an API indexing job for Jetson or Qdrant capacity:

```bash
sudo systemctl stop source-recall-mcp source-recall-api
sudo -u aiadmin env \
  SOURCE_RECALL_CONFIG=/etc/source-recall/source-recall.yaml \
  /opt/source-recall/.venv/bin/source-recall-index <repository>
sudo systemctl start source-recall-api source-recall-mcp
```

The default policy refuses dirty repositories. Pull or checkout the intended
commit, ensure `git status --porcelain` is empty, and run the command again.

An interrupted job is marked failed at the next API startup. Re-run it; a
completed authoritative pass reconciles stale points.

## Common failures

### `/ready` reports Qdrant unavailable

Confirm the Qdrant container/service, configured URL, firewall, and credentials.
Do not delete or recreate a collection until its snapshots and model contract
are understood.

### Vector contract mismatch

The existing collection has the wrong dimension or distance. Correct the
configuration if it is wrong. If the model/index contract changed, create the
next versioned collection and fully re-index every repository.

### Jetson NLP unavailable

Check the Jetson NLP host's `/live` and `/ready` routes, then its service logs.
SourceRecall embedding cannot continue without it. Search can fall back from
reranking only after the query embedding succeeds.

### ripgrep unavailable

Install `rg` in the API service's executable path. Semantic-only fallback is not
silently used because the documented search contract is hybrid.

### Indexing reports an uncommitted tree

Commit, stash, or discard the managed working-tree change. Alternatively disable
`require_clean_git` deliberately; the recorded commit will be prefixed with
`working-tree:` to disclose that the content does not exactly match a commit.

## Logs and retention

SourceRecall emits JSON to both journald and its rotating application file. The
default retains the active 10 MiB file plus five backups. Query text and source
content are excluded. Adjust journald retention separately.

## Backup and recovery

Back up these independently:

- Qdrant collections/snapshots — source chunks and vectors
- `/var/lib/source-recall/source-recall.db` — jobs and index metadata
- `/etc/source-recall/source-recall.yaml` — deployment configuration/secrets
- `/opt/source-recall/repositories` or their authoritative Git remotes

The SQLite database can be rebuilt operationally, but Qdrant must be restored or
all repositories fully re-indexed.
