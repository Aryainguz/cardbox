// The scene library. Each scene is (t, params) → draws one frame. Parameters are plain data from
// the reel spec; every element that appears takes an optional `on` (a spoken word, or a 0..1
// fraction of the line). Scenes leave the top ~300px for the beat's headline and keep content
// above y≈1290, where captions start.

// photo: an image in a framed card (or filling the top of the frame), pushing in slowly.
// params: image, from [x,y,w], to [x,y,w], full (bool), label {text, on, color}, stamp {text, on}
SCENES.photo = (t, p) => {
  const from = p.from || [0.5, 0.5, 1], to = p.to || [0.5, 0.45, 0.78];
  if (p.full) {
    // Full bleed (hook backgrounds): covers the format's picture area, not the stage.
    const [fx, fy, fw, fh] = FULL;
    x.fillStyle = C.bg; x.fillRect(0, 0, W, H);
    photo(t, p.image, from, to, [fx, fy, fw, fh], 0);
    if (!LIGHT) { x.save(); x.globalCompositeOperation = 'multiply'; x.fillStyle = 'rgb(190,205,215)'; x.fillRect(fx, fy, fw, fh); x.restore(); }
    if (fh < H) { const f = x.createLinearGradient(0, fh - 300, 0, fh); f.addColorStop(0, 'rgba(0,0,0,0)'); f.addColorStop(1, C.bg);
      x.fillStyle = f; x.fillRect(0, fh - 300, W, 300); }
    const cx = fx + fw / 2, cy = fy + fh * 0.5;
    if (p.stamp) { const s0 = when(p.stamp.on, 1, 2); stamp(p.stamp.text, cx, cy, s0, t, p.stamp.color || C.red); }
    if (p.label) pill(p.label.text, fx + 60, fy + fh - 80, p.label.color || C.accent, rise(t, when(p.label.on, 0.4, 1), 0.4));
    return;
  }
  film(t, () => {
    photo(t, p.image, from, to, [70, 380, 940, 860]);
    const sh = x.createLinearGradient(0, 380, 0, 1240); sh.addColorStop(0.55, 'rgba(0,0,0,0)'); sh.addColorStop(1, 'rgba(0,0,0,0.5)');
    x.save(); rrect(70, 380, 940, 860, 28); x.clip(); x.fillStyle = sh; x.fillRect(70, 380, 940, 860); x.restore();
    if (p.stamp) { const s0 = when(p.stamp.on, 1, 2);
      if (t > s0) { x.fillStyle = 'rgba(5,6,10,' + 0.35 * clamp((t - s0) / 0.3) + ')'; rrect(70, 380, 940, 860, 28); x.fill(); }
      stamp(p.stamp.text, 540, 790, s0, t, p.stamp.color || C.red); }
    if (p.label) pill(p.label.text, 110, 1190, p.label.color || C.accent, rise(t, when(p.label.on, 0.4, 1), 0.4));
  });
};

// donut: parts of a whole, swept in as they are said.
// params: segments [{label, value, color?, on?}], center {value, label}
SCENES.donut = (t, p) => film(t, () => {
  const segs = p.segments || [], total = segs.reduce((s, g) => s + g.value, 0) || 1, cx = 540, cy = 760, R = 270;
  const palette = [C.accent, C.accent2, C.green, C.amber, C.accent3];
  x.lineWidth = 90; x.strokeStyle = T.line; x.beginPath(); x.arc(cx, cy, R, 0, 7); x.stroke();
  let start = -Math.PI / 2;
  segs.forEach((g, i) => { const c = g.color || palette[i % palette.length], k = rise(t, when(g.on, i, segs.length), 0.7), sweep = (g.value / total) * Math.PI * 2;
    if (k > 0) glow(c, 24, () => { x.strokeStyle = c; x.lineWidth = 90; x.beginPath(); x.arc(cx, cy, R, start, start + sweep * k); x.stroke(); });
    start += sweep; });
  if (p.center) { txt(String(p.center.value), cx, cy + 20, fit(String(p.center.value), 400, 120, 800), C.text, 800, 'center');
    if (p.center.label) txt(p.center.label, cx, cy + 76, 34, C.mute, 600, 'center'); }
  segs.forEach((g, i) => { const a = rise(t, when(g.on, i, segs.length), 0.4); if (a <= 0) return; const y = 1130 + i * 56, c = g.color || palette[i % palette.length];
    x.globalAlpha = a; rrect(150, y - 26, 30, 30, 8); x.fillStyle = c; x.fill(); txt(g.label, 200, y, 36, C.text, 600);
    txt((g.display || (+g.value).toLocaleString('en-US')) + (p.unit || ''), 930, y, 36, c, 700, 'right'); x.globalAlpha = 1; });
});

