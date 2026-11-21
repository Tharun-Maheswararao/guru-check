// Guru Check frontend: Traders (library), Talk (NPC room), Race (simulate). Plain JS, no build step.
// Look: the Paper file "Guru Check · Anime" (character select, visual novel, VS battle, summon).
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
const KIND = { entry: 'ENTRY', exit: 'EXIT', stop_loss: 'STOP LOSS', filters: 'FILTER', claim: 'CLAIM' };
let current = null; // last opened npc_id

// ---------- sounds ----------
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
document.addEventListener('click', e => { if (e.target.closest('.pill,.card,.choice,.round,.speeds button')) SFX.click(); });

// Character art: the NPC's Gemini portrait, or a glowing initial until it has one.
const initial = n => esc((n.name || '?').trim()[0] || '?').toUpperCase();
function art(n) {
  const fallback = `<div class="noart">${initial(n)}</div>`;
  return n.portrait_path
    ? `<img class="art" src="/api/npcs/${n.npc_id}/portrait" alt="${esc(n.name)}" data-i="${initial(n)}" onerror="noArt(this)">`
    : fallback;
}
function noArt(img) { const d = document.createElement('div'); d.className = 'noart'; d.textContent = img.dataset.i || '?'; img.replaceWith(d); }

// ---------- routing ----------
function setNav(which) {
  document.querySelectorAll('nav a').forEach(a => a.classList.toggle('on', a.dataset.nav === which));
  $('#nav-room').classList.toggle('off', !current); $('#nav-sim').classList.toggle('off', !current);
  if (current) { $('#nav-room').href = `#/npc/${current}`; $('#nav-sim').href = `#/sim/${current}`; }
}
async function route() {
  stopSim(); stopVoice();
  $('#birth').classList.add('hidden'); clearInterval($('#birth-tl')._t);
  const [, page, id] = location.hash.split('/');
  try {
    if (page === 'npc' && id) { current = id; setNav('room'); await renderRoom(id); }
    else if (page === 'sim' && id) { current = id; setNav('sim'); await renderSim(id); }
    else { setNav('library'); await renderLibrary(); }
  } catch (e) { view.innerHTML = `<div class="lib"><h1>GAME <span>OVER</span></h1><p class="empty">${esc(e.message)}</p><div class="summonbar"><a class="pill" href="#/">BACK</a></div></div>`; }
  window.scrollTo(0, 0);
}
window.addEventListener('hashchange', route);

// ---------- traders: choose your trader ----------
async function renderLibrary() {
  const npcs = await api('/api/npcs');
  const sel = npcs.some(n => n.npc_id === current) ? current : npcs[0]?.npc_id;
  view.innerHTML = `
  <div class="lib">
    <h1>CHOOSE YOUR <span>TRADER</span></h1>
    <div class="roster">${npcs.map(n => `
      <a class="card${n.npc_id === sel ? ' sel' : ''}" href="#/npc/${n.npc_id}" title="${esc(n.video_title ? 'From the video: ' + n.video_title : '')}">
        ${art(n)}
        <div class="shade"></div>
        ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}
        <div class="info">
          <span class="badge ${vClass(n.verdict)}">${esc(n.verdict || '').toUpperCase()}</span>
          <div class="nm">${esc(n.name).toUpperCase()}</div>
          ${n.strategy_name ? `<div class="st" title="Strategy: ${esc(n.strategy_name)}">${esc(n.strategy_name)}</div>` : ''}
          <div class="ret" title="${n.annual_return_pct == null ? '' : `Average yearly return (compound) over ${n.years} years. Total: ${pct(Math.round(n.return_pct))}`}"
            style="${n.annual_return_pct == null ? 'color:var(--muted)' : n.annual_return_pct < 0 ? 'color:var(--pink)' : ''}">${n.annual_return_pct == null ? 'N/A' : pct(n.annual_return_pct) + '<small>/ YEAR</small>'}</div>
        </div>
      </a>`).join('') || '<p class="empty">No traders yet. Paste a video below to summon the first one.</p>'}
    </div>
    <form class="summonbar" id="paste">
      <label class="field"><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><rect x="1" y="4" width="18" height="12" rx="4" fill="#FF3D7F"/><path d="M8 7.5 L13 10 L8 12.5 Z" fill="#fff"/></svg>
        <input id="url" placeholder="Paste a trading video link" autocomplete="off" /></label>
      <button class="pill"><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M10 1 L12.4 7.6 L19 10 L12.4 12.4 L10 19 L7.6 12.4 L1 10 L7.6 7.6 Z" fill="#fff"/></svg>SUMMON</button>
    </form>
  </div>`;
  $('#paste').onsubmit = e => { e.preventDefault(); const u = $('#url').value.trim(); if (u) birth(u); };
}

