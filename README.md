# semantic-weaver

A minimal metadata-first semantic layer for local DuckDB-backed data questions.

## Goal

This PoC follows the concept in `concept.md` by modeling meaning as table/column metadata, searching that metadata semantically, and then generating SQL only when the retrieved definitions are compatible.

## Current scope

- metadata records for tables and columns
- term resolution and context-aware disambiguation
- semantic guardrails for conflicting populations and synonym-bearing worker concepts
- SQL generation grounded in retrieved metadata

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
pytest -q
```