// counter: a number running up (or down) to its value, optionally around a ring; `play` adds a
// waveform that starts when the count lands ("the song starts at 265 ms").
// params: to, from=0, decimals=0, prefix, unit, label, ring (bool), max (ring full scale), on, seconds=1.6, play, alarm
SCENES.counter = (t, p) => film(t, () => {
  const t0 = when(p.on, 0, 1), d = p.seconds || 1.6, k = clamp((t - t0) / d), e = ease(k);
  const from = p.from || 0, v = from + (p.to - from) * e, dec = p.decimals || 0;
  const s = (p.prefix || '') + v.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + (p.unit ? ' ' + p.unit : '');
  const done = k >= 1, hot = p.alarm && done ? C.red : C.accent, cy = 740;
  if (p.ring) {
    const max = p.max || p.to;
    x.lineWidth = 22; x.lineCap = 'round'; x.strokeStyle = T.line; x.beginPath(); x.arc(540, cy, 250, 0, 7); x.stroke();
    glow(hot, 30, () => { x.strokeStyle = hot; x.beginPath(); x.arc(540, cy, 250, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * clamp(v / max)); x.stroke(); });
  }
  const size = fit(s, p.ring ? 420 : 900, p.ring ? 120 : 170, 800);
  glow(done ? hot : 'rgba(0,0,0,0)', 30, () => txt(s, 540, cy + size * 0.3, size, done ? hot : C.text, 800, 'center'));
  if (p.label) txt(p.label, 540, cy + size * 0.3 + 64, 36, C.mute, 600, 'center');
  if (p.play) { const live = rise(t, t0 + d, 0.3); wave(540, 1150, 820, 120, t, live); if (live > 0) pill('▶ ' + (p.play === true ? 'playing' : p.play), 540, 1060, C.accent, live, 'center'); }
});

// bars: a comparison; the highlighted bar (default: the last) glows.
// params: bars [{label, value, note?, on?}], unit, highlight (index)
SCENES.bars = (t, p) => film(t, () => {
  const bars = p.bars || [], max = Math.max(...bars.map((b) => b.value), 1), hi = p.highlight ?? bars.length - 1;
  const top = 420, gap = Math.min(170, 820 / Math.max(bars.length, 1));
  bars.forEach((b, i) => {
    const a = rise(t, when(b.on, i, bars.length), 0.6), y = top + i * gap, c = i === hi ? C.accent : C.mute;
    if (a <= 0) return;
    x.globalAlpha = Math.min(1, a * 2); txt(b.label, 90, y, 38, C.text, 700);
    rrect(90, y + 22, 900, 48, 24); x.fillStyle = T.line; x.fill();
    glow(i === hi ? c : 'rgba(0,0,0,0)', 26, () => { rrect(90, y + 22, Math.max(48, 900 * (b.value / max) * a), 48, 24); x.fillStyle = c; x.fill(); });
    txt(b.note || (b.value.toLocaleString('en-US') + (p.unit || '')), 990, y, 36, i === hi ? C.accent : C.mute, 700, 'right'); x.globalAlpha = 1;
  });
});

// mesh: peers passing pieces of data to each other; an optional hub fades as peers take over.
// params: peers=13, hub (label), you (label), handoff (on), icon='laptop', hubIcon='server'
SCENES.mesh = (t, p) => film(t, () => {
  const r = rng(p.seed || 15), n = p.peers || 13, pts = [];
  for (let i = 0; i < n; i++) pts.push([140 + r() * 800, 560 + r() * 640]);
  pts[0] = [540, 880];
  const hub = [540, 430], hand = when(p.handoff, 1, 2), cols = [C.accent, C.accent2, C.amber, C.green];
  if (p.hub) wire(...hub, ...pts[0], C.blue, 1 - 0.85 * rise(t, hand, 0.8), t, 0.6, 3);
  pts.forEach((pt, i) => { if (!i) return; const j = i < 5 ? 0 : 1 + ((i * 7) % 4), [bx, by] = pts[j], a = rise(t, CONFIG.lead + i * 0.12, 0.4);
    x.globalAlpha = a * 0.35; x.strokeStyle = C.accent; x.lineWidth = 2; x.beginPath(); x.moveTo(...pt); x.lineTo(bx, by); x.stroke(); x.globalAlpha = 1;
    for (let q = 0; q < 2; q++) { const s = (t * 0.55 + q / 2 + i * 0.17) % 1, fwd = (i + q) % 2;
      const px = fwd ? pt[0] + (bx - pt[0]) * s : bx + (pt[0] - bx) * s, py = fwd ? pt[1] + (by - pt[1]) * s : by + (pt[1] - by) * s;
      x.globalAlpha = a; rrect(px - 9, py - 9, 18, 18, 4); x.fillStyle = cols[(i + q) % 4]; x.fill(); x.globalAlpha = 1; } });
  pts.forEach(([px, py], i) => node(px, py, p.icon || 'laptop', '', i ? C.accent : C.text, rise(t, CONFIG.lead + i * 0.08, 0.4), i ? 36 : 52));
  if (p.hub) { node(...hub, p.hubIcon || 'server', '', C.blue, 1, 46); txt(p.hub, hub[0] + 70, hub[1] + 12, 32, C.blue, 700); }
  if (p.you) pill(p.you, 600, 820, C.text, 1);
});

