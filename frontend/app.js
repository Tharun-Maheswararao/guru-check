// Guru Check frontend: Library, NPC Room, Simulate. Plain JS, no build step.
const $ = (s, el = document) => el.querySelector(s);
const view = $('#view');
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
};
const post = (path, body) => api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
const money = v => v == null ? 'N/A' : '$' + Math.round(v).toLocaleString();
const pct = v => v == null ? 'N/A' : (v > 0 ? '+' : '') + v + '%';
const ts = s => `${Math.floor((s || 0) / 60)}:${String(Math.floor((s || 0) % 60)).padStart(2, '0')}`;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const vClass = v => ({ 'Real Edge': 'v-real', 'Lucky': 'v-lucky', 'Just the Market': 'v-market', 'Untestable': 'v-untestable' }[v] || 'v-untestable');
let current = null; // last opened npc_id

// ---------- pixel sprite ----------
const MAP = ['....KKKKKKKK....', '...KHHHHHHHHK...', '..KHHHHHHHHHHK..', '..KHSSSSSSSSHK..', '..KSSSSSSSSSSK..', '..KSGGGGSGGGGK..', '..KSGGGGSGGGGK..', '..KSSSSSSSSSSK..', '..KSSSKKKKSSSK..', '...KSSSSSSSSK...', '....KKSSSSKK....', '..KKCCWTTWCCKK..', '.KCCCCWTTWCCCCK.', '.KCCCCWTTWCCCCK.', '.KCCCCCWWCCCCCK.', '.KKKKKKKKKKKKKK.'];
const BASE = { K: '#0B0913', S: '#F2C29B', G: '#12101C', W: '#F4F1EA', T: '#FF5470' };
const SETS = {
  gold: { ...BASE, H: '#3A2A1A', C: '#FFC93C' }, green: { ...BASE, H: '#151515', C: '#3DDC84', T: '#12101C' },
  red: { ...BASE, H: '#B5562B', C: '#FF5470', T: '#FFC93C' }, cyan: { ...BASE, H: '#2B2B44', C: '#7FD8FF', S: '#C98E6B' },
  violet: { ...BASE, H: '#F4F1EA', C: '#B18CFF', T: '#3DDC84' },
};
function sprite(color = 'gold', px = 6) {
  const c = SETS[color] || SETS.gold; let r = '';
  MAP.forEach((row, y) => {
    for (let x = 0; x < 16;) {
      const ch = row[x]; if (ch === '.') { x++; continue; }
      let e = x; while (e < 16 && row[e] === ch) e++;
      r += `<rect x="${x * px}" y="${y * px}" width="${(e - x) * px}" height="${px}" fill="${c[ch]}"/>`; x = e;
    }
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${16 * px}" height="${16 * px}" viewBox="0 0 ${16 * px} ${16 * px}" shape-rendering="crispEdges">${r}</svg>`;
}

// ---------- 8-bit sounds ----------
let actx = null, muted = false;
function blip(notes, type = 'square', len = 0.08) {
  if (muted) return;
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    notes.forEach((f, k) => {
      const o = actx.createOscillator(), g = actx.createGain(), t0 = actx.currentTime + k * len;
      o.type = type; o.frequency.value = f; g.gain.setValueAtTime(0.06, t0); g.gain.exponentialRampToValueAtTime(0.001, t0 + len * 0.95);
      o.connect(g).connect(actx.destination); o.start(t0); o.stop(t0 + len);
    });
  } catch (e) { /* audio blocked */ }
}
const SFX = {
  buy: () => blip([880, 1320]), sell: () => blip([440, 330]), pain: () => blip([392, 330, 262, 196], 'sawtooth', 0.14),
  born: () => blip([523, 659, 784, 1047], 'square', 0.1), click: () => blip([660], 'square', 0.04), win: () => blip([784, 988, 1175, 1568], 'triangle', 0.12),
};
document.addEventListener('click', e => { if (e.target.closest('.btn,.card,.chip')) SFX.click(); });

// portrait from Gemini image generation if the record has one, else the pixel sprite
function face(n, px) {
  return n.portrait_path ? `<img class="portrait" src="/api/npcs/${n.npc_id}/portrait" width="${16 * px}" height="${16 * px}" alt="${esc(n.name)}" onerror="this.outerHTML=sprite('${n.color}',${px})">` : sprite(n.color, px);
}

// ---------- routing ----------
function setNav(which) {
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('on', a.dataset.nav === which));
  $('#nav-room').classList.toggle('off', !current); $('#nav-sim').classList.toggle('off', !current);
  if (current) { $('#nav-room').href = `#/npc/${current}`; $('#nav-sim').href = `#/sim/${current}`; }
}
async function route() {
  stopSim(); window.speechSynthesis?.cancel();
  const [, page, id] = location.hash.split('/');
  try {
    if (page === 'npc' && id) { current = id; setNav('room'); await renderRoom(id); }
    else if (page === 'sim' && id) { current = id; setNav('sim'); await renderSim(id); }
    else { setNav('library'); await renderLibrary(); }
  } catch (e) { view.innerHTML = `<div class="start"><h1>GAME OVER</h1><p>${esc(e.message)}</p><a class="btn" href="#/">BACK</a></div>`; }
  window.scrollTo(0, 0);
}
window.addEventListener('hashchange', route);

