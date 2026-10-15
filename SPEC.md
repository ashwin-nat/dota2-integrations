# Dota GSI App — Spec

## Goal

Receive Dota 2 GSI payloads, parse the parts we care about into typed state, and drive a rule engine that fires sound / lighting / webhook actions on game events.

---

## Tech Stack

* Python 3.13
* Async runtime: `asyncio`
* HTTP server: `aiohttp`
* Config validation: `pydantic`
* Dependency & environment management: `uv`

Run with:

```bash
uv run python -m src.main
```

---

## Project Structure

```text
src/
├── main.py              # entry point — wires subsystems, runs asyncio tasks
├── log_setup.py         # stdout + rotating file logging
├── ingress/
│   └── http_server.py   # POST / handler, pushes payloads onto an asyncio.Queue
├── state/
│   ├── store.py         # GameState — parses payloads, runs rule monitors
│   ├── items.py / map.py / hero.py / player.py   # typed parsers
├── rules/
│   ├── config.py        # pydantic models for rules.json
│   ├── compiler.py      # compile_rules() -> CompiledRules
│   ├── bus.py           # RuleEventBus + EventContext
│   ├── action_executor.py
│   ├── monitor_base.py / item_monitors.py / map_monitor.py / hero_monitor.py
├── lighting/            # LightingArbiter + vendor drivers (tapo, tuya, log)
└── sound/               # SoundManager
```

---

## Data Flow

```text
Dota 2 ──POST──► http_server ──queue──► ingest task ──► GameState.update(data)
                                                            │
                                                            ├─ parse items / map / hero / player
                                                            ├─ rule_bus.set_time(game_time, clock_time)
                                                            ├─ run monitors ──► rule_bus.emit(event_key)
                                                            └─ light_arbiter.commit()

rule_bus.emit ──► light actions  → LightingArbiter (synchronous)
              └─► other actions  → per-type queue → ActionExecutor worker
```

---

## State Model

### `src/state/store.py`

```python
class GameState:
    def __init__(self, compiled_rules: CompiledRules, rule_bus: RuleEventBus, light_arbiter: LightingArbiter): ...

    def update(self, data: dict) -> None: ...   # parse payload, run monitors
    def version(self) -> int: ...                # increments on every update

    items: Items | None
    map: MapState | None
    player: PlayerState | None
    hero: HeroState | None
```

All dependencies are required constructor args, wired once at startup in `main.py`:

```python
arbiter = LightingArbiter(lighting)
rule_bus = RuleEventBus(arbiter)
compiled = compile_rules(rules_config.rules, rule_bus)
state = GameState(compiled, rule_bus, arbiter)
```

### Update semantics

* Updates without a `map` section, or where `map.game_state` is not `DOTA_GAMERULES_STATE_GAME_IN_PROGRESS`, are ignored.
* Otherwise each section is re-parsed and **replaces** the previous value (latest snapshot wins, no merging).
* A change in `map.matchid` clears all monitor state and lighting requests.
* `update()` is synchronous and must stay CPU-only. Anything I/O-bound (sound, lights, HTTP) goes through `RuleEventBus` and runs asynchronously.

---

## Rule Events

Monitors call `bus.emit(event_key)`. The bus attaches an `EventContext` to every action it dispatches:

```python
@dataclass
class EventContext:
    rule_id: str
    monitor_type: MonitorType
    event_name: str
    data: dict[str, Any]
    game_time: int | None    # stamped from map state at fire time
    clock_time: int | None
```

`ActionExecutor` logs the context before executing each action. Light actions never reach the executor, so the bus logs them directly.

---

## Concurrency Model

* Single writer: the `ingest` task calling `state.update()`
* Multiple readers allowed
* No locks