// terminal: commands typing out line by line in a dark window.
// params: title, lines [{text, on?, color?, output (bool)}]
SCENES.terminal = (t, p) => film(t, () => {
  const lines = p.lines || [], X0 = 90, Y0 = 400, Wd = 900, Hd = 820;
  glow('rgba(0,0,0,0.6)', 50, () => { rrect(X0, Y0, Wd, Hd, 26); x.fillStyle = '#0B0E14'; x.fill(); });
  rrect(X0, Y0, Wd, Hd, 26); x.strokeStyle = 'rgba(255,255,255,0.12)'; x.lineWidth = 2; x.stroke();
  ['#FF5F57', '#FEBC2E', '#28C840'].forEach((c, i) => { x.fillStyle = c; x.beginPath(); x.arc(X0 + 40 + i * 34, Y0 + 40, 10, 0, 7); x.fill(); });
  if (p.title) txt(p.title, X0 + Wd / 2, Y0 + 50, 28, '#9CA3AF', 600, 'center', 'Mono');
  let y = Y0 + 120;
  lines.forEach((l, i) => {
    const t0 = when(l.on, i, lines.length); if (t < t0) return;
    const speed = l.output ? 400 : 26, n = Math.floor((t - t0) * speed), s = (l.output ? '' : '$ ') + l.text, shown = s.slice(0, n);
    const typing = n < s.length && !l.output;
    txt(shown + (typing && Math.floor(t * 3) % 2 ? '▋' : ''), X0 + 40, y, fit(s, Wd - 80, 34, 400), l.color || (l.output ? '#9CA3AF' : '#4ADE80'), 400, 'left', 'Mono');
    y += 58;
  });
});

// flow: a vertical chain of steps (icon + label), with packets moving down the links.
// params: nodes [{icon, label, sub?, on?, color?}], bad (index from which links turn red)
SCENES.flow = (t, p) => film(t, () => {
  const nodes = p.nodes || [], n = nodes.length, top = 470, gap = Math.min(250, 760 / Math.max(n - 1, 1));
  nodes.forEach((d, i) => {
    const a = rise(t, when(d.on, i, n), 0.45), y = top + i * gap, c = d.color || (p.bad !== undefined && i >= p.bad ? C.red : C.accent);
    if (i > 0) wire(200, y - gap + 66, 200, y - 66, c, a, t + i * 0.3, 0.7, 3);
    node(200, y, d.icon || 'circle', '', c, a, 58);
    x.globalAlpha = a; txt(d.label, 300, y + (d.sub ? -2 : 14), fit(d.label, 680, 46), C.text, 700);
    if (d.sub) txt(d.sub, 300, y + 44, 30, C.mute, 600); x.globalAlpha = 1;
  });
});

// grid: a field of dots where `k` of `n` light up across the line (e.g. "1 in 10 people").
// params: n=100, k, cols=10, icon='user', result {text, on}
SCENES.grid = (t, p) => film(t, () => {
  const n = p.n || 100, k = p.k || 10, cols = p.cols || 10, rows = Math.ceil(n / cols), cell = Math.min(86, 900 / cols);
  const ox = 540 - (cols * cell) / 2 + cell / 2, oy = 440 + cell / 2, r = rng(9), lit = new Set();
  while (lit.size < Math.min(k, n)) lit.add(Math.floor(r() * n));
  const order = [...lit], prog = clamp((t - CONFIG.lead) / (CONFIG.voice * 0.8));
  for (let i = 0; i < n; i++) {
    const cx = ox + (i % cols) * cell, cy = oy + Math.floor(i / cols) * cell, idx = order.indexOf(i), on = idx >= 0 && idx / order.length < prog;
    ic(p.icon || 'user', cx, cy, cell * 0.7, on ? C.accent : C.mute, on ? 1 : 0.35);
  }
  if (p.result) pill(p.result.text, 540, oy + rows * cell + 70, C.accent, rise(t, when(p.result.on, 1, 1.2), 0.4), 'center');
});

// logo: an isometric box assembles itself (top drops in, sides slide in), a play mark pops on, then
// the name and tagline. params: name, tagline, on
SCENES.logo = (t, p) => film(t, () => {
  const t0 = when(p.on, 0, 1), cx = 540, cy = 720, s = 140;
  const P = (u, v, h) => [cx + (u - v) * 0.866 * s, cy + (u + v) * 0.5 * s - h * s];
  const face = (pts, color, dy, a) => { if (a <= 0) return; x.globalAlpha = a; x.beginPath();
    pts.forEach(([u, v, h], i) => { const [px, py] = P(u, v, h); i ? x.lineTo(px, py + dy) : x.moveTo(px, py + dy); });
    x.closePath(); x.fillStyle = color; x.fill(); x.globalAlpha = 1; };
  const a1 = rise(t, t0, 0.5), a2 = rise(t, t0 + 0.25, 0.5), a3 = rise(t, t0 + 0.45, 0.5);
  glow(C.accent, 60 * a3, () => {
    face([[-1, 1, 0], [1, 1, 0], [1, 1, 1.6], [-1, 1, 1.6]].map(([u, v, h]) => [u * 0.5 - 0.5, v * 0.5 + 0.5, h * 0.62]), C.accent, (1 - a2) * 120, a2);
    face([[-1, 1, 0], [1, 1, 0], [1, 1, 1.6], [-1, 1, 1.6]].map(([u, v, h]) => [u * 0.5 - 0.5, v * 0.5 + 0.5, h * 0.62]), 'rgba(0,0,0,0.42)', (1 - a2) * 120, a2);
    face([[1, -1, 0], [1, 1, 0], [1, 1, 1.6], [1, -1, 1.6]].map(([u, v, h]) => [u * 0.5 + 0.5, v * 0.5 - 0.5, h * 0.62]), C.accent, (1 - a2) * 120, a2);
    face([[1, -1, 0], [1, 1, 0], [1, 1, 1.6], [1, -1, 1.6]].map(([u, v, h]) => [u * 0.5 + 0.5, v * 0.5 - 0.5, h * 0.62]), 'rgba(0,0,0,0.22)', (1 - a2) * 120, a2);
    face([[-1, -1, 1.6], [1, -1, 1.6], [1, 1, 1.6], [-1, 1, 1.6]].map(([u, v, h]) => [u, v, h * 0.62]), C.accent, -(1 - a1) * 260, a1);
  });
  const pa = rise(t, t0 + 0.75, 0.35);
  if (pa > 0) { const [px, py] = P(1, 0.15, 0.45); x.save(); x.translate(px, py); x.scale(pa, pa);
    x.beginPath(); x.moveTo(-22, -34); x.lineTo(34, 0); x.lineTo(-22, 34); x.closePath(); x.fillStyle = C.bg; x.fill(); x.restore(); }
  const na = rise(t, t0 + 1.0, 0.5);
  if (na > 0) { x.globalAlpha = na; txt(p.name || 'cardbox', 540, 1060 + (1 - na) * 30, fit(p.name || 'cardbox', 900, 150, 800), C.text, 800, 'center');
    if (p.tagline) txt(p.tagline, 540, 1135, fit(p.tagline, 900, 44, 600), C.mute, 600, 'center'); x.globalAlpha = 1; }
});