// ---------- library ----------
async function renderLibrary() {
  const npcs = await api('/api/npcs');
  view.innerHTML = `
  <section class="start">
    <h1>WOULD YOU HAVE<br>GOT RICH?</h1>
    <p>Paste a trading video. Its strategy is born as a trader you can question and race.</p>
    <form class="paste" id="paste"><input id="url" placeholder="youtube.com/watch?v=…" autocomplete="off" /><button class="btn">PRESS START</button></form>
  </section>
  <div class="roster-h"><span class="px">CHOOSE A TRADER</span><span class="label">${npcs.length} STRATEGIES TESTED</span></div>
  <div class="roster">${npcs.map(n => `
    <a class="card" href="#/npc/${n.npc_id}">
      <div class="stage">${face(n, 6)}</div>
      <div class="nm">${esc(n.name).toUpperCase()}</div>
      <div class="ar">${esc(n.archetype || '')}</div>
      <span class="tag ${vClass(n.verdict)}">${esc(n.verdict || '').toUpperCase()}</span>
      <div class="ret" style="color:${n.return_pct == null ? 'var(--muted)' : n.return_pct >= 0 ? 'var(--green)' : 'var(--red)'}">${pct(n.return_pct)}</div>
      <div class="vid">from “${esc(n.video_title || '')}”</div>
      ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}
    </a>`).join('') || '<p class="empty">No NPCs yet. Paste a video to birth the first one.</p>'}
  </div>`;
  $('#paste').onsubmit = e => { e.preventDefault(); const u = $('#url').value.trim(); if (u) birth(u); };
}

const BIRTH_STEPS = [['watch', 'Watch the video'], ['scan', 'Scan for rules'], ['extract', 'Write the exact rules'], ['match', 'Check the library'],
  ['backtest', 'Backtest on full history'], ['randoms', 'Race 1,000 random traders'], ['judge', 'Judge the claims'], ['born', 'NPC is born']];
