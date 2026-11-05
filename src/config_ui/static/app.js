"use strict";

const CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/";
const itemImg = (img) => `${CDN}items/${img}.png`;
const abilityImg = (key) => `${CDN}abilities/${key}.png`;
const heroImg = (key) => `${CDN}heroes/${key}.png`;

// ---- What each kind of trigger can listen for ----

const ITEM_EVENTS = [
  { event: "ITEM_ACQUIRED", label: "Bought", desc: "When the item lands in your inventory (bought, picked up or assembled)." },
  { event: "COOLDOWN_STARTED", label: "Used", desc: "When you activate the item and it goes on cooldown." },
  { event: "COOLDOWN_READY", label: "Ready", desc: "When the item comes off cooldown and can be used again." },
  { event: "ITEM_LOST", label: "Lost", desc: "When the item leaves your inventory (sold, dropped, consumed or disassembled)." },
];

const MIDAS_EVENTS = [
  { event: "CHARGED", label: "1 charge", desc: "Hand of Midas has a charge ready.", monitor: { type: "midas" } },
  { event: "OVERCHARGED", label: "2 charges", desc: "Hand of Midas is sitting on 2 charges. Use it!", monitor: { type: "midas" } },
];

const ABILITY_EVENTS = [
  { event: "COOLDOWN_STARTED", label: "Cast", desc: "When you cast this ability and it goes on cooldown. Only fires once the ability is learned." },
];

const GAME_EVENTS = [
  { type: "map", event: "DAYTIME_STARTED", label: "Day breaks", sub: "Every day cycle", glyph: "☀️", baseline: true },
  { type: "map", event: "NIGHTTIME_STARTED", label: "Night falls", sub: "Every night cycle", glyph: "🌙", baseline: true },
  { type: "map", event: "PAUSED", label: "Game paused", sub: "Anyone pauses", glyph: "⏸️", baseline: true },
  { type: "map", event: "UNPAUSED", label: "Game unpaused", sub: "Play resumes", glyph: "▶️", baseline: true },
  { type: "hero", event: "HERO_KILLED", label: "You died", sub: "Your hero is killed", glyph: "💀" },
  { type: "hero", event: "HERO_RESPAWNED", label: "You respawned", sub: "Back from the fountain", glyph: "✨" },
  { type: "midas", event: "CHARGED", label: "Midas ready", sub: "1 charge available", img: itemImg("hand_of_midas") },
  { type: "midas", event: "OVERCHARGED", label: "Midas overcharged", sub: "2 charges, wasted gold!", img: itemImg("hand_of_midas") },
];

// Periodic triggers on the game clock. offset shifts each trigger (negative = that many seconds early);
// min_time / max_time are clock seconds limiting which triggers fire. Timings follow the current patch.
const REMINDER_PRESETS = [
  { id: "stack", label: "Stack camps", sub: "Every minute at x:53", glyph: "🏕️", monitor: { period: 60, offset: -7, min_time: 0, max_time: null } },
  { id: "bounty_rune", label: "Bounty runes", sub: "20 s before each 3:00 bounty", glyph: "💰", monitor: { period: 180, offset: -20, min_time: 0, max_time: null } },
  { id: "power_rune", label: "Power rune", sub: "15 s before each 2:00 rune, from 6:00", glyph: "⚡", monitor: { period: 120, offset: -15, min_time: 345, max_time: null } },
  { id: "wisdom_rune", label: "Wisdom runes", sub: "30 s before each 7:00 rune", glyph: "📘", monitor: { period: 420, offset: -30, min_time: 0, max_time: null } },
  { id: "lotus", label: "Lotus pool", sub: "15 s before each 3:00 lotus", glyph: "🪷", monitor: { period: 180, offset: -15, min_time: 0, max_time: null } },
];

const LIGHT_PRESETS = ["#ff0000", "#ff8800", "#ffd23f", "#33cc33", "#00c8ff", "#3355ff", "#a020f0", "#ffffff"];

// ---- State ----

const S = {
  config: null,       // rules.json as last loaded / edited
  saved: "",          // JSON of the config as last saved, for dirty tracking
  media: [],
  catalog: { heroes: [], items: [] },
  tab: "rules",
  selection: null,    // { kind: "item"|"ability"|"game"|"reminder", key, event? }
  activeEvent: null,
  heroKey: null,
  itemQuery: "",
  heroQuery: "",
  heroAttr: null,
  newRuleIds: new Set(),
  clips: [],          // soundboard.json clips (saved immediately, not via the Save button)
  maxClip: 5.2,
  clipQuery: "",
  ruleQuery: "",
  ruleKind: "",       // All rules filters: "" | item | ability | game | reminder
  ruleAction: "",     // "" | play_sound | light | webhook | missing
  ruleSort: "default",
  sharing: null,      // /api/sharing: folder, name, friends' rules and clips
  join: null,         // joining a shared folder from its link: { link, name, status }
  invite: null,       // /api/sharing/invite links while the invite panel is open
  shareSetup: null,   // folder picker state while turning sharing on or changing it
};

const lookup = { items: new Map(), abilities: new Map() };

const $ = (sel, root = document) => root.querySelector(sel);
const ICONS = {
  trash: "M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m5 5v6m4-6v6",
  save: "M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2zM17 21v-8H7v8M7 3v5h8",
  sound: "M11 5 6 9H2v6h4l5 4V5zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14",
  light: "M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.2 1 2.3h6c0-1.1.4-1.8 1-2.3A7 7 0 0 0 12 2z",
  webhook: "M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7",
  shuffle: "M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5",
  plus: "M12 5v14M5 12h14",
  copy: "M9 9h13v13H9zM5 15H2V2h13v3",
  swap: "M17 1l4 4-4 4M3 11V9a4 4 0 0 1 4-4h14M7 23l-4-4 4-4M21 13v2a4 4 0 0 1-4 4H3",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  invite: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM19 8v6M22 11h-6",
};
const icon = (name) => {
  const el = document.createElement("span");
  el.className = "ico";
  el.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONS[name]}"/></svg>`;
  return el;
};

const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
};

// ---- API ----

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(body.error || res.statusText), { body });
  return body;
}

async function loadAll() {
  const [config, media, board, info] = await Promise.all([api("/api/config"), api("/api/media"), api("/api/soundboard"), api("/api/info")]);
  S.dataDir = info.data_dir;
  $("#power").hidden = !info.can_shutdown;
  $("#save-recording").hidden = !info.recording;
  S.config = config;
  S.media = media;
  S.clips = board.clips;
  S.maxClip = board.max_seconds;
  S.saved = JSON.stringify(config);
  renderTopbar();
  render();
  loadSharing().then(render);
  // The catalog may need a first-time download, so don't block on it.
  api("/api/catalog").then((cat) => {
    S.catalog = cat;
    lookup.items = new Map(cat.items.map((i) => [i.key, i]));
    lookup.abilities = new Map();
    for (const hero of cat.heroes) for (const ab of hero.abilities) lookup.abilities.set(ab.key, { ...ab, hero });
    if (cat.offline) toast("Couldn't download the Dota hero & item list. You can still edit existing rules.", "err");
    render();
  }).catch(() => {
    S.catalog = { heroes: [], items: [], offline: true };
    toast("Couldn't load the Dota hero & item list.", "err");
    render();
  });
}

// ---- Rule helpers ----

const isBlink = (m) => m.type === "blink";
const monitorTarget = (m) => (m.type === "midas" ? "item_hand_of_midas" : isBlink(m) ? "item_blink" : m.target);

const periodicKey = (m) => [m.period, m.offset ?? 0, m.min_time ?? null, m.max_time ?? null].join("|");

function sameMonitor(a, b) {
  const norm = (m) => (isBlink(m) ? { type: "item", target: "item_blink", event: m.event } : m);
  a = norm(a); b = norm(b);
  if (a.type === "periodic" || b.type === "periodic") return a.type === b.type && periodicKey(a) === periodicKey(b);
  if (a.type === "once" || b.type === "once") return a.type === b.type && a.time === b.time;
  return a.type === b.type && (a.target || "") === (b.target || "") && a.event === b.event;
}

const rulesFor = (monitor) => S.config.rules.filter((r) => sameMonitor(r.monitor, monitor));
const activeActions = (r) => r.actions.filter((a) => a.enabled !== false);

function rulesForTarget(target) {
  return S.config.rules.filter((r) => monitorTarget(r.monitor) === target && activeActions(r).length);
}

function ruleIdFor(monitor) {
  const target = (monitor.target || monitor.type).replace(/^item_/, "");
  const suffix = {
    ITEM_ACQUIRED: "bought", COOLDOWN_STARTED: "used", COOLDOWN_READY: "ready", ITEM_LOST: "lost",
  }[monitor.event] || monitor.event.toLowerCase();
  let id = `${target}_${suffix}`;
  for (let n = 2; S.config.rules.some((r) => r.id === id); n++) id = `${target}_${suffix}_${n}`;
  return id;
}

function ensureRule(monitor) {
  let rule = rulesFor(monitor)[0];
  if (!rule) {
    rule = { id: ruleIdFor(monitor), monitor: { ...monitor }, actions: [] };
    S.config.rules.push(rule);
    S.newRuleIds.add(rule.id);
  }
  return rule;
}

function nextPriority() {
  let max = 0;
  for (const r of S.config.rules) for (const a of r.actions) if (a.type === "light" && a.priority) max = Math.max(max, a.priority);
  return max + 1;
}

