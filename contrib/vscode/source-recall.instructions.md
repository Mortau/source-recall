---
name: 'SourceRecall Retrieval Policy'
description: 'Choose when to use SourceRecall MCP repository intelligence versus VS Code live workspace tools.'
applyTo: '**'
---

# SourceRecall Retrieval Policy

SourceRecall is an indexed repository-intelligence service exposed through MCP. Use it for semantic discovery, broad repository understanding, and cross-repository retrieval. Do not use it as a replacement for VS Code's live workspace tools.

SourceRecall indexes clean Git working trees. Its indexed view can therefore lag behind the currently open working tree, including staged, unstaged, and untracked changes. When SourceRecall and the live workspace disagree, treat the live workspace as authoritative for the code currently being edited.

## When to use SourceRecall

Use the SourceRecall MCP tools when one or more of these conditions apply:

- The user asks where or how a concept is implemented but does not know the exact file, symbol, or terminology.
- The task requires semantic discovery rather than an exact text or symbol lookup.
- The task asks for architecture, subsystem behavior, request flow, data flow, or implementation patterns spread across multiple files.
- The task asks whether a similar implementation exists elsewhere in a repository.
- The task requires comparing implementations across repositories.
- The relevant repository is indexed by SourceRecall but is not currently open in the VS Code workspace.
- Native workspace search has not found a satisfactory answer and a semantic search may identify code expressed using different terminology.
- The user explicitly asks to search, query, or use SourceRecall.

Typical SourceRecall questions include:

- "Where is retry behavior implemented?"
- "How does authentication flow through this application?"
- "Find code related to Plex metadata normalization."
- "Where have I implemented something similar?"
- "Compare how repository A and repository B handle this problem."
- "Which repository contains the implementation for this concept?"

## When to prefer VS Code native tools

Prefer VS Code's native workspace, search, symbol, reference, diagnostics, terminal, and editing tools when:

- The user names a specific file, function, class, symbol, or currently selected code.
- The task concerns code that is actively being edited.
- The task depends on staged, unstaged, untracked, or otherwise unindexed changes.
- An exact text search, symbol search, definition lookup, reference lookup, or call-site search is sufficient.
- The task is debugging a current build, test, lint, type-check, or runtime failure.
- The task requires editing code.
- SourceRecall has already identified the relevant files and the next step is to inspect or modify their current contents.
- A small, clearly scoped question can be answered directly from the open workspace.

Do not call SourceRecall merely because the tools are available.

## SourceRecall tool policy

SourceRecall exposes these read-only MCP tools:

- `list_repositories()` discovers managed repositories and their index state.
- `search_codebase(repository, query, limit)` performs hybrid semantic and lexical retrieval with reranking.
- `get_file(repository, path)` reads the indexed version of a source file.
- `get_index_status()` reports SourceRecall service, model, schema, and index metadata.

Use them as follows:

### `list_repositories`

Call `list_repositories()` when the correct SourceRecall repository name is unknown or ambiguous, or when the task spans repositories and the available repository set is not already known.

Do not call it repeatedly once the relevant repository names are established.

### `search_codebase`

Use `search_codebase()` as the primary SourceRecall discovery tool.

Write search queries around the user's intent and behavior being sought, not only guessed identifiers. Prefer concise semantic queries such as:

- `authentication token validation request flow`
- `Plex metadata normalization fallback`
- `retry and backoff for failed API requests`
- `configuration loading and environment overrides`

Begin with a modest result limit. Expand or reformulate the query only when the initial results do not provide enough evidence.

For cross-repository analysis, search each relevant repository deliberately rather than assuming one repository's results represent all repositories.

### `get_file`

Use `get_file()` when a SourceRecall result points to a file in a repository that is not available in the live VS Code workspace, or when the indexed version itself is specifically relevant.

If the file is present in the current VS Code workspace, prefer reading the live workspace copy before drawing final conclusions or making changes.

### `get_index_status`

Use `get_index_status()` when:

- retrieval results appear unexpectedly stale or incomplete;
- index/model/schema state is directly relevant;
- the user asks about SourceRecall index health or freshness.

Do not call it for every code question.

## Retrieval-to-edit workflow

When SourceRecall is useful for a task that may result in code changes, follow this sequence:

1. Determine the repository or repositories involved.
2. Use SourceRecall to discover likely files, components, and implementation paths.
3. Narrow the evidence to the most relevant files.
4. For files in the current workspace, switch to VS Code native tools and read their live contents.
5. Trace exact symbols, references, diagnostics, and call sites using native tools where appropriate.
6. Make edits only against the live workspace.
7. Run the appropriate tests, linters, type checks, or diagnostics using the live workspace.
8. Do not assume the SourceRecall index reflects the edits just made.

SourceRecall should normally answer "where should I look?" and "what else is related?". VS Code native tools should normally answer "what is in the working tree right now?" and perform the actual change.

## Handling conflicting evidence

If SourceRecall results conflict with the current workspace:

- Prefer the live workspace for current implementation details.
- Treat the difference as a possible stale-index condition rather than silently combining incompatible versions.
- Mention the discrepancy when it materially affects the answer.
- Do not overwrite newer workspace behavior merely to match the indexed version.

If SourceRecall cannot find relevant code, do not conclude that the code does not exist until reasonable native workspace searches have also been considered.

If the SourceRecall MCP server or a SourceRecall tool is unavailable, continue with appropriate VS Code native tools rather than blocking the task or inventing retrieval results.

## Response behavior

Do not narrate every retrieval tool call. Summarize the evidence that matters.

When answering architectural or codebase questions, identify relevant repositories and file paths when that helps the user verify the result.

When SourceRecall was used only for discovery and the live workspace was subsequently inspected, base implementation-specific claims on the live workspace.

For cross-repository conclusions, keep evidence from each repository distinct so similarly named components are not accidentally conflated.

## Decision shorthand

Use this mental model:

- **Known file or symbol + current workspace** -> VS Code native tools.
- **Current edits or debugging** -> VS Code native tools.
- **Unknown location + conceptual question** -> SourceRecall first.
- **Architecture or subsystem discovery** -> SourceRecall first, then native tools for live verification.
- **Cross-repository question** -> SourceRecall.
- **Historical/indexed repository not open locally** -> SourceRecall.
- **Editing code discovered by SourceRecall** -> switch to the live workspace before editing.