// ---------- summon (birth) ----------
const BIRTH_STEPS = [['watch', 'Watching the video'], ['scan', 'Scanning for rules'], ['extract', 'Writing the exact rules'], ['match', 'Checking the library'],
  ['backtest', 'Testing the rules on every day'], ['randoms', 'Racing 1,000 random traders'], ['judge', 'Judging the claims'], ['born', 'A trader is born']];
async function birth(url) {
  const ov = $('#birth'), segs = $('#birth-steps'), label = $('#birth-label'), count = $('#birth-count'), err = $('#birth-error'), core = $('#birth-sprite');
  ov.classList.remove('hidden'); err.textContent = ''; label.textContent = 'Opening the video'; count.textContent = '';
  core.className = 'core'; core.textContent = '?';
  segs.innerHTML = BIRTH_STEPS.map(() => '<div class="seg"></div>').join('');
  const tl = $('#birth-tl'); tl.innerHTML = ''; clearInterval(tl._t);
  $('#birth-close').onclick = () => { ov.classList.add('hidden'); clearInterval(tl._t); };
  try {
    const r = await post('/api/birth', { url });
    if (r.status === 'exists') { label.textContent = 'Already summoned. Opening this trader.'; setTimeout(() => { ov.classList.add('hidden'); location.hash = `#/npc/${r.npc_id}`; }, 900); return; }
    const poll = async () => {
      const j = await api(`/api/birth/${r.job_id}`);
      const seen = Object.fromEntries(j.steps.map(s => [s.step, s.detail]));
      const lastStep = j.steps.length ? j.steps[j.steps.length - 1].step : null;
      segs.innerHTML = BIRTH_STEPS.map(([k]) => {
        const st = !seen[k] ? '' : (k === lastStep && j.status === 'running') ? 'now' : (k === lastStep && j.status === 'error') ? 'fail' : 'done';
        return `<div class="seg ${st}"></div>`;
      }).join('');
      const idx = BIRTH_STEPS.findIndex(([k]) => k === lastStep);
      if (idx >= 0) { label.textContent = seen[lastStep] || BIRTH_STEPS[idx][1]; count.textContent = `STEP ${idx + 1} OF ${BIRTH_STEPS.length}`; }
      if (j.preview && !tl.innerHTML) showBirthRules(tl, j.preview);
      if (j.status !== 'running') clearInterval(tl._t);
      if (j.status === 'done') {
        SFX.born(); core.classList.add('born');
        try { const n = await api(`/api/npcs/${j.npc_id}`); core.innerHTML = art(n); } catch (e) { /* keep the ? */ }
        setTimeout(() => { ov.classList.add('hidden'); location.hash = `#/npc/${j.npc_id}`; }, 1400);
      } else if (j.status === 'error') err.textContent = j.error;
      else setTimeout(poll, 1000);
    };
    poll();
  } catch (e) { err.textContent = e.message; }
}