async function birth(url) {
  const ov = $('#birth'), steps = $('#birth-steps'), err = $('#birth-error');
  ov.classList.remove('hidden'); steps.innerHTML = ''; err.textContent = '';
  $('#birth-sprite').innerHTML = sprite(['gold', 'green', 'red', 'cyan', 'violet'][Math.floor(Math.random() * 5)], 8);
  $('#birth-close').onclick = () => ov.classList.add('hidden');
  try {
    const r = await post('/api/birth', { url });
    if (r.status === 'exists') { steps.innerHTML = '<li>This video is already in the library. Opening its NPC.</li>'; setTimeout(() => { ov.classList.add('hidden'); location.hash = `#/npc/${r.npc_id}`; }, 900); return; }
    const poll = async () => {
      const j = await api(`/api/birth/${r.job_id}`);
      const seen = Object.fromEntries(j.steps.map(s => [s.step, s.detail]));
      const lastStep = j.steps.length ? j.steps[j.steps.length - 1].step : null;
      steps.innerHTML = BIRTH_STEPS.map(([k, label]) => {
        const st = !seen[k] ? 'todo' : (k === lastStep && j.status === 'running') ? 'now' : (k === lastStep && j.status === 'error') ? 'fail' : 'done';
        return `<li class="${st}">${esc(seen[k] || label)}</li>`;
      }).join('');
      if (j.status === 'done') { SFX.born(); $('#birth-sprite').classList.add('born'); setTimeout(() => { ov.classList.add('hidden'); location.hash = `#/npc/${j.npc_id}`; }, 1200); }
      else if (j.status === 'error') err.textContent = j.error;
      else setTimeout(poll, 1000);
    };
    poll();
  } catch (e) { err.textContent = e.message; }
}