const isBaseline = (monitor) => monitor.type === "map";
const hex = (a) => "#" + [a.r, a.g, a.b].map((v) => v.toString(16).padStart(2, "0")).join("");
const rgb = (hexStr) => ({ r: parseInt(hexStr.slice(1, 3), 16), g: parseInt(hexStr.slice(3, 5), 16), b: parseInt(hexStr.slice(5, 7), 16) });
const stripExt = (name) => name.replace(/\.[^.]+$/, "");
const fileName = (file) => stripExt(file.replace(/^media\//, ""));
const mediaLabel = (m) => stripExt(m.name);
const hasMedia = (file) => S.media.some((m) => m.file === file);
// A play_sound action holds weighted clips; the editor only offers a single clip at 100% for now
const clipOf = (a) => a.clips[0];
const CLIP_COLOURS = ["#c9a65a", "#4f8fd6", "#5fa85a", "#b8392a", "#8a6ad1", "#3fb0b0"];

function describeTrigger(m) {
  const ev = (list) => list.find((e) => e.event === m.event)?.label || m.event;
  if (m.type === "item" || m.type === "blink") {
    const target = monitorTarget(m);
    const item = lookup.items.get(target);
    return { title: `${item?.name || target} · ${ev(ITEM_EVENTS)}`, sub: target, img: item ? itemImg(item.img) : itemImg(target.replace(/^item_/, "")) };
  }
  if (m.type === "ability") {
    const ab = lookup.abilities.get(m.target);
    return { title: `${ab?.name || m.target} · Cast`, sub: ab ? `${ab.hero.name} · ${m.target}` : m.target, img: abilityImg(m.target), square: true };
  }
  if (m.type === "periodic") {
    const preset = reminderPreset(m);
    return { title: preset ? `Reminder · ${preset.label}` : `Reminder · every ${clock(m.period)}`, sub: reminderSummary(m), glyph: preset?.glyph || "⏰" };
  }
  if (m.type === "once") return { title: `Reminder · at ${clock(m.time)}`, sub: `Once at ${clock(m.time)}`, glyph: "⏰" };
  const g = GAME_EVENTS.find((e) => e.type === m.type && e.event === m.event);
  return { title: g?.label || m.event, sub: g?.sub || m.type, img: g?.img, glyph: g?.glyph };
}

// ---- Reminders (periodic and once monitors) ----

const isReminder = (m) => m.type === "periodic" || m.type === "once";

// Game clock seconds as m:ss; the clock is negative before the horn
const clock = (sec) => `${sec < 0 ? "-" : ""}${Math.floor(Math.abs(sec) / 60)}:${String(Math.abs(sec) % 60).padStart(2, "0")}`;
function parseClock(text) {
  const t = text.trim();
  if (!t) return null;
  const m = t.match(/^(-)?(?:(\d+):)?(\d{1,2})$/);
  if (!m) return undefined;
  const sec = (+(m[2] || 0)) * 60 + +m[3];
  return m[1] ? -sec : sec;
}
const reminderPreset = (m) => REMINDER_PRESETS.find((p) => sameMonitor({ type: "periodic", ...p.monitor }, m));

// The first few clock times this reminder fires at, as the backend computes them
function reminderTimes(m, count = 4) {
  const off = m.offset ?? 0;
  const start = Math.max(m.min_time ?? -90, -90);
  let t = start + (((off - start) % m.period) + m.period) % m.period;
  const out = [];
  for (; out.length < count && (m.max_time == null || t <= m.max_time); t += m.period) out.push(t);
  return out;
}

function reminderSummary(m) {
  const off = m.offset ?? 0;
  const shift = off < 0 ? `, ${-off} s early` : off > 0 ? `, ${off} s late` : "";
  const range = [m.min_time != null ? `from ${clock(m.min_time)}` : "", m.max_time != null ? `until ${clock(m.max_time)}` : ""].filter(Boolean).join(" ");
  return `Every ${clock(m.period)}${shift}${range ? `, ${range}` : ""}`;
}

function addReminder(preset) {
  const monitor = { type: "periodic", period: 300, offset: 0, min_time: 0, max_time: null, ...preset?.monitor };
  let rule = preset && rulesFor(monitor)[0];
  if (!rule) {
    const base = `reminder_${preset?.id || "custom"}`;
    let id = base;
    for (let n = 2; S.config.rules.some((r) => r.id === id); n++) id = `${base}_${n}`;
    rule = { id, monitor, actions: [] };
    S.config.rules.push(rule);
    S.newRuleIds.add(id);
  }
  S.tab = "events";
  select({ kind: "reminder", key: rule.id });
}

// ---- Dirty / save ----

function markDirty() {
  renderStatus();
}

function cleanedConfig() {
  // Drop rules created in this session that ended up with no actions.
  const rules = S.config.rules.filter((r) => r.actions.length || !S.newRuleIds.has(r.id));
  return { ...S.config, rules };
}

function isDirty() {
  return JSON.stringify(cleanedConfig()) !== S.saved;
}

function renderStatus(text, cls) {
  const status = $("#status");
  const dirty = isDirty();
  $("#save").disabled = !dirty;
  if (text) { status.textContent = text; status.className = `status ${cls || ""}`; return; }
  status.textContent = dirty ? "Unsaved changes" : "All changes live";
  status.className = `status ${dirty ? "dirty" : "ok"}`;
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function actionText(a) {
  if (a.type === "play_sound") return a.clips.length > 1 ? `play one of ${a.clips.length} sounds` : `play ${clipOf(a).file || "(no sound)"}${clipOf(a).volume != null ? ` at ${clipOf(a).volume}%` : ""}`;
  if (a.type === "light") return `light rgb(${a.r}, ${a.g}, ${a.b})`;
  if (a.type === "reset_light") return "reset light";
  return a.type;
}

// Human-readable list of differences between the saved config and the editor's copy.
function describeChanges() {
  const was = JSON.parse(S.saved);
  const now = cleanedConfig();
  const out = [];
  const add = (label, detail, monitor) => out.push({ label, detail, trigger: monitor && describeTrigger(monitor) });

  if (was.sound?.volume !== now.sound?.volume) add("Master volume", `${was.sound?.volume}% → ${now.sound?.volume}%`);
  if (was.lighting?.enabled !== now.lighting?.enabled) add("Lighting", now.lighting.enabled ? "enabled" : "disabled");
  if (was.lighting?.vendor !== now.lighting?.vendor) add("Lighting vendor", `${was.lighting?.vendor} → ${now.lighting?.vendor}`);
  if (!same(was.map_colours, now.map_colours)) add("Day/night colours", "changed");

  const wasRules = new Map((was.rules || []).map((r) => [r.id, r]));
  const nowRules = new Map(now.rules.map((r) => [r.id, r]));
  const title = (r) => describeTrigger(r.monitor).title;
  for (const [id, r] of nowRules) {
    const old = wasRules.get(id);
    if (!old) { add(`New rule: ${title(r)}`, r.actions.map(actionText).join(", "), r.monitor); continue; }
    const parts = [];
    if (!same(old.monitor, r.monitor)) parts.push(`trigger ${title(old)} → ${title(r)}`);
    if (!same(old.actions, r.actions)) {
      const o = old.actions.map(actionText), n = r.actions.map(actionText);
      parts.push(`actions: ${o.join(", ") || "none"} → ${n.join(", ") || "none"}`);
    }
    for (const k of Object.keys({ ...old, ...r })) {
      if (k === "id" || k === "monitor" || k === "actions" || same(old[k], r[k])) continue;
      parts.push(`${k}: ${JSON.stringify(old[k] ?? null)} → ${JSON.stringify(r[k] ?? null)}`);
    }
    if (parts.length) add(`Edited rule: ${title(r)}`, parts.join("; "), r.monitor);
  }
  for (const [id, r] of wasRules) if (!nowRules.has(id)) add(`Deleted rule: ${title(r)}`, r.actions.map(actionText).join(", "), r.monitor);
  const common = (m, other) => [...m.keys()].filter((id) => other.has(id));
  if (!same(common(wasRules, nowRules), common(nowRules, wasRules))) add("Rule order", "changed");

  if (!out.length) add("Other settings", "changed");
  return out;
}

// Nothing is written until Save, so Cancel leaves no file behind
function openSaveRecording() {
  const close = () => { backdrop.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const pad = (n) => String(n).padStart(2, "0");
  const now = new Date();
  const suggested = `gsi_${now.getFullYear()}_${pad(now.getMonth() + 1)}_${pad(now.getDate())}_${pad(now.getHours())}_${pad(now.getMinutes())}_${pad(now.getSeconds())}`;
  const saveIt = async () => {
    const res = await fetch("/record/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: input.value.trim() || suggested }) })
      .catch((e) => ({ ok: false, text: async () => e.message }));
    if (!res.ok) { toast((await res.text()).trim(), "err"); input.focus(); return; }
    const { file, count } = await res.json();
    toast(`Saved ${plural(count, "update")} to ${file}`, "ok", 7000);
    close();
  };
  const input = h("input", { type: "text", value: suggested, maxlength: 100, "aria-label": "Recording name", onkeydown: (e) => { if (e.key === "Enter") saveIt(); } });
  const backdrop = h("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(); } },
    h("div", { class: "modal recording-saved", role: "dialog", "aria-modal": "true", "aria-label": "Save recording" },
      h("div", { class: "modal-head" }, h("h2", {}, "Save recording"), h("button", { class: "btn btn-ghost btn-sm", "aria-label": "Close", onclick: close }, "✕")),
      h("div", { class: "recording-name" },
        h("p", { class: "hint" }, "Saves everything recorded so far to the recordings folder."),
        h("div", { class: "field" }, input, h("span", { class: "hint" }, ".jsonl"))),
      h("div", { class: "modal-foot" },
        h("span", { style: { flex: 1 } }),
        h("button", { class: "btn btn-ghost", onclick: close }, "Cancel"),
        h("button", { class: "btn btn-gold", onclick: saveIt }, icon("save"), "Save"))));
  document.body.append(backdrop);
  document.addEventListener("keydown", onKey);
  input.select();
}

function showChanges() {
  if (!S.config || !isDirty()) return;
  const close = () => { backdrop.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const items = describeChanges();
  const backdrop = h("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(); } },
    h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": "Unsaved changes" },
      h("div", { class: "modal-head" }, h("h2", {}, "Unsaved changes"), h("button", { class: "btn btn-ghost btn-sm", "aria-label": "Close", onclick: close }, "✕")),
      h("ul", { class: "changes" }, items.map((c) => h("li", {},
        c.trigger ? h("span", { class: `thumb ${c.trigger.square ? "square" : ""}`, style: c.trigger.img ? { backgroundImage: `url("${c.trigger.img}")` } : null }, c.trigger.glyph || "") : null,
        h("div", {}, h("strong", {}, c.label), c.detail ? h("div", { class: "hint" }, c.detail) : null)))),
      h("div", { class: "modal-foot" },
        h("span", { style: { flex: 1 } }),
        h("button", { class: "btn btn-ghost", onclick: close }, "Close"),
        h("button", { class: "btn btn-gold", onclick: () => { close(); save(); } }, icon("save"), "Save"))));
  document.body.append(backdrop);
  document.addEventListener("keydown", onKey);
}

function locToText(loc) {
  if (loc[0] === "rules" && typeof loc[1] === "number") {
    const rule = cleanedConfig().rules[loc[1]];
    if (rule) return describeTrigger(rule.monitor).title;
  }
  return loc.join(" › ") || "Config";
}

async function save() {
  const config = cleanedConfig();
  $("#save").disabled = true;
  renderStatus("Saving…");
  try {
    const res = await api("/api/config", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
    // Re-read so we mirror exactly what the server wrote (defaults filled in).
    S.config = await api("/api/config");
    S.saved = JSON.stringify(S.config);
    S.newRuleIds.clear();
    renderStatus();
    toast(res.restart_required ? "Saved. Restart the app for the lighting change to apply." : "Saved. Your rules are live, no restart needed.", "ok");
    render();
  } catch (e) {
    const errors = e.body?.errors || [{ loc: [], msg: e.message }];
    renderStatus("Couldn't save", "err");
    $("#save").disabled = false;
    toast(h("div", {}, h("strong", {}, "Fix these, then save again:"),
      h("ul", {}, errors.map((er) => h("li", {}, `${locToText(er.loc)}: ${er.msg}`)))), "err", 9000);
  }
}

async function powerOff() {
  const unsaved = isDirty() ? "\n\nYou have unsaved changes. They will be lost." : "";
  if (!confirm(`Turn off Soundbo?\n\nGame sounds and lights stop until you open the app again.${unsaved}`)) return;
  try {
    await api("/api/shutdown", { method: "POST" });
  } catch (e) {
    toast(`Couldn't turn off: ${e.message}`, "err");
    return;
  }
  S.config = null; // nothing left to protect in beforeunload
  previewAudio?.pause();
  document.body.replaceChildren(h("div", { class: "off-screen" },
    h("div", { class: "off-glyph" }, "⏻"),
    h("h1", {}, "Soundbo is off"),
    h("p", {}, "Open the app again to bring back your sounds, lights and this editor. You can close this tab."),
    S.dataDir ? h("p", { class: "hint" }, "Your rules, sounds and logs are in ", h("code", {}, S.dataDir)) : null));
  document.title = "Soundbo (off)";
}

// ---- Toasts ----

function toast(content, cls = "", ms = 4000) {
  const el = h("div", { class: `toast ${cls}`, role: "status" }, content);
  $("#toasts").append(el);
  setTimeout(() => el.remove(), ms);
}

// ---- Audio preview ----

const mediaUrl = (file) => "/" + file.split("/").map(encodeURIComponent).join("/");

let previewAudio = null;
let previewBtn = null;

function previewSound(file, volume, btn) {
  if (previewAudio) {
    previewAudio.pause();
    previewBtn?.classList.remove("playing");
    if (previewBtn === btn) { previewAudio = previewBtn = null; return; }
  }
  previewAudio = new Audio(mediaUrl(file));
  previewAudio.volume = Math.min(1, (volume ?? 100) / 100);
  previewBtn = btn;
  btn?.classList.add("playing");
  previewAudio.addEventListener("ended", () => btn?.classList.remove("playing"));
  previewAudio.play().catch(() => btn?.classList.remove("playing"));
}

const playButton = (file, getVolume) => {
  const btn = h("button", { class: "play", title: "Preview", "aria-label": `Preview ${fileName(file)}` }, "▶");
  btn.addEventListener("click", (e) => { e.stopPropagation(); previewSound(file, getVolume?.(), btn); });
  return btn;
};

async function uploadFile(file, saveAs) {
  const form = new FormData();
  form.append("file", file);
  try {
    const query = saveAs ? `?name=${encodeURIComponent(saveAs)}` : "";
    const res = await api(`/api/media${query}`, { method: "POST", body: form });
    S.media = await api("/api/media");
    toast(`Added ${res.name}`, "ok");
    return res.file;
  } catch (e) {
    toast(`Upload failed: ${e.message}`, "err");
    return null;
  }
}

// ---- Top bar ----

function renderTopbar() {
  const vol = $("#master-volume");
  vol.value = S.config.sound.volume;
  $("#master-volume-out").value = `${vol.value}%`;
  $("#lighting-enabled").checked = S.config.lighting.enabled;
  $("#lighting-vendor").value = S.config.lighting.vendor;
  renderStatus();
}

$("#master-volume").addEventListener("input", (e) => {
  S.config.sound.volume = +e.target.value;
  $("#master-volume-out").value = `${e.target.value}%`;
  markDirty();
});
$("#lighting-enabled").addEventListener("change", (e) => { S.config.lighting.enabled = e.target.checked; markDirty(); });
$("#lighting-vendor").addEventListener("change", (e) => { S.config.lighting.vendor = e.target.value; markDirty(); });
$("#save").addEventListener("click", save);
$("#status").addEventListener("click", (e) => { if (e.currentTarget.classList.contains("dirty")) showChanges(); });
$("#power").addEventListener("click", powerOff);
$("#save-recording").addEventListener("click", openSaveRecording);
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); if (isDirty()) save(); }
});
window.addEventListener("beforeunload", (e) => { if (S.config && isDirty()) e.preventDefault(); });

$("#tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (!btn) return;
  S.tab = btn.dataset.tab;
  render();
  // Pick up whatever friends synced since last look
  if (["friends", "soundboard", "rules"].includes(S.tab)) Promise.all([loadSharing(), refreshClips()]).then(render);
});

// ---- Board ----

function render() {
  for (const b of document.querySelectorAll("#tabs button")) b.classList.toggle("active", b.dataset.tab === S.tab);
  const board = $("#board");
  const scroll = board.scrollTop;
  // The soundboard and Friends tabs don't use the inspector, so they get its width too
  $(".layout").classList.toggle("no-inspector", S.tab === "soundboard" || S.tab === "friends");
  board.replaceChildren(...[({ rules: renderRules, items: renderItems, heroes: renderHeroes, events: renderEvents, sounds: renderSounds, soundboard: renderSoundboard, friends: renderFriends }[S.tab])()].flat().filter(Boolean));
  board.scrollTop = scroll;
  renderInspector();
}

function select(selection) {
  S.selection = selection;
  S.activeEvent = selection.event || null;
  render();
}

function slot({ img, label, cost, cls = "", count = 0, selected, onclick, title }) {
  const el = h("button", {
    class: `slot ${cls} ${count ? "has-rules" : ""} ${selected ? "selected" : ""}`,
    title, "aria-label": title || label, onclick,
    style: img ? { backgroundImage: `url("${img}")` } : null,
  },
  count ? h("span", { class: "badge" }, count) : null,
  label ? h("span", { class: "label" }, label) : null,
  cost ? h("span", { class: "cost" }, cost) : null);
  return el;
}

const RULE_KINDS = [["", "All triggers"], ["item", "Items"], ["ability", "Abilities"], ["game", "Game events"], ["reminder", "Reminders"]];
const RULE_ACTIONS = [["", "Any action"], ["play_sound", "Plays a sound"], ["light", "Sets a light"], ["webhook", "Calls a webhook"], ["missing", "Missing sound file"]];
const RULE_SORTS = [["default", "File order"], ["name", "Name A–Z"], ["name-desc", "Name Z–A"], ["kind", "Trigger type"], ["actions", "Most actions"]];

const ruleKind = (m) => (["item", "blink", "midas"].includes(m.type) ? "item" : m.type === "ability" ? "ability" : isReminder(m) ? "reminder" : "game");

function visibleRules() {
  const q = S.ruleQuery.trim().toLowerCase();
  const rules = S.config.rules.filter((r) => {
    if (S.ruleKind && ruleKind(r.monitor) !== S.ruleKind) return false;
    if (S.ruleAction === "missing" && !brokenRule(r)) return false;
    if (S.ruleAction && S.ruleAction !== "missing" && !r.actions.some((a) => a.type === S.ruleAction)) return false;
    if (!q) return true;
    const d = describeTrigger(r.monitor);
    const text = [r.id, d.title, d.sub, ...r.actions.flatMap((a) => (a.type === "play_sound" ? a.clips.map((c) => fileName(c.file)) : [a.url || ""]))];
    return text.some((t) => t && t.toLowerCase().includes(q));
  });
  const title = (r) => describeTrigger(r.monitor).title.toLowerCase();
  const order = { item: 0, ability: 1, game: 2, reminder: 3 };
  const sorts = {
    name: (a, b) => title(a).localeCompare(title(b)),
    "name-desc": (a, b) => title(b).localeCompare(title(a)),
    kind: (a, b) => order[ruleKind(a.monitor)] - order[ruleKind(b.monitor)] || title(a).localeCompare(title(b)),
    actions: (a, b) => activeActions(b).length - activeActions(a).length || title(a).localeCompare(title(b)),
  };
  return sorts[S.ruleSort] ? [...rules].sort(sorts[S.ruleSort]) : rules;
}

function ruleToolbar() {
  const search = h("input", { type: "search", placeholder: "Search rules, heroes, sounds…", value: S.ruleQuery, "aria-label": "Search rules" });
  search.addEventListener("input", (e) => { S.ruleQuery = e.target.value; rerenderKeepFocus(search); });
  const pick = (key, options, label) => {
    const sel = h("select", { "aria-label": label, onchange: (e) => { S[key] = e.target.value; render(); } },
      options.map(([v, text]) => h("option", { value: v, selected: S[key] === v }, text)));
    return sel;
  };
  const filtered = S.ruleQuery || S.ruleKind || S.ruleAction;
  return h("div", { class: "rule-toolbar" }, search,
    pick("ruleKind", RULE_KINDS, "Filter by trigger"),
    pick("ruleAction", RULE_ACTIONS, "Filter by action"),
    pick("ruleSort", RULE_SORTS, "Sort rules"),
    filtered ? h("button", { class: "btn btn-sm", onclick: () => { S.ruleQuery = S.ruleKind = S.ruleAction = ""; render(); } }, "Clear") : null);
}

// One chip per sound; a rule with several shows each one's odds
const soundChips = (a) => a.clips.map((c) => {
  const ok = hasMedia(c.file);
  return h("span", { class: `chip ${a.enabled === false ? "off" : ""} ${ok ? "" : "missing"}`, title: c.file },
    ok ? playButton(c.file, () => c.volume) : "♪ ", a.clips.length > 1 ? `${fileName(c.file)} · ${c.probability}%` : `${fileName(c.file)} · ${c.volume}%`);
});

function ruleRow(r) {
  const d = describeTrigger(r.monitor);
  const acts = r.actions.flatMap((a) => {
    const off = a.enabled === false ? "off" : "";
    if (a.type === "play_sound") return soundChips(a);
    if (a.type === "light") return [h("span", { class: `chip ${off}` }, h("span", { class: "swatch", style: { background: hex(a) } }), a.priority ? `prio ${a.priority}` : "baseline")];
    return [h("span", { class: `chip ${off}`, title: a.url }, "⇢ webhook")];
  });
  // A div, not a button: the sound chips hold their own preview buttons
  return h("div", {
    class: `rule-row ${activeActions(r).length ? "" : "inactive"}`,
    role: "button", tabindex: "0",
    onclick: () => jumpTo(r.monitor, r),
    onkeydown: (e) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); jumpTo(r.monitor, r); } },
  },
  h("span", { class: `thumb ${d.square ? "square" : ""}`, style: d.img ? { backgroundImage: `url("${d.img}")` } : null }, d.glyph || ""),
  h("span", { class: "trig" }, h("div", { class: "t" }, d.title), h("div", { class: "s" }, d.sub)),
  h("span", { class: "acts" }, acts.length ? acts : h("span", { class: "hint" }, "No actions")),
  h("span", { class: "arrow" }, "›"));
}

