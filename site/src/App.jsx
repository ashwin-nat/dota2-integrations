import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useMotionValue, useScroll, useSpring, useTransform, animate } from "framer-motion";
import { play } from "./sfx.js";

const REPO = "ashwin-nat/dota2-integrations";
const GITHUB = `https://github.com/${REPO}`;
// Always the newest release's files, so this page never needs updating for a new version
const asset = (name) => `${GITHUB}/releases/latest/download/${name}`;

const DOWNLOADS = [
  { os: "windows", label: "Windows", sub: "Windows 10 and 11", file: "juke-windows.exe", icon: "⊞" },
  { os: "mac-arm", label: "Mac · Apple Silicon", sub: "M1, M2, M3, M4", file: "juke-mac.zip", icon: "🍎" },
  { os: "mac-intel", label: "Mac · Intel", sub: "Older Intel Macs", file: "juke-mac-intel.zip", icon: "💻" },
];

function detectOs() {
  const ua = navigator.userAgent;
  if (/Windows/i.test(ua)) return "windows";
  if (/Mac/i.test(ua)) return "mac-arm";
  return null;
}

const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.6, delay: i * 0.08, ease: [0.2, 0.7, 0.2, 1] } }),
};

function Section({ id, eyebrow, title, children, lead }) {
  return (
    <section id={id} className="section">
      <motion.div className="section-head" initial="hidden" whileInView="show" viewport={{ once: true, margin: "-80px" }}>
        <motion.div className="eyebrow" variants={fadeUp}>{eyebrow}</motion.div>
        <motion.h2 variants={fadeUp} custom={1}>{title}</motion.h2>
        {lead && <motion.p className="lead" variants={fadeUp} custom={2}>{lead}</motion.p>}
      </motion.div>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------- Nav + hero

function Nav() {
  const { scrollY } = useScroll();
  const bg = useTransform(scrollY, [0, 120], ["rgba(9,11,15,0)", "rgba(9,11,15,0.85)"]);
  return (
    <motion.nav className="nav" style={{ backgroundColor: bg }}>
      <a className="brand" href="#top"><Diamond size={22} /> Juke</a>
      <div className="nav-links">
        <a href="#demo">Demo</a>
        <a href="#features">Features</a>
        <a href="#squad">Squad</a>
        <a href="#download" className="nav-cta">Download</a>
      </div>
    </motion.nav>
  );
}

function Diamond({ size = 28, spin = false }) {
  return (
    <motion.svg width={size} height={size} viewBox="0 0 64 64" aria-hidden
      animate={spin ? { rotate: 360 } : undefined} transition={spin ? { duration: 18, repeat: Infinity, ease: "linear" } : undefined}>
      <path d="M32 4 60 32 32 60 4 32Z" fill="var(--gold)" />
      <path d="M32 20 44 32 32 44 20 32Z" fill="#782b1e" />
    </motion.svg>
  );
}

const TICKER = [
  { icon: "⚡", trigger: "Blink Dagger · Used", action: "whoosh.mp3", color: "#56b6ff" },
  { icon: "🌙", trigger: "Night falls", action: "Lights → midnight blue", color: "#3355ff" },
  { icon: "🪙", trigger: "Hand of Midas · Ready", action: "coin.mp3", color: "#ffd23f" },
  { icon: "🛡️", trigger: "Black King Bar · Used", action: "Lights → gold + shield.mp3", color: "#f0d28a" },
  { icon: "💀", trigger: "You died", action: "womp-womp.mp3", color: "#ff4d4d" },
  { icon: "☀️", trigger: "Day breaks", action: "Lights → warm sunrise", color: "#ff9a3c" },
];

function Hero({ os }) {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => (n + 1) % TICKER.length), 2200);
    return () => clearInterval(t);
  }, []);
  const ev = TICKER[i];
  const main = DOWNLOADS.find((d) => d.os === os);
  return (
    <header id="top" className="hero">
      <motion.div className="hero-glow" animate={{ background: `radial-gradient(600px 400px at 70% 40%, ${ev.color}33, transparent 70%)` }} transition={{ duration: 0.8 }} />
      <Sparks />
      <div className="hero-inner">
        <motion.div className="hero-copy" initial="hidden" animate="show">
          <motion.div className="eyebrow" variants={fadeUp}>Game soundboard · Free · Windows & Mac</motion.div>
          <motion.h1 variants={fadeUp} custom={1}>Your game.<br /><span className="gold">Your sounds.</span><br />Your lights.</motion.h1>
          <motion.p className="lead" variants={fadeUp} custom={2}>
            Juke is a soundboard that reacts to your game. The moment something happens in your match, it plays the sound
            you picked and changes your room lights: you blink in, pop BKB, your Midas comes off cooldown, night falls.
            Dota 2 is the first game; more are on the way.
          </motion.p>
          <motion.div className="hero-ctas" variants={fadeUp} custom={3}>
            <a className="btn btn-gold btn-lg" href={main ? asset(main.file) : "#download"}>
              ⇩ {main ? `Download for ${main.os === "windows" ? "Windows" : "Mac"}` : "Download"}
            </a>
            <a className="btn btn-lg" href="#demo">▶ Try it here</a>
          </motion.div>
          <motion.p className="fine" variants={fadeUp} custom={4}>
            Uses Valve's official Game State Integration. Nothing touches the game client.
          </motion.p>
        </motion.div>

        <div className="hero-stage" aria-live="polite">
          <Diamond size={220} spin />
          <AnimatePresence mode="popLayout">
            <motion.div key={i} className="event-card" style={{ "--c": ev.color }}
              initial={{ opacity: 0, y: 40, scale: 0.9, rotateX: -30 }}
              animate={{ opacity: 1, y: 0, scale: 1, rotateX: 0 }}
              exit={{ opacity: 0, y: -40, scale: 0.9 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}>
              <span className="event-icon">{ev.icon}</span>
              <div>
                <div className="event-trigger">{ev.trigger}</div>
                <div className="event-action">→ {ev.action}</div>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
      <motion.a href="#demo" className="scroll-hint" animate={{ y: [0, 8, 0] }} transition={{ duration: 1.8, repeat: Infinity }}>⌄</motion.a>
    </header>
  );
}