// The rules float out of the circle as they are found, lighting up one at a time.
const ORBIT = [[-250, 70, -6], [520, 120, 5], [-230, 300, 4], [510, 350, -4], [-140, 470, -3], [430, -10, 6]];
function showBirthRules(el, p) {
  const pins = (p.rules_timeline || []).slice(0, ORBIT.length), v = p.video || {};
  if (!p.testable) {
    el.innerHTML = `<div class="rchip k-claim" style="left:${ORBIT[1][0]}px;top:${ORBIT[1][1]}px"><i></i><b>UNTESTABLE</b></div>`;
    return;
  }
  el.innerHTML = pins.map((x, k) => `<a class="rchip k-${x.kind}" data-k="${k}" href="${videoAt(v.url, x.timestamp_s)}" target="_blank"
      title="${esc(x.rule)}" style="left:${ORBIT[k][0]}px;top:${ORBIT[k][1]}px;transform:rotate(${ORBIT[k][2]}deg)"><i></i><b>${KIND[x.kind] || esc(x.kind)}</b><span>${ts(x.timestamp_s)}</span></a>`).join('');
  if (!pins.length) return;
  let k = 0;
  const show = () => { el.querySelectorAll('.rchip').forEach(a => a.classList.toggle('lit', +a.dataset.k === k % pins.length)); k++; };
  show(); el._t = setInterval(show, 1800);
}

