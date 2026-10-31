---
name: dota-replay
description: Record real Dota 2 GSI data and replay it into the dota2-integrations app, step by step if needed, to reproduce or debug a rule or monitor without launching the game. Use when the user says things like "I have a recording", "why didn't my rule fire", "reproduce this bug", "record my game", or "step through the replay". Not for writing rules (use dota-rules) or first-time install (use dota-setup).
---

# dota2-integrations record and replay

Recordings are JSONL files in `recordings/`: one `{"ts": ..., "data": <GSI payload>}` per line. The replay tool is `tools/replay.py`; it POSTs frames to a running app.

## Record

```bash
uv run python -m src.main --record
```

Play, then open `http://127.0.0.1:6969/record/save`. It writes `recordings/gsi_<timestamp>.jsonl` with everything since startup. Frames arrive many times a second, so don't try to annotate while recording; annotate afterwards in step mode.

## Replay

Start the app normally (no `--record`), then in another terminal:

```bash
uv run python tools/replay.py recordings/x.jsonl                # recorded timing
uv run python tools/replay.py recordings/x.jsonl --instant      # no delays
uv run python tools/replay.py recordings/x.jsonl --step         # interactive
```

Rules fire for real (sounds, lights, webhooks), so use a scratch `rules.json` with harmless actions when debugging.

## Step mode

| Command | Does |
|---|---|
| `<enter>` / `n [N]` | send the next N frames |
| `c [prefix]` | send frames until a field changes (optionally only under a dotted path such as `abilities.ability3`) or a rule fires |
| `d` | what changed in the last step |
| `s [path]` | dump the app's raw state, or one dotted path of it |
| `note <text>` | annotate the current frame |
| `q` | quit |

Each frame sent prints any rule events that fired (`FIRED rule=... event=...`) and its note, if it has one. The diff hides per-frame noise (`provider.timestamp`, `map.game_time`, `map.clock_time`, `previously.*`, `added.*`).

A good debugging loop: `c abilities.ability3` (or whatever field the rule depends on) to jump to the interesting frame, `d` to see exactly what changed, `s <path>` to look at the state the monitor saw, and compare with whether `FIRED` appeared.

## Debugging a monitor or rule

A worked example: the `centaur_work_horse` ability monitor stopped working once the ability transformed into `centaur_mount` and back. The approach that found and fixed it:

1. **Reproduce from a recording, not from theory.** Get a recording of the misbehaviour (the user can note the moment afterwards with `note`). Don't guess at game mechanics; the payload is the ground truth.
2. **Look at the raw fields the monitor reads, per frame.** Step to the relevant region with `c <prefix>` and read `d`. Here the diff showed `abilities.ability3.name` going `centaur_work_horse` -> `centaur_mount` -> `centaur_work_horse` with the slot unchanged and the cooldown only appearing on the revert.
3. **Name the assumption the monitor made that the data breaks.** Monitors encode assumptions (a name is stable, a slot never changes, a counter only goes up, `max_cooldown` is reliable). Compare each against the frames. Here: "an ability keeps its name", so the lookup failed mid-transform, state was reset, and the 0 -> cooldown transition was lost.
4. **Decide what "correct" means before coding.** Working is not the same as right. The first fix made the monitor fire when the revert showed a cooldown (functionally correct, but late and unintuitive); what the player actually cares about is the click, which is the moment the ability is replaced. If the semantics are ambiguous, ask.
5. **Fix generically.** Prefer a rule that follows the data (track the slot) over a hardcoded list of special cases (an alias table for one hero).
6. **Verify by replaying the same recording.** Confirm the event fires at the intended frame, exactly once (`c` stops on `FIRED`), and that nothing fires on the later frames. A quick pass over other recordings checks you haven't broken the normal case.
7. **State the limits.** Write down what the fix doesn't cover (e.g. other heroes whose abilities swap slots), so the next person knows where to look.

Gotchas when reproducing:
- A rule with no enabled actions is skipped at compile time and will never show `FIRED`; give the scratch rule a harmless action (a light needs a `priority`).
- The app rewrites `rules.json` on load, so edit it with the app stopped.
- Only one app can hold port 6969. If `/state` returns 404 or frames seem ignored, an older instance is probably still running.
- `ts` is the stable key for a frame; frame numbers in the stepper are 1-based and shift if the recording is trimmed.

## Notes

`note` writes `recordings/x.notes.json` (`{ts: text}`), leaving the recording untouched. A frame can also carry an inline `"note"` field in its jsonl line. On every replay the note is injected into the POSTed JSON as a top-level `note` field; the app logs `GSI note: ...` and strips it before processing, so notes line up with the log output.

## Debug endpoint

`GET /state` (always on) waits for queued payloads to be processed, then returns `{"version", "raw", "fired"}`: the latest raw payload and the rule events fired since the previous call. It drains `fired`, so the stepper is its only intended consumer.
