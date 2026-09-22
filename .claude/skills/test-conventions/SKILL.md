---
name: test-conventions
description: Writing or fixing tests in this repository (pytest, FastAPI, SQLite, mocks, dev scripts). Use before adding a fixture, an API test, a test that runs a turn, a subprocess test, or a mock server.
---

# Test conventions

- **Isolated database for anything that reads or writes it**: the `fresh_db` fixture, then
  `await init_db()` (an autouse async fixture in the file). `run_turn` reads its agent from the
  database, so every test and dev script that runs a turn needs one.
- **Caches and registries**: `get_settings.cache_clear()` after every `monkeypatch.setenv`;
  `deps.reset_failure_state()`; `registry.clear()` and `models._active.clear()` for jobs and
  name claims, in setup and teardown.
- **API tests** use `httpx.ASGITransport(app=app, raise_app_exceptions=False)`, `base_url
  http://t`, the key header; `ALLOWED_HOSTS` already lists `t`. Override a scope with
  `app.dependency_overrides[get_principal]` and clear it after.
- **Mocks that speak HTTP** are real `HTTPServer`/`ThreadingHTTPServer` threads on port 0, or
  `httpx.MockTransport` when the transport is what is under test. A subprocess inherits
  `DATABASE_URL` through `monkeypatch.setenv`.
- **Nothing depends on the machine**: no Docker, no fixed port, no real file of `data/`.
- **Constants come from probes**: see skill `measure-first`; a comparison runs on one real path.
- **Secrets**: throwaway keys are generated (`Fernet.generate_key()`) or use the `conftest.py`
  test key; low-entropy values such as `"test-key-" + "a" * 20`; no tracked file holds a real
  token or the earlier project's name.
- **Style**: 100 columns from the first line; `ruff format` on new files only; `ruff check .`
  clean. The repo language is English.
- **Every test earns its place**: it fails when its control is removed (skill `mutation-check`);
  a test that cannot fail is deleted.
- **After a shared change** (`conftest.py`, `app/db`, `app/config.py`, `app/graph.py`,
  `start.sh`, a function that gained a dependency) run the full suite before reporting.