// ---------- talk: visual novel ----------
let history = [];
const QUESTIONS = ['Is your strategy real?', 'How did you do in 2022?', 'What was your worst moment?', 'What are your rules?'];
async function renderRoom(id) {
  const n = await api(`/api/npcs/${id}`);
  const r = n.results || {};
  const video = (n.source_videos || [])[0] || {};
  const pins = n.rules_timeline || [];
  const dur = video.duration_s || Math.max(60, ...pins.map(x => x.timestamp_s + 30));
  history = [];
  const opener = n.results
    ? `I turned $10,000 into ${money(r.final_balance)}. But ${r.share_random_better}% of random traders did better than me.`
    : `Hi, I'm ${n.name}. Fair warning: nobody can test my strategy.`;
  const crossMarket = n.market && n.market.stated && n.market.tested_on && !n.market.tested_on.startsWith(n.market.stated);
  const bar = (k, v, shown, color) => `<div class="bar"><div class="k">${k}</div><div class="t"><i style="width:${Math.max(0, Math.min(100, Math.abs(v || 0)))}%;background:${color}"></i></div><div class="v">${shown}</div></div>`;
  view.innerHTML = `
  <section class="vn">
    <div class="vn-glow"></div>
    <div class="vn-art" id="npc">${art(n)}</div>
    <div class="vn-side">
      <div class="vn-head"><span class="badge ${vClass(n.verdict)}">${esc(n.verdict).toUpperCase()}</span><div class="nm">${esc(n.name).toUpperCase()}</div>
        ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}</div>
      ${n.results ? `
      <div><div class="kicker">$10,000 BECAME</div><div class="bigmoney">${money(r.final_balance)}</div></div>
      <div class="bars">
        ${bar('WIN RATE', r.win_rate, `${r.win_rate}%`, 'var(--mint)')}
        ${bar('WORST DROP', r.max_drawdown, `${r.max_drawdown}%`, 'var(--pink)')}
        ${bar('VS RANDOM', r.random_percentile, `${r.random_percentile}%`, 'var(--yellow)')}
      </div>` : `<div><div class="kicker">WHY UNTESTABLE</div><div class="why">${esc(n.untestable_reason || '')}</div></div>`}
      ${crossMarket ? `<div class="kicker">VIDEO TRADES ${esc(n.market.stated)} · TESTED ON ${esc(n.market.tested_on)}</div>` : ''}
      <div class="choices" id="choices"></div>
      ${n.results ? `<a class="pill racebtn" href="#/sim/${id}">START THE RACE <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3 L17 10 L5 17 Z" fill="#fff"/></svg></a>` : ''}
    </div>
    <div class="dbox">
      <div class="nametag">${esc(n.name).toUpperCase()}</div>
      <div class="you" id="you"></div>
      <div class="say" id="say"></div>
      <div class="note hidden" id="note"></div>
      <div class="drow">
        <a class="cite hidden" id="cite" target="_blank"></a>
        <div class="vtrack"><div class="rail"></div><div class="prog" id="prog"></div>${pins.map((p, k) => `
          <a class="pin k-${p.kind}" data-k="${k}" style="left:${Math.min(98.5, Math.max(1.5, 100 * p.timestamp_s / dur))}%" title="${esc(KIND[p.kind] || p.kind)} ${ts(p.timestamp_s)}: ${esc(p.rule)}" href="${videoAt(video.url, p.timestamp_s)}" target="_blank"></a>`).join('')}</div>
        <div class="dur">${ts(dur)}</div>
      </div>
      <form class="ask" id="ask"><input id="q" placeholder="Ask ${esc(n.name)} anything…" autocomplete="off" />
        <button type="button" class="mic" id="mic" title="Talk with your voice">${micSvg()}</button></form>
    </div>
    <div class="dlog" id="dlg"></div>
  </section>`;
  const setSay = text => { $('#say').textContent = `"${text}"`; };
  const cite = p => {
    if (!p) return;
    const c = $('#cite'); c.classList.remove('hidden');
    c.textContent = `Video ${ts(p.timestamp_s)}`; c.href = videoAt(video.url, p.timestamp_s);
    $('#prog').style.width = Math.min(100, 100 * p.timestamp_s / dur) + '%';
  };
  const asked = new Set();
  const showChoices = () => {
    const left = QUESTIONS.filter(q => !asked.has(q)).slice(0, 2);
    $('#choices').innerHTML = left.map(q => `<button class="choice">${q}</button>`).join('');
    document.querySelectorAll('.choice').forEach(c => c.onclick = () => ask(c.textContent));
  };
  setSay(opener);
  cite(pins.find(p => p.kind === 'claim') || pins[0]);
  addMsg('npc', opener);
  const ask = async q => {
    if (!q) return;
    asked.add(q); showChoices(); addMsg('user', q); $('#q').value = '';
    $('#you').innerHTML = `<b>YOU:</b> ${esc(q)}`; $('#say').textContent = '…';
    try {
      const { answer, offline, voice_chunks } = await post(`/api/npcs/${id}/talk`, { question: q, history });
      if (offline && !window._offlineNoted) {
        window._offlineNoted = true;
        addMsg('note', offline === 'no_key'
          ? 'Offline mode: this server has no GEMINI_API_KEY, so answers are simple templates from the saved numbers.'
          : 'Gemini did not answer, so this reply is a simple template from the saved numbers.');
      }
      await speakAnswer(id, answer, voice_chunks);  // waits until the voice starts (at most 6s)
      addMsg('npc', answer); history.push({ role: 'user', text: q }, { role: 'npc', text: answer });
      setSay(answer);
    } catch (e) { $('#say').textContent = 'Error: ' + e.message; }
  };
  showChoices();
  $('#ask').onsubmit = e => { e.preventDefault(); ask($('#q').value.trim()); };
  setupMic(ask);
}
// The full chat stays in a hidden log; notes show under the line in the dialogue box.
function addMsg(who, text) {
  if (who === 'note') { const el = $('#note'); el.textContent = text; el.classList.remove('hidden'); return el; }
  const d = document.createElement('div'); d.className = 'msg m-' + who; d.textContent = text;
  $('#dlg').appendChild(d); return d;
}
function videoAt(url, s) {
  if (!url) return '#';
  return url + (url.includes('?') ? '&' : '?') + 't=' + Math.floor(s || 0) + 's';
}
function micSvg() { return '<svg width="20" height="24" viewBox="0 0 20 24" aria-hidden="true"><rect x="6" y="1" width="8" height="14" rx="4" fill="#fff"/><path d="M2 11 C 2 17, 18 17, 18 11 M10 17 V22" fill="none" stroke="#fff" stroke-width="2.5" stroke-linecap="round"/></svg>'; }

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
// The NPC speaks in its own Gemini voice. /talk already started making the audio in sentence chunks;
// the text appears when the first chunk starts playing, so words and voice arrive together. If the
// voice is muted, off, or slower than 6s, the text shows at once and the browser's voice reads it.
let voiceAudio = null, voiceToken = 0;
const fetchVoice = (id, text) => fetch(`/api/npcs/${id}/speak`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
  .then(r => (r.ok ? r.blob() : null)).catch(() => null);
const within = (p, ms) => Promise.race([p, new Promise(r => setTimeout(() => r(null), ms))]);
function stopVoice() {
  voiceToken++; voiceAudio?.pause(); window.speechSynthesis?.cancel(); $('#npc')?.classList.remove('talking');
}
function playBlob(blob, token) {
  return new Promise(done => {
    if (token !== voiceToken) return done();
    const npc = $('#npc');
    voiceAudio = new Audio(URL.createObjectURL(blob));
    voiceAudio.onplay = () => npc?.classList.add('talking');
    voiceAudio.onended = voiceAudio.onpause = () => { npc?.classList.remove('talking'); done(); };
    voiceAudio.play().catch(done);
  });
}
function browserSpeak(text) {
  if (muted || !window.speechSynthesis) return;
  const npc = $('#npc'), u = new SpeechSynthesisUtterance(text); u.rate = 1.05; u.pitch = 1.1;
  u.onstart = () => npc?.classList.add('talking'); u.onend = () => npc?.classList.remove('talking');
  speechSynthesis.speak(u);
}
async function speakAnswer(id, text, chunks) {
  stopVoice();
  const token = voiceToken;
  if (muted) return;
  if (!id || !chunks || !chunks.length) { browserSpeak(text); return; }
  const blobs = chunks.map(c => fetchVoice(id, c));  // all chunks in parallel; played in order
  const first = await within(blobs[0], 6000);
  if (!first || token !== voiceToken) { if (token === voiceToken) browserSpeak(text); return; }
  (async () => {
    for (const pending of blobs) {
      const blob = await pending;
      if (!blob || token !== voiceToken) return;
      await playBlob(blob, token);
    }
  })();
}
function speak(text, id) { return speakAnswer(id, text, [text]); }

// ---------- race: VS battle ----------
let sim = null;
function stopSim() { if (sim) { cancelAnimationFrame(sim.raf); sim = null; } }
const SPEEDS = [1, 4, 12];
const COIN_NAME = { BTC: 'BITCOIN', ETH: 'ETHEREUM', SOL: 'SOLANA' };
const COIN_SIGN = { BTC: '₿', ETH: 'Ξ', SOL: '◎' };
const MON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
const niceDate = s => { const [y, m, d] = String(s).slice(0, 10).split('-'); return m ? `${MON[+m - 1]} ${+d} ${y}` : s; };
const PLAY_ICON = '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><path d="M4 2 L16 9 L4 16 Z" fill="#15141B"/></svg>';
const PAUSE_ICON = '<svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true"><rect x="3" y="2" width="4" height="14" rx="1.5" fill="#15141B"/><rect x="11" y="2" width="4" height="14" rx="1.5" fill="#15141B"/></svg>';
const SPEED_LINES = '<svg class="lines" viewBox="0 0 760 640" aria-hidden="true"><path d="M640 300 L890 300 M627 365 L858 461 M590 420 L767 597 M535 457 L631 688 M470 470 L470 720 M405 457 L309 688 M350 420 L173 597 M313 365 L82 461 M300 300 L50 300 M313 235 L82 139 M350 180 L173 3 M405 143 L309 -88 M470 130 L470 -120 M535 143 L631 -88 M590 180 L767 3 M627 235 L858 139" fill="none" stroke="#FF3D7F" stroke-opacity="0.25" stroke-width="7" stroke-linecap="round"/></svg>';
async function renderSim(id) {
  const n = await api(`/api/npcs/${id}`);
  const t = await api(`/api/npcs/${id}/trades`);
  const NAME = esc(n.name).toUpperCase(), sym = esc(t.market.split('-')[0]), coin = COIN_NAME[sym] || sym;
  view.innerHTML = `
  <section class="vs">
    <div class="vs-hud">
      <div class="fighter">
        <div class="avatar">${art(n)}</div>
        <div class="fbody"><div class="frow"><span class="nm">${NAME}</span><span><span id="s-bal" style="color:var(--yellow)"></span><span class="chg" id="s-chg"></span></span></div>
          <div class="hp"><i id="hp1" style="background:var(--yellow)"></i></div></div>
      </div>
      <div class="vsmid"><b>VS</b><span id="s-date"></span><span>DAY <span id="s-day"></span></span></div>
      <div class="fighter p2">
        <div class="avatar"><div class="coin">${COIN_SIGN[sym] || sym[0]}</div></div>
        <div class="fbody"><div class="frow"><span id="s-hold" style="color:var(--cyan)"></span><span class="nm">JUST HOLD</span></div>
          <div class="hp"><i id="hp2" style="background:var(--cyan)"></i></div></div>
      </div>
    </div>
    <div class="arena"><canvas id="race"></canvas>
      <div class="legend"><span><i style="background:var(--yellow)"></i>${NAME}</span><span><i style="background:var(--cyan)"></i>HOLD ${coin}</span><span><i style="background:rgba(255,61,127,.35)"></i>1,000 RANDOM TRADERS</span><span><i style="background:var(--mint)"></i>BUY</span><span><i style="background:var(--pink)"></i>SELL</span></div>
      <div class="overlay hidden" id="pain"></div>
      <div class="overlay hidden" id="ending"></div>
    </div>
    <div class="vs-controls">
      <button class="round main" id="c-play" title="Pause"></button>
      <div class="speeds">${SPEEDS.map(s => `<button data-speed="${s}">x${s}</button>`).join('')}</div>
      <button class="round" id="c-restart" title="Restart"><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M15.5 6 A7 7 0 1 0 17 11" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/><path d="M16 1.5 V6.5 H11" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
      <a class="backlink" href="#/npc/${id}">BACK TO ${NAME}</a>
      ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}
    </div>
  </section>`;

  const cv = $('#race'), ctx = cv.getContext('2d');
  const N = t.equity.length, pain = t.pain_moment || {}, tradesAt = {};
  t.trades.forEach(x => (tradesAt[x.i] = tradesAt[x.i] || []).push(x));
  const all = [...t.equity, ...t.hold, ...t.random_band.p90, ...t.random_band.p10];
  const lo = Math.min(...all) * 0.95, hi = Math.max(...all) * 1.05, logY = hi / lo > 8;
  const best = Math.max(t.start_cash, ...t.equity, ...t.hold);  // a full health bar
  sim = { i: 0, speed: 4, playing: true, painShown: false, quitAt: null, raf: 0 };
  let stride = 1;
  // Year markers: the first chart point of each calendar year, plus real days since the start.
  const toMs = s => Date.parse(String(s).length > 10 ? String(s).replace(' ', 'T') + 'Z' : s + 'T00:00:00Z');
  const t0 = toMs(t.dates[0]);
  const years = t.dates.map((s, k) => k === 0 || s.slice(0, 4) !== t.dates[k - 1].slice(0, 4) ? [k, s.slice(0, 4)] : null).filter(Boolean);

  function size() {
    const r = cv.getBoundingClientRect(); cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio;
    stride = Math.max(1, Math.round(N / Math.max(20, (r.width - 80) / 8)));  // one point about every 8px
  }
  size(); window.onresize = () => sim && size();
  const X = i => (40 * devicePixelRatio + (cv.width - 80 * devicePixelRatio) * i / (N - 1));
  const Y = v => { const pad = 70 * devicePixelRatio, h = cv.height - pad - 70 * devicePixelRatio;
    const f = logY ? (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) : (v - lo) / (hi - lo); return pad + h * (1 - f); };
  const snap = (k, upto) => Math.min(upto, Math.ceil(k / stride) * stride);

  // smooth glowing line through one sample per stride, ending exactly at "now"
  function line(arr, upto, color, w) {
    ctx.strokeStyle = color; ctx.lineWidth = w * devicePixelRatio; ctx.lineJoin = 'round'; ctx.lineCap = 'round';
    ctx.beginPath(); ctx.moveTo(X(0), Y(arr[0]));
    for (let s = stride; ; s += stride) { const k = Math.min(s, upto); ctx.lineTo(X(k), Y(arr[k])); if (k >= upto) break; }
    ctx.stroke();
  }
  function draw() {
    const i = Math.floor(sim.i), d = devicePixelRatio, W = cv.width, H = cv.height;
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = '#24222E'; ctx.lineWidth = 2 * d;
    for (let y = 140 * d; y < H - 60 * d; y += 100 * d) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
    ctx.setLineDash([8 * d, 8 * d]); ctx.strokeStyle = '#4A4560'; ctx.beginPath(); ctx.moveTo(0, Y(t.start_cash)); ctx.lineTo(W, Y(t.start_cash)); ctx.stroke(); ctx.setLineDash([]);
    // year lines and labels along the bottom, thinned so labels never overlap
    ctx.font = `800 ${12 * d}px "M PLUS Rounded 1c", sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    let lastX = -Infinity;
    years.forEach(([k, y]) => {
      const x = X(k);
      if (k > 0) { ctx.strokeStyle = '#24222E'; ctx.lineWidth = 2 * d; ctx.beginPath(); ctx.moveTo(x, 56 * d); ctx.lineTo(x, H - 50 * d); ctx.stroke(); }
      if (x - lastX < 56 * d) return;
      ctx.fillStyle = k <= i ? '#C9C3E0' : '#4A4560'; ctx.fillText(y, Math.max(x, 28 * d), H - 24 * d); lastX = x;
    });
    // random crowd band
    ctx.fillStyle = 'rgba(255,61,127,0.10)'; ctx.beginPath();
    for (let k = 0; k <= i; k++) ctx[k ? 'lineTo' : 'moveTo'](X(k), Y(t.random_band.p90[k]));
    for (let k = i; k >= 0; k--) ctx.lineTo(X(k), Y(t.random_band.p10[k]));
    ctx.fill();
    line(t.hold, i, '#7FD8FF', 5);
    const q = sim.quitAt, upto = Math.min(i, q ?? i);
    line(t.equity, upto, 'rgba(255,210,63,0.25)', 20);
    line(t.equity, upto, '#FFD23F', 7);
    if (q != null && i > q) { ctx.setLineDash([6 * d, 8 * d]); ctx.globalAlpha = .45; line(t.equity, i, '#FFD23F', 4); ctx.globalAlpha = 1; ctx.setLineDash([]); }
    for (let k = 0; k <= i; k++) (tradesAt[k] || []).forEach(x => {
      const s = snap(k, i); ctx.fillStyle = x.side === 'buy' ? '#3DF0A6' : '#FF3D7F';
      ctx.beginPath(); ctx.arc(X(s), Y(t.equity[s]), 7 * d, 0, 2 * Math.PI); ctx.fill();
    });
    // now line, dimmed future, runner
    ctx.strokeStyle = 'rgba(255,255,255,0.5)'; ctx.setLineDash([6 * d, 6 * d]); ctx.lineWidth = 2 * d; ctx.beginPath(); ctx.moveTo(X(i), 0); ctx.lineTo(X(i), H); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(21,20,27,0.55)'; ctx.fillRect(X(i) + d, 0, W, H);
    const rx = X(i), ry = Y(t.equity[i]);
    ctx.fillStyle = 'rgba(255,61,127,0.35)'; ctx.beginPath(); ctx.arc(rx, ry, 26 * d, 0, 2 * Math.PI); ctx.fill();
    if (runner.ok) {
      ctx.save(); ctx.beginPath(); ctx.arc(rx, ry, 20 * d, 0, 2 * Math.PI); ctx.clip();
      const sw = runner.naturalWidth, sh = runner.naturalHeight, side = Math.min(sw, sh * 0.75);
      ctx.drawImage(runner, (sw - side) / 2, sh * 0.04, side, side, rx - 20 * d, ry - 20 * d, 40 * d, 40 * d); ctx.restore();
    } else { ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(rx, ry, 9 * d, 0, 2 * Math.PI); ctx.fill(); }
    const bal = t.equity[i], chg = 100 * (bal / t.start_cash - 1), hold = t.hold[i];
    $('#s-date').textContent = niceDate(t.dates[i]);
    $('#s-day').textContent = Math.floor((toMs(t.dates[i]) - t0) / 864e5) + 1;  // real days since the start
    $('#s-bal').textContent = money(bal); $('#s-chg').textContent = pct(Math.round(chg)); $('#s-chg').style.color = chg >= 0 ? 'var(--mint)' : 'var(--pink)';
    $('#s-hold').textContent = money(hold);
    $('#hp1').style.width = Math.max(2, 100 * bal / best) + '%'; $('#hp2').style.width = Math.max(2, 100 * hold / best) + '%';
    document.querySelectorAll('[data-speed]').forEach(b => b.classList.toggle('on', +b.dataset.speed === sim.speed));
  }
  const runner = new Image(); runner.onload = () => { runner.ok = true; };
  if (n.portrait_path) runner.src = `/api/npcs/${n.npc_id}/portrait`;

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
  const play = on => { sim.playing = on; $('#c-play').innerHTML = on ? PAUSE_ICON : PLAY_ICON; $('#c-play').title = on ? 'Pause' : 'Play'; };
  function showPain() {
    play(false);
    const m = $('#pain'); m.classList.remove('hidden');
    const why = pain.losing_streak ? `${pain.losing_streak} loss${pain.losing_streak === 1 ? '' : 'es'} in a row.` : 'The deepest hole of the run.';
    m.innerHTML = `${SPEED_LINES}<h2>PAIN MOMENT!</h2><div class="hit">-${Math.abs(Math.round(pain.drawdown_pct))}%</div>
      <p>${why} Stay or quit?</p>
      <div class="row"><button class="pill" id="keep">HOLD ON</button><button class="pill ghost" id="quit">BAIL OUT</button></div>`;
    $('#keep').onclick = () => { m.classList.add('hidden'); play(true); };
    $('#quit').onclick = () => { m.classList.add('hidden'); sim.quitAt = Math.floor(sim.i); play(true); };
  }
  function showEnding() {
    play(false);
    const e = $('#ending'), r = n.results || {}, last = t.equity[N - 1];
    const quitBal = sim.quitAt != null ? t.equity[sim.quitAt] : null;
    e.classList.remove('hidden');
    e.innerHTML = `<h2>THE END</h2><div class="hit gold">${money(last)}</div>
      <div class="res">
        ${quitBal != null ? `<div><span>IF YOU BAILED OUT</span><b>${money(quitBal)}</b></div>` : ''}
        <div><span>JUST HOLD ${coin}</span><b>${money(t.hold[N - 1])}</b></div>
        <div><span>RANDOMS WHO DID BETTER</span><b>${r.share_random_better ?? 'N/A'}%</b></div>
        <div><span>VERDICT</span><span class="badge ${vClass(n.verdict)}">${esc(n.verdict).toUpperCase()}</span></div>
      </div>
      <div class="row"><button class="pill" id="again">RACE AGAIN</button><a class="pill ghost" href="#/npc/${id}">BACK</a></div>`;
    $('#again').onclick = restart;
  }
  function restart() { Object.assign(sim, { i: 0, painShown: false, quitAt: null }); $('#ending').classList.add('hidden'); $('#pain').classList.add('hidden'); play(true); }
  $('#c-play').onclick = () => { if (sim.i >= N - 1) return; play(!sim.playing); $('#pain').classList.add('hidden'); };
  document.querySelectorAll('[data-speed]').forEach(b => b.onclick = () => sim.speed = +b.dataset.speed);
  $('#c-restart').onclick = restart;
  play(true);
  tick();
}

route();
document.addEventListener('keydown', e => { if (e.key === 'm' && e.target.tagName !== 'INPUT') muted = !muted; });
