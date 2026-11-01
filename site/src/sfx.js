// Every sound on the site is synthesised here with Web Audio: no audio files to ship or license.

let ctx;
const ac = () => {
  ctx ??= new (window.AudioContext || window.webkitAudioContext)();
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
};

function tone({ freq, to, dur = 0.3, type = "sine", gain = 0.25, at = 0, vibrato = 0 }) {
  const c = ac();
  const t = c.currentTime + at;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  if (to) osc.frequency.exponentialRampToValueAtTime(to, t + dur);
  if (vibrato) {
    const lfo = c.createOscillator();
    const lg = c.createGain();
    lfo.frequency.value = 6;
    lg.gain.value = vibrato;
    lfo.connect(lg).connect(osc.frequency);
    lfo.start(t);
    lfo.stop(t + dur);
  }
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(gain, t + 0.015);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  osc.connect(g).connect(c.destination);
  osc.start(t);
  osc.stop(t + dur + 0.05);
}

function noise({ dur = 0.3, gain = 0.3, at = 0, cutoff = 1200 }) {
  const c = ac();
  const t = c.currentTime + at;
  const buf = c.createBuffer(1, Math.ceil(c.sampleRate * dur), c.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  const src = c.createBufferSource();
  const filter = c.createBiquadFilter();
  const g = c.createGain();
  src.buffer = buf;
  filter.type = "lowpass";
  filter.frequency.value = cutoff;
  g.gain.setValueAtTime(gain, t);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(filter).connect(g).connect(ac().destination);
  src.start(t);
}

export const SOUNDS = {
  airhorn: () => [0, 0.32, 0.52].forEach((at, i) =>
    [440, 554, 659].forEach((f) => tone({ freq: f, dur: i === 2 ? 0.7 : 0.22, type: "sawtooth", gain: 0.07, at, vibrato: 8 }))),
  bonk: () => { tone({ freq: 700, to: 90, dur: 0.25, gain: 0.4 }); noise({ dur: 0.05, gain: 0.3, cutoff: 3000 }); },
  ding: () => { tone({ freq: 1320, dur: 1.1, gain: 0.2 }); tone({ freq: 2640, dur: 0.6, gain: 0.06 }); },
  laser: () => tone({ freq: 1800, to: 180, dur: 0.35, type: "square", gain: 0.1 }),
  womp: () => [[330, 0], [294, 0.35], [262, 0.7]].forEach(([f, at], i) =>
    tone({ freq: f, to: f * 0.85, dur: i === 2 ? 0.9 : 0.3, type: "sawtooth", gain: 0.12, at, vibrato: i === 2 ? 10 : 0 })),
  coin: () => { tone({ freq: 988, dur: 0.08, type: "square", gain: 0.12 }); tone({ freq: 1319, dur: 0.45, type: "square", gain: 0.12, at: 0.08 }); },
  boom: () => { noise({ dur: 1.2, gain: 0.6, cutoff: 400 }); tone({ freq: 120, to: 40, dur: 0.8, gain: 0.5 }); },
  drumroll: () => {
    for (let i = 0; i < 14; i++) noise({ dur: 0.06, gain: 0.15 + i * 0.01, at: i * 0.045, cutoff: 900 });
    noise({ dur: 0.9, gain: 0.25, at: 0.66, cutoff: 9000 });
  },
  whoosh: () => noise({ dur: 0.5, gain: 0.25, cutoff: 2500 }),
  shield: () => { tone({ freq: 220, to: 660, dur: 0.5, type: "triangle", gain: 0.2 }); tone({ freq: 330, to: 990, dur: 0.5, type: "triangle", gain: 0.1 }); },
  sunrise: () => [523, 659, 784, 1047].forEach((f, i) => tone({ freq: f, dur: 0.5, type: "triangle", gain: 0.12, at: i * 0.1 })),
  nightfall: () => [784, 622, 523, 392].forEach((f, i) => tone({ freq: f, dur: 0.6, type: "sine", gain: 0.14, at: i * 0.14 })),
};

export const play = (name) => {
  try {
    SOUNDS[name]?.();
  } catch {
    // Audio blocked or unsupported: the page works silently
  }
};
