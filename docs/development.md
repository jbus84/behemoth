# Development Workflow

## Pre-commit Hooks
We use pre-commit to enforce basic hygiene, type checking, and docs build consistency.

Install hooks:

```bash
make precommit-install
```

Run all hooks manually:

```bash
make precommit-run
```

What runs by default:

- Formatting hygiene: trailing whitespace, EOF newline, YAML/TOML checks, merge conflict markers, large files.
- `ruff` lint + format for Python.
- `ty` type check across `src`, `services`, `scripts`, `tests`.

What runs on `pre-push`:

- Full docs build via `make docs-build` (export OpenAPI + mkdocs build).

If you need to bypass hooks temporarily, use `SKIP=ty,docs-build` with pre-commit. Avoid this for normal development.

## Docs Build
To preview docs locally:

```bash
make docs
```

To build docs:

```bash
make docs-build
```

## Test Run
Quick test run:

```bash
make test
```

Postgres integration test:

```bash
make test-postgres
```

## Linting/Formatting
Lint:

```bash
make lint
```

Format:

```bash
make format
```
