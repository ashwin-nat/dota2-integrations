---
name: dota-monitor
description: Add a new monitor type or a new event to an existing monitor in the Soundbo app (a new trigger such as "when my ability's charge is spent", "when I level up", "when gold passes N"), decide whether generic bases are enough or special handling is needed (like Midas, Blink, BKB), add a new ability or item shape to the state parser when the GSI data needs it, and write the tests. Use when the user asks to add, define or support a new trigger/monitor/event, or a hero whose ability doesn't fire. Not for writing rules in rules.json (use dota-rules) or for recording and stepping through games (use dota-replay).
---

# Adding a monitor

The code is the source of truth; this skill is the route through it. Read `src/rules/monitor_base.py`, `src/rules/monitor_config.py` and the module closest to what you are adding before you write anything. Work one step at a time and show the user the decision (step 2) before you write code.

## 1. Pin down the trigger

The user's only required input is **a recording of the relevant item, ability, hero or scenario** (and a sentence on what should trigger). Don't quiz them about GSI fields or internals; work those out yourself from the recording (step 2) and then confirm your reading with them. If they haven't supplied a recording, ask for one (and which `recordings/*.jsonl` file, or `--record` via `dota-replay`); that is the only thing to ask for up front.

From the request and the recording, infer these, and list them as assumptions for the user to confirm or correct:

- What the player experiences, in one sentence: "play a sound when X".
- Whether it is a **moment** (fires once, e.g. a cast) or a **state** (active for a while, e.g. "while Midas has 2 charges"). This decides whether lights set by the rule are held or dropped, because a monitor's event stays active until `_end()`.
- Which part of the game data it reads: items, abilities, hero, player, map. `StateSnapshot` carries exactly these (`items`, `prev_items`, `abilities`, `hero`, `player`, `map`).
- What happens when joining a game mid-way (first frame already in the state): fire, or only record. Default to what the nearest existing monitor does.

Ask a question only when the recording cannot answer it (for example, two plausible readings of "used" and the frames fit both).

## 2. Look at real data before choosing a design

Never design from memory of how GSI looks. Do the extraction yourself, from the recording the user gave you:

- Use `tools/frames.py` (stdlib only, no throwaway script needed). `uv run python tools/frames.py <recording> --list` shows the heroes, abilities and items in the file and the slots they sat in. Then follow one thing: `--ability <name>`, `--item <name>`, `--slot abilities.ability3` (whatever sits in that slot), `--hero`, or `--path map.paused`. It prints one row per frame where the block changed (the slot, the fields, `clock_time`), `--context N` adds frames around each change, `--fields a,b` narrows the columns, `--from/--to` bound the clock, `--all` shows every frame. It never dumps whole payloads. If it doesn't show what you need, extend the tool rather than writing a one-off.
- Show a compact table of a few frames before, during and after each trigger moment, plus one or two ordinary frames, and any frames where other slots change at the same time. Frames arrive about 1 s apart, so a quick sequence can skip a state (a 1 -> 3 cooldown with no 0 frame; this is what `8dbc24d` fixed).
- Look for edge cases in the same file: death, hero swap or transform (Centaur, Invoker, Kez, Largo), pause, a match change. If the recording has none, say that, and don't claim they work.
- From the table, state what you infer: which fields move on the trigger, what `cooldown` / `charges` / the name do, whether it needs a new ability or item shape. Then ask the user to confirm that reading (the frames you picked and the inferred trigger) before you write code. A short "this is what I see, is this the moment you mean?" is enough.

If the recording doesn't contain the trigger, say so and ask for another one; don't invent field names.

### Decision: generic base, subclass, or new type

Go down this list and stop at the first that fits.

1. **An existing event on an existing type already does it.** Check the monitor tables in `CLAUDE.md` and the `Literal[...]` of each config. Often the answer is a rule, not code (use `dota-rules`).
2. **Add an event to an existing type.** Add the literal to its config's `event`, a class to its registry (`ITEM_MONITOR_REGISTRY`, `ABILITY_MONITOR_REGISTRY`, ...), and a label in `app.js`.
3. **Specialise one target of a type** when most targets behave one way and a single item or ability differs. Subclass the generic monitor and override only the differing hook, then route that target to its own registry:
   - Blink: `BlinkCooldownStartedMonitor` overrides `_started` to ignore the 3 s damage-cancel cooldown. It also has its own `blink` type as a shortcut for `item` on `item_blink`.
   - BKB: `BkbCooldownStartedMonitor` ends after the buff window because GSI has no buff data. Routed through `ITEM_SPECIFIC_REGISTRIES` by item name, so the rule is still a plain `item` rule.
   - Midas: its own `midas` type because its events are about charges, not cooldowns, and the target is fixed (`item_hand_of_midas`).
   Prefer routing by name inside an existing type (`ITEM_SPECIFIC_REGISTRIES`) over a new `MonitorType`; a new type only earns its place when the events themselves are different or the target is fixed and the editor needs a dedicated entry.