function renderRules() {
  const rules = visibleRules();
  const live = rules.filter((r) => activeActions(r).length);
  const idle = rules.filter((r) => !activeActions(r).length);
  const row = ruleRow;
  return [
    h("div", { class: "board-head" }, h("h1", {}, "All rules")),
    h("p", { class: "hint" }, "Every trigger that does something. Click one to edit it, or browse Items, Heroes and Game events to add new ones."),
    followedNote(),
    ruleToolbar(),
    !rules.length ? h("p", { class: "hint" }, S.config.rules.length ? "No rules match." : "No rules yet.") : null,
    live.length ? h("div", { class: "section-title" }, "Active", h("span", { class: "count" }, live.length)) : null,
    live.length ? h("div", { class: "rule-list" }, live.map(row)) : null,
    idle.length ? h("div", { class: "section-title" }, "Doing nothing yet", h("span", { class: "count" }, idle.length)) : null,
    idle.length ? h("div", { class: "rule-list" }, idle.map(row)) : null,
  ];
}

function followedNote() {
  const followed = [...(S.sharing?.people || []), ...(S.sharing?.packs || [])].filter((f) => f.following);
  if (!followed.length) return null;
  return h("p", { class: "insp-warn followed-note" }, "Also playing sounds from ",
    followed.flatMap((f, i) => [i ? ", " : "", h("strong", {}, f.name),
      ` (${plural(f.rules.filter((r) => hasSound(r) && !S.config.rules.some((m) => sameMonitor(m.monitor, r.monitor) && hasSound(m))).length, "trigger")})`]),
    ". ", h("button", { class: "linkish", onclick: () => { S.tab = "friends"; render(); } }, "Manage in Friends"));
}

function jumpTo(monitor, rule) {
  if (monitor.type === "item" || monitor.type === "blink") {
    S.tab = "items";
    select({ kind: "item", key: monitorTarget(monitor), event: monitor.event });
  } else if (monitor.type === "ability") {
    S.tab = "heroes";
    S.heroKey = lookup.abilities.get(monitor.target)?.hero.key || S.heroKey;
    select({ kind: "ability", key: monitor.target, event: monitor.event });
  } else if (isReminder(monitor)) {
    S.tab = "events";
    select({ kind: "reminder", key: (rule || rulesFor(monitor)[0])?.id });
  } else {
    S.tab = "events";
    select({ kind: "game", key: `${monitor.type}:${monitor.event}` });
  }
}

function renderItems() {
  const q = S.itemQuery.toLowerCase();
  const items = S.catalog.items.filter((i) => !q || i.name.toLowerCase().includes(q) || i.key.includes(q));
  const groups = ["Basics", "Upgrades", "Consumables", "Secret Shop", "Neutral"];
  const search = h("input", { type: "search", placeholder: "Search items…", value: S.itemQuery, "aria-label": "Search items" });
  search.addEventListener("input", (e) => { S.itemQuery = e.target.value; rerenderKeepFocus(search); });

  const used = S.config.rules.filter((r) => ["item", "blink", "midas"].includes(r.monitor.type)).map((r) => monitorTarget(r.monitor));
  const unknown = [...new Set(used)].filter((k) => S.catalog.items.length && !lookup.items.has(k));

  const out = [h("div", { class: "board-head" }, h("h1", {}, "Items"), search)];
  if (!S.catalog.items.length) {
    out.push(h("p", { class: "hint" }, S.catalog.offline ? "Item list unavailable offline." : "Loading the shop…"));
  }
  for (const g of groups) {
    const list = items.filter((i) => i.group === g);
    if (!list.length) continue;
    out.push(h("div", { class: "section-title" }, g, h("span", { class: "count" }, list.length)));
    out.push(h("div", { class: "icon-grid" }, list.map((i) => slot({
      img: itemImg(i.img),
      title: i.name,
      cost: i.cost || null,
      count: rulesForTarget(i.key).length,
      selected: S.selection?.kind === "item" && S.selection.key === i.key,
      onclick: () => select({ kind: "item", key: i.key }),
    }))));
  }
  if (unknown.length) {
    out.push(h("div", { class: "section-title" }, "Other"));
    out.push(h("div", { class: "icon-grid" }, unknown.map((k) => slot({ cls: "no-img", label: k, count: rulesForTarget(k).length, onclick: () => select({ kind: "item", key: k }) }))));
  }
  return out;
}

function rerenderKeepFocus(input) {
  const pos = input.selectionStart;
  render();
  const again = $(`#board input[type=search]`);
  again?.focus();
  again?.setSelectionRange(pos, pos);
}

function renderHeroes() {
  const q = S.heroQuery.toLowerCase();
  const heroes = S.catalog.heroes.filter((x) => (!q || x.name.toLowerCase().includes(q)) && (!S.heroAttr || x.attr === S.heroAttr));
  const search = h("input", { type: "search", placeholder: "Search heroes…", value: S.heroQuery, "aria-label": "Search heroes" });
  search.addEventListener("input", (e) => { S.heroQuery = e.target.value; rerenderKeepFocus(search); });
  const attrs = [["str", "var(--str)", "Strength"], ["agi", "var(--agi)", "Agility"], ["int", "var(--int)", "Intelligence"], ["all", "var(--uni)", "Universal"]];
  const attrBar = h("div", { class: "attr-bar" }, attrs.map(([a, c, name]) => h("button", {
    class: S.heroAttr === a ? "on" : "", title: name, "aria-label": name, "aria-pressed": String(S.heroAttr === a),
    onclick: () => { S.heroAttr = S.heroAttr === a ? null : a; render(); },
  }, h("span", { class: "attr-dot", style: { background: c } }))));

  const out = [h("div", { class: "board-head" }, h("h1", {}, "Heroes"), attrBar, search)];
  const hero = S.catalog.heroes.find((x) => x.key === S.heroKey);
  if (hero) out.push(renderHeroDetail(hero));
  if (!S.catalog.heroes.length) out.push(h("p", { class: "hint" }, S.catalog.offline ? "Hero list unavailable offline." : "Loading heroes…"));

  const heroCount = (x) => x.abilities.reduce((n, ab) => n + rulesForTarget(ab.key).length, 0);
  if (heroes.length) out.push(h("div", { class: "icon-grid heroes" }, heroes.map((x) => slot({
    img: heroImg(x.key), cls: "hero", label: x.name, title: x.name,
    count: heroCount(x),
    selected: x.key === S.heroKey,
    onclick: () => { S.heroKey = x.key; S.selection = null; render(); $("#board").scrollTop = 0; },
  }))));
  return out;
}

function renderHeroDetail(hero) {
  return h("section", { class: "hero-detail" },
    h("div", { class: "hero-portrait", style: { backgroundImage: `url("${heroImg(hero.key)}")` }, role: "img", "aria-label": hero.name }),
    h("div", {},
      h("h2", {}, hero.name),
      h("div", { class: "hint" }, "Click an ability to play something when you cast it. Passives never trigger."),
      h("div", { class: "ability-row" }, hero.abilities.map((ab) => h("div", { class: `ability-cell ${ab.has_cd ? "" : "passive"}` },
        slot({
          img: abilityImg(ab.key), cls: "ability", title: ab.name,
          count: rulesForTarget(ab.key).length,
          selected: S.selection?.kind === "ability" && S.selection.key === ab.key,
          onclick: () => select({ kind: "ability", key: ab.key }),
        }),
        h("div", { class: "name" }, ab.name))))));
}

function renderEvents() {
  const reminders = S.config.rules.filter((r) => isReminder(r.monitor));
  const card = ({ key, glyph, label, sub, n, onclick }) => h("button", {
    class: `event-card ${n ? "has-rules" : ""} ${S.selection?.kind === "reminder" && S.selection.key === key ? "selected" : ""}`, onclick,
  }, h("span", { class: "glyph" }, glyph), h("span", {}, h("div", { class: "t" }, label), h("div", { class: "s" }, sub)), n ? h("span", { class: "badge" }, `${n} ⚡`) : null);
  const reminderSection = [
    h("div", { class: "section-title" }, "Reminders", h("span", { class: "count" }, reminders.length)),
    h("p", { class: "hint" }, "Play a sound on the game clock: stack camps, runes, lotus, or your own timer, repeating or just once."),
    reminders.length ? h("div", { class: "event-grid" }, reminders.map((r) => {
      const d = describeTrigger(r.monitor);
      return card({ key: r.id, glyph: d.glyph, label: d.title.replace(/^Reminder · /, ""), sub: d.sub, n: activeActions(r).length, onclick: () => select({ kind: "reminder", key: r.id }) });
    })) : null,
    h("div", { class: "reminder-add" }, h("span", { class: "hint" }, "Add:"),
      REMINDER_PRESETS.filter((p) => !reminders.some((r) => sameMonitor(r.monitor, { type: "periodic", ...p.monitor })))
        .map((p) => h("button", { class: "btn btn-sm", title: p.sub, onclick: () => addReminder(p) }, `${p.glyph} ${p.label}`)),
      h("button", { class: "btn btn-sm", onclick: () => addReminder(null) }, "⏰ Custom timer")),
  ];
  return [
    h("div", { class: "board-head" }, h("h1", {}, "Game events")),
    h("div", { class: "event-grid" }, GAME_EVENTS.map((g) => {
      const n = rulesFor({ type: g.type, event: g.event }).filter((r) => activeActions(r).length).reduce((s, r) => s + activeActions(r).length, 0);
      const key = `${g.type}:${g.event}`;
      return h("button", {
        class: `event-card ${n ? "has-rules" : ""} ${S.selection?.kind === "game" && S.selection.key === key ? "selected" : ""}`,
        onclick: () => select({ kind: "game", key }),
      },
      h("span", { class: "glyph", style: g.img ? { backgroundImage: `url("${g.img}")` } : null }, g.img ? "" : g.glyph),
      h("span", {}, h("div", { class: "t" }, g.label), h("div", { class: "s" }, g.sub)),
      n ? h("span", { class: "badge" }, `${n} ⚡`) : null);
    })),
    ...reminderSection,
  ];
}

function renderSounds() {
  const usage = new Map();
  for (const r of S.config.rules) for (const c of soundClips(r)) usage.set(c.file, (usage.get(c.file) || 0) + 1);
  const input = h("input", { type: "file", accept: ".mp3,.wav,.ogg,audio/*", multiple: true, id: "upload-input" });
  input.addEventListener("change", async () => { for (const f of input.files) await uploadFile(f); render(); });
  const zone = h("div", { class: "dropzone" }, "Drop .mp3 / .wav / .ogg clips here, or ", h("label", { for: "upload-input" }, "browse"), input);
  makeDropTarget(zone, async (files) => { for (const f of files) await uploadFile(f); render(); });

  const missing = [...usage.keys()].filter((f) => !hasMedia(f));
  return [
    h("div", { class: "board-head" }, h("h1", {}, "Sounds")),
    zone,
    missing.length ? h("div", { class: "section-title" }, "Wanted (used by rules, not on disk)", h("span", { class: "count" }, missing.length)) : null,
    missing.length ? h("div", { class: "sound-list" }, missing.map((f) => {
      const row = h("div", { class: "sound-row" },
        h("span", { class: "play missing" }, "!"),
        h("span", { class: "n", title: f }, fileName(f)),
        h("span", { class: "u" }, "drop a clip here"));
      makeDropTarget(row, async ([file]) => {
        // Keep the expected name but the dropped file's real extension
        const path = await uploadFile(file, fileName(f) + file.name.slice(file.name.lastIndexOf(".")));
        if (!path) return;
        for (const r of S.config.rules) for (const a of r.actions) if (a.type === "play_sound" && a.clips.some((c) => c.file === f)) {
          for (const c of a.clips) if (c.file === f) c.file = path;
          a.enabled = true;
        }
        markDirty();
        render();
      });
      return row;
    })) : null,
    h("div", { class: "section-title" }, "Library", h("span", { class: "count" }, S.media.length)),
    h("div", { class: "sound-list" }, S.media.map((m) => h("div", { class: "sound-row" },
      playButton(m.file),
      h("span", { class: "n", title: mediaLabel(m) }, mediaLabel(m)),
      h("span", { class: "u" }, usage.get(m.file) ? `used ×${usage.get(m.file)}` : "unused")))),
  ];
}

