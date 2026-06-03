# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`browser-stealth-py` is a **standalone, parser-free** stealth browser fetcher: the
browser-automation engine of [Scrapling](https://github.com/D4Vinci/Scrapling)
extracted so it stands alone, with the entire `parser`/`Selector`/`translator`/`storage`
dependency tree removed. It drives Chromium through **patchright** (a stealth-patched
Playwright fork) and returns a lightweight `Response` (HTTP metadata + raw `body` /
decoded `text`) that the caller parses with whatever they like.

Most modules are **ported verbatim from Scrapling** (each file's docstring names its
upstream origin). The deliberate deviations from upstream are: `Response` is a plain
container instead of a `Selector` subclass, and `_detect_cloudflare` sniffs embedded
Turnstile via a regex (`__TURNSTILE_SCRIPT_RE__` in `_base.py`) instead of a `Selector`.
When porting more from Scrapling or reconciling behavior, preserve that lineage —
don't reintroduce the parser dependency.

## Commands

Uses **uv**. There is no build step, no test suite, and no linter/formatter config in
this repo — don't go looking for `pytest`/`ruff`/`make` targets; they don't exist here.
(Many `# pragma: no cover` markers survive from upstream but no coverage harness is wired up.)

```bash
uv venv
uv pip install -e .                    # core (parser-free)
uv pip install -e ".[parse]"           # + lxml/parsel convenience parsers
uv run patchright install chromium     # one-time browser binary install

uv run python examples/basic.py        # sync + async demo
uv run --env-file .env python examples/spider_cloud_proxy.py   # examples needing secrets
```

Secrets live in `.env` (gitignored); `.env.example` is the tracked template — copy it
and load with `uv run --env-file .env`. Never hardcode keys in `examples/`.

## Architecture

### Request flow

`StealthyFetcher.fetch()` (`fetcher.py`) is a thin one-shot wrapper that opens a
`StealthySession`, calls `.fetch(url)`, and closes it. The real work lives in the session:

```
fetcher.py            StealthyFetcher.fetch / async_fetch  (one-shot convenience)
  └─ _session.py      Stealthy(Async)Session  — start(), the fetch() loop, _cloudflare_solver()
       ├─ _base.py    Sync/AsyncSession (page/context lifecycle) + StealthySessionMixin (flags/fingerprint)
       ├─ _validators.py  msgspec config structs + per-call override resolution
       ├─ navigation.py   route interception (resource/domain blocking) + proxy dict normalization
       ├─ _page.py        PagePool / PageInfo (tab pooling + state)
       └─ convertor.py    ResponseFactory: Playwright response -> Response (response.py)
```

`fetch()` is a retry loop (`self._config.retries`): pick a proxy → acquire a page via
`_page_generator` → register a response handler that captures the main-frame navigation
response (and optional `capture_xhr` matches) → `page.goto` → stability waits → optional
Cloudflare solve / `page_action` / `wait_selector` → build `Response`. Proxy-related
errors (`is_proxy_error`) are retried with a delay.

### Three browser launch modes (this drives the most important behavioral constraint)

`start()` in `_session.py` branches on config:
- **persistent context (default)** — `launch_persistent_context` with a temp `user_data_dir`. `self.context` is set, `self.browser` is `None`.
- **browser mode** — triggered by `proxy_rotator` or `cdp_url`. Launches a detached `browser`; fresh contexts are spun per request.
- **CDP** — `cdp_url` attaches over CDP.

The per-call proxy override `session.fetch(url, proxy=...)` and proxy *rotation* both
require a `browser` object, so they **only work in browser mode**. On a default
persistent-context session, `_page_generator` raises *"Browser not initialized for
proxy rotation mode"*. For a default session, set a **static** `proxy=` at construction.
(See README "Sessions & proxies" and `examples/proxy.py`.)

### Config validation pipeline

Three layers, intentionally:
1. **`StealthSession` / `StealthFetchParams` TypedDicts** (`_types.py`) — the typed `**kwargs` surface for IDEs (consumed via `Unpack`).
2. **`StealthConfig` (← `PlaywrightConfig`)** msgspec `Struct`s (`_validators.py`) — runtime validation in `__post_init__`: normalizes proxy strings to Playwright dicts, rejects `proxy` + `proxy_rotator` together, expands `block_ads` into `blocked_domains`, and **bumps `timeout` to ≥60s when `solve_cloudflare=True`**.
3. **`_fetch_params` dataclass** — built by `validate_fetch()`, which merges **session-level config with per-call `fetch()` overrides** (only keys the caller passed override; everything else falls back to `session._config`).

`validate()` filters out args equal to their defaults before calling msgspec `convert`
(a speed optimization) and re-raises `ValidationError` as `TypeError`.

### Stealth flags & fingerprints

`StealthySessionMixin.__generate_stealth_options` (`_base.py`) assembles Chromium launch
args from `constants.py`: `DEFAULT_ARGS + STEALTH_ARGS`, minus `HARMFUL_ARGS`
(`ignore_default_args`), plus conditional flags for `block_webrtc` / `hide_canvas` /
`allow_webgl` / `dns_over_https`. Context options force a fixed 1920×1080 / dark
color-scheme / `device_scale_factor: 2` fingerprint. When the user gives no `useragent`
and runs headless, a real UA is generated by **browserforge** (`fingerprints.py`); the
hardcoded `chromium_version`/`chrome_version` there must be bumped to track real Chrome.

### Sync / async duplication — edit both

`_base.py` (`SyncSession`/`AsyncSession`) and `_session.py`
(`StealthySession`/`AsyncStealthySession`), and `convertor.py`'s sync/async response
factories, are **parallel implementations of the same logic**. Any behavioral change to
one almost always needs the mirror change in the other. The Cloudflare solver and the
fetch loop are the largest duplicated blocks — diff them when touching either.

### patchright vs playwright (not interchangeable)

The *runtime drivers* `sync_playwright`/`async_playwright` are imported from **patchright**
(the stealth fork) in `_session.py`. Everything else — type imports, `Page`, `Route`,
`Response`, `Error` — comes from **playwright**. Keep that split: types and errors from
`playwright`, the launched driver from `patchright`.

### Response construction

`ResponseFactory` (`convertor.py`) prefers live `page.content()` for HTML responses
(falling back to `final_response.body()`), walks the redirect chain into `history`,
and attaches `captured_xhr`. `_get_page_content` retries around a known Playwright
`page.content()` flake. `Response` (`response.py`) stores bytes in `_body` and exposes
`body`/`text`; `StatusText` maps status codes to reason phrases for when Playwright
returns an empty `status_text`.