// ---------- NPC room ----------
let history = [];
async function renderRoom(id) {
  const n = await api(`/api/npcs/${id}`);
  const trades = n.results ? await api(`/api/npcs/${id}/trades`).catch(() => null) : null;
  const r = n.results || {};
  const video = (n.source_videos || [])[0] || {};
  const dur = video.duration_s || Math.max(60, ...(n.rules_timeline || []).map(x => x.timestamp_s + 30));
  history = [];
  const opener = n.results
    ? `I turned $10,000 into ${money(r.final_balance)}. But ${r.share_random_better}% of random traders did better than me.`
    : `Hi, I'm ${n.name}. Fair warning: nobody can test my strategy.`;
  view.innerHTML = `
  <section class="room">
    <div class="left">
      <div class="scene panel">
        <div class="window"></div>
        <div class="monitor">${monitorSvg(trades)}</div>
        <div class="desk"></div>
        <div class="npc" id="npc">${face(n, 12)}</div>
        <div class="bubble"><div class="who">${esc(n.name).toUpperCase()} SAYS</div><div id="say">${esc(opener)}</div>
          <div class="cite" id="cite"></div></div>
        <div class="plate"><span class="nm">${esc(n.name).toUpperCase()}</span><span class="ar">${esc(n.archetype || '')}</span>
          <span class="tag ${vClass(n.verdict)}" style="transform:rotate(-4deg)">${esc(n.verdict).toUpperCase()}</span>
          ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}</div>
      </div>
      ${n.results ? `
      <div class="stats">
        <div class="stat panel"><div class="label">BALANCE FROM $10,000</div><div class="val" style="color:var(--gold)">${money(r.final_balance)}</div></div>
        <div class="stat panel"><div class="label">WIN RATE</div><div class="val">${r.win_rate}%</div></div>
        <div class="stat panel"><div class="label">WORST DROP</div><div class="val" style="color:var(--red)">${r.max_drawdown}%</div></div>
        <div class="stat panel"><div class="label">BEATS RANDOM</div><div class="val" style="color:var(--cyan)">${r.random_percentile}%</div></div>
        <div class="stat panel"><div class="label">JUST HOLDING</div><div class="val">${money(r.hold_final)}</div></div>
      </div>` : `<div class="panel untestable"><div class="label">WHY UNTESTABLE</div><p>${esc(n.untestable_reason || '')}</p></div>`}
      <div class="timeline panel">
        <div class="label">SOURCE VIDEO · ${esc(video.title || '').toUpperCase()} · ${ts(dur)}</div>
        <div class="track">${(n.rules_timeline || []).map(p => `
          <a class="pin k-${p.kind}" style="left:${Math.min(97, Math.max(3, 100 * p.timestamp_s / dur))}%" title="${esc(p.rule)}" href="${videoAt(video.url, p.timestamp_s)}" target="_blank">
            <i></i><span>${p.kind === 'filters' ? 'FILTER' : p.kind.replace('_', ' ').toUpperCase()} ${ts(p.timestamp_s)}</span></a>`).join('')}
        </div>
        ${(n.market && n.market.stated && n.market.tested_on && !n.market.tested_on.startsWith(n.market.stated)) ? `<p style="color:var(--soft);font-size:14px;margin:26px 0 0">Video trades ${esc(n.market.stated)}, tested on ${esc(n.market.tested_on)}.</p>` : ''}
      </div>
    </div>
    <div class="right">
      <div class="panel dialogue" id="dlg"></div>
      <div class="chips">${['Is your strategy real?', 'How did you do in 2022?', 'What was your worst moment?', 'What are your rules?'].map(q => `<button class="chip">${q}</button>`).join('')}</div>
      <form class="ask" id="ask"><input id="q" placeholder="Ask ${esc(n.name)} anything…" autocomplete="off" />
        <button type="button" class="mic" id="mic" title="Hold a voice chat">${micSvg()}</button></form>
      ${n.results ? `<a class="btn" style="text-align:center" href="#/sim/${id}">▶ SIMULATE</a>` : ''}
    </div>
  </section>`;
  const firstPin = (n.rules_timeline || []).find(p => p.kind === 'claim') || (n.rules_timeline || [])[0];
  if (firstPin) { $('#cite').textContent = `CITES VIDEO ${ts(firstPin.timestamp_s)} ↗`; $('#cite').onclick = () => window.open(videoAt(video.url, firstPin.timestamp_s)); }
  addMsg('npc', opener);
  const ask = async q => {
    if (!q) return; addMsg('user', q); $('#q').value = '';
    const thinking = addMsg('npc', '…');
    try {
      const { answer } = await post(`/api/npcs/${id}/talk`, { question: q, history });
      thinking.textContent = answer; history.push({ role: 'user', text: q }, { role: 'npc', text: answer });
      $('#say').textContent = answer; speak(answer);
    } catch (e) { thinking.textContent = 'Error: ' + e.message; }
  };
  $('#ask').onsubmit = e => { e.preventDefault(); ask($('#q').value.trim()); };
  document.querySelectorAll('.chip').forEach(c => c.onclick = () => ask(c.textContent));
  setupMic(ask);
}
function addMsg(who, text) {
  const d = document.createElement('div'); d.className = 'msg m-' + who; d.textContent = text;
  $('#dlg').appendChild(d); $('#dlg').scrollTop = 1e6; return d;
}
function videoAt(url, s) {
  if (!url) return '#';
  return url + (url.includes('?') ? '&' : '?') + 't=' + Math.floor(s || 0) + 's';
}
function monitorSvg(t) {
  if (!t) return '<svg viewBox="0 0 100 50"><text x="50" y="30" fill="#3DDC84" font-size="8" text-anchor="middle" font-family="monospace">NO DATA</text></svg>';
  const p = t.price, step = Math.max(1, Math.floor(p.length / 40)), pts = [];
  const mn = Math.min(...p), mx = Math.max(...p);
  for (let i = 0; i < p.length; i += step) pts.push([(100 * i / p.length).toFixed(1), (46 - 42 * (p[i] - mn) / (mx - mn || 1)).toFixed(1)]);
  return `<svg viewBox="0 0 100 50" preserveAspectRatio="none"><polyline points="${pts.map(x => x.join(',')).join(' ')}" fill="none" stroke="#3DDC84" stroke-width="1.5"/></svg>`;
}
function micSvg() { return '<svg width="24" height="24" viewBox="0 0 8 8" shape-rendering="crispEdges"><rect x="3" y="0" width="2" height="5" fill="#7FD8FF"/><rect x="2" y="3" width="1" height="2" fill="#7FD8FF"/><rect x="5" y="3" width="1" height="2" fill="#7FD8FF"/><rect x="3" y="5" width="2" height="1" fill="#7FD8FF"/><rect x="3" y="6" width="2" height="1" fill="#7FD8FF"/><rect x="2" y="7" width="4" height="1" fill="#7FD8FF"/></svg>'; }

