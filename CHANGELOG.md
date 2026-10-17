# Changelog

## Unreleased

- Repo hygiene: removed the accidentally committed `.venv/` virtualenv plus `*.egg-info` and `__pycache__` build artifacts, and added a `.gitignore` (`.venv`, `__pycache__`, `*.egg-info`, `dist`, `.env`, `client_secrets.json`, `token*.json`). Git history was squashed so the virtualenv is gone from history too.

## 0.1.0 — 2026-10-17

First release.
- `aiseo audit <url>`: 0-100 AI-visibility score across 6 categories (AI crawler access, discovery files, structured data, content, meta, technical) with ranked fixes. Text and `--json` output.
- `aiseo keywords <seed>`: free keyword ideas from Google autocomplete (seed, question and alphabet expansion).
- `aiseo gsc`: Search Console CLI — auth (cached OAuth), properties, analytics, sitemaps, URL inspection.
- Offline test suite (8 tests) with local HTTP fixtures.
