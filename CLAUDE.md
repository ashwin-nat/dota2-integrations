# CLAUDE.md

## Project

Dota 2 GSI (Game State Integration) receiver. Accepts raw POST payloads from the Dota 2 client and holds the latest snapshot in memory with no schema assumptions.

## Tech Stack

- Python 3.13
- `asyncio` — async runtime
- `aiohttp` — HTTP server
- `uv` — dependency and environment management

## Running

```bash
uv run python -m src.main
```

Listens on `http://127.0.0.1:6969`. Dota 2 sends POST requests to `/`.

## Project Structure

```
src/
├── main.py               # entry point — asyncio.run(main_loop())
├── core/
│   └── runtime.py        # wires GameState + aiohttp, runs the event loop
├── ingress/
│   └── http_handler.py   # POST / handler; state injected via functools.partial
└── state/
    └── store.py          # GameState — latest-snapshot store, no schema
```

## Key Design Decisions

- **No schema assumptions** — GSI payload is stored as an opaque `dict`.
- **Latest snapshot wins** — each `state.set(data)` fully replaces the previous state.
- **Transport-agnostic state layer** — `GameState` has no aiohttp dependency.
- **Type-safe handler injection** — `handle_gsi(state, request)` receives `GameState` as a bound arg via `partial(handle_gsi, state)`, avoiding untyped `app["state"]` dict access.
- **No locks** — single writer (HTTP handler), multiple readers allowed.

## State API (`src/state/store.py`)

```python
state.get()      # -> dict | None   current snapshot
state.set(data)  # -> None          replace snapshot, increment version
state.version()  # -> int           monotonic counter, increments on every set
```