// voice: browser speech to text in, text to speech out
function setupMic(ask) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition, mic = $('#mic');
  if (!SR) { mic.title = 'Voice needs Chrome'; mic.style.opacity = .4; return; }
  let rec = null;
  mic.onclick = () => {
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = 'en-US'; rec.interimResults = true;
    mic.classList.add('live');
    rec.onresult = e => { const t = [...e.results].map(r => r[0].transcript).join(''); $('#q').value = t; if (e.results[e.results.length - 1].isFinal) ask(t); };
    rec.onend = () => { mic.classList.remove('live'); rec = null; };
    rec.start();
  };
}
function speak(text) {
  if (!window.speechSynthesis) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text); u.rate = 1.05; u.pitch = 1.1;
  const npc = $('#npc'); u.onstart = () => npc?.classList.add('talking'); u.onend = () => npc?.classList.remove('talking');
  speechSynthesis.speak(u);
}

// ---------- simulate ----------
let sim = null;
function stopSim() { if (sim) { cancelAnimationFrame(sim.raf); sim = null; } }
async function renderSim(id) {
  const n = await api(`/api/npcs/${id}`);
  const t = await api(`/api/npcs/${id}/trades`);
  view.innerHTML = `
  <section class="sim">
    <div class="simhud">
      <div class="stat panel"><div class="label">DATE</div><div class="val" id="s-date"></div></div>
      <div class="stat panel"><div class="label">DAY</div><div class="val" id="s-day"></div></div>
      <div class="stat panel wallet"><div class="label">${esc(n.name).toUpperCase()}'S WALLET</div><div class="val"><span id="s-bal" style="color:var(--gold)"></span> <span id="s-chg" style="font-size:12px"></span></div></div>
      <div class="stat panel"><div class="label">HOLD ${esc(t.market.split('-')[0])}</div><div class="val" id="s-hold" style="color:var(--cyan)"></div></div>
      <div class="stat panel"><div class="label">SPEED</div><div class="val" id="s-speed" style="color:var(--cyan)"></div></div>
    </div>
    <div class="raceWrap"><canvas id="race"></canvas>
      <div class="legend"><span><b style="background:var(--gold)"></b>${esc(n.name).toUpperCase()}</span><span><b style="background:var(--cyan)"></b>HOLD ${esc(t.market.split('-')[0])}</span><span><b style="background:rgba(143,136,173,.5)"></b>1,000 RANDOM TRADERS</span><span><b style="background:var(--green);width:8px"></b>BUY</span><span><b style="background:var(--red);width:8px"></b>SELL</span></div>
      <div class="modal hidden" id="pain"></div>
    </div>
    <div class="controls">
      <button class="btn small" id="c-play">PAUSE</button>
      <button class="btn small ghost" data-speed="1">x1</button><button class="btn small ghost" data-speed="4">x4</button><button class="btn small ghost" data-speed="12">x12</button>
      <button class="btn small ghost" id="c-restart">RESTART</button>
      <a class="btn small ghost" href="#/npc/${id}">BACK TO ${esc(n.name).toUpperCase()}</a>
      ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}
    </div>
    <div class="ending hidden" id="ending"></div>
  </section>`;

  const cv = $('#race'), ctx = cv.getContext('2d');
  const N = t.equity.length, pain = t.pain_moment || {}, tradesAt = {};
  t.trades.forEach(x => (tradesAt[x.i] = tradesAt[x.i] || []).push(x));
  const all = [...t.equity, ...t.hold, ...t.random_band.p90, ...t.random_band.p10];
  const lo = Math.min(...all) * 0.95, hi = Math.max(...all) * 1.05, logY = hi / lo > 8;
  sim = { i: 0, speed: 4, playing: true, painShown: false, quitAt: null, raf: 0 };

  function size() { const r = cv.getBoundingClientRect(); cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio; }
  size(); window.onresize = size;
  const X = i => (40 + (cv.width - 80) * i / (N - 1));
  const Y = v => { const pad = 90 * devicePixelRatio, h = cv.height - pad - 40 * devicePixelRatio;
    const f = logY ? (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) : (v - lo) / (hi - lo); return pad + h * (1 - f); };

  function line(arr, upto, color, w) {
    ctx.strokeStyle = color; ctx.lineWidth = w * devicePixelRatio; ctx.beginPath();
    for (let i = 0; i <= upto; i++) { const x = X(i), y = Y(arr[i]); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
    ctx.stroke();
  }
  function draw() {
    const i = Math.floor(sim.i), d = devicePixelRatio;
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.strokeStyle = '#2C2742'; ctx.lineWidth = 2 * d; ctx.setLineDash([8 * d, 8 * d]);
    for (let k = 1; k < 6; k++) { const y = 90 * d + (cv.height - 130 * d) * k / 6; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(cv.width, y); ctx.stroke(); }
    ctx.setLineDash([]); ctx.strokeStyle = '#4A4366'; ctx.beginPath(); ctx.moveTo(0, Y(t.start_cash)); ctx.lineTo(cv.width, Y(t.start_cash)); ctx.stroke();
    ctx.fillStyle = '#8F88AD'; ctx.font = `${9 * d}px 'Press Start 2P'`; ctx.fillText('$10,000', 44 * d, Y(t.start_cash) - 8 * d);
    // random crowd band
    ctx.fillStyle = 'rgba(143,136,173,0.18)'; ctx.beginPath();
    for (let k = 0; k <= i; k++) ctx[k ? 'lineTo' : 'moveTo'](X(k), Y(t.random_band.p90[k]));
    for (let k = i; k >= 0; k--) ctx.lineTo(X(k), Y(t.random_band.p10[k]));
    ctx.fill();
    line(t.hold, i, '#7FD8FF', 3);
    line(t.equity, Math.min(i, sim.quitAt ?? i), '#FFC93C', 4);
    if (sim.quitAt != null && i > sim.quitAt) { ctx.setLineDash([6 * d, 6 * d]); ctx.globalAlpha = .45; line(t.equity, i, '#FFC93C', 3); ctx.globalAlpha = 1; ctx.setLineDash([]); }
    for (let k = 0; k <= i; k++) (tradesAt[k] || []).forEach(x => { ctx.fillStyle = x.side === 'buy' ? '#3DDC84' : '#FF5470'; ctx.fillRect(X(k) - 6 * d, Y(t.equity[k]) - 6 * d, 12 * d, 12 * d); });
    // now line and runner
    ctx.strokeStyle = '#F4F1EA'; ctx.setLineDash([6 * d, 6 * d]); ctx.lineWidth = 2 * d; ctx.beginPath(); ctx.moveTo(X(i), 0); ctx.lineTo(X(i), cv.height); ctx.stroke(); ctx.setLineDash([]);
    if (runner.complete) ctx.drawImage(runner, X(i) - 24 * d, Y(t.equity[i]) - 52 * d, 48 * d, 48 * d);
    const bal = t.equity[i], chg = 100 * (bal / t.start_cash - 1);
    $('#s-date').textContent = t.dates[i].slice(0, 10); $('#s-day').textContent = i + 1;
    $('#s-bal').textContent = money(bal); $('#s-chg').textContent = pct(chg.toFixed(1)); $('#s-chg').style.color = chg >= 0 ? 'var(--green)' : 'var(--red)';
    $('#s-hold').textContent = money(t.hold[i]); $('#s-speed').textContent = 'x' + sim.speed;
  }
  const runner = new Image(); runner.src = 'data:image/svg+xml;base64,' + btoa(sprite(n.color, 3));

  function tick() {
    if (!sim) return;
    if (sim.playing) {
      const prev = Math.floor(sim.i);
      sim.i = Math.min(N - 1, sim.i + sim.speed * Math.max(1, N / 900));
      for (let k = prev + 1; k <= Math.floor(sim.i); k++) (tradesAt[k] || []).forEach(x => SFX[x.side]?.());
      if (!sim.painShown && pain.i != null && sim.i >= pain.i && pain.drawdown_pct < -10) { sim.i = pain.i; sim.painShown = true; sim.playing = false; SFX.pain(); showPain(); }
      if (sim.i >= N - 1 && sim.playing) { sim.playing = false; (t.equity[N - 1] > t.hold[N - 1] ? SFX.win : SFX.pain)(); showEnding(); }
    }
    draw(); sim.raf = requestAnimationFrame(tick);
  }
  function showPain() {
    $('#c-play').textContent = 'PLAY';
    const m = $('#pain'); m.classList.remove('hidden');
    m.innerHTML = `<div style="display:flex;gap:12px;align-items:center"><span class="tag" style="background:var(--red)">PAIN MOMENT</span><span class="label">PAUSED</span></div>
      <h2>YOU'RE DOWN ${Math.abs(pain.drawdown_pct)}%.</h2>
      <p>${esc(n.name)} ${pain.losing_streak ? `just lost ${pain.losing_streak} trade${pain.losing_streak === 1 ? '' : 's'} in a row` : 'is in the deepest hole of the whole run'}. Keep following the rules, or quit now?</p>
      <div class="row"><button class="btn" id="keep">KEEP GOING</button><button class="btn ghost" id="quit">QUIT</button></div>
      <small>After you choose, we show where each path ended.</small>`;
    $('#keep').onclick = () => { m.classList.add('hidden'); sim.playing = true; $('#c-play').textContent = 'PAUSE'; };
    $('#quit').onclick = () => { m.classList.add('hidden'); sim.quitAt = Math.floor(sim.i); sim.playing = true; $('#c-play').textContent = 'PAUSE'; };
  }
  function showEnding() {
    $('#c-play').textContent = 'PLAY';
    const e = $('#ending'), r = n.results || {};
    const quitBal = sim.quitAt != null ? t.equity[sim.quitAt] : null;
    e.classList.remove('hidden');
    e.innerHTML = `
      <div class="stat panel"><div class="label">${esc(n.name).toUpperCase()} ENDED</div><div class="val" style="color:var(--gold)">${money(t.equity[N - 1])}</div></div>
      ${quitBal != null ? `<div class="stat panel"><div class="label">IF YOU QUIT</div><div class="val">${money(quitBal)}</div></div>` : ''}
      <div class="stat panel"><div class="label">JUST HOLDING</div><div class="val" style="color:var(--cyan)">${money(t.hold[N - 1])}</div></div>
      <div class="stat panel"><div class="label">RANDOM TRADERS BETTER</div><div class="val">${r.share_random_better}%</div></div>
      <div class="stat panel"><div class="label">VERDICT</div><div class="val"><span class="tag ${vClass(n.verdict)}">${esc(n.verdict).toUpperCase()}</span></div></div>`;
  }
  $('#c-play').onclick = () => { if (sim.i >= N - 1) return; sim.playing = !sim.playing; $('#c-play').textContent = sim.playing ? 'PAUSE' : 'PLAY'; $('#pain').classList.add('hidden'); };
  document.querySelectorAll('[data-speed]').forEach(b => b.onclick = () => sim.speed = +b.dataset.speed);
  $('#c-restart').onclick = () => { Object.assign(sim, { i: 0, playing: true, painShown: false, quitAt: null }); $('#ending').classList.add('hidden'); $('#pain').classList.add('hidden'); $('#c-play').textContent = 'PAUSE'; };
  tick();
}

route();
document.addEventListener('keydown', e => { if (e.key === 'm' && e.target.tagName !== 'INPUT') muted = !muted; });
