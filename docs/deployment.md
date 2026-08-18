# Deployment

These instructions target Node 4 with SourceRecall in `/opt/source-recall`,
Qdrant already available to the node, and Jetson NLP reachable over the trusted
network.

## Prerequisites

- Python 3.10 or newer
- Git
- ripgrep (`rg`)
- A Qdrant server compatible with `qdrant-client==1.19.0`
- The deployed Jetson NLP embedding/reranking API
- An `aiadmin` service account

## Create runtime directories

```bash
sudo install -d -o aiadmin -g aiadmin -m 0750 \
  /opt/source-recall \
  /srv/source-recall/repositories
sudo install -d -o root -g aiadmin -m 0750 /etc/source-recall
```

systemd creates `/var/lib/source-recall` and `/var/log/source-recall` through
`StateDirectory` and `LogsDirectory`.

Place clean repository checkouts directly beneath
`/srv/source-recall/repositories`, for example:

```text
/srv/source-recall/repositories/episode-tracker/.git
```

## Install SourceRecall

Copy or clone the release into `/opt/source-recall`, then run:

```bash
cd /opt/source-recall
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install --no-deps .
```

The first requirements installation verifies every production pin. The final
command installs SourceRecall and its console entry points without resolving a
second dependency set.

## Configure

```bash
sudo install -o root -g aiadmin -m 0640 \
  config/source-recall.yaml.example \
  /etc/source-recall/source-recall.yaml
sudoedit /etc/source-recall/source-recall.yaml
```

At minimum, confirm the Qdrant URL, collection name, Jetson NLP address,
repository root, model identifier, dimensions, and MCP bind address. Generate an
optional API token with `openssl rand -hex 32`.

Do not reuse a collection after changing the embedding model, dimensions,
chunker version, or schema version. Create `source_recall_v2` and re-index.

## Install services

```bash
sudo install -o root -g root -m 0644 \
  deploy/systemd/source-recall-api.service \
  /etc/systemd/system/source-recall-api.service
sudo install -o root -g root -m 0644 \
  deploy/systemd/source-recall-mcp.service \
  /etc/systemd/system/source-recall-mcp.service
sudo systemctl daemon-reload
sudo systemctl enable --now source-recall-api.service
sudo systemctl enable --now source-recall-mcp.service
```

The API intentionally runs one worker. Do not add Uvicorn workers while indexing
uses the in-process serialized executor.

## Initial validation and indexing

```bash
curl --fail http://127.0.0.1:8070/live
curl --fail http://127.0.0.1:8070/ready
curl --fail http://127.0.0.1:8070/status

curl --fail -X POST http://127.0.0.1:8070/index \
  -H 'Content-Type: application/json' \
  -d '{"repository":"episode-tracker"}'
```

If an API token is enabled, add its Bearer header to `/status`, `/index`, and
`/search` requests. Health routes remain unauthenticated for service monitoring.
Poll the returned job with `GET /index-status/{job_id}` until it is completed
before running the search validator.

Finish with the deployment validator:

```bash
/opt/source-recall/.venv/bin/python \
  /opt/source-recall/diags/validate_deployment.py \
  --api-url http://127.0.0.1:8070 \
  --repository episode-tracker \
  --query "application entry point" \
  --output /tmp/source-recall-validation.json
```
