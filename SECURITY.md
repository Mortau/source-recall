# Security policy

## Supported versions

SourceRecall is currently pre-1.0. Security fixes are applied to the latest
revision on the default branch.

## Deployment boundary

SourceRecall is intended for a single operator or trusted private network. It
does not provide TLS termination, multi-tenant authorization, rate limiting, or
MCP client authentication.

The HTTP API supports an optional Bearer token for all non-health routes. The
MCP adapter uses that token when calling the API, but its own network endpoint
must remain private or be protected by an authenticated reverse proxy.

Never expose Qdrant, the SourceRecall API, the MCP endpoint, or Jetson NLP
directly to the public internet.

## Sensitive data

Indexed Qdrant payloads contain source code. Application logs contain repository
names, paths, request metadata, and failures, but intentionally do not record
search query text or authentication tokens.

Keep the production YAML configuration outside the repository with mode `0640`
or stricter. Do not commit tokens, private Qdrant credentials, production logs,
SQLite state, Qdrant snapshots, or repository contents.

## Reporting a vulnerability

Do not open a public issue containing exploit details, credentials, private
source, or logs. Contact the repository owner privately and include the affected
revision, impact, reproduction steps, and any proposed mitigation.
