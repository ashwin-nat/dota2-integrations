# Dota GSI App — State Layer Spec (v0, uv-based)

## Goal

Store the latest incoming GSI payload **as-is**, with **zero schema assumptions**, and make it available to the rest of the system.

---

## Tech Stack

* Python 3.12+
* Async runtime: `asyncio`
* HTTP server: `aiohttp`
* Dependency & environment management: uv

---

## Project Structure

```text
dota_gsi_app/
│
├── src/
│   ├── state/
│   │   └── store.py          # GameState (single source of truth)
│   │
│   ├── ingress/
│   │   └── http_handler.py   # aiohttp POST endpoint
│   │
│   ├── core/
│   │   └── runtime.py        # orchestrates tasks
│   │
│   └── main.py               # entry point
│
├── pyproject.toml
└── README.md
```

---

## Environment Setup (uv)

### Initialize project

```bash
uv init
```

---

### Add dependency

```bash
uv add aiohttp
```

---

### Run the app

```bash
uv run python -m src.main
```

---

## Design Principles

* **No schema assumptions**
  Treat incoming data as opaque JSON (`dict`).

* **Latest snapshot wins**
  Each new payload fully replaces the previous state.

* **No merging / no parsing**
  Do not interpret or transform data at this stage.

* **Transport-agnostic**
  State layer must not depend on HTTP / aiohttp.

* **Event-ready (future)**
  Updates must be replace-based to allow diffing later.

---

## State Model

### `src/state/store.py`

```python
class GameState:
    def __init__(self):
        self._data: dict | None = None
        self._version: int = 0

    def get(self) -> dict | None:
        return self._data

    def set(self, data: dict):
        # store a copy to avoid accidental mutation
        self._data = data.copy()
        self._version += 1

    def version(self) -> int:
        return self._version
```

---

## Update Semantics

* Input: `dict` (raw GSI payload)
* Operation: `set(data)`
* Behavior:

  * Previous state is discarded
  * New state becomes the single source of truth
  * Version is incremented

```text
old_state → discarded
new_state → stored
```

---

## Processing Contract

### Input to state layer:

```python
dict
```

### Output from state layer:

```python
dict | None
```

---

## Ingress (HTTP Layer)

### `src/ingress/http_handler.py`

```python
from aiohttp import web

async def handle_gsi(request: web.Request):
    try:
        data = await request.json()
    except Exception:
        return web.Response(status=400, text="Invalid JSON")

    state = request.app["state"]
    state.set(data)

    return web.Response(text="OK")
```

---

## Runtime (Orchestration)

### `src/core/runtime.py`

```python
import asyncio
from aiohttp import web
from src.ingress.http_handler import handle_gsi


async def run_server(state):
    app = web.Application()
    app["state"] = state
    app.router.add_post("/", handle_gsi)

    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, "127.0.0.1", 6969)
    await site.start()

    print("Listening on http://127.0.0.1:6969")

    return runner


async def main_loop():
    from src.state.store import GameState

    state = GameState()

    runner = await run_server(state)

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
```

---

## Entry Point

### `src/main.py`

```python
import asyncio
from src.core.runtime import main_loop

if __name__ == "__main__":
    asyncio.run(main_loop())
```

---

## Concurrency Model

* Single writer (HTTP handler → state.set)
* Multiple readers allowed
* No locks required (initial version)

---

## Constraints

* Do NOT access nested fields (no schema assumptions)
* Do NOT mutate returned state
* Do NOT partially update state
* Do NOT introduce derived values

---

## Future Extensions (Not in Scope)

* Typed models
* Partial updates / merge logic
* Diff computation
* Event bus integration
* Validation layer

---

## Summary

This layer acts as a:

```text
Latest Snapshot Store
```

It provides a stable foundation for:

* schema discovery through observation
* diff-based processing later
* event-driven architecture