// chat: a conversation with an AI assistant. params: title, messages [{from: user|ai, text, on}]
SCENES.chat = (t, p) => film(t, () => {
  const msgs = p.messages || [], X0 = 70, W0 = 940;
  rrect(X0, 380, W0, 860, 30); x.fillStyle = T.surface; x.fill(); x.strokeStyle = T.line; x.lineWidth = 2; x.stroke();
  txt(p.title || 'AI assistant', X0 + 36, 440, 30, C.mute, 600);
  x.fillStyle = T.line; x.fillRect(X0, 470, W0, 2);
  let y = 520;
  msgs.forEach((m, i) => {
    const t0 = when(m.on, i, msgs.length), user = m.from === 'user' || m.from === 'you';
    const named = !user && m.from && m.from !== 'ai', pal = [C.amber, C.blue, C.violet, C.green, C.red];
    const tint = named ? ((p.colors || {})[m.from] || pal[[...m.from].reduce((h, ch) => h + ch.charCodeAt(0), 0) % pal.length]) : null;
    if (t < t0 - (user ? 0 : 0.6)) return;
    const lines = wrap(m.text, named ? 580 : 640, 36), bh = lines.length * 48 + 36, bw = Math.max(...lines.map((l) => x.measureText(l).width)) + 56;
    const bx = user ? X0 + W0 - 36 - bw : X0 + 36 + (named ? 76 : 0), a = rise(t, t0, 0.3);
    if (named && t >= t0 - 0.6) {  // monogram avatar and name, in the person's color
      x.globalAlpha = t < t0 ? 0.6 : a; x.beginPath(); x.arc(X0 + 66, y + 30, 28, 0, 7); x.fillStyle = tint; x.fill();
      txt(m.from[0].toUpperCase(), X0 + 66, y + 42, 32, C.bg, 800, 'center'); x.globalAlpha = 1;
      if (t >= t0) { x.globalAlpha = a; txt(m.from, bx + 4, y - 10, 26, tint, 700); x.globalAlpha = 1; }
      if (t >= t0) y += 8;
    }
    if (!user && t < t0) {  // typing dots before the assistant answers
      rrect(bx, y, 140, 70, 26); x.fillStyle = LIGHT ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.07)'; x.fill();
      for (let d = 0; d < 3; d++) { x.globalAlpha = 0.35 + 0.65 * Math.abs(Math.sin(t * 5 + d)); x.beginPath(); x.arc(bx + 42 + d * 28, y + 35, 8, 0, 7); x.fillStyle = C.mute; x.fill(); }
      x.globalAlpha = 1; return;
    }
    x.globalAlpha = a; x.save(); x.translate(0, (1 - a) * 20);
    rrect(bx, y, bw, bh, 26); x.fillStyle = user ? C.accent : (LIGHT ? 'rgba(0,0,0,0.05)' : 'rgba(255,255,255,0.07)'); x.fill();
    lines.forEach((l, j) => txt(l, bx + 28, y + 56 + j * 48, 36, user ? C.bg : C.text, 600));
    x.restore(); x.globalAlpha = 1;
    y += bh + 26;
  });
});

