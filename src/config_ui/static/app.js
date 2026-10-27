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

const LIGHT_PRESETS = ["#ff0000", "#ff8800", "#ffd23f", "#33cc33", "#00c8ff", "#3355ff", "#a020f0", "#ffffff"];

// ---- State ----

const S = {
  config: null,       // rules.json as last loaded / edited
  saved: "",          // JSON of the config as last saved, for dirty tracking
  media: [],
  catalog: { heroes: [], items: [] },
  tab: "rules",
  selection: null,    // { kind: "item"|"ability"|"game", key, event? }
  activeEvent: null,
  heroKey: null,
  itemQuery: "",
  heroQuery: "",
  heroAttr: null,
  newRuleIds: new Set(),
};

const lookup = { items: new Map(), abilities: new Map() };

const $ = (sel, root = document) => root.querySelector(sel);
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
  const [config, media] = await Promise.all([api("/api/config"), api("/api/media")]);
  S.config = config;
  S.media = media;
  S.saved = JSON.stringify(config);
  renderTopbar();
  render();
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

function sameMonitor(a, b) {
  const norm = (m) => (isBlink(m) ? { type: "item", target: "item_blink", event: m.event } : m);
  a = norm(a); b = norm(b);
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
const fileName = (file) => file.replace(/^media\//, "");
const hasMedia = (file) => S.media.some((m) => m.file === file);

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
  const g = GAME_EVENTS.find((e) => e.type === m.type && e.event === m.event);
  return { title: g?.label || m.event, sub: g?.sub || m.type, img: g?.img, glyph: g?.glyph };
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

// ---- Toasts ----

function toast(content, cls = "", ms = 4000) {
  const el = h("div", { class: `toast ${cls}`, role: "status" }, content);
  $("#toasts").append(el);
  setTimeout(() => el.remove(), ms);
}

// ---- Audio preview ----

let previewAudio = null;
let previewBtn = null;

function previewSound(file, volume, btn) {
  if (previewAudio) {
    previewAudio.pause();
    previewBtn?.classList.remove("playing");
    if (previewBtn === btn) { previewAudio = previewBtn = null; return; }
  }
  previewAudio = new Audio("/" + file.split("/").map(encodeURIComponent).join("/"));
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
document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "s") { e.preventDefault(); if (isDirty()) save(); }
});
window.addEventListener("beforeunload", (e) => { if (S.config && isDirty()) e.preventDefault(); });

$("#tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (!btn) return;
  S.tab = btn.dataset.tab;
  render();
});

// ---- Board ----

