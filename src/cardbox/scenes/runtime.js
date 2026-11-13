// Scene runtime: shared drawing helpers for every scene. Runs in a headless page with one canvas
// the size of the output format. The renderer injects CONFIG = { theme, format, font, icons, photos,
// dur, voice, lead, words, params } and calls drawAt(t) once per frame.
//
// Scenes draw in design coordinates: a 1080-wide stage whose content band is y 330..1290 (the
// vertical layout). film() maps that stage onto the real frame for each format, so one scene works
// in vertical, landscape and square.
//
// Timing: everything that carries information should appear when it is said. `when(spec, i, n)`
// turns a param into a time: a word ("billion") fires when that word is spoken, a number in 0..1
// is a fraction of the spoken line, and nothing spreads items evenly across the line.

const cv = document.getElementById('c'), x = cv.getContext('2d');
const W = cv.width, H = cv.height, DW = 1080;  // real frame size; design stage width
const STAGE = CONFIG.format.stage, FULL = CONFIG.format.full;
const T = CONFIG.theme, FONT = CONFIG.font === 'mono' ? 'Mono' : 'Inter', LIGHT = T.light === '1';
const C = { bg: T.bg, text: T.text, mute: T.mute, accent: T.accent, accent2: T.accent2, accent3: T.accent3,
  green: T.green, red: T.red, amber: T.amber, blue: T.blue, violet: T.violet };
const SCENES = {};

const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const ease = (v) => 1 - Math.pow(1 - clamp(v), 3);
function rng(seed) { return () => { seed |= 0; seed = (seed + 0x6D2B79F5) | 0; let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const norm = (s) => String(s).toLowerCase().replace(/[^a-z0-9]/g, '');

// The time (s) at which the i-th of n elements should appear, or the time of a cue.
function at(i, n) { return CONFIG.lead + (CONFIG.voice * i) / Math.max(n, 1); }
function cue(word) {
  const w = norm(word); if (!w) return null;
  for (const [v, s] of CONFIG.words) if (v === w || v.startsWith(w)) return CONFIG.lead + s;
  return null;
}
function when(spec, i = 0, n = 1) {
  if (typeof spec === 'string') { const c = cue(spec); if (c !== null) return c; }
  if (typeof spec === 'number') return CONFIG.lead + CONFIG.voice * clamp(spec);
  return at(i, n);
}
// 0 → 1 over `d` seconds starting at time `t0`.
const rise = (t, t0, d = 0.45) => ease((t - t0) / d);

function txt(s, px, py, size, color = C.text, weight = 700, align = 'left', font = FONT) {
  x.font = weight + ' ' + size + 'px ' + font; x.fillStyle = color; x.textAlign = align; x.textBaseline = 'alphabetic'; x.fillText(s, px, py);
}
function fit(s, maxW, size, weight = 700) { x.font = weight + ' ' + size + 'px ' + FONT; while (size > 18 && x.measureText(s).width > maxW) { size -= 2; x.font = weight + ' ' + size + 'px ' + FONT; } return size; }
function glow(color, blur, fn) { x.save(); x.shadowColor = color; x.shadowBlur = blur; fn(); x.restore(); }
function rrect(px, py, w, h, r) { x.beginPath(); x.roundRect(px, py, w, h, r); }
function pill(s, px, py, color, alpha = 1, align = 'left') {
  if (alpha <= 0) return;
  x.globalAlpha = alpha; x.font = '700 40px ' + FONT; const w = x.measureText(s).width + 48, left = align === 'center' ? px - w / 2 : px;
  rrect(left, py - 50, w, 70, 20); x.fillStyle = T.surface; x.fill(); x.strokeStyle = color; x.lineWidth = 2; x.stroke();
  txt(s, left + 24, py - 4, 40, C.text); x.globalAlpha = 1;
}

// Background with the theme glow and a faint grid.
function backdrop(tint) {
  x.fillStyle = C.bg; x.fillRect(0, 0, W, H);
  const g = x.createRadialGradient(220, 380, 0, 220, 380, 900);
  g.addColorStop(0, tint || T.glow1); g.addColorStop(1, 'rgba(0,0,0,0)'); x.fillStyle = g; x.fillRect(0, 0, W, H);
  x.strokeStyle = T.grid; x.lineWidth = 1;
  for (let i = 0; i < W; i += 60) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i, H); x.stroke(); }
  for (let j = 0; j < H; j += 60) { x.beginPath(); x.moveTo(0, j); x.lineTo(W, j); x.stroke(); }
}