// script: a plain-text script whose paragraphs light up one by one, each becoming a video frame.
// params: title, paragraphs [text...], on
SCENES.script = (t, p) => film(t, () => {
  const paras = p.paragraphs || [], n = paras.length;
  rrect(60, 390, 560, 840, 26); x.fillStyle = T.surface; x.fill(); x.strokeStyle = T.line; x.lineWidth = 2; x.stroke();
  txt(p.title || 'script.txt', 92, 446, 28, C.mute, 600, 'left', 'Mono');
  let y = 510;
  paras.forEach((para, i) => {
    const t0 = when(Array.isArray(p.on) ? p.on[i] : undefined, i, n), on = t > t0, lines = wrap(para, 480, 28, 400);
    if (on) { rrect(78, y - 36, 524, lines.length * 40 + 24, 12); x.fillStyle = LIGHT ? 'rgba(0,0,0,0.04)' : 'rgba(255,255,255,0.05)'; x.fill(); }
    lines.forEach((l, j) => txt(l, 96, y + j * 40, 28, on ? C.text : C.mute, 400, 'left', 'Mono'));
    // the frame this paragraph becomes
    const a = rise(t, t0 + 0.15, 0.5), fy = 400 + i * (800 / Math.max(n, 1)), fh = Math.min(240, 760 / Math.max(n, 1)) - 20, fw = fh * 0.5625 * 1.9;
    if (a > 0) {
      const fx = 690 + (1 - a) * -120;
      x.globalAlpha = a;
      glow(C.accent, 26 * a, () => { rrect(fx, fy, fw, fh, 16); x.fillStyle = C.bg; x.fill(); x.strokeStyle = C.accent; x.lineWidth = 3; x.stroke(); });
      const head = para.split(/[.?!]/)[0].split(' ').slice(0, 4).join(' ');
      wrap(head, fw - 40, 30, 800).slice(0, 2).forEach((l, j) => txt(l, fx + 20, fy + 52 + j * 36, 30, C.text, 800));
      rrect(fx + 20, fy + fh - 40, fw - 40, 10, 5); x.fillStyle = C.accent; x.fill();
      x.globalAlpha = 1;
      x.strokeStyle = C.accent; x.globalAlpha = a * 0.5; x.lineWidth = 2; x.setLineDash([8, 8]);
      x.beginPath(); x.moveTo(610, y - 8); x.lineTo(fx, fy + fh / 2); x.stroke(); x.setLineDash([]); x.globalAlpha = 1;
    }
    y += lines.length * 40 + 44;
  });
});

// voice: a waveform with the transcript appearing word by word; one misheard word is caught, struck
// out, re-recorded and corrected. params: text, wrong {index, heard}, on
SCENES.voice = (t, p) => film(t, () => {
  const words = String(p.text || '').split(/\s+/), t0 = when(p.on, 0, 1), span = CONFIG.voice * 0.45;
  const wr = p.wrong || {}, fixAt = t0 + span + 0.6, fixed = t > fixAt + 0.5;
  const live = t > t0 && t < t0 + span ? 1 : (t > fixAt && t < fixAt + 0.5 ? 1 : 0.15);
  wave(540, 560, 900, 220, t, live);
  rrect(70, 760, 940, 340, 26); x.fillStyle = T.surface; x.fill(); x.strokeStyle = T.line; x.lineWidth = 2; x.stroke();
  txt('heard', 104, 816, 28, C.mute, 600);
  let px = 104, py = 890;
  words.forEach((w, i) => {
    const at = t0 + span * (i / words.length); if (t < at) return;
    const bad = i === wr.index, shown = bad && !fixed ? (wr.heard || w) : w, size = 50;
    x.font = '700 ' + size + 'px ' + FONT; const ww = x.measureText(shown).width;
    if (px + ww > 980) { px = 104; py += 70; }
    const color = bad ? (fixed ? C.green : C.red) : C.text;
    txt(shown, px, py, size, color, 700);
    if (bad && !fixed && t > t0 + span + 0.2) { x.strokeStyle = C.red; x.lineWidth = 5; x.beginPath(); x.moveTo(px - 4, py - 16); x.lineTo(px + ww + 4, py - 16); x.stroke(); }
    px += ww + 18;
  });
  if (t > t0 + span + 0.2 && !fixed) pill('↻ re-recording that line', 104, 1190, C.amber, rise(t, t0 + span + 0.2, 0.3));
  if (fixed) pill('✓ 100% match', 104, 1190, C.green, rise(t, fixAt + 0.5, 0.3));
});

// formats: one frame morphing between 9:16, 16:9 and 1:1. params: labels [3 strings], on [3 cues]
SCENES.formats = (t, p) => film(t, () => {
  const shapes = [[9, 16], [16, 9], [1, 1]], labels = p.labels || ['Reels · Shorts · TikTok', 'YouTube', 'LinkedIn'];
  const cues = shapes.map((_, i) => when(Array.isArray(p.on) ? p.on[i] : undefined, i, 3));
  let k = 0; cues.forEach((c, i) => { if (t >= c) k = i; });
  const prev = shapes[Math.max(0, k - 1)], cur = shapes[k], e = rise(t, cues[k], 0.6), box = 470;
  const ar = (prev[0] / prev[1]) + ((cur[0] / cur[1]) - (prev[0] / prev[1])) * (k === 0 ? 1 : e);
  const fw = ar >= 1 ? box * 1.45 : box * ar * 1.25, fh = ar >= 1 ? box * 1.45 / ar : box * 1.25, fx = 540 - fw / 2, fy = 700 - fh / 2;
  glow(C.accent, 40, () => { rrect(fx, fy, fw, fh, 28); x.fillStyle = C.bg; x.fill(); x.strokeStyle = C.accent; x.lineWidth = 5; x.stroke(); });
  const land = ar > 1.2;
  rrect(fx + 36, fy + 40, Math.min(fw * 0.5, 300), 30, 10); x.fillStyle = C.mute; x.globalAlpha = 0.5; x.fill(); x.globalAlpha = 1;
  rrect(fx + 36, fy + 90, Math.min(fw * (land ? 0.42 : 0.8), 460), 54, 12); x.fillStyle = C.text; x.fill();
  const cx = land ? fx + fw * 0.72 : fx + fw / 2, cy = land ? fy + fh / 2 + 10 : fy + fh * 0.62, r = Math.min(fw, fh) * 0.2;
  x.lineWidth = r * 0.35; x.strokeStyle = T.line; x.beginPath(); x.arc(cx, cy, r, 0, 7); x.stroke();
  glow(C.accent, 20, () => { x.strokeStyle = C.accent; x.beginPath(); x.arc(cx, cy, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * (0.3 + 0.6 * ((t * 0.2) % 1))); x.stroke(); });
  const ratio = cur[0] + ':' + cur[1];
  txt(ratio, 540, Math.min(fy + fh + 80, 1190), 60, C.accent, 800, 'center');
  txt(labels[k], 540, Math.min(fy + fh + 135, 1250), 38, C.text, 700, 'center');
});

