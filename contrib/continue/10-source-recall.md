---
name: SourceRecall Retrieval Policy
description: Use SourceRecall MCP for semantic and cross-repository discovery while treating the live Continue workspace as authoritative for current code.
alwaysApply: true
---

# SourceRecall Retrieval Policy

SourceRecall is a read-only indexed repository intelligence service exposed through MCP.

Use SourceRecall for discovery and broad codebase understanding. Use Continue's built-in workspace tools for the current working tree, exact code inspection, editing, debugging, and validation.

## Use SourceRecall when

- The user asks where or how a concept is implemented but does not know the exact file, symbol, or terminology.
- The task requires semantic discovery rather than exact text or symbol lookup.
- The task asks about architecture, subsystem behavior, request flow, data flow, or implementation patterns spread across multiple files.
- The task asks whether a similar implementation exists elsewhere.
- The task requires comparing code across repositories.
- The relevant repository is indexed by SourceRecall but is not open in the current workspace.
- Continue's normal workspace searches have not found a satisfactory answer and a semantic search may find code using different terminology.
- The user explicitly asks to use or search SourceRecall.

Examples:

- "Where is retry behavior implemented?"
- "How does authentication flow through this application?"
- "Find code related to Plex metadata normalization."
- "Where have I implemented something similar?"
- "Compare how repository A and repository B solve this problem."

## Prefer Continue workspace tools when

- The user names a specific file, function, class, symbol, or selected block of code.
- The question concerns code currently being edited.
- The task depends on staged, unstaged, untracked, or otherwise unindexed changes.
- Exact grep, file search, symbol lookup, reference lookup, or repository-map inspection is sufficient.
- The task concerns a current build, test, lint, type-check, diagnostic, or runtime failure.
- The task requires modifying code.
- SourceRecall has already identified relevant files that exist in the current workspace.
- A small scoped question can be answered directly from the open workspace.

Do not invoke SourceRecall merely because its MCP tools are available.

## SourceRecall MCP tools

Use the SourceRecall tools deliberately:

- `list_repositories()` — discover managed repositories when the repository name is unknown or when a task spans repositories.
- `search_codebase(repository, query, limit)` — primary semantic and lexical discovery tool.
- `get_file(repository, path)` — read an indexed file when it is not available in the live workspace or when the indexed version is specifically relevant.
- `get_index_status()` — inspect index or model state when retrieval appears stale or incomplete, or when the user asks about index health.

Do not call every SourceRecall tool for every query.

## Search behavior

For `search_codebase`, search for the user's intent and behavior rather than only guessed identifiers.

Prefer queries such as:

- `authentication token validation request flow`
- `Plex metadata normalization fallback`
- `retry and backoff for failed API requests`
- `configuration loading environment overrides`

Begin with a modest result limit. Reformulate or expand only if the initial results are insufficient.

For cross-repository analysis, search each relevant repository explicitly and keep evidence from each repository distinct.

## Retrieval-to-edit workflow

When SourceRecall is useful for a task that may lead to code changes:

1. Use SourceRecall to discover likely repositories, files, components, and implementation paths.
2. Narrow the results to the most relevant files.
3. If those files exist in the current Continue workspace, switch to Continue's built-in file, search, grep, repository-map, and diff tools.
4. Read the live versions before drawing implementation-specific conclusions.
5. Make edits only against the live workspace.
6. Run appropriate tests, linters, type checks, diagnostics, or commands against the live workspace.
7. Do not assume the SourceRecall index includes changes made during the current session.

SourceRecall should usually answer:

- "Where should I look?"
- "What else is related?"
- "Where is something similar implemented?"
- "Which repository contains this concept?"

Continue's workspace tools should usually answer:

- "What is in the working tree right now?"
- "What references this symbol?"
- "What changed?"
- "What should be edited?"
- "Do the current tests pass?"

## Source of truth

SourceRecall may represent an earlier indexed Git state.

When SourceRecall and the live workspace disagree:

- Treat the live workspace as authoritative for current code.
- Treat the mismatch as a possible stale-index condition.
- Mention the discrepancy when it materially affects the answer.
- Do not overwrite newer workspace behavior merely to match the indexed version.

If SourceRecall finds nothing relevant, do not conclude that the code does not exist until reasonable workspace searches have also been considered.

If SourceRecall is unavailable, continue using appropriate Continue built-in tools rather than blocking the task or inventing retrieval results.

## Decision shorthand

- Known file/symbol in current workspace -> Continue tools.
- Current edits/debugging/tests -> Continue tools.
- Unknown location + conceptual question -> SourceRecall first.
- Architecture/subsystem discovery -> SourceRecall first, then live verification.
- Cross-repository question -> SourceRecall.
- Indexed repository not open locally -> SourceRecall.
- Editing code discovered through SourceRecall -> verify and edit the live workspace copy.