function makeDropTarget(el, onFiles, accept = (f) => /\.(mp3|wav|ogg)$/i.test(f.name)) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add(el.classList.contains("action") ? "drop-over" : "over"); });
  el.addEventListener("dragleave", () => el.classList.remove("over", "drop-over"));
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    el.classList.remove("over", "drop-over");
    const files = [...e.dataTransfer.files].filter(accept);
    if (files.length) onFiles(files);
  });
}

// ---- Soundboard ----

const CLIP_ACCEPT = "audio/*,video/*,.mp3,.wav,.ogg,.m4a,.aac,.flac,.opus,.mp4,.mov,.webm,.mkv";
const isClipSource = (f) => /^(audio|video)\//.test(f.type) || /\.(mp3|wav|ogg|m4a|aac|flac|opus|mp4|mov|webm|mkv)$/i.test(f.name);
const EMOJI_PICKS = ["🔊", "😂", "💀", "🔥", "😱", "🤡", "👀", "💩", "📢", "🎺", "🥁", "💥", "⚡", "🧊", "👑", "🐐"];
// The trim view shows at most this much audio; longer sources also get an overview strip
const TRIM_VIEW_SECONDS = 15;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const fmtTime = (t) => `${Math.floor(t / 60)}:${(t % 60).toFixed(2).padStart(5, "0")}`;

async function refreshClips() {
  // Clips are files in media/, so the rule sound pickers need the new list too
  const [board, media] = await Promise.all([api("/api/soundboard"), api("/api/media")]);
  S.clips = board.clips;
  S.media = media;
}

const ruleUses = (file) => S.config.rules.filter((r) => soundClips(r).some((c) => c.file === file)).length;

// The server already rewrote rules.json for a renamed (to) or deleted (to = null) clip.
// Mirror that in the editor's copy and its saved snapshot so unsaved edits stay intact.
function applyClipFileChange(from, to) {
  const fix = (cfg) => {
    for (const r of cfg.rules) {
      r.actions = r.actions.filter((a) => {
        if (a.type !== "play_sound" || !a.clips.some((c) => c.file === from)) return true;
        if (to) { for (const c of a.clips) if (c.file === from) c.file = to; return true; }
        const kept = a.clips.filter((c) => c.file !== from);
        if (!kept.length) return false;
        // Same as the server: the first remaining sound takes the deleted one's odds
        kept[0].probability += a.clips.filter((c) => c.file === from).reduce((sum, c) => sum + c.probability, 0);
        a.clips = kept;
        return true;
      });
    }
  };
  fix(S.config);
  const saved = JSON.parse(S.saved);
  fix(saved);
  S.saved = JSON.stringify(saved);
  renderStatus();
}

async function playClip(clip, tile) {
  try {
    await api(`/api/soundboard/${clip.id}/play`, { method: "POST" });
  } catch (e) {
    toast(`Couldn't play ${clip.name}: ${e.message}`, "err");
    return;
  }
  tile.classList.remove("playing");
  void tile.offsetWidth; // restart the progress animation
  tile.style.setProperty("--dur", `${clip.duration}s`);
  tile.classList.add("playing");
  clearTimeout(tile._done);
  tile._done = setTimeout(() => tile.classList.remove("playing"), clip.duration * 1000);
}

function renderSoundboard() {
  const q = S.clipQuery.trim().toLowerCase();
  const clips = S.clips.filter((c) => !q || c.name.toLowerCase().includes(q));
  const search = h("input", { type: "search", placeholder: "Search sounds…", value: S.clipQuery, "aria-label": "Search sounds" });
  search.addEventListener("input", (e) => { S.clipQuery = e.target.value; rerenderKeepFocus(search); });

  const tile = (c) => {
    const el = h("div", {
      class: "sb-tile", role: "button", tabindex: "0",
      title: `Play ${c.name} on this PC\n${fileName(c.file)}${ruleUses(c.file) ? ` · used by ${ruleUses(c.file)} rule(s)` : ""}`,
      onclick: () => playClip(c, el),
      onkeydown: (e) => { if (e.target === el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); playClip(c, el); } },
    },
    h("span", { class: "sb-emoji" }, c.emoji || "🔊"),
    h("span", { class: "sb-name" }, c.name),
    h("span", { class: "sb-tools" },
      playButton(c.file, () => c.volume),
      h("button", { class: "sb-tool", title: "Edit", "aria-label": `Edit ${c.name}`, onclick: (e) => { e.stopPropagation(); openClipEditor({ clip: c }); } }, "✎")));
    return el;
  };

  const grid = h("div", { class: "sb-grid" },
    clips.map(tile),
    q ? null : h("button", { class: "sb-tile sb-add", onclick: () => openClipEditor() }, h("span", { class: "sb-emoji" }, "+"), h("span", { class: "sb-name" }, "Add sound")));
  makeDropTarget(grid, ([file]) => openClipEditor({ file }), isClipSource);

  return [
    h("div", { class: "board-head" }, h("h1", {}, "Soundboard"), search,
      h("button", { class: "btn btn-sm", title: "Stop every sound playing on this PC", onclick: () => api("/api/soundboard/stop", { method: "POST" }) }, "■ Stop all"),
      h("button", { class: "btn btn-gold btn-sm", onclick: () => openClipEditor() }, icon("plus"), "Add sound")),
    h("p", { class: "hint" }, `Click a sound to play it on this PC's speakers. ▶ previews it in the browser only. Clips can be up to ${S.maxClip} seconds, cut from an audio file, a video, or a YouTube link. Each clip is saved as an MP3 named after it, so you can also pick it as the sound for items, abilities and game events.`),
    grid,
    !S.clips.length ? h("p", { class: "hint sb-empty" }, "No sounds yet. Drop an audio or video file on the board, or click Add sound.") : null,
    ...(q ? [] : renderFriendClips()),
    q && !clips.length ? h("p", { class: "hint" }, `No sounds match “${S.clipQuery}”.`) : null,
  ];
}

function drawWave(canvas, buffer, t0, t1) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, ht = canvas.clientHeight;
  canvas.width = w * dpr;
  canvas.height = ht * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  g.fillStyle = getComputedStyle(canvas).color;
  const chans = Array.from({ length: Math.min(2, buffer.numberOfChannels) }, (_, c) => buffer.getChannelData(c));
  const sr = buffer.sampleRate, s0 = Math.floor(t0 * sr), s1 = Math.floor(t1 * sr);
  const per = (s1 - s0) / w, mid = ht / 2;
  for (let x = 0; x < w; x++) {
    const a = s0 + Math.floor(x * per), b = Math.min(s1, s0 + Math.floor((x + 1) * per));
    let peak = 0;
    for (const d of chans) for (let i = a; i < b; i++) { const v = Math.abs(d[i]); if (v > peak) peak = v; }
    const bar = Math.max(1, peak * mid * 0.95);
    g.fillRect(x, mid - bar, 1, bar * 2);
  }
}

// 16-bit PCM WAV of [start, end), with a 5 ms fade at each edge so cuts don't click
function encodeWav(buffer, start, end) {
  const sr = buffer.sampleRate, ch = Math.min(2, buffer.numberOfChannels);
  const s0 = Math.floor(start * sr), n = Math.max(1, Math.floor(end * sr) - s0);
  const fade = Math.min(Math.floor(sr * 0.005), Math.floor(n / 2));
  const bytes = n * ch * 2;
  const out = new DataView(new ArrayBuffer(44 + bytes));
  const str = (o, txt) => { for (let i = 0; i < txt.length; i++) out.setUint8(o + i, txt.charCodeAt(i)); };
  str(0, "RIFF"); out.setUint32(4, 36 + bytes, true); str(8, "WAVE");
  str(12, "fmt "); out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, ch, true);
  out.setUint32(24, sr, true); out.setUint32(28, sr * ch * 2, true); out.setUint16(32, ch * 2, true); out.setUint16(34, 16, true);
  str(36, "data"); out.setUint32(40, bytes, true);
  const chans = Array.from({ length: ch }, (_, c) => buffer.getChannelData(c));
  for (let i = 0, o = 44; i < n; i++) {
    const gain = i < fade ? i / fade : i >= n - fade ? (n - i) / fade : 1;
    for (const d of chans) {
      const v = clamp((d[s0 + i] || 0) * gain, -1, 1);
      out.setInt16(o, v < 0 ? v * 0x8000 : v * 0x7fff, true);
      o += 2;
    }
  }
  return new Blob([out], { type: "audio/wav" });
}