4. **A new monitor type.** Use it when the data source or the meaning is different from every existing one.

### Choosing the base class

| Base | Use when | You write |
|---|---|---|
| `Monitor` | One-shot, stateless-ish: emits on a transition and never retracts (`MapMonitor`, `OnceMonitor`) | `evaluate`, `clear`; call `self._bus.emit(self._event_key)` |
| `StatefulMonitor` | Something begins and later ends, no named target (`HeroMonitor`) | `evaluate`, `clear` (call `super().clear()`); `_fire()` / `_end()` |
| `TargetedStatefulMonitor` | Watches one named item or ability (`self._target`) | same; `self._target` comes from `rule.monitor.target`, so `__init__(rule, bus)` |

Rules for all of them:

- Return early when the snapshot part you need is `None`, and **do not end an active state in that case**. The "missing snapshot part" test enforces this.
- `_fire()` sets the monitor active and emits; `_end()` is a no-op unless active, so call it freely on every evaluation.
- The compiler calls `run(snap)`, which wraps `evaluate` and marks events from a monitor's first update `initial` (sounds skip them). Tests that call `evaluate` directly bypass that; use `run` to test it (see `tests/test_initial_events.py`).
- Keep per-match memory (previous values, seen flags, slot ids) in `__init__` and reset every bit of it in `clear()`. A forgotten field leaks one match into the next.
- Only set `runs_before_horn = True` if the monitor reads nothing but the map clock (periodic and once). Pre-game frames carry no hero, items or abilities.
- `takes_light_priority = False` only if the monitor sets the baseline colour (map). Everything else requires a light priority.
- One monitor instance per rule. Never share state between rules or key anything by target alone.

## 3. State parsing: do the data shapes already exist?

Typed state lives in `src/state/`. A monitor should read typed fields, not the raw dict. Check whether the parser already exposes what you need, and only extend it when it does not.

**Abilities** (`src/state/abilities.py`) are parsed per slot by `_parse_ability`. The base `Ability` has the common fields (`slot_id`, `name`, `level`, `can_cast`, `passive`, `ability_active`, `cooldown`, `max_cooldown`, `ultimate`). Some abilities report extra fields and a different meaning for `cooldown`; those get their own frozen subclass of `Ability`, selected inside `_parse_ability` by which keys are present. Today:

- `ChargeAbility` (key `charges` present): Shrapnel, Demonic Purge. `cooldown` doesn't track the recharge, so a cast is a drop in `charges`.

To decide whether your ability needs a new shape:

1. Print the ability's raw dict across a cast, a recharge and a level-up from a recording.
2. If it has only the common fields and `cooldown` goes up on cast, it is the base shape: no parser change, the existing `AbilityCooldownStartedMonitor` covers it.
3. If it has extra keys, or `cooldown` stays 0 on cast, or the name changes in place, or other slots change at the same time, it is a new shape. We add shapes as we meet them, not speculatively. Add the subclass with the new fields, extend the key check in `_parse_ability` (make sure the check is specific enough not to catch existing shapes), and add a branch in the monitor, as `_evaluate_charges` does. Existing in-place transform handling (`_handle_transform`) is only for a name vanishing from a slot; don't overload it.
4. Keep the shape's docstring honest: say which heroes motivated it and what `cooldown` means for it.

**Items** (`src/state/items.py`): `EmptyItem`, `NoChargeItem`, `SingleChargeItem`, `MultiChargeItem`. A new item shape follows the same rule: add a type only when the raw fields differ, and make monitors `isinstance`-check it (see `_get_cooldown`).

**Other parts** (`hero.py`, `player.py`, `map.py`): add the field to the typed parser, from `.get()` with a safe default so older recordings still parse. Remember pre-game frames only carry `map`.

Parsing changes get a parser test too (below).

## 4. Wire it up

Backend, in this order:

1. The monitor module (`src/rules/<name>_monitor.py`, or the existing module if you extended one): config model (a `MonitorConfig` subclass with `type: Literal[MonitorType.X]`, its fields, `_create(bus, rule)`) and the monitor class. One module holds both.
2. `MonitorType` value in `src/rules/monitor_config.py`.
3. The config class in the `AnyMonitor` union in `src/rules/config.py` (and its import). Nothing else in the compiler changes: it calls `rule.monitor.build(bus, rule)`.
4. **Sharing:** the server has no trigger key (`sharing.py` just copies rules). Whether a friend's rule is "the same" as yours is decided in the editor by `sameMonitor` in `app.js` (see below). The default `type + target + event` works for most monitors; a monitor identified by other fields needs a branch there (periodic and once are examples), as one with an alias does (blink). A computed `event` (as `hero_bool` and `hero_int` serialize) already separates `field`s.
5. **Docs:** update `CLAUDE.md` (monitor table, project structure, and any new design note, including why a special case exists) and the `dota-rules` skill if a user can now ask for the trigger.

