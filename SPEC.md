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
│   ├── store.py         # GameState — parses payloads, builds a StateSnapshot, runs the monitors
│   ├── items.py / abilities.py / map.py / hero.py / player.py   # typed parsers
├── rules/
│   ├── config.py        # pydantic models for rules.json (rules, actions, AnyMonitor union)
│   ├── monitor_config.py  # MonitorType, MonitorConfig base (build)
│   ├── compiler.py      # compile_rules() -> CompiledRules (one monitor per rule)
│   ├── bus.py           # EventBus (topic router), Event, EventType
│   ├── monitor_base.py  # StateSnapshot, Monitor, StatefulMonitor
│   ├── item_monitors.py / ability_monitors.py / map_monitor.py / hero_monitor.py / periodic_monitor.py
│   │                    # each holds the monitor's config model and the monitor class
│   └── actions/         # ActionBinding + LightExecutor / SoundExecutor / WebhookExecutor
├── lighting/            # LightingArbiter + vendor drivers (tapo, tuya, log)
└── sound/               # SoundManager
```

---

## Data Flow

```text
Dota 2 ──POST──► http_server ──queue──► ingest task ──► GameState.update(data)
                                                            │
                                                            ├─ parse items / abilities / map / hero / player
                                                            ├─ bus.game_time / bus.clock_time = ...
                                                            ├─ compiled.evaluate_all(StateSnapshot) ──► bus.emit / bus.retract(key)
                                                            └─ light_arbiter.commit()

bus.emit(key)    ──► subscribed executors, in order:
                       LightExecutor    → LightingArbiter.set   (synchronous)
                       SoundExecutor    → its queue → worker (burst drop)
                       WebhookExecutor  → its queue → worker (cooldown, POST in a task)
bus.retract(key) ──► LightExecutor → LightingArbiter.clear; sound and webhook ignore it
```

---

## State Model

### `src/state/store.py`

```python
class GameState:
    def __init__(self, compiled_rules: CompiledRules, bus: EventBus, light_arbiter: LightingArbiter): ...

    def update(self, data: dict) -> None: ...   # parse payload, run monitors
    def version(self) -> int: ...                # increments on every update

    items: Items | None
    map: MapState | None
    player: PlayerState | None
    hero: HeroState | None
```

All dependencies are required constructor args, wired once at startup in `main.py`:

```python
arbiter   = LightingArbiter(lighting)
executors = [LightExecutor(arbiter), SoundExecutor(sound), WebhookExecutor()]
bus       = EventBus()
compiled  = compile_rules(rules_config.rules, bus, {e.action_type: e for e in executors})
state     = GameState(compiled, bus, arbiter)
```

### Update semantics

* Updates without a `map` section, or where `map.game_state` is not `DOTA_GAMERULES_STATE_GAME_IN_PROGRESS`, are ignored, except that `DOTA_GAMERULES_STATE_PRE_GAME` updates run the `periodic` and `once` monitors, so timers can fire before the horn.
* Otherwise each section is re-parsed and **replaces** the previous value (latest snapshot wins, no merging).
* A change in `map.matchid` clears all monitor state and lighting requests.
* `update()` is synchronous and must stay CPU-only. Anything I/O-bound (sound, lights, HTTP) goes through the `EventBus` to an executor and runs asynchronously.

---

## Rule Events

Monitors call `bus.emit(key)` when a state begins (or a one-off event happens) and `bus.retract(key)` when a state they signalled ends. The bus stamps the current game and clock time and calls every handler subscribed to that key:

```python
@dataclass(frozen=True)
class Event:
    key: str
    type: EventType          # STARTED or ENDED
    game_time: int | None    # stamped from map state at publish time
    clock_time: int | None
```

At compile time every enabled action is stored as an `ActionBinding` (`rule_id`, `monitor_type`, `event_name`, `action`) on the executor for its type, and each executor subscribes to the keys it holds. The executor logs the owning rule plus the event times before running an action, so the `rule_id` in the log is always the rule that owns the action. Each rule publishes under its own key (its id; config validation rejects duplicate ids), so each key has one rule and every action runs once, even when several rules watch the same trigger.

---

## Concurrency Model

* Single writer: the `ingest` task calling `state.update()`
* Multiple readers allowed
* No locks