// alert: an incident. The screen pulses red, a push notification slides down, and a latency chart
// spikes (with a glitch) when the spike is cued. Sized to read in the top half too (hook backgrounds).
// params: app, channel, title, body, metric {label, from, to, unit}, on
SCENES.alert = (t, p) => film(t, () => {
  const t0 = when(p.on, 0, 1), spike = t0 + 0.9, m = p.metric || { label: 'p95 latency', from: 80, to: 2400, unit: 'ms' };
  const pulse = 0.5 + 0.5 * Math.sin(t * 5);
  const g = x.createRadialGradient(540, 420, 40, 540, 420, 900);
  g.addColorStop(0, 'rgba(255,72,72,' + (0.10 + 0.10 * pulse * rise(t, spike, 0.3)) + ')'); g.addColorStop(1, 'rgba(255,72,72,0)');
  x.fillStyle = g; x.fillRect(-200, 0, 1480, 1400);
  // the notification
  const ny = 215 + (1 - rise(t, t0, 0.55)) * -340;  // below the handle line
  glow('rgba(0,0,0,0.6)', 40, () => { rrect(70, ny, 940, 180, 36); x.fillStyle = 'rgba(28,28,34,0.94)'; x.fill(); });
  rrect(70, ny, 940, 180, 36); x.strokeStyle = 'rgba(255,255,255,0.10)'; x.lineWidth = 2; x.stroke();
  rrect(104, ny + 34, 64, 64, 16); x.fillStyle = C.red; x.fill(); ic('bell-ring', 136, ny + 66, 38, '#fff');
  txt((p.app || 'Orbit').toUpperCase() + '  ·  ' + (p.channel || '#alerts'), 192, ny + 60, 26, C.mute, 600);
  txt('now', 976, ny + 60, 26, C.mute, 600, 'right');
  txt(p.title || 'Prod is down', 192, ny + 108, fit(p.title || 'Prod is down', 780, 40), C.text, 700);
  txt(p.body || 'p95 latency is climbing. Can you take a look?', 192, ny + 150, fit(p.body || '', 780, 30, 500), C.mute, 500);
  // the chart
  const cx0 = 70, cy0 = 430, cw = 940, ch = 340, a = rise(t, t0 + 0.3, 0.5);
  if (a > 0) {
    x.globalAlpha = a;
    rrect(cx0, cy0, cw, ch, 30); x.fillStyle = 'rgba(20,20,24,0.9)'; x.fill(); x.strokeStyle = T.line; x.lineWidth = 2; x.stroke();
    txt(m.label, cx0 + 34, cy0 + 56, 30, C.mute, 600);
    const k = clamp((t - spike) / 1.2), e = ease(k), val = Math.round(m.from + (m.to - m.from) * e);
    const hot = k > 0.05, col = hot ? C.red : C.green;
    glow(hot ? C.red : 'rgba(0,0,0,0)', 26, () => txt(val.toLocaleString('en-US') + ' ' + (m.unit || ''), cx0 + cw - 34, cy0 + 70, 64, hot ? C.red : C.text, 800, 'right'));
    x.beginPath();
    const pts = 70, sx = cx0 + 34, sw = cw - 68, base = cy0 + ch - 60;
    for (let i = 0; i <= pts; i++) {
      const u = i / pts, noise = Math.sin(i * 1.7 + t * 3) * 6 + Math.sin(i * 0.43) * 4;
      const rise_ = u > 0.62 ? Math.pow((u - 0.62) / 0.38, 2) * (ch - 150) * e : 0;
      const px = sx + u * sw, py = base - 30 - noise - rise_;
      i ? x.lineTo(px, py) : x.moveTo(px, py);
    }
    glow(col, 22, () => { x.strokeStyle = col; x.lineWidth = 6; x.lineJoin = 'round'; x.stroke(); });
    if (hot && Math.floor(t * 3) % 2 === 0) pill('INCIDENT', cx0 + 34, cy0 + 150, C.red, 1);
    x.globalAlpha = 1;
    // glitch: a few displaced bands of the frame for a moment after the spike
    const gk = 1 - Math.abs(t - spike - 0.15) / 0.25;
    if (gk > 0) { const r = rng(Math.floor(t * 30)); for (let i = 0; i < 7; i++) { const by = 100 + r() * 700, bh = 8 + r() * 40;
      x.drawImage(cv, 0, by, cv.width, bh, (r() - 0.5) * 90 * gk, by, cv.width, bh); } }
  }
});