// The film pass: a slow push-in on whatever `draw` paints, then dust, vignette and grain.
const NOISE = (() => { const c = document.createElement('canvas'); c.width = c.height = 256; const g = c.getContext('2d');
  const d = g.createImageData(256, 256), r = rng(5);
  for (let i = 0; i < d.data.length; i += 4) { const v = r() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
  g.putImageData(d, 0, 0); return c; })();
// Maps design coordinates (1080-wide stage, content y 330..1290) onto this format's frame.
function stage() { x.translate(STAGE[0], STAGE[1]); x.scale(STAGE[2], STAGE[2]); x.translate(0, -330); }
function film(t, draw, tint) {
  backdrop(tint);
  const z = 1 + 0.045 * clamp(t / CONFIG.dur);
  x.save(); stage(); x.translate(540, 810); x.scale(z, z); x.translate(-540, -810); draw(); x.restore();
  const r = rng(21);
  for (let i = 0; i < 46; i++) {
    const px = (r() * W + t * (8 + r() * 14)) % W, py = (r() * H - t * (10 + r() * 20) + H) % H;
    x.fillStyle = (LIGHT ? 'rgba(0,0,0,' : 'rgba(255,255,255,') + (0.04 + r() * 0.1) + ')'; x.beginPath(); x.arc(px, py, 1 + r() * 2, 0, 7); x.fill();
  }
  const v = x.createRadialGradient(W / 2, H * 0.45, Math.min(W, H) * 0.4, W / 2, H * 0.45, Math.max(W, H) * 0.65);
  v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, LIGHT ? 'rgba(0,0,0,0.12)' : 'rgba(0,0,0,0.6)'); x.fillStyle = v; x.fillRect(0, 0, W, H);
  x.save(); x.globalAlpha = 0.045; x.globalCompositeOperation = 'overlay';
  const f = Math.floor(t * 30); x.translate(-((f * 97) % 256), -((f * 61) % 256));
  x.fillStyle = x.createPattern(NOISE, 'repeat'); x.fillRect(0, 0, W + 256, H + 256); x.restore();
}

// Lucide icons drawn as images, one per name and color; the renderer preloads every one used.
const IMG = new Map(); window.__loading = [];
function ic(name, cx, cy, size, color = C.text, alpha = 1) {
  if (!CONFIG.icons[name]) return;
  const key = name + color; let im = IMG.get(key);
  if (!im) {
    im = new Image(); window.__loading.push(new Promise((res) => { im.onload = res; im.onerror = res; }));
    im.src = 'data:image/svg+xml;utf8,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="192" height="192" viewBox="0 0 24 24" fill="none" stroke="'
      + color + '" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">' + CONFIG.icons[name] + '</svg>');
    IMG.set(key, im);
  }
  if (!im.complete || alpha <= 0) return;
  x.globalAlpha = alpha; x.drawImage(im, cx - size / 2, cy - size / 2, size, size); x.globalAlpha = 1;
}
// A glowing ring with an icon in it and an optional label underneath.
function node(cx, cy, icon, label, color, a, r = 62) {
  if (a <= 0) return;
  const s = 0.8 + 0.2 * a;
  x.save(); x.globalAlpha = a; x.translate(cx, cy); x.scale(s, s);
  glow(color, 30, () => { x.beginPath(); x.arc(0, 0, r, 0, 7); x.fillStyle = T.surface; x.fill(); x.lineWidth = 3; x.strokeStyle = color; x.stroke(); });
  x.restore();
  if (icon) ic(icon, cx, cy, r * 1.05, color, a);
  if (label) { x.globalAlpha = a; txt(label, cx, cy + r + 50, fit(label, 300, 34, 600), C.text, 600, 'center'); x.globalAlpha = 1; }
}
// A line between two points with packets travelling along it.
function wire(ax, ay, bx, by, color, a, t, speed = 0.5, width = 3) {
  if (a <= 0) return;
  x.globalAlpha = a * 0.5; x.strokeStyle = color; x.lineWidth = width; x.beginPath(); x.moveTo(ax, ay); x.lineTo(bx, by); x.stroke();
  x.globalAlpha = a;
  for (let k = 0; k < 2; k++) {
    const p = (t * speed + k / 2) % 1;
    glow(color, 14, () => { x.beginPath(); x.arc(ax + (bx - ax) * p, ay + (by - ay) * p, 6, 0, 7); x.fillStyle = color; x.fill(); });
  }
  x.globalAlpha = 1;
}
// A waveform; `live` 0..1 fades it from flat to moving.
function wave(cx, cy, w, h, t, live, color = C.accent) {
  const bars = 38, bw = w / bars;
  for (let i = 0; i < bars; i++) {
    const v = 0.15 + 0.85 * live * Math.abs(Math.sin(i * 0.7 + t * 7) * Math.sin(i * 0.23 + t * 3.1));
    const bh = Math.max(6, v * h); rrect(cx - w / 2 + i * bw + 2, cy - bh / 2, bw - 5, bh, 3); x.fillStyle = color; x.fill();
  }
}
// A rubber stamp slamming down: overshoots in scale, then settles.
function stamp(text, cx, cy, t0, t, color = C.red, rot = -0.18) {
  const k = clamp((t - t0) / 0.28); if (k <= 0) return;
  const s = 1 + 1.4 * Math.pow(1 - k, 3);
  x.save(); x.translate(cx, cy); x.rotate(rot); x.scale(s, s); x.globalAlpha = k;
  const size = fit(text, 760, 92, 800); x.font = '800 ' + size + 'px ' + FONT; const w = x.measureText(text).width + 70;
  rrect(-w / 2, -70, w, 130, 18); x.lineWidth = 9; x.strokeStyle = color; x.stroke();
  x.fillStyle = LIGHT ? 'rgba(255,255,255,0.6)' : 'rgba(0,0,0,0.25)'; x.fill(); x.fillStyle = color; x.textAlign = 'center'; x.fillText(text, 0, size * 0.32); x.restore();
}