function openClipEditor({ clip, file } = {}) {
  let ctx = null, buffer = null, preview = null, playheadEl = null;
  let sel = { start: 0, end: 0 }, view = { start: 0, end: 0 };
  const redraws = [];

  const name = h("input", { type: "text", maxlength: 32, placeholder: "Name your sound", value: clip?.name || "", "aria-label": "Sound name" });
  const emoji = h("input", { type: "text", class: "sb-emoji-input", maxlength: 16, placeholder: "🔊", value: clip?.emoji || "", "aria-label": "Emoji" });
  const vol = h("input", { type: "range", min: 0, max: 100, value: clip?.volume ?? 100, "aria-label": "Volume" });
  const volOut = h("output", {}, `${vol.value}%`);
  vol.addEventListener("input", () => {
    volOut.value = `${vol.value}%`;
    if (preview) preview.gain.gain.value = vol.value / 100;
  });
  const picks = h("div", { class: "sb-picks" }, EMOJI_PICKS.map((e) => h("button", { type: "button", onclick: () => { emoji.value = e; } }, e)));

  const source = h("div", { class: "sb-source" });
  const submit = h("button", { class: "btn btn-gold", disabled: !clip, onclick: onSubmit }, clip ? "Save" : "Add to soundboard");
  const playBtn = h("button", { class: "play", title: "Preview (Space)", "aria-label": "Preview selection", onclick: () => (preview ? stopPreview() : startPreview()) }, "▶");

  const onKey = (e) => {
    if (e.key === "Escape") close();
    if (e.key === " " && buffer && !["INPUT", "BUTTON"].includes(e.target.tagName)) { e.preventDefault(); playBtn.click(); }
  };
  const onResize = () => redraws.forEach((f) => f());
  const close = () => {
    stopPreview();
    if (recorder) { recorder.onstop = null; recorder.stream.getTracks().forEach((t) => t.stop()); recorder.stop(); recorder = null; }
    ctx?.close();
    backdrop.remove();
    document.removeEventListener("keydown", onKey);
    window.removeEventListener("resize", onResize);
  };

  const backdrop = h("div", { class: "modal-backdrop", onmousedown: (e) => { if (e.target === backdrop) close(); } },
    h("div", { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": clip ? "Edit sound" : "Add a sound" },
      h("div", { class: "modal-head" }, h("h2", {}, clip ? "Edit sound" : "Add a sound"), h("button", { class: "btn btn-ghost btn-sm", "aria-label": "Close", onclick: () => close() }, "✕")),
      source,
      h("div", { class: "sb-fields" },
        h("label", { class: "field" }, h("span", { class: "lbl" }, "Name"), name),
        h("div", { class: "field" }, h("span", { class: "lbl" }, "Emoji"), emoji, picks),
        h("label", { class: "field" }, h("span", { class: "lbl" }, "Volume"), vol, volOut)),
      h("div", { class: "modal-foot" },
        clip ? h("button", { class: "btn btn-ghost btn-danger", onclick: onDelete }, "Delete") : null,
        h("span", { style: { flex: 1 } }),
        h("button", { class: "btn btn-ghost", onclick: () => close() }, "Cancel"),
        submit)));
  document.body.append(backdrop);
  document.addEventListener("keydown", onKey);
  window.addEventListener("resize", onResize);

  if (clip) loadClip();
  else if (file) loadFile(file);
  else showPicker();

  function showPicker() {
    buffer = null;
    submit.disabled = true;
    const input = h("input", { type: "file", accept: CLIP_ACCEPT, id: "sb-file" });
    input.addEventListener("change", () => input.files[0] && loadFile(input.files[0]));
    const zone = h("div", { class: "dropzone" }, "Drop an audio or video file here, or ", h("label", { for: "sb-file" }, "browse"), input);
    makeDropTarget(zone, ([f]) => loadFile(f), isClipSource);
    const link = h("input", { type: "url", placeholder: "https://www.youtube.com/watch?v=…", "aria-label": "Video link" });
    const fetchBtn = h("button", { class: "btn", onclick: () => fetchLink(link.value, fetchBtn) }, "Get audio");
    link.addEventListener("keydown", (e) => { if (e.key === "Enter") fetchBtn.click(); });
    const recBtn = h("button", { class: "btn", onclick: () => recordMic(recBtn) }, "🎙 Record with microphone");
    source.replaceChildren(zone, h("div", { class: "sb-or" }, "or paste a link"), h("div", { class: "sb-link" }, link, fetchBtn),
      h("p", { class: "hint" }, "YouTube, Twitch clips, TikTok, X and most other video sites work."),
      h("div", { class: "sb-or" }, "or record yourself"), h("div", { class: "sb-link" }, recBtn));
    setTimeout(() => link.focus());
  }

  let recorder = null;
  async function recordMic(btn) {
    if (recorder) { recorder.stop(); return; }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      toast(`Couldn't use the microphone: ${e.message || e.name}`, "err", 6000);
      return;
    }
    const chunks = [];
    const rec = new MediaRecorder(stream);
    recorder = rec;
    const t0 = Date.now();
    const tick = setInterval(() => { btn.textContent = `⏹ Stop (${((Date.now() - t0) / 1000).toFixed(1)} s)`; }, 100);
    btn.textContent = "⏹ Stop (0.0 s)";
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      clearInterval(tick);
      stream.getTracks().forEach((t) => t.stop());
      recorder = null;
      if (!chunks.length) { btn.textContent = "🎙 Record with microphone"; return; }
      await loadFile(new File([new Blob(chunks, { type: rec.mimeType })], "Recording"));
    };
    rec.start();
  }

  async function fetchLink(url, btn) {
    if (!url.trim()) return;
    btn.disabled = true;
    btn.textContent = "Downloading…";
    try {
      const res = await fetch("/api/soundboard/fetch", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url.trim() }) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).error || res.statusText);
      const title = decodeURIComponent(res.headers.get("X-Title") || "clip");
      await loadFile(new File([await res.arrayBuffer()], title));
    } catch (e) {
      toast(`Couldn't get audio from that link: ${e.message}`, "err", 8000);
      btn.disabled = false;
      btn.textContent = "Get audio";
    }
  }

  async function decode(data) {
    // 44.1 kHz whatever the device's rate, so the server's MP3 encoder always accepts it
    ctx ??= new AudioContext({ sampleRate: 44100 });
    return ctx.decodeAudioData(data);
  }

  async function loadFile(f) {
    source.replaceChildren(h("p", { class: "hint sb-loading" }, `Reading ${f.name}…`));
    try {
      buffer = await decode(await f.arrayBuffer());
    } catch {
      toast(`Couldn't read the audio in ${f.name}. Try an .mp3, .wav, .ogg or .mp4 file.`, "err", 6000);
      showPicker();
      return;
    }
    if (!name.value) name.value = f.name.replace(/\.[^.]+$/, "").replace(/[_]+/g, " ").trim().slice(0, 32);
    sel = { start: 0, end: Math.min(buffer.duration, S.maxClip) };
    view = { start: 0, end: Math.min(buffer.duration, TRIM_VIEW_SECONDS) };
    submit.disabled = false;
    showTrimmer(f.name);
  }

  async function loadClip() {
    source.replaceChildren(h("p", { class: "hint sb-loading" }, "Loading…"));
    try {
      buffer = await decode(await (await fetch(mediaUrl(clip.file))).arrayBuffer());
    } catch {
      source.replaceChildren(h("p", { class: "missing-note" }, "The audio file for this sound is missing."));
      return;
    }
    sel = { start: 0, end: buffer.duration };
    view = { ...sel };
    const canvas = h("canvas", { class: "sb-wave" });
    const playhead = h("div", { class: "sb-playhead" });
    source.replaceChildren(h("div", { class: "sb-detail sb-static" }, canvas, playhead),
      h("div", { class: "sb-times" }, playBtn, h("span", {}, `${buffer.duration.toFixed(2)} s`)));
    playheadEl = playhead;
    redraws.push(() => drawWave(canvas, buffer, 0, buffer.duration));
    requestAnimationFrame(onResize);
  }

  function showTrimmer(label) {
    const D = buffer.duration, M = S.maxClip, MIN = 0.1;
    const long = D > TRIM_VIEW_SECONDS;
    const pct = (t) => `${((t - view.start) / (view.end - view.start)) * 100}%`;

    const canvas = h("canvas", { class: "sb-wave" });
    const selEl = h("div", { class: "sb-sel" }, h("span", { class: "sb-handle l", "aria-label": "Trim start" }), h("span", { class: "sb-handle r", "aria-label": "Trim end" }));
    const playhead = h("div", { class: "sb-playhead" });
    playheadEl = playhead;
    const detail = h("div", { class: "sb-detail" }, canvas, selEl, playhead);

    const ovCanvas = h("canvas", { class: "sb-wave" });
    const ovView = h("div", { class: "sb-ov-view" });
    const ovSel = h("div", { class: "sb-ov-sel" });
    const overview = long ? h("div", { class: "sb-overview", title: "Click to jump to that part" }, ovCanvas, ovView, ovSel) : null;

    const times = h("span", { class: "sb-time-text" });
    const update = () => {
      selEl.style.left = pct(sel.start);
      selEl.style.width = `${((sel.end - sel.start) / (view.end - view.start)) * 100}%`;
      if (long) {
        Object.assign(ovView.style, { left: `${(view.start / D) * 100}%`, width: `${((view.end - view.start) / D) * 100}%` });
        Object.assign(ovSel.style, { left: `${(sel.start / D) * 100}%`, width: `${Math.max(0.3, ((sel.end - sel.start) / D) * 100)}%` });
      }
      const len = sel.end - sel.start;
      times.replaceChildren(fmtTime(sel.start), " → ", fmtTime(sel.end), h("strong", { class: len >= M - 0.01 ? "at-max" : "" }, ` ${len.toFixed(2)} s`), ` / ${M} s max`);
    };
    const drawDetail = () => drawWave(canvas, buffer, view.start, view.end);
    // Keep the selection comfortably inside the visible window
    const follow = (force) => {
      const V = view.end - view.start, pad = V * 0.08;
      if (!force && sel.start >= view.start + pad && sel.end <= view.end - pad) return;
      const s = clamp((sel.start + sel.end) / 2 - V / 2, 0, D - V);
      if (s === view.start) return;
      view = { start: s, end: s + V };
      drawDetail();
    };

    const timeAt = (e, el, t0, t1) => {
      const r = el.getBoundingClientRect();
      return t0 + clamp((e.clientX - r.left) / r.width, 0, 1) * (t1 - t0);
    };
    detail.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      stopPreview();
      let mode = e.target.classList.contains("l") ? "l" : e.target.classList.contains("r") ? "r" : "move";
      const t = timeAt(e, detail, view.start, view.end);
      if (mode === "move" && e.target !== selEl) {
        // Clicked outside the selection: move it to start there
        const len = sel.end - sel.start;
        sel.start = clamp(t, 0, D - len);
        sel.end = sel.start + len;
        update();
      }
      const base = { ...sel }, t0 = timeAt(e, detail, view.start, view.end);
      detail.setPointerCapture(e.pointerId);
      detail.classList.add("dragging");
      const move = (ev) => {
        const dt = timeAt(ev, detail, view.start, view.end) - t0;
        if (mode === "move") {
          const len = base.end - base.start;
          sel.start = clamp(base.start + dt, 0, D - len);
          sel.end = sel.start + len;
        } else if (mode === "l") {
          sel.start = clamp(base.start + dt, Math.max(0, base.end - M), base.end - MIN);
        } else {
          sel.end = clamp(base.end + dt, base.start + MIN, Math.min(D, base.start + M));
        }
        update();
      };
      const up = () => {
        detail.removeEventListener("pointermove", move);
        detail.removeEventListener("pointerup", up);
        detail.removeEventListener("pointercancel", up);
        detail.classList.remove("dragging");
        follow(false);
        update();
        startPreview();
      };
      detail.addEventListener("pointermove", move);
      detail.addEventListener("pointerup", up);
      detail.addEventListener("pointercancel", up);
    });

    overview?.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      stopPreview();
      const jump = (ev) => {
        const len = sel.end - sel.start;
        sel.start = clamp(timeAt(ev, overview, 0, D) - len / 2, 0, D - len);
        sel.end = sel.start + len;
        follow(true);
        update();
      };
      jump(e);
      overview.setPointerCapture(e.pointerId);
      overview.addEventListener("pointermove", jump);
      overview.addEventListener("pointerup", () => { overview.removeEventListener("pointermove", jump); startPreview(); }, { once: true });
    });

    const nudge = (which, d) => () => {
      stopPreview();
      if (which === "start") sel.start = clamp(sel.start + d, Math.max(0, sel.end - M), sel.end - MIN);
      else sel.end = clamp(sel.end + d, sel.start + MIN, Math.min(D, sel.start + M));
      follow(false);
      update();
    };
    const nudgeBtns = (which) => h("span", { class: "sb-nudge" },
      h("button", { class: "btn btn-sm btn-ghost", title: `${which} −0.05 s`, onclick: nudge(which, -0.05) }, "‹"),
      h("button", { class: "btn btn-sm btn-ghost", title: `${which} +0.05 s`, onclick: nudge(which, 0.05) }, "›"));

    source.replaceChildren(
      h("div", { class: "sb-src-row" }, h("span", { class: "sb-src-name", title: label }, "♪ ", label, ` · ${fmtTime(D)}`),
        h("button", { class: "btn btn-sm btn-ghost", onclick: () => { stopPreview(); showPicker(); } }, "Change")),
      overview,
      detail,
      h("div", { class: "sb-times" }, playBtn, nudgeBtns("start"), times, nudgeBtns("end")),
      h("p", { class: "hint" }, "Drag the gold edges to trim, or drag the middle to slide the clip.", long ? " Click the strip above to jump to another part." : ""));

    redraws.length = 0;
    redraws.push(drawDetail, () => long && drawWave(ovCanvas, buffer, 0, D));
    update();
    requestAnimationFrame(onResize);
  }

  function startPreview() {
    if (!buffer) return;
    stopPreview();
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    const gain = ctx.createGain();
    gain.gain.value = vol.value / 100;
    src.connect(gain).connect(ctx.destination);
    src.start(0, sel.start, sel.end - sel.start);
    preview = { src, gain, at: ctx.currentTime, from: sel.start };
    src.onended = () => { if (preview?.src === src) stopPreview(); };
    playBtn.textContent = "■";
    playBtn.classList.add("playing");
    const tick = () => {
      if (preview?.src !== src || !playheadEl) return;
      const t = preview.from + (ctx.currentTime - preview.at);
      playheadEl.style.left = `${((t - view.start) / (view.end - view.start)) * 100}%`;
      playheadEl.style.display = "block";
      requestAnimationFrame(tick);
    };
    tick();
  }

  function stopPreview() {
    if (!preview) return;
    const { src } = preview;
    preview = null;
    try { src.stop(); } catch { /* already ended */ }
    playBtn.textContent = "▶";
    playBtn.classList.remove("playing");
    if (playheadEl) playheadEl.style.display = "none";
  }

  async function onSubmit() {
    const meta = { name: name.value.trim(), emoji: emoji.value.trim(), volume: +vol.value };
    if (!meta.name) { name.focus(); toast("Give your sound a name.", "err"); return; }
    submit.disabled = true;
    try {
      if (clip) {
        const res = await api(`/api/soundboard/${clip.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(meta) });
        if (res.renamed) applyClipFileChange(res.renamed.from, res.renamed.to);
      } else {
        const form = new FormData();
        form.append("meta", JSON.stringify(meta));
        form.append("file", encodeWav(buffer, sel.start, sel.end), "clip.wav");
        await api("/api/soundboard", { method: "POST", body: form });
      }
      await refreshClips();
      close();
      toast(clip ? `Saved ${meta.name}` : `Added ${meta.name} to the soundboard`, "ok");
      render();
    } catch (e) {
      submit.disabled = false;
      const errors = e.body?.errors?.map((er) => `${er.loc.join(" ")}: ${er.msg}`) || [e.message];
      toast(`Couldn't save: ${errors.join("; ")}`, "err", 7000);
    }
  }

  async function onDelete() {
    const uses = ruleUses(clip.file);
    const note = uses ? `\n\nIt's the sound for ${uses} rule(s). It will be removed from those rules.` : "";
    if (!confirm(`Delete “${clip.name}” from the soundboard? The file ${fileName(clip.file)} stays in your Sounds library.${note}`)) return;
    try {
      await api(`/api/soundboard/${clip.id}`, { method: "DELETE" });
      applyClipFileChange(clip.file, null);
      await refreshClips();
      close();
      toast(`Deleted ${clip.name}`, "ok");
      render();
    } catch (e) {
      toast(`Couldn't delete: ${e.message}`, "err");
    }
  }
}

// ---- Friends (shared folder) ----

async function loadSharing() {
  try {
    S.sharing = await api("/api/sharing");
  } catch (e) {
    S.sharing = { enabled: false, people: [], error: e.message };
  }
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function ago(iso) {
  if (!iso) return "never";
  const s = (Date.now() - new Date(iso)) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

const soundClips = (r) => r.actions.filter((a) => a.type === "play_sound").flatMap((a) => a.clips);
const soundFiles = (r) => soundClips(r).map((c) => c.file).sort().join("|");
// A sound the shared folder doesn't have: the rule can't be copied
const brokenRule = (r) => soundClips(r).some((c) => !hasMedia(c.file));
const hasSound = (r) => r.actions.some((a) => a.type === "play_sound" && a.enabled !== false);
const haveRule = (rule) => S.config.rules.some((r) => sameMonitor(r.monitor, rule.monitor) && soundFiles(r) === soundFiles(rule));
// One of your rules already plays a different sound on this trigger
const clashingRules = (rule) => S.config.rules.filter((r) => sameMonitor(r.monitor, rule.monitor) && hasSound(r) && soundFiles(r) !== soundFiles(rule));

function copyFriendRules(friend, rules, { replace = false } = {}) {
  // All or nothing: a rule whose sound isn't in your library could never play
  const missing = [...new Set(rules.flatMap((r) => soundClips(r).filter((c) => !hasMedia(c.file)).map((c) => fileName(c.file))))];
  if (missing.length) {
    toast(`Nothing copied: ${friend.name}'s sound${missing.length === 1 ? "" : "s"} ${missing.join(", ")} ${missing.length === 1 ? "isn't" : "aren't"} in the shared folder. Ask them to re-upload ${missing.length === 1 ? "it" : "them"}.`, "err");
    return;
  }
  for (const rule of rules) {
    const copy = structuredClone(rule);
    if (replace) {
      // Swap only the sounds; your lights and webhooks on that trigger stay
      const mine = clashingRules(rule);
      for (const r of mine) r.actions = r.actions.filter((a) => a.type !== "play_sound");
      mine[0].actions.unshift(...copy.actions.filter((a) => a.type === "play_sound"));
      continue;
    }
    // Prefixed with the friend's name (as when their rules play via "follow"), so it never clashes with a rule of yours
    const base = `${friend.name}/${rule.id}`;
    let id = base;
    for (let n = 2; S.config.rules.some((r) => r.id === id); n++) id = `${base}_${n}`;
    copy.id = id;
    // Light priorities must stay unique across your own rules
    let prio = nextPriority();
    for (const a of copy.actions) if (a.type === "light" && a.priority != null) a.priority = prio++;
    S.config.rules.push(copy);
  }
  markDirty();
  render();
  const what = rules.length === 1 ? describeTrigger(rules[0].monitor).title : `${rules.length} rules`;
  toast(`${replace ? "Replaced your sound for" : "Copied"} ${what} from ${friend.name}. Press Save to keep ${rules.length === 1 ? "it" : "them"}.`, "ok");
}

async function setFollow(friend, follow) {
  try {
    S.sharing = await api("/api/sharing/follow", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: friend.key, follow }) });
    toast(follow ? `${friend.name}'s sounds now play on this PC too.` : `Stopped playing ${friend.name}'s sounds.`, "ok");
  } catch (e) {
    toast(`Couldn't update: ${e.message}`, "err");
  }
  render();
}