function render() {
  for (const b of document.querySelectorAll("#tabs button")) b.classList.toggle("active", b.dataset.tab === S.tab);
  const board = $("#board");
  const scroll = board.scrollTop;
  board.replaceChildren(...[({ rules: renderRules, items: renderItems, heroes: renderHeroes, events: renderEvents, sounds: renderSounds }[S.tab])()].flat().filter(Boolean));
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

function renderRules() {
  const rules = S.config.rules;
  const live = rules.filter((r) => activeActions(r).length);
  const idle = rules.filter((r) => !activeActions(r).length);
  const row = (r) => {
    const d = describeTrigger(r.monitor);
    const acts = r.actions.map((a) => {
      const off = a.enabled === false ? "off" : "";
      if (a.type === "play_sound") return h("span", { class: `chip ${off} ${hasMedia(a.file) ? "" : "missing"}`, title: a.file }, "♪ ", fileName(a.file), ` · ${a.volume}%`);
      if (a.type === "light") return h("span", { class: `chip ${off}` }, h("span", { class: "swatch", style: { background: hex(a) } }), a.priority ? `prio ${a.priority}` : "baseline");
      return h("span", { class: `chip ${off}`, title: a.url }, "⇢ webhook");
    });
    return h("button", {
      class: `rule-row ${activeActions(r).length ? "" : "inactive"}`,
      onclick: () => jumpTo(r.monitor),
    },
    h("span", { class: `thumb ${d.square ? "square" : ""}`, style: d.img ? { backgroundImage: `url("${d.img}")` } : null }, d.glyph || ""),
    h("span", { class: "trig" }, h("div", { class: "t" }, d.title), h("div", { class: "s" }, d.sub)),
    h("span", { class: "acts" }, acts.length ? acts : h("span", { class: "hint" }, "No actions")),
    h("span", { class: "arrow" }, "›"));
  };
  return [
    h("div", { class: "board-head" }, h("h1", {}, "All rules")),
    h("p", { class: "hint" }, "Every trigger that does something. Click one to edit it, or browse Items, Heroes and Game events to add new ones."),
    h("div", { class: "section-title" }, "Active", h("span", { class: "count" }, live.length)),
    h("div", { class: "rule-list" }, live.map(row)),
    idle.length ? h("div", { class: "section-title" }, "Doing nothing yet", h("span", { class: "count" }, idle.length)) : null,
    idle.length ? h("div", { class: "rule-list" }, idle.map(row)) : null,
  ];
}

function jumpTo(monitor) {
  if (monitor.type === "item" || monitor.type === "blink") {
    S.tab = "items";
    select({ kind: "item", key: monitorTarget(monitor), event: monitor.event });
  } else if (monitor.type === "ability") {
    S.tab = "heroes";
    S.heroKey = lookup.abilities.get(monitor.target)?.hero.key || S.heroKey;
    select({ kind: "ability", key: monitor.target, event: monitor.event });
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
  ];
}

function renderSounds() {
  const usage = new Map();
  for (const r of S.config.rules) for (const a of r.actions) if (a.type === "play_sound") usage.set(a.file, (usage.get(a.file) || 0) + 1);
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
        const path = await uploadFile(file, fileName(f).replace(/\.[^.]+$/, "") + file.name.slice(file.name.lastIndexOf(".")));
        if (!path) return;
        for (const r of S.config.rules) for (const a of r.actions) if (a.type === "play_sound" && a.file === f) Object.assign(a, { file: path, enabled: true });
        markDirty();
        render();
      });
      return row;
    })) : null,
    h("div", { class: "section-title" }, "Library", h("span", { class: "count" }, S.media.length)),
    h("div", { class: "sound-list" }, S.media.map((m) => h("div", { class: "sound-row" },
      playButton(m.file),
      h("span", { class: "n", title: m.name }, m.name),
      h("span", { class: "u" }, usage.get(m.file) ? `used ×${usage.get(m.file)}` : "unused")))),
  ];
}

function makeDropTarget(el, onFiles) {
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add(el.classList.contains("action") ? "drop-over" : "over"); });
  el.addEventListener("dragleave", () => el.classList.remove("over", "drop-over"));
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    el.classList.remove("over", "drop-over");
    const files = [...e.dataTransfer.files].filter((f) => /\.(mp3|wav|ogg)$/i.test(f.name));
    if (files.length) onFiles(files);
  });
}

// ---- Inspector ----