// cards: a challenge-card stack. Each card shows a tag, a question and code; a 30-second timer runs,
// the answer line is tapped, the border sweeps green with a check, and the card flies off for the next.
// params: cards [{tag, question, code: [lines], answer (line index), note, on}], seconds
SCENES.cards = (t, p) => film(t, () => {
  const cards = p.cards || [], n = cards.length, X0 = 90, Y0 = 400, Wc = 900, Hc = 780;
  const starts = cards.map((c, i) => when(c.on, i, n));
  let k = 0; starts.forEach((s, i) => { if (t >= s) k = i; });
  for (let g = 2; g >= 1; g--) { rrect(X0 + g * 18, Y0 - g * 22, Wc - g * 36, Hc, 34); x.fillStyle = 'rgba(28,28,34,' + (0.55 - g * 0.15) + ')'; x.fill(); }
  const draw = (c, i, fly) => {
    const s = starts[i], next = i + 1 < n ? starts[i + 1] : 1e9, span = Math.min(next, CONFIG.dur) - s;
    const tap = s + span * 0.55, ok = rise(t, tap + 0.15, 0.45);
    x.save();
    if (fly > 0) { x.translate(540 - 900 * fly, 790 + 120 * fly); x.rotate(-0.35 * fly); x.translate(-540, -790); x.globalAlpha = 1 - fly; }
    else { const inA = rise(t, s, 0.35); x.globalAlpha = inA; x.translate(0, (1 - inA) * 40); }
    glow('rgba(0,0,0,0.6)', 40, () => { rrect(X0, Y0, Wc, Hc, 34); x.fillStyle = '#141418'; x.fill(); });
    rrect(X0, Y0, Wc, Hc, 34); x.strokeStyle = T.line; x.lineWidth = 2; x.stroke();
    if (ok > 0) glow(C.green, 30, () => { x.save(); rrect(X0, Y0, Wc, Hc, 34); x.lineWidth = 5; x.strokeStyle = C.green;
      x.setLineDash([3200 * ok, 4000]); x.stroke(); x.restore(); });
    pill(c.tag || 'FIND THE BUG', X0 + 34, Y0 + 82, C.blue, 1);
    // timer ring
    const total = p.seconds || 30, left = clamp(total - Math.floor(Math.max(0, t - s) * 4), 0, total), tr = 38, tcx = X0 + Wc - 70, tcy = Y0 + 62;
    x.lineWidth = 7; x.strokeStyle = T.line; x.beginPath(); x.arc(tcx, tcy, tr, 0, 7); x.stroke();
    x.strokeStyle = ok > 0 ? C.green : C.amber; x.beginPath(); x.arc(tcx, tcy, tr, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * left / total); x.stroke();
    txt(String(left), tcx, tcy + 11, 30, C.text, 700, 'center');
    let y = Y0 + 160;
    wrap(c.question, Wc - 80, 38, 600).slice(0, 3).forEach((ln) => { txt(ln, X0 + 40, y, 38, C.text, 600); y += 50; });
    y += 20;
    (c.code || []).forEach((ln, j) => {
      const bad = j === c.answer, tapped = t > tap;
      if (bad && tapped) { rrect(X0 + 24, y - 40, Wc - 48, 58, 12); x.fillStyle = ok > 0 ? 'rgba(52,211,153,0.16)' : 'rgba(255,92,92,0.18)'; x.fill(); }
      txt(String(j + 1), X0 + 50, y, 26, C.mute, 400, 'right', 'Mono');
      txt(ln, X0 + 76, y, fit(ln, Wc - 140, 30, 400), '#E4E4E9', 400, 'left', 'Mono');
      if (bad && Math.abs(t - tap) < 0.35) { const r = 20 + 60 * clamp((t - tap) / 0.35); x.strokeStyle = 'rgba(255,225,77,' + (1 - clamp((t - tap) / 0.35)) + ')';
        x.lineWidth = 5; x.beginPath(); x.arc(X0 + 300, y - 10, r, 0, 7); x.stroke(); }
      y += 62;
    });
    if (ok > 0) {
      const cy = Y0 + Hc - 90;
      glow(C.green, 20, () => { x.beginPath(); x.arc(X0 + 70, cy, 32, 0, 7); x.fillStyle = C.green; x.fill(); });
      x.strokeStyle = '#0A0A0C'; x.lineWidth = 7; x.lineCap = 'round'; x.beginPath();
      const d = clamp(ok * 1.6); x.moveTo(X0 + 55, cy); x.lineTo(X0 + 55 + 10 * Math.min(1, d * 2), cy + 10 * Math.min(1, d * 2));
      if (d > 0.5) x.lineTo(X0 + 65 + 20 * (d - 0.5) * 2, cy + 10 - 22 * (d - 0.5) * 2); x.stroke();
      x.globalAlpha *= ok; txt(c.note || 'Correct.', X0 + 120, cy + 12, fit(c.note || 'Correct.', Wc - 170, 32, 600), C.text, 600);
    }
    x.restore();
  };
  if (k > 0) { const fly = rise(t, starts[k], 0.4); if (fly < 1) draw(cards[k - 1], k - 1, fly); }
  if (n) draw(cards[k], k, 0);
});

