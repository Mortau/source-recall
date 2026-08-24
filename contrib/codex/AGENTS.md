# SourceRecall Retrieval Policy

SourceRecall is a read-only indexed repository-intelligence service exposed through MCP.

Use SourceRecall for semantic discovery, broad codebase understanding, and cross-repository retrieval. Use Codex's local repository and shell tools for the current working tree, exact inspection, editing, debugging, and validation.

## Use SourceRecall when

- The user asks where or how a concept is implemented but does not know the exact file, symbol, or terminology.
- The task needs semantic discovery rather than exact text or symbol lookup.
- The task concerns architecture, subsystem behavior, request flow, data flow, or implementation patterns spread across multiple files.
- The task asks whether a similar implementation exists elsewhere.
- The task compares code across repositories.
- A relevant repository is indexed by SourceRecall but is not the current repository.
- Local repository searches have not found a satisfactory answer and semantic retrieval may find code expressed with different terminology.
- The user explicitly asks to search or use SourceRecall.

## Prefer Codex local tools when

- The user names a specific file, function, class, symbol, or code region.
- The task concerns code currently being edited.
- The answer depends on staged, unstaged, untracked, or otherwise unindexed changes.
- Exact text search, symbol inspection, Git inspection, or local shell commands are sufficient.
- The task concerns a current build, test, lint, type-check, or runtime failure.
- The task requires editing code.
- SourceRecall has already identified files that are present in the current working tree.

Do not use SourceRecall merely because its MCP tools are available.

## SourceRecall tools

Use the SourceRecall MCP tools deliberately:

- `list_repositories()` — discover repository names when unknown or when a task spans repositories.
- `search_codebase(repository, query, limit)` — primary semantic and lexical discovery tool.
- `get_file(repository, path)` — read an indexed file when it is not available locally or when the indexed version itself is relevant.
- `get_index_status()` — inspect index/model state when retrieval appears stale or incomplete, or when the user asks about index health.

Do not call every SourceRecall tool for every request.

For `search_codebase`, query for the behavior or concept being sought rather than only guessed identifiers. Start with a modest result limit and reformulate only when the initial evidence is insufficient.

For cross-repository analysis, search each relevant repository explicitly and keep evidence from different repositories distinct.

## Retrieval-to-edit workflow

When SourceRecall is useful for a task that may result in code changes:

1. Use SourceRecall to discover likely repositories, files, components, and implementation paths.
2. Narrow the results to the most relevant files.
3. If those files exist in the current working tree, read their live local versions before drawing implementation-specific conclusions.
4. Use local search, Git, and shell tools to trace exact references and current behavior as needed.
5. Make edits only against the live working tree.
6. Run appropriate tests, linters, type checks, builds, or diagnostics against the live working tree.
7. Do not assume SourceRecall includes changes made during the current session.

SourceRecall should usually answer:

- Where should I look?
- What else is related?
- Where is something similar implemented?
- Which repository contains this concept?

Codex local tools should usually answer:

- What is in the working tree right now?
- What changed?
- What references or calls this code?
- What should be edited?
- Do the current tests pass?

## Source of truth

SourceRecall may represent an earlier indexed Git state.

If SourceRecall and the current working tree disagree:

- Treat the current working tree as authoritative for current implementation details.
- Treat the mismatch as a possible stale-index condition.
- Mention the discrepancy when it materially affects the answer.
- Do not overwrite newer local behavior merely to match the indexed version.

If SourceRecall returns no relevant result, do not conclude that the code does not exist until reasonable local searches have also been considered.

If SourceRecall is unavailable, continue with appropriate local Codex tools rather than blocking the task or inventing retrieval results.

## Decision shorthand

- Known file or symbol in current repository -> local Codex tools.
- Current edits, debugging, or tests -> local Codex tools.
- Unknown location plus conceptual question -> SourceRecall first.
- Architecture or subsystem discovery -> SourceRecall first, then local verification.
- Cross-repository question -> SourceRecall.
- Indexed repository not currently open -> SourceRecall.
- Editing code discovered through SourceRecall -> verify and edit the live local copy.