function renderFriends() {
  const packInput = h("input", { type: "file", accept: ".zip,application/zip", id: "pack-input", hidden: true });
  packInput.addEventListener("change", () => packInput.files[0] && importPackFile(packInput.files[0]));
  const head = h("div", { class: "board-head" }, h("h1", {}, "Friends & packs"),
    h("a", { class: "btn btn-sm", href: "/api/pack/export", download: "", title: "Download your rules, soundboard clips and their sounds as one .zip" }, "⇩ Export my pack"),
    h("label", { class: "btn btn-sm", for: "pack-input", title: "Add a friend's .zip pack" }, icon("upload"), "Import pack"), packInput,
    S.sharing?.enabled ? h("button", { class: "btn btn-sm", title: "Check the shared folder for changes", onclick: async () => { await Promise.all([loadSharing(), refreshClips()]); render(); } }, "↻ Refresh") : null);
  if (!S.sharing) return [head, h("p", { class: "hint" }, "Loading…")];
  if (S.shareSetup) return [head, renderShareSetup()];

  const sh = S.sharing;
  const out = [head];

  // One box for every kind of invite: a library or pack link, or a shared folder link
  const link = h("input", { type: "url", placeholder: "Paste the invite link a friend sent you", "aria-label": "Invite link", value: S.join?.link || "" });
  const addBtn = h("button", { class: "btn btn-gold", onclick: () => useInviteLink(link.value, addBtn) }, "Join");
  link.addEventListener("keydown", (e) => { if (e.key === "Enter") addBtn.click(); });
  const packBar = h("div", { class: "pack-bar" }, link, addBtn);
  makeDropTarget(packBar, ([f]) => importPackFile(f), (f) => /\.zip$/i.test(f.name));
  out.push(h("div", { class: "section-title" }, "Libraries & packs", h("span", { class: "count" }, sh.packs.length)));
  out.push(packBar);
  if (S.join) out.push(renderJoin());
  else out.push(h("p", { class: "hint" }, "Got a link from a friend? Paste it here. A library link needs nothing else installed and stays up to date by itself. You can also drop a pack .zip on this box."));
  for (const p of sh.packs) out.push(renderFriend(p));

  // Shared folder: automatic two-way sync for people running Google Drive for desktop
  out.push(h("div", { class: "section-title" }, "Shared folder", sh.enabled ? h("span", { class: "count" }, sh.people.length) : null));
  if (!sh.enabled) {
    out.push(h("div", { class: "share-card" },
      h("div", { class: "share-who" },
        h("div", {}, h("strong", {}, "Sync automatically"), " with friends who use Google Drive for desktop (or Dropbox, OneDrive, iCloud)."),
        h("div", { class: "hint" }, "Everyone's rules and sounds stay up to date both ways, with no exporting.")),
      h("button", { class: "btn btn-sm", onclick: () => { S.shareSetup = { name: sh.name, browse: null }; render(); } }, "Set up")));
    return out;
  }
  out.push(h("div", { class: "share-card" },
    h("div", { class: "share-who" },
      h("div", {}, "Sharing as ", h("strong", {}, sh.name)),
      h("div", { class: "hint", title: sh.folder }, "Folder: ", h("code", {}, sh.folder))),
    h("button", { class: "btn btn-sm btn-gold", onclick: openInvite }, icon("invite"), "Invite friends"),
    h("button", { class: "btn btn-sm", onclick: () => { S.shareSetup = { name: sh.name, browse: null }; render(); } }, "Change"),
    h("button", { class: "btn btn-sm btn-ghost btn-danger", onclick: turnOffSharing }, "Stop sharing")));
  if (S.invite) out.push(renderInvite());
  if (!sh.available) {
    out.push(h("p", { class: "insp-warn" }, "The shared folder isn't reachable right now (is Google Drive running?). Sounds play from this PC's own copies until it's back."));
  }
  if (!sh.people.length) {
    out.push(h("p", { class: "hint share-empty" }, "No friends here yet. Share this folder with them. Once they turn on sharing and pick the same folder, their rules and clips show up here."));
  }
  for (const f of sh.people) out.push(renderFriend(f));
  return out;
}

async function importPackFile(file) {
  const form = new FormData();
  form.append("file", file);
  await finishPackImport(api("/api/packs", { method: "POST", body: form }));
}

const isFolderLink = (url) => /\/folders\//.test(url);

async function useInviteLink(url, btn) {
  url = url.trim();
  if (!url) return;
  if (!isFolderLink(url)) {
    S.join = null;
    return importPackLink(url, btn);
  }
  S.join = { link: url, name: S.join?.name ?? S.sharing.name, status: "checking" };
  render();
  await tryJoin();
}

// Joining a shared folder waits on things done outside the app (installing Drive, adding
// the folder to it), so keep checking until they're done.
async function tryJoin() {
  const j = S.join;
  if (!j) return;
  clearTimeout(j.timer);
  try {
    const res = await api("/api/sharing/join", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ link: j.link, name: j.name }) });
    if (S.join !== j) return;
    Object.assign(j, { status: res.status, openUrl: res.open_url, downloadUrl: res.download_url, error: null });
    if (res.status === "joined") {
      S.sharing = res;
      S.join = null;
      await refreshClips();
      toast(`You're in! Everyone's rules and clips are below.${res.copied ? ` Copied ${res.copied} of your sounds in.` : ""}`, "ok", 6000);
    } else if (S.tab === "friends") {
      j.timer = setTimeout(tryJoin, 4000);
    }
  } catch (e) {
    if (S.join !== j) return;
    Object.assign(j, { status: "error", error: e.message });
  }
  if (S.tab === "friends" && !document.activeElement?.closest?.(".join-card")) render();
}

function renderJoin() {
  const j = S.join;
  const name = h("input", { type: "text", maxlength: 24, value: j.name, "aria-label": "Your name", oninput: (e) => { j.name = e.target.value; } });
  const step = (n, done, active, ...body) => h("li", { class: `${done ? "done" : ""} ${active ? "active" : ""}` }, h("span", { class: "step-n" }, done ? "✓" : n), h("div", {}, ...body));
  const noDrive = j.status === "no_drive";
  const notAdded = j.status === "not_added";
  return h("div", { class: "share-card join-card" },
    h("div", { class: "share-who" },
      h("div", {}, h("strong", {}, "This is a shared folder link"), " for people who add sounds (admins). Just want to play the sounds? Ask for the ", h("em", {}, "library link"), " instead; it needs nothing installed."),
      j.status === "error" ? h("p", { class: "insp-warn" }, j.error) : null,
      h("ol", { class: "join-steps" },
        step(1, !noDrive && j.status !== "checking", noDrive, h("strong", {}, "Install Google Drive for desktop"), " and sign in with the Google account the folder was shared with. ",
          noDrive ? h("a", { class: "btn btn-sm", href: j.downloadUrl, target: "_blank", rel: "noopener" }, "Download Drive") : null),
        step(2, false, notAdded, h("strong", {}, "Add the folder to your Drive: "), "open it, click the folder name at the top → ", h("strong", {}, "Organize → Add shortcut → My Drive"), ". ",
          notAdded ? h("a", { class: "btn btn-sm", href: j.openUrl, target: "_blank", rel: "noopener" }, "Open the folder") : null),
        step(3, false, false, "Your name for friends: ", name)),
      h("div", { class: "hint" }, j.status === "checking" ? "Checking…" : "Waiting… this joins by itself as soon as the folder shows up on this computer.")),
    h("button", { class: "btn btn-sm btn-ghost", onclick: () => { clearTimeout(j.timer); S.join = null; render(); } }, "Cancel"));
}

async function openInvite() {
  S.invite = { loading: true };
  render();
  try {
    S.invite = await api("/api/sharing/invite");
  } catch (e) {
    S.invite = { error: e.message };
  }
  render();
}

function copyText(text, what) {
  navigator.clipboard.writeText(text).then(() => toast(`Copied ${what}.`, "ok"), () => toast("Couldn't copy; select the text and copy it yourself.", "err"));
}

function renderInvite() {
  const inv = S.invite;
  const close = h("button", { class: "btn btn-sm btn-ghost", onclick: () => { S.invite = null; render(); } }, "Close");
  if (inv.loading) return h("div", { class: "share-card invite" }, h("div", { class: "share-who" }, "Preparing invite links…"), close);
  if (inv.error) return h("div", { class: "share-card invite" }, h("p", { class: "insp-warn" }, inv.error), close);
  const linkRow = (url, what) => h("div", { class: "invite-link" }, h("code", {}, url), h("button", { class: "btn btn-sm", onclick: () => copyText(url, what) }, "Copy"));
  const message = (url) => `Join our Dota sounds in Soundbo: open the app → Friends & packs → paste this link → Join.\n${url}`;
  const reader = inv.library_link
    ? [linkRow(inv.library_link, "the library link"),
      inv.library_public
        ? h("p", { class: "hint ok-note" }, "✓ Anyone with this link can join. Their copy updates by itself when you add sounds.")
        : h("p", { class: "insp-warn" }, "Only you can open it so far. Do this once: ",
          h("a", { href: inv.library_link, target: "_blank", rel: "noopener" }, "open it in Drive"), " → ", h("strong", {}, "Share → General access → Anyone with the link (Viewer)"), ". ",
          h("button", { class: "linkish", onclick: openInvite }, "Check again")),
      h("button", { class: "btn btn-sm", onclick: () => copyText(message(inv.library_link), "the invite message") }, "Copy invite message")]
    : [h("p", { class: "hint" }, "Google Drive is still uploading the library. ", h("button", { class: "linkish", onclick: openInvite }, "Check again"), " in a minute.")];
  return h("div", { class: "share-card invite" },
    h("div", { class: "share-who" },
      h("div", {}, h("strong", {}, "Friends who play the sounds"), h("span", { class: "hint" }, " · no install, read-only")),
      ...reader,
      h("div", { class: "invite-admin" }, h("strong", {}, "Admins who add sounds"), h("span", { class: "hint" }, " · need Google Drive for desktop")),
      inv.folder_link
        ? [h("p", { class: "hint" }, "Share the folder with them in Drive as ", h("strong", {}, "Editor"), ", then send them this link to paste into the app:"),
          linkRow(inv.folder_link, "the folder link"),
          h("a", { class: "btn btn-sm", href: inv.folder_link, target: "_blank", rel: "noopener" }, "Open the folder in Drive")]
        : h("p", { class: "hint" }, "Share the shared folder with them as Editor; they pick it under Set up.")),
    close);
}

async function importPackLink(url, btn) {
  if (!url.trim()) return;
  btn.disabled = true;
  btn.textContent = "Downloading…";
  await finishPackImport(api("/api/packs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url.trim() }) }));
  btn.disabled = false;
  btn.textContent = "Join";
}

async function finishPackImport(request) {
  try {
    const res = await request;
    S.sharing = res;
    await refreshClips();
    toast(res.pack.library
      ? `Joined ${res.pack.name}! Its sounds play in your games now and update by themselves.`
      : `Added ${res.pack.name}. Copy the rules you like, or turn on "Play their sounds too".`, "ok", 6000);
  } catch (e) {
    toast(e.message, "err", 8000);
  }
  render();
}

async function packAction(p, action) {
  try {
    if (action === "remove") {
      if (!confirm(`Remove the pack "${p.name}"?\n\nIts sounds stay, so rules you copied from it keep working.`)) return;
      S.sharing = await api(`/api/packs/${p.id}`, { method: "DELETE" });
    } else {
      const res = await api(`/api/packs/${p.id}/refresh`, { method: "POST" });
      S.sharing = res;
      await refreshClips();
      toast(res.changed ? `Updated ${p.name}.` : `${p.name} is already up to date.`, "ok");
    }
  } catch (e) {
    toast(e.message, "err", 7000);
  }
  render();
}

// Whether each friend's rule list is expanded, so copying a rule (which re-renders) doesn't collapse it
const rulesOpen = new Map();

function renderFriend(f) {
  const isPack = f.kind === "pack";
  const fresh = f.rules.filter((r) => !haveRule(r) && !clashingRules(r).length && !brokenRule(r));
  // What following would actually play: yours win on triggers you already have
  const playable = f.rules.filter((r) => hasSound(r) && !S.config.rules.some((m) => sameMonitor(m.monitor, r.monitor) && hasSound(m)));
  const withSound = f.rules.filter(hasSound).length;
  const row = (r) => {
    const d = describeTrigger(r.monitor);
    const clash = !haveRule(r) && clashingRules(r).length > 0;
    const broken = brokenRule(r);
    const why = broken ? "Its sound is missing from the shared folder" : null;
    return h("div", { class: "rule-row friend-rule" },
      h("span", { class: `thumb ${d.square ? "square" : ""}`, style: d.img ? { backgroundImage: `url("${d.img}")` } : null }, d.glyph || ""),
      h("span", { class: "trig" }, h("div", { class: "t" }, d.title),
        h("div", { class: "s" }, clash ? `You already have: ${clashingRules(r).flatMap((m) => soundClips(m).map((c) => fileName(c.file))).join(", ")}` : d.sub)),
      h("span", { class: "acts" }, r.actions.flatMap((a) => {
        const off = a.enabled === false ? "off" : "";
        if (a.type === "play_sound") return soundChips(a);
        return h("span", { class: `chip ${off}` }, h("span", { class: "swatch", style: { background: hex(a) } }), "light");
      })),
      haveRule(r) ? h("span", { class: "have" }, "✓ In yours")
        : clash ? h("span", { class: "copy-choice" },
          h("button", { class: "btn btn-sm", disabled: broken, title: why || "Use their sound instead of yours (your lights stay)", onclick: () => copyFriendRules(f, [r], { replace: true }) }, icon("swap"), "Replace mine"),
          h("button", { class: "btn btn-sm btn-ghost", disabled: broken, title: why || "Keep yours and add theirs; both play", onclick: () => copyFriendRules(f, [r]) }, icon("plus"), "Add both"))
        : h("button", { class: "btn btn-sm", disabled: broken, title: why, onclick: () => copyFriendRules(f, [r]) }, icon("copy"), "Copy"));
  };
  const follow = h("label", { class: "toggle", title: "Their sounds play on this PC for triggers you don't have a sound for (lights stay yours)" },
    h("input", { type: "checkbox", checked: f.following, onchange: (e) => setFollow(f, e.target.checked) }),
    h("span", { class: "toggle-track" }), h("span", {}, "Play their sounds too"));
  const source = isPack ? (f.source ? "from a link" : "from a file") : "";
  return h("section", { class: `friend ${isPack ? "pack" : ""}` },
    h("div", { class: "friend-head" },
      h("div", { class: "friend-avatar" }, isPack ? "📦" : f.name.slice(0, 1).toUpperCase()),
      h("div", { class: "friend-name" }, h("strong", {}, f.name),
        h("div", { class: "hint" }, [`${plural(f.rules.length, "rule")}`, `${plural(f.soundboard.length, "soundboard clip")}`, source, `updated ${ago(f.updated)}`].filter(Boolean).join(" · "))),
      follow,
      fresh.length ? h("button", { class: "btn btn-sm btn-gold", title: "Copy the rules for triggers you don't have yet", onclick: () => copyFriendRules(f, fresh) }, icon("copy"), `Copy new (${fresh.length})`) : null,
      isPack && f.source ? h("button", { class: "btn btn-sm btn-ghost", title: "Check the link for a newer version", onclick: () => packAction(f, "refresh") }, "↻") : null,
      isPack ? h("button", { class: "btn btn-sm btn-ghost btn-danger", title: "Remove this pack", onclick: () => packAction(f, "remove") }, "✕") : null),
    f.following && withSound
      ? h("p", { class: "hint follow-note" }, playable.length
        ? `${playable.length} of their ${withSound} sounds play in your games.${withSound > playable.length ? ` The other ${withSound - playable.length} are on triggers where your own sound plays.` : ""}`
        : "You already have your own sound for every trigger they use, so yours play.")
      : null,
    f.rules.length
      ? h("details", { class: "friend-rules", open: rulesOpen.get(f.key) ?? f.rules.length <= 6, ontoggle: (e) => rulesOpen.set(f.key, e.target.open) },
        h("summary", {}, isPack ? "Rules in this pack" : "Their rules"),
        h("div", { class: "rule-list" }, f.rules.map(row)))
      : h("p", { class: "hint" }, "No rules yet."));
}

async function turnOffSharing() {
  if (!confirm("Stop sharing?\n\nShared sounds are copied back to this PC so your rules keep working. Your friends will no longer see your rules.")) return;
  try {
    const res = await api("/api/sharing", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: null, name: S.sharing.name }) });
    S.sharing = res;
    await refreshClips();
    toast(`Sharing is off.${res.copied ? ` Copied ${res.copied} sounds back to this PC.` : ""}`, "ok");
  } catch (e) {
    toast(`Couldn't turn off sharing: ${e.message}`, "err");
  }
  render();
}