Editor (`src/config_ui/static/app.js`, vanilla, no build step):

- An event list like `ITEM_EVENTS` / `ABILITY_EVENTS` / `GAME_EVENTS` entry giving the label and description the user sees. A `GAME_EVENTS` entry carries the monitor's extra fields in `monitor: { ... }` (e.g. `{ field: "buyback_cooldown" }` for `hero_int`); the editor merges them with `type` and `event` when it creates the rule.
- `sameMonitor` and `monitorTarget` if the monitor is identified by something other than `type + target + event` (reminders and blink need this).
- `describeTrigger` for the rule's title, sub-title and image.
- `ruleKind` so the rule lands in the right "All rules" filter, and the picker path (`select(...)`, the `sel.kind` branches near the event list) so the user can pick it.
- `ruleIdFor` suffixes if the event name makes an ugly id (`hero_buyback_cooldown_rises` became `hero_buyback_used`).
- If the monitor has fields beyond `target` and `event`, the inspector needs controls and the save path (`RulesConfig` validation) must round-trip them.

Check the editor in a browser (`uv run python -m src.main --no-browser`, open `/ui`) with sound volume set to 0 when you run the app. Create the rule, save, reload, and confirm the rule is still shown under the right filter.

## 5. Tests

Tests go in `tests/test_compiler_and_monitors.py` (monitors) and `tests/test_game_state.py` / the relevant state test (parsers), run with `uv run pytest`. Follow the helpers already there: `_setup(rules)` returns `(compiled, bus, arbiter, executors)`, `_light(priority)` is the harmless action to use, `_ability_starts(targets, frames)` counts firings per ability, `_ability_snap` / `_slots_snap` build frames.

A new monitor needs, at minimum:

1. **Fires on the trigger, exactly once.** Build a short frame sequence and assert the exact count of STARTED events (published on the bus), not just "at least one".
2. **Does not fire when it shouldn't.** The nearby cases that look similar: the previous state repeating, the first frame, a different target, a different slot.
3. **Ends its state** (for a stateful monitor) and retracts, if the design says it ends: assert the light is cleared via the arbiter calls.
4. **`clear()` resets everything.** Feed frames, `compiled.clear_all()`, then repeat the first frame and check no stale previous-value effect (see `test_clear_all_resets_monitors`).
5. **Add it to `test_every_monitor_does_nothing_when_its_snapshot_part_is_missing`.** Add a rule for the new monitor to that list; the test compiles every type and checks nothing fires or ends on a snapshot with all parts `None`.
6. **Config round-trip.** The rule validates through `RulesConfig` (the `AnyMonitor` discriminator picks it) and bad values are rejected. Add to `tests/test_config.py` if there are fields with constraints.
7. **Sharing** has no server-side key to test; `sameMonitor` is in `app.js`, so check it in the editor (a friend's rule on the same trigger is hidden under "Only differences", one on a different field is not).
8. **Parser test** for a new ability, item or other shape: raw dict in, expected typed object out, including that existing shapes still parse to their old types.

When the work started from a real recording, add a **regression test from that data**: copy the few relevant frames inline (as tuples or small dicts, the way the Invoker, Kez and Largo tests do), never reference a file in `recordings/` because that folder is gitignored and absent in CI. Name the test after the hero or situation, and put a comment saying what the real game did.

Finally, replay the recording through the running app (`dota-replay` skill, volume 0, a harmless light action since rules with no enabled actions are skipped) and confirm the fired events match what the user expected in game, then run the whole suite.

## 6. Hand-off

When the implementation and tests are done and the suite passes, give the user a short summary. Keep it brief, with these two parts:

**Code changes**
- Route taken (event on an existing type, specialised target, new type) and why.
- Whether a new ability or item shape was needed, and what it is.
- Files changed, one line each, and the tests added.
- Anything you couldn't verify without a live game.

**`rules.json` schema implications**
- The exact new or changed `monitor` block, as a JSON example (`type`, fields, allowed `event` values).
- Whether existing rules still load unchanged (they should; say so, or say what breaks and why).
- Any new validation rule, and any effect on sharing (does a friend's rule on the same trigger count as the same as yours, per `sameMonitor` in `app.js`) or on the editor (new picker entry, new inspector field).
- Whether `rules.example.json` or the `dota-rules` skill needed an update.

Then stop and let the user review. **Do not commit until they explicitly approve.** If they ask for changes, make them and give the summary again; approval of an earlier version doesn't carry over. Once they approve, commit on the current branch (no new branch, no push, no attribution trailers).
