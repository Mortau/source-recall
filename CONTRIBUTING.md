# Contributing

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

The test suite uses fakes for Qdrant and Jetson NLP. A live deployment is not
required for normal development.

## Quality checks

```bash
ruff check .
ruff format . --check
pytest
python -m build
```

Keep public behavior documented, avoid logging source or query content, and add
tests for configuration, path handling, indexing, or retrieval changes.

## Pull requests

Use a focused branch, explain the behavior change and deployment impact, and
include the validation commands and results. Model, vector-dimension, chunker,
or schema changes must use a new versioned Qdrant collection and require a full
re-index.