async function browseTo(path) {
  try {
    S.shareSetup.browse = await api(`/api/sharing/browse${path ? `?path=${encodeURIComponent(path)}` : ""}`);
  } catch (e) {
    toast(e.message, "err");
  }
  render();
}

function renderShareSetup() {
  const sh = S.sharing;
  S.shareSetup ??= { name: sh.name, browse: null };
  const st = S.shareSetup;
  if (!st.browse) {
    if (!st.loading) { st.loading = true; browseTo(null); }
    return h("p", { class: "hint" }, "Looking for Google Drive…");
  }
  const b = st.browse;

  const nameInput = h("input", { type: "text", maxlength: 24, value: st.name, "aria-label": "Your name", oninput: (e) => { st.name = e.target.value; } });
  const newFolder = h("input", { type: "text", value: st.newFolder ?? "Dota Sounds", "aria-label": "New folder name", oninput: (e) => { st.newFolder = e.target.value; } });

  const choose = async (folder, create = false) => {
    try {
      const res = await api("/api/sharing", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder, name: st.name, create }) });
      S.sharing = res;
      S.shareSetup = null;
      await refreshClips();
      toast(`Sharing is on.${res.copied ? ` Copied ${res.copied} of your sounds into the shared folder.` : ""}`, "ok", 6000);
    } catch (e) {
      toast(e.message, "err", 7000);
    }
    render();
  };

  const picker = b.path == null
    ? h("div", { class: "folder-list" }, b.suggestions.map((s) =>
      h("button", { class: "folder", onclick: () => browseTo(s.path) }, h("span", { class: "folder-ico" }, "☁"), h("span", {}, s.label), h("code", {}, s.path))))
    : h("div", {},
      h("div", { class: "folder-path" },
        h("button", { class: "btn btn-sm btn-ghost", onclick: () => browseTo(null) }, "☁ Places"),
        b.parent ? h("button", { class: "btn btn-sm btn-ghost", onclick: () => browseTo(b.parent) }, "↑ Up") : null,
        h("code", {}, b.path)),
      h("div", { class: "folder-list" },
        b.dirs.length ? b.dirs.map((d) => h("button", { class: `folder ${d.shared ? "shared" : ""}`, onclick: () => browseTo(d.path) },
          h("span", { class: "folder-ico" }, "▸"), h("span", {}, d.name), d.shared ? h("span", { class: "chip" }, "has friends' files") : null))
          : h("p", { class: "hint" }, "No folders inside.")),
      h("div", { class: "folder-actions" },
        h("button", { class: `btn ${b.shared ? "btn-gold" : ""}`, onclick: () => choose(b.path) }, b.shared ? "Join this shared folder" : "Use this folder"),
        h("span", { class: "hint" }, "or make a new one here:"), newFolder,
        h("button", { class: "btn", onclick: () => choose(`${b.path.replace(/[\\/]+$/, "")}${b.path.includes("\\") ? "\\" : "/"}${(st.newFolder ?? "Dota Sounds").trim()}`, true) }, "Create & use")));

  return h("div", { class: "share-setup" },
    h("p", {}, "Share sounds, soundboard clips and rules with friends through a folder you all sync, like Google Drive. Everyone keeps their own rules; you can copy theirs, or have their sounds play in your games too. Lights and webhooks stay private."),
    h("ol", { class: "share-steps" },
      h("li", {}, "Everyone installs ", h("strong", {}, "Google Drive for desktop"), "."),
      h("li", {}, "One person makes a folder (e.g. ", h("em", {}, "Dota Sounds"), ") and shares it with the others as ", h("strong", {}, "Editor"), "."),
      h("li", {}, "Friends open it under ", h("em", {}, "Shared with me"), " → right-click → ", h("strong", {}, "Organize → Add shortcut"), " → My Drive, so it syncs to their computer."),
      h("li", {}, "In Drive for desktop settings, choose ", h("strong", {}, "Mirror files"), ", or right-click the folder → ", h("strong", {}, "Available offline"), ", so sounds play instantly in-game."),
      h("li", {}, "Then everyone picks that folder below.")),
    h("label", { class: "field" }, h("span", { class: "lbl" }, "Your name"), nameInput),
    sh.enabled ? h("button", { class: "btn", title: "Keep the current shared folder and just change your name", onclick: () => choose(sh.folder) }, "Save name") : null,
    h("div", { class: "section-title" }, "Shared folder"),
    picker,
    h("button", { class: "btn btn-ghost", onclick: () => { S.shareSetup = null; render(); } }, "Cancel"));
}

function renderFriendClips() {
  const people = [...(S.sharing?.people || []), ...(S.sharing?.packs || [])].filter((f) => f.soundboard.length);
  return people.flatMap((f) => [
    h("div", { class: "section-title" }, `${f.name}'s sounds`, h("span", { class: "count" }, f.soundboard.length)),
    h("div", { class: "sb-grid friend-clips" }, f.soundboard.map((c) => {
      const el = h("div", {
        class: `sb-tile ${hasMedia(c.file) ? "" : "unsynced"}`, role: "button", tabindex: "0",
        title: hasMedia(c.file) ? `Play ${c.name} on this PC` : `${fileName(c.file)} hasn't synced to this PC yet`,
        onclick: () => playFriendClip(c, el),
        onkeydown: (e) => { if (e.target === el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); playFriendClip(c, el); } },
      },
      h("span", { class: "sb-emoji" }, c.emoji || "🔊"),
      h("span", { class: "sb-name" }, c.name),
      hasMedia(c.file) ? h("span", { class: "sb-tools" }, playButton(c.file, () => c.volume)) : null);
      return el;
    })),
  ]);
}

async function playFriendClip(c, tile) {
  if (!hasMedia(c.file)) return;
  try {
    await api("/api/play", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file: c.file, volume: c.volume }) });
  } catch (e) {
    toast(`Couldn't play ${c.name}: ${e.message}`, "err");
    return;
  }
  tile.classList.remove("playing");
  void tile.offsetWidth;
  tile.style.setProperty("--dur", `${c.duration}s`);
  tile.classList.add("playing");
  clearTimeout(tile._done);
  tile._done = setTimeout(() => tile.classList.remove("playing"), c.duration * 1000);
}

// ---- Inspector ----

function renderInspector() {
  const insp = $("#inspector");
  const sel = S.selection;
  if (!sel) {
    insp.replaceChildren(h("div", { class: "inspector-empty" },
      h("div", { class: "inspector-empty-glyph" }, "◈"),
      h("p", {}, "Pick an item, ability, game event or reminder to choose what happens when it triggers.")));
    return;
  }

  let head, events, warn, timing;
  if (sel.kind === "reminder") {
    const rule = S.config.rules.find((r) => r.id === sel.key);
    if (!rule) { S.selection = null; renderInspector(); return; }
    const d = describeTrigger(rule.monitor);
    head = { title: d.title.replace(/^Reminder · /, ""), glyph: d.glyph, sub: "Reminder" };
    // Each reminder is its own rule (the compiler keys periodic monitors per rule), even on a shared schedule
    events = [{ event: "TICK", label: "Timer", desc: rule.monitor.type === "once" ? "When the game clock reaches this time, this plays." : "Each time the timer comes round, this plays.", monitor: rule.monitor, rule }];
    timing = renderReminderTiming(rule);
  } else if (sel.kind === "item") {
    const item = lookup.items.get(sel.key);
    head = { title: item?.name || sel.key, img: itemImg(item?.img || sel.key.replace(/^item_/, "")) };
    events = ITEM_EVENTS.map((e) => ({ ...e, monitor: { type: "item", target: sel.key, event: e.event } }));
    if (sel.key === "item_hand_of_midas") events.push(...MIDAS_EVENTS.map((e) => ({ ...e, monitor: { type: "midas", event: e.event } })));
    if (item && !item.has_cd) warn = "This item has no active, so Used and Ready never fire. Bought and Lost still work.";
  } else if (sel.kind === "ability") {
    const ab = lookup.abilities.get(sel.key);
    head = { title: ab?.name || sel.key, img: abilityImg(sel.key), square: true, sub: ab?.hero.name, desc: ab?.desc };
    events = ABILITY_EVENTS.map((e) => ({ ...e, monitor: { type: "ability", target: sel.key, event: e.event } }));
    if (ab && !ab.has_cd) warn = "This looks like a passive (no cooldown), so it will never trigger.";
  } else {
    const [type, event] = sel.key.split(":");
    const g = GAME_EVENTS.find((x) => x.type === type && x.event === event);
    head = { title: g.label, img: g.img, glyph: g.glyph, sub: g.sub };
    events = [{ event, label: g.label, desc: g.sub, monitor: { type, event } }];
    if (g.baseline) warn = "Lights set here become the room's baseline colour until the next day/night change.";
  }

  const current = events.find((e) => e.event === S.activeEvent) || events[0];
  S.activeEvent = current.event;

  insp.replaceChildren(...[
    h("div", { class: "insp-head" },
      h("div", { class: `insp-icon ${head.square ? "square" : ""}`, style: head.img ? { backgroundImage: `url("${head.img}")` } : null }, head.glyph || ""),
      h("div", {}, h("h2", {}, head.title), h("code", {}, head.sub ? `${head.sub} · ` : "", sel.key))),
    head.desc ? h("p", { class: "insp-desc" }, head.desc) : null,
    warn ? h("div", { class: "insp-warn" }, warn) : null,
    timing || null,
    events.length > 1 ? h("div", { class: "event-tabs", role: "tablist" }, events.map((e) => {
      const live = rulesFor(e.monitor).some((r) => activeActions(r).length);
      return h("button", {
        role: "tab", "aria-selected": String(e === current), class: e === current ? "active" : "",
        onclick: () => { S.activeEvent = e.event; renderInspector(); },
      }, e.label, live ? h("span", { class: "dot" }) : null);
    })) : h("div", { style: { height: "14px" } }),
    renderEventBody(current),
  ].filter(Boolean));
}

const addSoundButton = (add) => h("button", { class: "btn btn-sm", disabled: !S.media[0], onclick: () => add({ type: "play_sound", enabled: true, clips: [{ file: S.media[0].file, probability: 100, volume: 50 }] }) }, icon("sound"), "Sound");

// The schedule a reminder had before Repeats was flipped, so flipping it back restores it
const otherSchedule = new Map();

function renderReminderTiming(rule) {
  const m = rule.monitor;
  const changed = () => { markDirty(); render(); };
  const repeats = h("label", { class: "toggle" },
    h("input", { type: "checkbox", checked: m.type === "periodic", onchange: (e) => {
      const fallback = e.target.checked
        ? { type: "periodic", period: 300, offset: 0, min_time: 0, max_time: null }
        : { type: "once", time: reminderTimes(m).find((t) => t > 0) ?? 300 };
      const next = otherSchedule.get(rule.id) || fallback;
      otherSchedule.set(rule.id, m);
      rule.monitor = next;
      changed();
    } }),
    h("span", { class: "toggle-track" }), h("span", {}, "Repeats"));
  if (m.type === "once") {
    return h("div", { class: "reminder-timing" }, repeats,
      h("div", { class: "field" }, h("span", { class: "lbl" }, "At"),
        h("input", { type: "text", inputmode: "numeric", placeholder: "m:ss", value: clock(m.time), "aria-label": "Game time", class: "clock-input",
          onchange: (e) => {
            const v = parseClock(e.target.value);
            if (v == null) { toast("At: use minutes:seconds, like 12:30", "err"); render(); return; }
            m.time = v;
            changed();
          } }),
        h("span", { class: "hint" }, "game clock")),
      h("p", { class: "hint" }, `Plays once at ${clock(m.time)}, each match.`));
  }
  const clockInput = (label, key, { required = false, hint } = {}) => h("div", { class: "field" }, h("span", { class: "lbl" }, label),
    h("input", { type: "text", inputmode: "numeric", placeholder: required ? "m:ss" : "any", value: m[key] == null ? "" : clock(m[key]), "aria-label": label, class: "clock-input",
      onchange: (e) => {
        const v = parseClock(e.target.value);
        if (v === undefined || (required && (v == null || v < 1))) { toast(`${label}: use minutes:seconds, like 2:00`, "err"); render(); return; }
        if (key !== "period" && v != null && ((key === "min_time" && m.max_time != null && v > m.max_time) || (key === "max_time" && m.min_time != null && v < m.min_time))) {
          toast("“From” has to be before “Until”", "err"); render(); return;
        }
        m[key] = v;
        changed();
      } }),
    hint ? h("span", { class: "hint" }, hint) : null);
  const off = m.offset ?? 0;
  const secs = h("input", { type: "number", min: 0, max: 59, value: Math.abs(off), "aria-label": "Seconds",
    onchange: (e) => { const n = Math.max(0, Math.min(59, Math.round(+e.target.value || 0))); m.offset = dir.value === "late" ? n : -n; changed(); } });
  const dir = h("select", { "aria-label": "Early or late", onchange: () => { const n = Math.abs(m.offset ?? 0); m.offset = dir.value === "late" ? n : -n; changed(); } },
    h("option", { value: "early", selected: off <= 0 }, "s early"), h("option", { value: "late", selected: off > 0 }, "s late"));
  const times = reminderTimes(m);
  return h("div", { class: "reminder-timing" }, repeats,
    clockInput("Every", "period", { required: true }),
    h("div", { class: "field", title: "Shift each reminder so you have time to act (up to 59 s)" }, h("span", { class: "lbl" }, "Shift"), secs, dir),
    clockInput("From", "min_time", { hint: "game clock, blank = from the start" }),
    clockInput("Until", "max_time", { hint: "blank = all game" }),
    h("p", { class: "hint" }, times.length ? `Plays at ${times.map(clock).join(", ")}${m.max_time == null || times.length === 4 ? "…" : ""}` : "This range never fires."));
}