function Sparks() {
  const sparks = useMemo(() => Array.from({ length: 22 }, (_, i) => ({
    left: Math.random() * 100, size: 2 + Math.random() * 3, delay: Math.random() * 6, dur: 6 + Math.random() * 6, key: i,
  })), []);
  return (
    <div className="sparks" aria-hidden>
      {sparks.map((s) => (
        <motion.span key={s.key} style={{ left: `${s.left}%`, width: s.size, height: s.size }}
          initial={{ y: "105vh", opacity: 0 }} animate={{ y: "-10vh", opacity: [0, 1, 0] }}
          transition={{ duration: s.dur, delay: s.delay, repeat: Infinity, ease: "linear" }} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- Live demo

const SLOTS = [
  { key: "blink", icon: "⚡", name: "Blink Dagger", sound: "whoosh", cd: 3, light: "#56b6ff" },
  { key: "bkb", icon: "🛡️", name: "Black King Bar", sound: "shield", cd: 6, light: "#f0d28a" },
  { key: "midas", icon: "🪙", name: "Hand of Midas", sound: "coin", cd: 4, light: "#ffd23f" },
  { key: "rapier", icon: "🗡️", name: "Divine Rapier", sound: "airhorn", cd: 5, light: "#ff4d4d" },
  { key: "refresher", icon: "🔄", name: "Refresher Orb", sound: "drumroll", cd: 7, light: "#a020f0" },
  { key: "ult", icon: "💥", name: "Your ultimate", sound: "boom", cd: 8, light: "#ff8800" },
];

const COMBO_NAMES = { 2: "Double!", 3: "Triple!", 4: "Ultra!", 5: "RAMPAGE!" };

function ItemSlot({ slot, onUse }) {
  const progress = useMotionValue(0);
  const [ready, setReady] = useState(true);
  const sweep = useTransform(progress, (p) => `conic-gradient(rgba(0,0,0,.72) ${p * 360}deg, transparent 0deg)`);
  const use = () => {
    if (!ready) { play("bonk"); return; }
    setReady(false);
    onUse(slot);
    progress.set(1);
    animate(progress, 0, { duration: slot.cd, ease: "linear", onComplete: () => setReady(true) });
  };
  return (
    <motion.button className={`slot ${ready ? "ready" : ""}`} onClick={use} whileHover={{ y: -4 }} whileTap={{ scale: 0.9 }}
      aria-label={`Use ${slot.name}`} title={`${slot.name} → ${slot.sound}.mp3`}>
      <span className="slot-icon">{slot.icon}</span>
      <motion.span className="slot-cd" style={{ background: sweep }} />
      <span className="slot-name">{slot.name}</span>
    </motion.button>
  );
}

function Demo() {
  const [light, setLight] = useState("#ff9a3c");
  const [night, setNight] = useState(false);
  const [feed, setFeed] = useState([]);
  const [combo, setCombo] = useState(null);
  const recent = useRef([]);
  const id = useRef(0);

  const log = (icon, text, color) => {
    setFeed((f) => [{ id: ++id.current, icon, text, color, at: new Date() }, ...f].slice(0, 5));
  };

  const useSlot = (slot) => {
    play(slot.sound);
    setLight(slot.light);
    log(slot.icon, <><b>{slot.name}</b> used → <code>{slot.sound}.mp3</code> + lights</>, slot.light);
    const now = Date.now();
    recent.current = [...recent.current.filter((t) => now - t < 2500), now];
    const n = recent.current.length;
    if (n >= 2) setCombo({ n: Math.min(n, 5), key: now });
  };

  useEffect(() => {
    if (!combo) return;
    if (combo.n >= 3) setTimeout(() => play("airhorn"), 250);
    const t = setTimeout(() => setCombo(null), 1400);
    return () => clearTimeout(t);
  }, [combo]);

  const toggleNight = () => {
    const n = !night;
    setNight(n);
    play(n ? "nightfall" : "sunrise");
    const c = n ? "#3355ff" : "#ff9a3c";
    setLight(c);
    log(n ? "🌙" : "☀️", n ? <><b>Night falls</b> → lights midnight blue</> : <><b>Day breaks</b> → lights warm sunrise</>, c);
  };

  return (
    <Section id="demo" eyebrow="Live demo" title="Play a pretend match"
      lead="Click your items. Each one plays its sound and turns the room light its colour. Sound on! Chain a few quickly for a combo.">
      <motion.div className="demo" initial={{ opacity: 0, y: 40 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: 0.7 }}>
        <motion.div className="room-light" animate={{ backgroundColor: light, boxShadow: `0 0 120px 40px ${light}55` }} transition={{ duration: 0.5 }} />
        <div className="demo-hud">
          <div className="hud-top">
            <span className="hud-label">Inventory</span>
            <button className={`daynight ${night ? "night" : ""}`} onClick={toggleNight} aria-label="Toggle day and night">
              <motion.span className="dn-knob" layout transition={{ type: "spring", stiffness: 500, damping: 30 }}>{night ? "🌙" : "☀️"}</motion.span>
            </button>
          </div>
          <div className="slots">
            {SLOTS.map((s) => <ItemSlot key={s.key} slot={s} onUse={useSlot} />)}
          </div>
          <AnimatePresence>
            {combo && (
              <motion.div key={combo.key} className="combo" initial={{ scale: 2.2, opacity: 0, rotate: -8 }} animate={{ scale: 1, opacity: 1, rotate: -4 }} exit={{ opacity: 0, y: -30 }}
                transition={{ type: "spring", stiffness: 400, damping: 14 }}>
                {COMBO_NAMES[combo.n]}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
        <div className="demo-feed">
          <div className="hud-label">Juke log</div>
          <ul>
            <AnimatePresence initial={false}>
              {feed.length === 0 && <motion.li key="empty" className="feed-empty" exit={{ opacity: 0 }}>Waiting for something to happen…</motion.li>}
              {feed.map((e) => (
                <motion.li key={e.id} layout initial={{ opacity: 0, x: -30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} style={{ "--c": e.color }}>
                  <span className="feed-icon">{e.icon}</span><span>{e.text}</span>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        </div>
      </motion.div>
      <p className="fine center">In the real app this happens on its own while you play, and the light is your actual smart bulb.</p>
    </Section>
  );
}

// ---------------------------------------------------------------- Soundboard

const PADS = [
  ["📯", "Airhorn", "airhorn"], ["🔨", "Bonk", "bonk"], ["🔔", "Ding", "ding"], ["🔫", "Pew", "laser"],
  ["📉", "Womp womp", "womp"], ["🪙", "Ka-ching", "coin"], ["💣", "Boom", "boom"], ["🥁", "Drumroll", "drumroll"],
];

function Pad({ emoji, name, sound, i }) {
  const [hits, setHits] = useState([]);
  const hit = () => {
    play(sound);
    const k = Date.now();
    setHits((h) => [...h, k]);
    setTimeout(() => setHits((h) => h.filter((x) => x !== k)), 700);
  };
  return (
    <motion.button className="pad" onClick={hit} variants={fadeUp} custom={i} whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.92 }}>
      {hits.map((k) => <motion.span key={k} className="ripple" initial={{ scale: 0, opacity: 0.6 }} animate={{ scale: 3, opacity: 0 }} transition={{ duration: 0.7 }} />)}
      <span className="pad-emoji">{emoji}</span>
      <span className="pad-name">{name}</span>
    </motion.button>
  );
}

const BARS = Array.from({ length: 64 }, (_, i) => 0.25 + Math.abs(Math.sin(i * 0.37) * Math.cos(i * 0.11)) * 0.75);
const CLIP_SECONDS = 14;
const MAX_TRIM = 5.2;

function Trimmer() {
  const track = useRef(null);
  const [range, setRange] = useState([0.18, 0.5]);
  const seconds = (range[1] - range[0]) * CLIP_SECONDS;
  const drag = (which) => (e) => {
    e.preventDefault();
    const rect = track.current.getBoundingClientRect();
    const move = (ev) => {
      const x = Math.min(1, Math.max(0, ((ev.touches?.[0] ?? ev).clientX - rect.left) / rect.width));
      // The other handle follows so the clip never gets longer than 5.2 s
      setRange(([a, b]) => {
        const max = MAX_TRIM / CLIP_SECONDS;
        if (which === 0) {
          const start = Math.min(x, b - 0.02);
          return [start, Math.min(b, start + max)];
        }
        const end = Math.max(x, a + 0.02);
        return [Math.max(a, end - max), end];
      });
    };
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div className="trimmer">
      <div className="trim-head">
        <span className="hud-label">Trim a clip from any YouTube link</span>
        <motion.span key={seconds.toFixed(1)} className={`trim-len ${seconds > 5.1 ? "max" : ""}`} initial={{ scale: 1.3 }} animate={{ scale: 1 }}>
          {seconds.toFixed(1)} s / {MAX_TRIM} s
        </motion.span>
      </div>
      <div className="wave" ref={track}>
        {BARS.map((h, i) => {
          const on = i / BARS.length >= range[0] && i / BARS.length <= range[1];
          return <motion.span key={i} className={on ? "on" : ""} animate={{ scaleY: on ? h : h * 0.6 }} transition={{ duration: 0.2 }} />;
        })}
        <div className="trim-sel" style={{ left: `${range[0] * 100}%`, width: `${(range[1] - range[0]) * 100}%` }} />
        <span className="handle" style={{ left: `${range[0] * 100}%` }} onPointerDown={drag(0)} role="slider" aria-label="Clip start" aria-valuenow={Math.round(range[0] * CLIP_SECONDS * 10) / 10} />
        <span className="handle" style={{ left: `${range[1] * 100}%` }} onPointerDown={drag(1)} role="slider" aria-label="Clip end" aria-valuenow={Math.round(range[1] * CLIP_SECONDS * 10) / 10} />
      </div>
      <p className="fine">Drag the handles. Like Discord's soundboard, clips are up to 5.2 seconds. Saved as an MP3 you can attach to any item, ability or game event.</p>
    </div>
  );
}

function Soundboard() {
  return (
    <Section id="soundboard" eyebrow="Soundboard" title="Your squad's meme library"
      lead="Pull audio from YouTube, TikTok, Twitch clips or any video. Trim it, name it, give it an emoji. Then play it from the board or hook it to a trigger.">
      <div className="soundboard">
        <motion.div className="pads" initial="hidden" whileInView="show" viewport={{ once: true }}>
          {PADS.map(([e, n, s], i) => <Pad key={n} emoji={e} name={n} sound={s} i={i} />)}
        </motion.div>
        <motion.div initial={{ opacity: 0, x: 40 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ duration: 0.7 }}>
          <Trimmer />
        </motion.div>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- Features

const FEATURES = [
  { icon: "🎯", title: "Every item, every hero", text: "Pick from a shop-style item grid or a hero's abilities. Trigger on used, ready, bought or lost, or on day and night." },
  { icon: "💡", title: "Smart lights", text: "TP-Link Tapo and Tuya / Smart Life bulbs change colour with the game: gold for BKB, blue at night, back to normal after." },
  { icon: "🎮", title: "More games coming", text: "Dota 2 is built in today. Juke is made so other games can plug in next, starting with CS2." },
  { icon: "🧩", title: "Browser editor", text: "Point, click, preview, save. Changes apply instantly, even mid-match, with no restart." },
  { icon: "🤝", title: "Share with your squad", text: "One link gives your friends all your sounds, and it keeps updating. Nothing for them to set up." },
  { icon: "🔌", title: "Webhooks", text: "Trigger anything else: a stream overlay, a Discord bot, your own smart-home setup." },
  { icon: "🛡️", title: "Safe to use", text: "Reads only what Valve's official Game State Integration sends. No injection, no memory reading, no overlay." },
  { icon: "⚙️", title: "Sets itself up", text: "Finds your Dota install and writes the config for you. It then sits in your menu bar or tray." },
];

function TiltCard({ children, i }) {
  const rx = useSpring(0, { stiffness: 200, damping: 15 });
  const ry = useSpring(0, { stiffness: 200, damping: 15 });
  return (
    <motion.div className="feature" variants={fadeUp} custom={i} style={{ rotateX: rx, rotateY: ry }}
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        ry.set(((e.clientX - r.left) / r.width - 0.5) * 12);
        rx.set(-((e.clientY - r.top) / r.height - 0.5) * 12);
      }}
      onPointerLeave={() => { rx.set(0); ry.set(0); }}>
      {children}
    </motion.div>
  );
}

function Features() {
  return (
    <Section id="features" eyebrow="Features" title="Everything you need, nothing you don't">
      <motion.div className="features" initial="hidden" whileInView="show" viewport={{ once: true, margin: "-60px" }}>
        {FEATURES.map((f, i) => (
          <TiltCard key={f.title} i={i}>
            <div className="feature-icon">{f.icon}</div>
            <h3>{f.title}</h3>
            <p>{f.text}</p>
          </TiltCard>
        ))}
      </motion.div>
    </Section>
  );
}

// ---------------------------------------------------------------- Squad sharing

function Squad() {
  const listeners = ["🧙", "🏹", "🪓", "🐉"];
  return (
    <Section id="squad" eyebrow="Squad sharing" title="One person adds the sounds. Everyone hears them."
      lead="Admins keep a shared Google Drive folder. Juke turns it into a library link. Friends paste that link once and stay up to date.">
      <div className="squad">
        <svg className="squad-lines" viewBox="0 0 600 260" preserveAspectRatio="none" aria-hidden>
          {[60, 200].map((y) => <path key={y} d={`M110 ${y} C 200 ${y}, 220 130, 290 130`} />)}
          {[40, 100, 160, 220].map((y) => <path key={y} d={`M310 130 C 380 130, 400 ${y}, 490 ${y}`} />)}
        </svg>
        <div className="squad-col">
          {["You", "Your duo"].map((n, i) => (
            <motion.div key={n} className="node admin" initial={{ opacity: 0, x: -30 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.15 }}>
              <span>👑</span><div><b>{n}</b><small>admin · adds clips</small></div>
            </motion.div>
          ))}
        </div>
        <motion.div className="node library" initial={{ scale: 0.6, opacity: 0 }} whileInView={{ scale: 1, opacity: 1 }} viewport={{ once: true }}
          animate={{ boxShadow: ["0 0 0 0 rgba(201,166,90,.5)", "0 0 0 18px rgba(201,166,90,0)"] }} transition={{ boxShadow: { duration: 1.8, repeat: Infinity } }}>
          <span>📦</span><div><b>Library link</b><small>updates by itself</small></div>
        </motion.div>
        <div className="squad-col">
          {listeners.map((e, i) => (
            <motion.div key={i} className="node" initial={{ opacity: 0, x: 30 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.3 + i * 0.1 }}>
              <span>{e}</span><div><b>Friend {i + 1}</b><small>paste link · done</small></div>
            </motion.div>
          ))}
        </div>
      </div>
      <motion.div className="steps-3" initial="hidden" whileInView="show" viewport={{ once: true }}>
        {[
          ["1", "Invite", "In Friends, click Invite friends and copy the message."],
          ["2", "Paste", "Your friend pastes the link into Juke and presses Join."],
          ["3", "Play", "Your sounds play in their games and update every 30 minutes."],
        ].map(([n, t, d], i) => (
          <motion.div key={n} className="step" variants={fadeUp} custom={i}><span className="step-n">{n}</span><b>{t}</b><p>{d}</p></motion.div>
        ))}
      </motion.div>
    </Section>
  );
}

// ---------------------------------------------------------------- Download

function Download({ os }) {
  return (
    <Section id="download" eyebrow="Download" title="Get Juke"
      lead="Free and open source. Start it, and it opens in your browser and sets up Dota for you. Restart Dota if it was running.">
      <motion.div className="downloads" initial="hidden" whileInView="show" viewport={{ once: true }}>
        {DOWNLOADS.map((d, i) => (
          <motion.a key={d.os} href={asset(d.file)} className={`download ${d.os === os ? "mine" : ""}`} variants={fadeUp} custom={i}
            whileHover={{ y: -6 }} whileTap={{ scale: 0.97 }}>
            {d.os === os && <span className="badge">Your computer</span>}
            <span className="dl-icon">{d.icon}</span>
            <b>{d.label}</b>
            <small>{d.sub}</small>
            <span className="dl-file">{d.file}</span>
          </motion.a>
        ))}
      </motion.div>
      <div className="notes">
        <details>
          <summary>First launch on a Mac</summary>
          <p>The app isn't signed by Apple yet. Unzip it and move it to Applications. Double-click it, then open <b>System Settings → Privacy &amp; Security</b> and click <b>Open Anyway</b>. If macOS says it "is damaged", run this once in Terminal:</p>
          <pre>xattr -dr com.apple.quarantine /Applications/Juke.app</pre>
        </details>
        <details>
          <summary>First launch on Windows</summary>
          <p>If SmartScreen warns about an unknown app, click <b>More info → Run anyway</b>. Juke then shows up as a ◆ in the system tray. Click it to open the editor.</p>
        </details>
        <details>
          <summary>Build from source</summary>
          <pre>{`git clone ${GITHUB}.git\ncd dota2-integrations\nuv sync\nuv run python -m src.main`}</pre>
        </details>
      </div>
    </Section>
  );
}

// ---------------------------------------------------------------- Page

function ScrollBar() {
  const { scrollYProgress } = useScroll();
  const x = useSpring(scrollYProgress, { stiffness: 120, damping: 25 });
  return <motion.div className="progress" style={{ scaleX: x }} />;
}

export default function App() {
  const [os, setOs] = useState(null);
  useEffect(() => setOs(detectOs()), []);
  return (
    <>
      <ScrollBar />
      <Nav />
      <Hero os={os} />
      <main>
        <Demo />
        <Soundboard />
        <Features />
        <Squad />
        <Download os={os} />
      </main>
      <footer className="footer">
        <div className="brand"><Diamond size={18} /> Juke</div>
        <div className="footer-links">
          <a href={GITHUB}>GitHub</a>
          <a href={`${GITHUB}/releases`}>All releases</a>
          <a href={`${GITHUB}/issues`}>Report a bug</a>
        </div>
        <p className="fine">A fan-made tool. Not affiliated with or endorsed by Valve. Dota 2 is a trademark of Valve Corporation.</p>
      </footer>
    </>
  );
}