function renderInspector() {
  const insp = $("#inspector");
  const sel = S.selection;
  if (!sel) {
    insp.replaceChildren(h("div", { class: "inspector-empty" },
      h("div", { class: "inspector-empty-glyph" }, "◈"),
      h("p", {}, "Pick an item, ability or game event to choose what happens when it triggers.")));
    return;
  }

  let head, events, warn;
  if (sel.kind === "item") {
    const item = lookup.items.get(sel.key);
    head = { title: item?.name || sel.key, img: itemImg(item?.img || sel.key.replace(/^item_/, "")) };
    events = ITEM_EVENTS.map((e) => ({ ...e, monitor: { type: "item", target: sel.key, event: e.event } }));
    if (sel.key === "item_hand_of_midas") events.push(...MIDAS_EVENTS.map((e) => ({ ...e, monitor: { type: "midas", event: e.event } })));
    if (item && !item.has_cd) warn = "This item has no active, so Used and Ready never fire. Bought and Lost still work.";
  } else if (sel.kind === "ability") {
    const ab = lookup.abilities.get(sel.key);
    head = { title: ab?.name || sel.key, img: abilityImg(sel.key), square: true, sub: ab?.hero.name };
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
    warn ? h("div", { class: "insp-warn" }, warn) : null,
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

function renderEventBody(ev) {
  const monitor = ev.monitor;
  const rules = rulesFor(monitor);
  const actions = rules.flatMap((r) => r.actions.map((a) => ({ rule: r, action: a })));
  const changed = () => { markDirty(); render(); };

  const add = (action) => { ensureRule(monitor).actions.push(action); changed(); };
  const firstSound = S.media[0]?.file;

  return h("div", { class: "event-body" },
    h("p", { class: "event-desc" }, ev.desc),
    actions.length ? actions.map(({ rule, action }) => renderAction(rule, action, monitor, changed)) : h("p", { class: "hint" }, "Nothing happens yet. Add a sound or a light:"),
    h("div", { class: "add-row" },
      h("button", { class: "btn btn-sm", disabled: !firstSound, onclick: () => add({ type: "play_sound", enabled: true, file: firstSound, volume: 50 }) }, "+ Sound"),
      h("button", { class: "btn btn-sm", onclick: () => add({ type: "light", enabled: true, r: 255, g: 0, b: 0, priority: isBaseline(monitor) ? null : nextPriority() }) }, "+ Light"),
      h("button", { class: "btn btn-sm btn-ghost", onclick: () => add({ type: "webhook", enabled: true, url: "https://", api_key: null, auth_type: null, timeout: 2, cooldown: 0 }) }, "+ Webhook")),
  );
}

function renderAction(rule, a, monitor, changed) {
  const remove = () => { rule.actions.splice(rule.actions.indexOf(a), 1); changed(); };
  const enabled = h("label", { class: "toggle", title: "On / off" },
    h("input", { type: "checkbox", checked: a.enabled !== false, onchange: (e) => { a.enabled = e.target.checked; changed(); } }),
    h("span", { class: "toggle-track" }));
  const del = h("button", { class: "btn btn-sm btn-ghost btn-danger", title: "Remove", "aria-label": "Remove action", onclick: remove }, "✕");
  const cls = `action ${a.type === "play_sound" ? "sound" : a.type} ${a.enabled === false ? "disabled" : ""}`;

  if (a.type === "play_sound") {
    const known = hasMedia(a.file);
    const options = S.media.map((m) => h("option", { value: m.file, selected: m.file === a.file }, m.name));
    if (!known) options.unshift(h("option", { value: a.file, selected: true }, `⚠ ${fileName(a.file)} (missing)`));
    const sel = h("select", { "aria-label": "Sound file", onchange: (e) => { a.file = e.target.value; changed(); } }, options);
    const out = h("output", {}, `${a.volume}%`);
    const vol = h("input", { type: "range", min: 0, max: 100, value: a.volume, "aria-label": "Volume",
      oninput: (e) => { a.volume = +e.target.value; out.value = `${a.volume}%`; markDirty(); } });
    const pcBtn = h("button", { class: "btn btn-sm btn-ghost", title: "Play it through the app, like in-game", disabled: !known,
      onclick: () => api("/api/play", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ file: a.file, volume: a.volume }) }).catch((e) => toast(e.message, "err")) }, "🔊 Test");
    const card = h("div", { class: cls },
      h("div", { class: "action-head" }, h("span", { class: "kind" }, "♪ Play sound"), pcBtn, enabled, del),
      h("div", { class: "field" }, known ? playButton(a.file, () => a.volume) : h("span", { class: "play missing" }, "!"), sel),
      h("div", { class: "field" }, h("span", { class: "lbl" }, "Volume"), vol, out),
      known ? null : h("div", { class: "missing-note" }, "This file isn't in media/ yet. Drop a clip onto this card to add it."));
    makeDropTarget(card, async ([file]) => {
      const path = await uploadFile(file);
      if (path) { a.file = path; a.enabled = true; changed(); }
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