function renderEventBody(ev) {
  const monitor = ev.monitor;
  const rules = ev.rule ? [ev.rule] : rulesFor(monitor);
  const actions = rules.flatMap((r) => r.actions.map((a) => ({ rule: r, action: a })));
  const changed = () => { markDirty(); render(); };

  const add = (action) => { (ev.rule || ensureRule(monitor)).actions.push(action); changed(); };
  const what = ev.rule ? "reminder" : rules.length > 1 ? `${rules.length} rules` : "rule";
  // Only rules change here; sound files stay in the library
  const removeRules = () => {
    if (actions.length && !confirm(`Delete this ${what} and its ${plural(actions.length, "action")}? Your sound files stay.`)) return;
    for (const r of rules) {
      S.config.rules.splice(S.config.rules.indexOf(r), 1);
      S.newRuleIds.delete(r.id);
      otherSchedule.delete(r.id);
    }
    if (ev.rule) S.selection = null; // a reminder's panel has nothing left to show
    changed();
  };

  return h("div", { class: "event-body" },
    h("p", { class: "event-desc" }, ev.desc),
    actions.length ? actions.map(({ rule, action }) => renderAction(rule, action, monitor, changed)) : h("p", { class: "hint" }, "Nothing happens yet. Add a sound or a light:"),
    h("div", { class: "add-row" },
      addSoundButton(add),
      h("button", { class: "btn btn-sm", onclick: () => add({ type: "light", enabled: true, r: 255, g: 0, b: 0, priority: isBaseline(monitor) ? null : nextPriority() }) }, icon("light"), "Light"),
      h("button", { class: "btn btn-sm btn-ghost", onclick: () => add({ type: "webhook", enabled: true, url: "https://", api_key: null, auth_type: null, timeout: 2, cooldown: 0 }) }, icon("webhook"), "Webhook")),
    rules.length ? h("button", { class: "btn btn-sm btn-delete", onclick: removeRules }, icon("trash"), `Delete ${what}`) : null,
  );
}

const clipEmoji = (file) => [...S.clips, ...[...(S.sharing?.people || []), ...(S.sharing?.packs || [])].flatMap((f) => f.soundboard)].find((c) => c.file === file)?.emoji || "🔊";

// Discord-style soundboard grid for choosing a rule's sound
function openSoundPicker(anchor, selected, onPick) {
  let query = "";
  const grid = h("div", { class: "sb-grid sp-grid" });
  const search = h("input", { type: "search", placeholder: "Search sounds…", "aria-label": "Search sounds" });
  const close = () => {
    pop.remove();
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("mousedown", onOutside, true);
    window.removeEventListener("resize", close);
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const onOutside = (e) => { if (!pop.contains(e.target) && !anchor.contains(e.target)) close(); };

  const fill = () => {
    const q = query.trim().toLowerCase();
    const items = S.media.filter((m) => !q || mediaLabel(m).toLowerCase().includes(q));
    grid.replaceChildren(...(items.length ? items.map((m) => {
      const pick = () => { close(); onPick(m.file); };
      const clip = S.clips.find((c) => c.file === m.file);
      return h("div", {
        class: `sb-tile ${m.file === selected ? "selected" : ""}`, role: "button", tabindex: "0", title: fileName(m.file),
        onclick: pick,
        onkeydown: (e) => { if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(); } },
      },
      h("span", { class: "sb-emoji" }, clipEmoji(m.file)),
      h("span", { class: "sb-name" }, mediaLabel(m)),
      h("span", { class: "sb-tools" }, playButton(m.file, () => clip?.volume ?? 100)));
    }) : [h("p", { class: "hint" }, S.media.length ? "No sounds match." : "No sounds yet. Add some in the Soundboard tab.")]));
  };
  search.addEventListener("input", (e) => { query = e.target.value; fill(); });
  fill();

  const pop = h("div", { class: "sp-pop", role: "dialog", "aria-label": "Choose a sound" }, search, grid);
  document.body.append(pop);
  const r = anchor.getBoundingClientRect();
  const width = Math.min(460, window.innerWidth - 16);
  const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
  const below = window.innerHeight - r.bottom, above = r.top;
  const up = below < 280 && above > below;
  Object.assign(pop.style, { width: `${width}px`, left: `${left}px` });
  if (up) pop.style.bottom = `${window.innerHeight - r.top + 6}px`; else pop.style.top = `${r.bottom + 6}px`;
  grid.style.maxHeight = `${Math.max(140, Math.min(360, (up ? above : below) - 80))}px`;
  document.addEventListener("keydown", onKey);
  document.addEventListener("mousedown", onOutside, true);
  window.addEventListener("resize", close);
  search.focus();
}

function renderAction(rule, a, monitor, changed) {
  const remove = () => { rule.actions.splice(rule.actions.indexOf(a), 1); changed(); };
  const enabled = h("label", { class: "toggle", title: "On / off" },
    h("input", { type: "checkbox", checked: a.enabled !== false, onchange: (e) => { a.enabled = e.target.checked; changed(); } }),
    h("span", { class: "toggle-track" }));
  const del = h("button", { class: "btn btn-sm btn-ghost btn-danger", title: "Remove", "aria-label": "Remove action", onclick: remove }, "✕");
  const cls = `action ${a.type === "play_sound" ? "sound" : a.type} ${a.enabled === false ? "disabled" : ""}`;

  if (a.type === "play_sound") {
    const clips = a.clips;
    const multi = clips.length > 1;
    const color = (i) => CLIP_COLOURS[i % CLIP_COLOURS.length];

    // Distribution bar: one segment per clip, drag the handle between two segments to move the odds from one to the other
    const segs = clips.map((c, i) => h("div", { class: "dist-seg", style: { flexGrow: String(c.probability), background: color(i) } }, h("span", {}, `${c.probability}%`)));
    const refresh = () => clips.forEach((c, i) => {
      segs[i].style.flexGrow = String(c.probability);
      segs[i].firstChild.textContent = `${c.probability}%`;
      segs[i].classList.toggle("zero", c.probability === 0);
      pcts[i].value = `${c.probability}%`;
    });
    const move = (i, to) => { // boundary between clip i and i+1 so that clip i holds `to`
      const total = clips[i].probability + clips[i + 1].probability;
      clips[i].probability = Math.max(0, Math.min(total, to));
      clips[i + 1].probability = total - clips[i].probability;
      refresh(); markDirty();
    };
    const parts = [];
    clips.forEach((c, i) => {
      parts.push(segs[i]);
      if (i === clips.length - 1) return;
      const handle = h("div", { class: "dist-handle", role: "slider", tabindex: "0", "aria-label": `Odds between variant ${i + 1} and ${i + 2}`,
        "aria-valuemin": 0, "aria-valuemax": 100,
        onkeydown: (e) => {
          const step = e.key === "ArrowLeft" ? -1 : e.key === "ArrowRight" ? 1 : 0;
          if (step) { e.preventDefault(); move(i, clips[i].probability + (e.shiftKey ? 5 : 1) * step); }
        },
        onpointerdown: (e) => {
          e.preventDefault();
          handle.setPointerCapture(e.pointerId);
          const bar = handle.parentElement.getBoundingClientRect();
          const startX = e.clientX, startP = clips[i].probability;
          const onMove = (ev) => {
            let to = startP + Math.round(((ev.clientX - startX) / bar.width) * 100);
            if (ev.shiftKey) to = Math.round(to / 5) * 5;
            move(i, to);
          };
          const onUp = () => { handle.removeEventListener("pointermove", onMove); handle.removeEventListener("pointerup", onUp); handle.removeEventListener("pointercancel", onUp); };
          handle.addEventListener("pointermove", onMove);
          handle.addEventListener("pointerup", onUp);
          handle.addEventListener("pointercancel", onUp);
        } });
      parts.push(handle);
    });
    const bar = h("div", { class: "dist-bar", title: "Drag the handles to set how likely each sound is. Hold Shift to snap to 5%." }, parts);

    const pcts = clips.map(() => h("output", { class: "clip-pct" }));
    const rows = clips.map((c, i) => {
      const known = hasMedia(c.file);
      const current = S.media.find((m) => m.file === c.file);
      const sel = h("button", { class: `sound-pick ${known ? "" : "missing"}`, type: "button", title: "Choose a sound", "aria-label": "Choose sound",
        onclick: () => openSoundPicker(sel, c.file, (file) => { c.file = file; changed(); }) },
        h("span", { class: "sb-emoji" }, known ? clipEmoji(c.file) : "⚠"),
        h("span", { class: "sb-name" }, known ? mediaLabel(current) : `${fileName(c.file)} (missing)`),
        h("span", { class: "sound-pick-caret" }, "▾"));
      const out = h("output", {}, `${c.volume}%`);
      const vol = h("input", { type: "range", min: 0, max: 100, value: c.volume, "aria-label": "Volume",
        oninput: (e) => { c.volume = +e.target.value; out.value = `${c.volume}%`; markDirty(); } });
      const test = h("button", { class: "btn btn-sm btn-ghost", title: "Play it through the app, like in-game", disabled: !known,
        onclick: () => api("/api/play", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file: c.file, volume: c.volume }) }).catch((e) => toast(e.message, "err")) }, "🔊");
      const drop = multi ? h("button", { class: "btn btn-sm btn-ghost btn-danger", title: "Remove this variant", "aria-label": "Remove variant",
        onclick: () => { // its share goes to the neighbour
          const give = clips[i - 1] || clips[i + 1];
          give.probability += c.probability;
          clips.splice(i, 1); changed();
        } }, "✕") : null;
      pcts[i].value = `${c.probability}%`;
      return h("div", { class: "clip-row" },
        h("div", { class: "field" },
          multi ? h("span", { class: "clip-swatch", style: { background: color(i) } }) : null,
          known ? playButton(c.file, () => c.volume) : h("span", { class: "play missing" }, "!"), sel,
          multi ? pcts[i] : null, test, drop),
        h("div", { class: "field" }, h("span", { class: "lbl" }, "Volume"), vol, out),
        known ? null : h("div", { class: "missing-note" }, "This file isn't in media/ yet. Drop a clip onto this card to add it."));
    });

    const addVariant = () => { // new variant takes an even share; the others shrink in proportion
      const share = Math.floor(100 / (clips.length + 1));
      const rest = 100 - share;
      const scaled = clips.map((c) => (c.probability * rest) / 100);
      const floors = scaled.map(Math.floor);
      let left = rest - floors.reduce((s, v) => s + v, 0);
      scaled.map((v, i) => [v - floors[i], i]).sort((x, y) => y[0] - x[0]).forEach(([, i]) => { if (left > 0) { floors[i]++; left--; } });
      clips.forEach((c, i) => { c.probability = floors[i]; });
      const pick = S.media.find((m) => !clips.some((c) => c.file === m.file)) || S.media[0];
      clips.push({ file: pick.file, probability: share, volume: clips[clips.length - 1].volume });
      changed();
    };
    const equalize = () => {
      const base = Math.floor(100 / clips.length), extra = 100 - base * clips.length;
      clips.forEach((c, i) => { c.probability = base + (i < extra ? 1 : 0); });
      changed();
    };

    const card = h("div", { class: cls },
      h("div", { class: "action-head" }, h("span", { class: "kind" }, multi ? `♪ Play one of ${clips.length} sounds` : "♪ Play sound"), enabled, del),
      multi ? bar : null,
      rows,
      h("div", { class: "add-row" },
        h("button", { class: "btn btn-sm", disabled: !S.media[0], title: "Add another sound; each time this fires, one is picked at random by the odds above", onclick: addVariant }, icon("shuffle"), "Variant"),
        multi ? h("button", { class: "btn btn-sm btn-ghost", title: "Give every variant the same odds", onclick: equalize }, "Even split") : null));
    makeDropTarget(card, async ([file]) => {
      const path = await uploadFile(file);
      if (!path) return;
      if (multi) { addVariant(); clips[clips.length - 1].file = path; } else clips[0].file = path;
      a.enabled = true; changed();
    });
    return card;
  }

  if (a.type === "light") {
    const color = h("input", { type: "color", value: hex(a), "aria-label": "Light colour",
      oninput: (e) => { Object.assign(a, rgb(e.target.value)); markDirty(); } });
    const presets = h("div", { class: "light-presets" }, LIGHT_PRESETS.map((c) => h("button", {
      style: { background: c }, title: c, "aria-label": `Set colour ${c}`,
      onclick: () => { Object.assign(a, rgb(c)); changed(); },
    })));
    return h("div", { class: cls },
      h("div", { class: "action-head" }, h("span", { class: "kind" }, "💡 Set light"), enabled, del),
      h("div", { class: "field" }, h("span", { class: "lbl" }, "Colour"), color, presets),
      isBaseline(monitor)
        ? h("div", { class: "field" }, h("span", { class: "lbl" }, "Priority"), h("span", { class: "hint" }, "Baseline (lowest)"))
        : h("div", { class: "field", title: "When two lights want to be on, the higher number wins. Each must be different." },
          h("span", { class: "lbl" }, "Priority"),
          h("input", { type: "number", min: 1, value: a.priority ?? "", "aria-label": "Priority", onchange: (e) => { a.priority = e.target.value ? +e.target.value : null; changed(); } }),
          h("span", { class: "hint" }, "higher wins")),
    );
  }

  // webhook
  const field = (label, key, type = "text", parse = (v) => v || null) => h("div", { class: "field" }, h("span", { class: "lbl" }, label),
    h("input", { type, value: a[key] ?? "", "aria-label": label, onchange: (e) => { a[key] = parse(e.target.value); changed(); } }));
  return h("div", { class: cls },
    h("div", { class: "action-head" }, h("span", { class: "kind" }, "⇢ Webhook"), enabled, del),
    field("URL", "url", "url", (v) => v),
    field("API key", "api_key", "password"),
    h("div", { class: "field" }, h("span", { class: "lbl" }, "Auth"),
      h("select", { "aria-label": "Auth type", onchange: (e) => { a.auth_type = e.target.value || null; changed(); } },
        ["", "bearer", "header", "query"].map((v) => h("option", { value: v, selected: (a.auth_type || "") === v }, v || "none")))),
    field("Cooldown", "cooldown", "number", (v) => +v || 0));
}

loadAll().catch((e) => toast(`Couldn't load config: ${e.message}`, "err", 10000));