// rings: activity rings closing one after another, then a row of streak days lighting up.
// params: rings [{label, value (0..1), color}], days, streak (label), on
SCENES.rings = (t, p) => film(t, () => {
  const rings = p.rings || [{ label: 'Solve', value: 1, color: C.blue }, { label: 'Design', value: 1, color: C.violet }, { label: 'Recall', value: 1, color: C.green }];
  const t0 = when(p.on, 0, 1), cx = 540, cy = 690, radii = [260, 196, 132];
  let all = true;
  rings.forEach((r, i) => {
    const k = rise(t, t0 + i * 0.45, 1.0) * (r.value ?? 1), col = r.color || [C.blue, C.violet, C.green][i % 3];
    if (k < 0.999) all = false;
    x.lineCap = 'round'; x.lineWidth = 50; x.strokeStyle = T.line; x.beginPath(); x.arc(cx, cy, radii[i], 0, 7); x.stroke();
    glow(col, 26, () => { x.strokeStyle = col; x.beginPath(); x.arc(cx, cy, radii[i], -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0.001, k)); x.stroke(); });
    const ly = 1030 + i * 52;
    rrect(250, ly - 26, 30, 30, 9); x.fillStyle = col; x.fill(); txt(r.label, 300, ly, 36, C.text, 600);
    txt(Math.round(k * 100) + '%', 830, ly, 36, col, 700, 'right');
  });
  if (all) { const a = rise(t, t0 + rings.length * 0.45 + 1, 0.4); pill(p.closed || 'Rings closed', cx, cy + 22, C.green, a, 'center'); }
  const days = p.days || 7, dt0 = t0 + 0.6;
  for (let d = 0; d < days; d++) {
    const on = rise(t, dt0 + d * 0.18, 0.25), dx = 540 + (d - (days - 1) / 2) * 92;
    glow(on > 0.5 ? C.amber : 'rgba(0,0,0,0)', 18, () => { x.beginPath(); x.arc(dx, 1240, 26, 0, 7); x.fillStyle = on > 0.5 ? C.amber : T.line; x.fill(); });
  }
  if (p.streak) txt(p.streak, 540, 1300, 30, C.amber, 700, 'center');
});

// appreveal: an app icon pops in with a light sweep, then the name, a tagline and a badge.
// params: image (the icon), name, tagline, badge, on
SCENES.appreveal = (t, p) => film(t, () => {
  const t0 = when(p.on, 0, 1), k = clamp((t - t0) / 0.6), s = k <= 0 ? 0 : 1 + 0.18 * Math.sin(k * Math.PI) * (1 - k) + (ease(k) - 1) * 0.6 + 0.6 * ease(k) - 0.6 + 0.0;
  const size = 320, cx = 540, cy = 620, scale = Math.max(0, ease(k) * (1 + 0.12 * Math.sin(Math.min(1, k) * Math.PI)));
  // rays and sparks
  const r = rng(3), ra = rise(t, t0 + 0.2, 0.6);
  for (let i = 0; i < 26; i++) { const ang = r() * Math.PI * 2, d = 220 + r() * 260 * ra, sz = 2 + r() * 5;
    x.globalAlpha = ra * (0.25 + 0.6 * r()) * (0.6 + 0.4 * Math.sin(t * 3 + i)); x.fillStyle = i % 3 ? C.accent : '#fff';
    x.beginPath(); x.arc(cx + Math.cos(ang) * d, cy + Math.sin(ang) * d, sz, 0, 7); x.fill(); }
  x.globalAlpha = 1;
  if (scale > 0) {
    x.save(); x.translate(cx, cy); x.scale(scale, scale);
    glow(C.accent, 80, () => { rrect(-size / 2, -size / 2, size, size, 72); x.fillStyle = '#000'; x.fill(); });
    x.save(); rrect(-size / 2, -size / 2, size, size, 72); x.clip();
    const im = PH[p.image]; if (im && im.complete) x.drawImage(im, -size / 2, -size / 2, size, size);
    const sweep = clamp((t - t0 - 0.5) / 0.8);
    if (sweep > 0 && sweep < 1) { const sx = -size + sweep * size * 2.2; const g = x.createLinearGradient(sx, -size / 2, sx + 120, size / 2);
      g.addColorStop(0, 'rgba(255,255,255,0)'); g.addColorStop(0.5, 'rgba(255,255,255,0.45)'); g.addColorStop(1, 'rgba(255,255,255,0)');
      x.fillStyle = g; x.fillRect(-size / 2, -size / 2, size, size); }
    x.restore(); x.restore();
  }
  const na = rise(t, t0 + 0.55, 0.45);
  if (na > 0) { x.globalAlpha = na; txt(p.name || 'App', cx, 920 + (1 - na) * 30, fit(p.name || 'App', 900, 140, 800), C.text, 800, 'center');
    if (p.tagline) txt(p.tagline, cx, 990, fit(p.tagline, 880, 40, 600), C.mute, 600, 'center'); x.globalAlpha = 1; }
  const ba = rise(t, t0 + 0.9, 0.45);
  if (ba > 0 && p.badge) {
    x.globalAlpha = ba; x.font = '700 40px ' + FONT; const bw = x.measureText(p.badge).width + 130, bx = cx - bw / 2, by = 1060;
    glow(C.accent, 30, () => { rrect(bx, by, bw, 92, 46); x.fillStyle = C.accent; x.fill(); });
    x.beginPath(); x.moveTo(bx + 52, by + 28); x.lineTo(bx + 52, by + 64); x.lineTo(bx + 82, by + 46); x.closePath(); x.fillStyle = C.bg; x.fill();
    txt(p.badge, bx + 100, by + 60, 40, C.bg, 700); x.globalAlpha = 1;
  }
});