// Photos (from CONFIG.photos), preloaded.
const PH = {};
for (const [k, u] of Object.entries(CONFIG.photos)) { const im = new Image(); window.__loading.push(new Promise((r) => { im.onload = r; im.onerror = r; })); im.src = u; PH[k] = im; }
// Draws a crop of a photo into a rect. `a` → `b` are [centre x, centre y, width] as fractions of the
// image, eased across the beat for a slow, directed push-in.
function photo(t, name, a, b, rect, radius = 28, alpha = 1) {
  const im = PH[name]; if (!im || !im.complete || !im.naturalWidth || alpha <= 0) return false;
  const [rx, ry, rw, rh] = rect, k = clamp(t / CONFIG.dur), e = ease(k) * 0.6 + k * 0.4;
  const [fx, fy, fw] = a.map((v, i) => v + (b[i] - v) * e);
  let cw = fw * im.naturalWidth, ch = cw * rh / rw;
  if (ch > im.naturalHeight) { ch = im.naturalHeight; cw = ch * rw / rh; }
  const sx = clamp(fx * im.naturalWidth - cw / 2, 0, im.naturalWidth - cw), sy = clamp(fy * im.naturalHeight - ch / 2, 0, im.naturalHeight - ch);
  x.globalAlpha = alpha;
  if (radius) glow(LIGHT ? 'rgba(0,0,0,0.25)' : 'rgba(0,0,0,0.8)', 50, () => { rrect(rx, ry, rw, rh, radius); x.fillStyle = '#000'; x.fill(); });
  x.save(); rrect(rx, ry, rw, rh, radius); x.clip(); x.drawImage(im, sx, sy, cw, ch, rx, ry, rw, rh); x.restore();
  if (radius) { rrect(rx, ry, rw, rh, radius); x.strokeStyle = T.line; x.lineWidth = 2; x.stroke(); }
  x.globalAlpha = 1; return true;
}

let FRAME_T = 0;
window.drawAt = (t) => { FRAME_T = t; SCENES[CONFIG.scene](t, CONFIG.params || {}); };

// Wraps text into lines no wider than maxW at the given size.
function wrap(s, maxW, size, weight = 600) {
  x.font = weight + ' ' + size + 'px ' + FONT;
  const out = []; let line = '';
  for (const w of String(s).split(/\s+/)) {
    const test = line ? line + ' ' + w : w;
    if (x.measureText(test).width > maxW && line) { out.push(line); line = w; } else line = test;
  }
  if (line) out.push(line);
  return out;
}
