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
  stopSim(); stopVoice();
  $('#birth').classList.add('hidden'); clearInterval($('#birth-tl')._t);
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
  const sel = npcs.some(n => n.npc_id === current) ? current : npcs[0]?.npc_id;
  view.innerHTML = `
  <div class="lib">
  <section class="start">
    <h1>WOULD YOU HAVE<br>GOT RICH?</h1>
    <p>Paste a trading video. Its strategy is born as a trader you can question and race.</p>
    <form class="paste" id="paste"><input id="url" placeholder="youtube.com/watch?v=…" autocomplete="off" /><button class="btn">PRESS START</button></form>
  </section>
  <div class="roster-h"><span class="px">CHOOSE A TRADER</span><span class="label">${npcs.length} STRATEGIES TESTED</span></div>
  <div class="roster">${npcs.map(n => `
    <a class="card${n.npc_id === sel ? ' sel' : ''}" href="#/npc/${n.npc_id}" title="${esc(n.video_title ? 'From the video: ' + n.video_title : '')}">
      <div class="stage">${face(n, 6)}</div>
      <div class="nm">${esc(n.name).toUpperCase()}</div>
      <div class="ar">${esc(n.archetype || '')}</div>
      <span class="tag ${vClass(n.verdict)}">${esc(n.verdict || '').toUpperCase()}</span>
      <div class="ret" title="${n.annual_return_pct == null ? '' : `Average yearly return (compound) over ${n.years} years. Total: ${pct(Math.round(n.return_pct))}`}"
        style="color:${n.annual_return_pct == null ? 'var(--muted)' : n.annual_return_pct >= 0 ? 'var(--green)' : 'var(--red)'}">${n.annual_return_pct == null ? 'N/A' : pct(n.annual_return_pct) + '/YR'}</div>
      ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}
    </a>`).join('') || '<p class="empty">No NPCs yet. Paste a video to birth the first one.</p>'}
  </div>
  </div>`;
  $('#paste').onsubmit = e => { e.preventDefault(); const u = $('#url').value.trim(); if (u) birth(u); };
}

const BIRTH_STEPS = [['watch', 'Watch the video'], ['scan', 'Scan for rules'], ['extract', 'Write the exact rules'], ['match', 'Check the library'],
  ['backtest', 'Backtest on full history'], ['randoms', 'Race 1,000 random traders'], ['judge', 'Judge the claims'], ['born', 'NPC is born']];
async function birth(url) {
  const ov = $('#birth'), steps = $('#birth-steps'), err = $('#birth-error');
  ov.classList.remove('hidden'); steps.innerHTML = ''; err.textContent = '';
  const tl = $('#birth-tl'); tl.classList.add('hidden'); tl.innerHTML = ''; clearInterval(tl._t);
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
      if (j.preview && !tl.innerHTML) showBirthTimeline(tl, j.preview);
      if (j.status !== 'running') clearInterval(tl._t);
      if (j.status === 'done') { SFX.born(); $('#birth-sprite').classList.add('born'); setTimeout(() => { ov.classList.add('hidden'); location.hash = `#/npc/${j.npc_id}`; }, 1200); }
      else if (j.status === 'error') err.textContent = j.error;
      else setTimeout(poll, 1000);
    };
    poll();
  } catch (e) { err.textContent = e.message; }
}

// The rules appear on the video timeline while the backtest runs, read out one pin at a time.
function showBirthTimeline(el, p) {
  const KIND = { entry: 'ENTRY', exit: 'EXIT', stop_loss: 'STOP LOSS', filters: 'FILTER', claim: 'BOLD CLAIM' };
  const pins = p.rules_timeline || [], v = p.video || {};
  const dur = v.duration_s || Math.max(60, ...pins.map(x => x.timestamp_s + 30));
  const name = p.strategy_name ? `"${esc(p.strategy_name).toUpperCase()}"` : 'THE RULES';
  el.innerHTML = `
    <div class="tl-h"><span>${name} · FOUND IN THE VIDEO</span><span>${ts(dur)}</span></div>
    <div class="track"><div class="bar"></div>${pins.map((x, k) => `
      <a class="pin k-${x.kind}" data-k="${k}" style="left:${Math.min(98.5, Math.max(1.5, 100 * x.timestamp_s / dur))}%"
         title="${esc(KIND[x.kind] || x.kind)} ${ts(x.timestamp_s)}: ${esc(x.rule)}" href="${videoAt(v.url, x.timestamp_s)}" target="_blank"></a>`).join('')}</div>
    <div class="nowrule" id="nowrule">${p.testable ? '' : `<b class="c-claim">UNTESTABLE</b>${esc(p.untestable_reason || '')}`}</div>`;
  el.classList.remove('hidden');
  if (!p.testable || !pins.length) return;
  let k = 0;
  const show = () => {
    const x = pins[k % pins.length];
    el.querySelectorAll('.pin').forEach(a => a.classList.toggle('lit', +a.dataset.k === k % pins.length));
    $('#nowrule').innerHTML = `<b class="c-${x.kind}" style="color:var(--${{ entry: 'green', exit: 'red', stop_loss: 'cyan', filters: 'muted', claim: 'gold' }[x.kind]})">${KIND[x.kind] || x.kind} ${ts(x.timestamp_s)}</b>${esc(x.rule)}`;
    k++;
  };
  show(); el._t = setInterval(show, 1800);
}

// ---------- NPC room ----------
let history = [];
async function renderRoom(id) {
  const n = await api(`/api/npcs/${id}`);
  const r = n.results || {};
  const video = (n.source_videos || [])[0] || {};
  const dur = video.duration_s || Math.max(60, ...(n.rules_timeline || []).map(x => x.timestamp_s + 30));
  history = [];
  const opener = n.results
    ? `I turned $10,000 into ${money(r.final_balance)}. But ${r.share_random_better}% of random traders did better than me.`
    : `Hi, I'm ${n.name}. Fair warning: nobody can test my strategy.`;
  const pins = n.rules_timeline || [];
  const kinds = [...new Set(pins.map(p => p.kind))];
  const KIND = { entry: 'ENTRY', exit: 'EXIT', stop_loss: 'STOP LOSS', filters: 'FILTER', claim: 'BOLD CLAIM' };
  const legendKinds = ['entry', 'exit', 'stop_loss', 'claim'].concat(kinds.includes('filters') ? ['filters'] : []);
  const crossMarket = n.market && n.market.stated && n.market.tested_on && !n.market.tested_on.startsWith(n.market.stated);
  const meter = (k, v, shown, color) => `<div class="grp"><div class="row"><span class="k">${k}</span><span class="v">${shown}</span></div>
          <div class="meter"><i style="width:${Math.max(0, Math.min(100, Math.abs(v || 0)))}%;background:${color}"></i></div></div>`;
  view.innerHTML = `
  <section class="room">
    <div class="left">
      <div class="stagebox">
        ${ROOM_SVG}
        <div class="npc" id="npc">${face(n, 14)}</div>
        <div class="bubble"><div class="who">${esc(n.name).toUpperCase()} SAYS</div><div class="say" id="say"></div>
          <div class="cite hidden" id="cite"></div></div>
        ${TAIL_SVG}
        <div class="plate"><div class="pt"><div class="nm">${esc(n.name).toUpperCase()}</div><div class="ar">${esc(n.archetype || '')}</div></div>
          <span class="tag ${vClass(n.verdict)}">${esc(n.verdict).toUpperCase()}</span>
          ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}</div>
        ${n.results ? `
        <div class="statbox">
          <div class="row"><span class="k">BALANCE</span><span class="v big">${money(r.final_balance)}</span></div>
          ${meter('WIN RATE', r.win_rate, `${r.win_rate}%`, 'var(--green)')}
          ${meter('WORST DROP', r.max_drawdown, `${r.max_drawdown}%`, 'var(--red)')}
          ${meter('BEATS RANDOM', r.random_percentile, `${r.random_percentile}%`, 'var(--cyan)')}
        </div>` : `
        <div class="statbox"><div class="row"><span class="k">WHY UNTESTABLE</span></div><p>${esc(n.untestable_reason || '')}</p></div>`}
      </div>
      <div class="timeline">
        <a class="play" href="${videoAt(video.url, 0)}" target="_blank" title="Open the source video">${PLAY_SVG('#FFC93C')}</a>
        <div class="tl">
          <div class="tl-h"><span>SOURCE VIDEO · "${esc(video.title || '').toUpperCase()}"</span><span>${ts(dur)}</span></div>
          <div class="track"><div class="bar"></div><div class="prog" id="prog"></div>${pins.map((p, k) => `
            <a class="pin k-${p.kind}" data-k="${k}" style="left:${Math.min(98.5, Math.max(1.5, 100 * p.timestamp_s / dur))}%" title="${esc(KIND[p.kind] || p.kind)} ${ts(p.timestamp_s)}: ${esc(p.rule)}" href="${videoAt(video.url, p.timestamp_s)}" target="_blank"></a>`).join('')}
          </div>
          <div class="tl-legend">${legendKinds.map(k => `<span class="c-${k}">■ ${KIND[k]}</span>`).join('')}
            ${crossMarket ? `<span class="mkt">Video trades ${esc(n.market.stated)}, tested on ${esc(n.market.tested_on)}.</span>` : ''}</div>
        </div>
      </div>
    </div>
    <div class="right">
      <div class="panel dialogue"><div class="label">DIALOGUE</div><div class="msgs" id="dlg"></div>
        <div class="chips" id="chips">${['Is your strategy real?', 'How did you do in 2022?', 'What was your worst moment?', 'What are your rules?'].map(q => `<button class="chip">${q}</button>`).join('')}</div></div>
      <form class="ask" id="ask"><input id="q" placeholder="Ask ${esc(n.name)} anything…" autocomplete="off" />
        <button type="button" class="mic" id="mic" title="Hold a voice chat">${micSvg()}</button></form>
      ${n.results ? `<a class="btn simbtn" href="#/sim/${id}">${PLAY_SVG('#12101C')}SIMULATE</a>` : ''}
    </div>
  </section>`;
  const setSay = text => { $('#say').textContent = `"${text}"`; };
  const cite = p => {
    if (!p) return;
    $('#cite').classList.remove('hidden');
    $('#cite').textContent = `▶ CITES VIDEO ${ts(p.timestamp_s)}`;
    $('#cite').onclick = () => window.open(videoAt(video.url, p.timestamp_s));
    $('#prog').style.width = Math.min(100, 100 * p.timestamp_s / dur) + '%';
  };
  setSay(opener);
  cite(pins.find(p => p.kind === 'claim') || pins[0]);
  addMsg('npc', opener);
  const ask = async q => {
    if (!q) return; $('#chips')?.classList.add('hidden'); addMsg('user', q); $('#q').value = '';
    const thinking = addMsg('npc', '…');
    try {
      const { answer, offline, voice_chunks } = await post(`/api/npcs/${id}/talk`, { question: q, history });
      if (offline && !window._offlineNoted) {
        window._offlineNoted = true;
        addMsg('note', offline === 'no_key'
          ? 'Offline mode: this server has no GEMINI_API_KEY, so answers are simple templates from the saved numbers. Add the key to .env and restart.'
          : 'Gemini did not answer, so this reply is a simple template from the saved numbers.');
      }
      await speakAnswer(id, answer, voice_chunks);  // waits until the voice starts (at most 6s)
      thinking.textContent = answer; $('#dlg').scrollTop = 1e6; history.push({ role: 'user', text: q }, { role: 'npc', text: answer });
      setSay(answer);
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
// pixel room scene from the Paper artboard "2 · NPC room: talk"
const ROOM_SVG = `<svg class="scene" width="932" height="640" viewBox="0 0 932 640" shape-rendering="crispEdges" aria-hidden="true">
<rect width="932" height="640" fill="#241F38"/><rect x="0" y="456" width="932" height="184" fill="#171427"/><rect x="0" y="456" width="932" height="8" fill="#0B0913"/>
<path d="M0 520H932M0 584H932" fill="none" stroke="#1E1A30" stroke-width="4"/>
<rect x="48" y="56" width="300" height="200" fill="#0B0913"/><rect x="56" y="64" width="284" height="184" fill="#2A3566"/>
<rect x="88" y="90" width="4" height="4" fill="#F4F1EA"/><rect x="180" y="80" width="4" height="4" fill="#F4F1EA"/><rect x="290" y="100" width="4" height="4" fill="#F4F1EA"/><rect x="240" y="74" width="4" height="4" fill="#FFC93C"/>
<rect x="56" y="180" width="40" height="68" fill="#1B2148"/><rect x="100" y="150" width="56" height="98" fill="#1B2148"/><rect x="160" y="196" width="36" height="52" fill="#1B2148"/><rect x="200" y="130" width="60" height="118" fill="#1B2148"/><rect x="264" y="170" width="76" height="78" fill="#1B2148"/>
<rect x="112" y="166" width="8" height="8" fill="#FFC93C"/><rect x="132" y="190" width="8" height="8" fill="#FFC93C"/><rect x="216" y="146" width="8" height="8" fill="#FFC93C"/><rect x="236" y="176" width="8" height="8" fill="#7FD8FF"/><rect x="280" y="190" width="8" height="8" fill="#FFC93C"/>
<rect x="196" y="56" width="8" height="200" fill="#0B0913"/><rect x="48" y="152" width="300" height="8" fill="#0B0913"/>
<rect x="560" y="48" width="324" height="216" fill="#0B0913"/><rect x="572" y="60" width="300" height="192" fill="#120F1F"/>
<path d="M572 108H872M572 156H872M572 204H872" fill="none" stroke="#1E1A30" stroke-width="2"/>
<rect x="600" y="150" width="12" height="40" fill="#3DDC84"/><rect x="605" y="140" width="2" height="60" fill="#3DDC84"/><rect x="628" y="130" width="12" height="36" fill="#3DDC84"/><rect x="656" y="140" width="12" height="44" fill="#FF5470"/><rect x="684" y="110" width="12" height="44" fill="#3DDC84"/><rect x="712" y="120" width="12" height="60" fill="#FF5470"/><rect x="740" y="150" width="12" height="52" fill="#FF5470"/><rect x="768" y="128" width="12" height="40" fill="#3DDC84"/><rect x="796" y="100" width="12" height="38" fill="#3DDC84"/><rect x="824" y="90" width="12" height="30" fill="#3DDC84"/>
<rect x="584" y="70" width="64" height="12" fill="#FFC93C"/><rect x="560" y="264" width="324" height="8" fill="#0B0913"/><rect x="704" y="272" width="36" height="24" fill="#0B0913"/>
<rect x="440" y="404" width="300" height="20" fill="#5A3E2B"/><rect x="440" y="424" width="300" height="8" fill="#3A281C"/><rect x="456" y="432" width="16" height="72" fill="#3A281C"/><rect x="708" y="432" width="16" height="72" fill="#3A281C"/>
<rect x="600" y="372" width="72" height="32" fill="#0B0913"/><rect x="606" y="378" width="60" height="22" fill="#7FD8FF"/>
<rect x="480" y="388" width="40" height="16" fill="#FFC93C"/><rect x="484" y="380" width="32" height="8" fill="#FFC93C"/><rect x="488" y="372" width="24" height="8" fill="#FFC93C"/>
<rect x="800" y="360" width="40" height="96" fill="#2E6B3F"/><rect x="792" y="344" width="56" height="24" fill="#3DDC84"/><rect x="808" y="328" width="24" height="20" fill="#3DDC84"/><rect x="796" y="440" width="48" height="16" fill="#5A3E2B"/>
</svg>`;
const TAIL_SVG = '<svg class="tail" width="36" height="32" viewBox="0 0 9 8" shape-rendering="crispEdges" aria-hidden="true"><rect x="5" y="0" width="4" height="2" fill="#0B0913"/><rect x="3" y="2" width="4" height="2" fill="#0B0913"/><rect x="1" y="4" width="4" height="2" fill="#0B0913"/><rect x="0" y="6" width="2" height="2" fill="#0B0913"/><rect x="5" y="0" width="3" height="1" fill="#F4F1EA"/><rect x="4" y="2" width="2" height="1" fill="#F4F1EA"/></svg>';
const PLAY_SVG = c => `<svg width="20" height="20" viewBox="0 0 5 5" shape-rendering="crispEdges" aria-hidden="true"><rect x="1" y="0" width="1" height="5" fill="${c}"/><rect x="2" y="1" width="1" height="3" fill="${c}"/><rect x="3" y="2" width="1" height="1" fill="${c}"/></svg>`;
function micSvg() { return '<svg width="22" height="22" viewBox="0 0 7 7" shape-rendering="crispEdges"><rect x="2" y="0" width="3" height="4" fill="#12101C"/><rect x="1" y="3" width="1" height="1" fill="#12101C"/><rect x="5" y="3" width="1" height="1" fill="#12101C"/><rect x="2" y="4" width="3" height="1" fill="#12101C"/><rect x="3" y="5" width="1" height="2" fill="#12101C"/></svg>'; }

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
// The NPC speaks in its own Gemini voice; if that fails, the browser's voice takes over.
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

// ---------- simulate ----------
let sim = null;
function stopSim() { if (sim) { cancelAnimationFrame(sim.raf); sim = null; } }
const SPEEDS = [1, 4, 12];
const COIN_NAME = { BTC: 'BITCOIN', ETH: 'ETHEREUM', SOL: 'SOLANA' };
const MON = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
const niceDate = s => { const [y, m, d] = String(s).slice(0, 10).split('-'); return m ? `${MON[+m - 1]} ${+d} ${y}` : s; };
async function renderSim(id) {
  const n = await api(`/api/npcs/${id}`);
  const t = await api(`/api/npcs/${id}/trades`);
  const NAME = esc(n.name).toUpperCase(), sym = esc(t.market.split('-')[0]), coin = COIN_NAME[sym] || sym;
  view.innerHTML = `
  <section class="sim">
    <div class="simhud">
      <div class="tile" style="min-width:220px"><div class="label">DATE</div><div class="val" id="s-date"></div></div>
      <div class="tile" style="min-width:92px"><div class="label">DAY</div><div class="val" id="s-day"></div></div>
      <div class="tile grow"><div class="label">${NAME}'S WALLET</div><div class="vrow"><span class="val" id="s-bal" style="color:var(--gold)"></span><span class="chg" id="s-chg"></span></div></div>
      <div class="tile speed" id="s-speedtile" title="Change speed" style="min-width:92px"><div class="label">SPEED</div><div class="val" id="s-speed"></div></div>
    </div>
    <div class="raceArea">
      <div class="raceWrap"><canvas id="race"></canvas>
        <div class="legend"><span><b style="background:var(--gold)"></b>${NAME}</span><span><b style="background:var(--cyan)"></b>HOLD ${coin}</span><span><b style="background:var(--muted);opacity:.5"></b>1,000 RANDOM TRADERS</span><span><b class="sq" style="background:var(--green)"></b>BUY</span><span><b class="sq" style="background:var(--red)"></b>SELL</span></div>
        <div class="controls">
          <button class="btn small" id="c-play">PAUSE</button>
          ${SPEEDS.map(s => `<button class="btn small ghost" data-speed="${s}">x${s}</button>`).join('')}
          <button class="btn small ghost" id="c-restart">RESTART</button>
          <a class="btn small ghost" href="#/npc/${id}">BACK TO ${NAME}</a>
          ${n.demo ? '<span class="demo">DEMO DATA</span>' : ''}
        </div>
      </div>
      <div class="modal hidden" id="pain"></div>
      <div class="modal hidden" id="ending"></div>
    </div>
  </section>`;

  const cv = $('#race'), ctx = cv.getContext('2d');
  const N = t.equity.length, pain = t.pain_moment || {}, tradesAt = {};
  t.trades.forEach(x => (tradesAt[x.i] = tradesAt[x.i] || []).push(x));
  const all = [...t.equity, ...t.hold, ...t.random_band.p90, ...t.random_band.p10];
  const lo = Math.min(...all) * 0.95, hi = Math.max(...all) * 1.05, logY = hi / lo > 8;
  sim = { i: 0, speed: 4, playing: true, painShown: false, quitAt: null, raf: 0 };
  let stride = 1;
  // Year markers: the first chart point of each calendar year, plus real days since the start.
  const toMs = s => Date.parse(String(s).length > 10 ? String(s).replace(' ', 'T') + 'Z' : s + 'T00:00:00Z');
  const t0 = toMs(t.dates[0]);
  const years = t.dates.map((s, k) => k === 0 || s.slice(0, 4) !== t.dates[k - 1].slice(0, 4) ? [k, s.slice(0, 4)] : null).filter(Boolean);

  function size() {
    const r = cv.getBoundingClientRect(); cv.width = r.width * devicePixelRatio; cv.height = r.height * devicePixelRatio;
    stride = Math.max(1, Math.round(N / Math.max(20, (r.width - 80) / 10))); // about 10px per pixel step
  }
  size(); window.onresize = () => sim && size();
  const X = i => (40 * devicePixelRatio + (cv.width - 80 * devicePixelRatio) * i / (N - 1));
  const Y = v => { const pad = 90 * devicePixelRatio, h = cv.height - pad - 80 * devicePixelRatio;
    const f = logY ? (Math.log(v) - Math.log(lo)) / (Math.log(hi) - Math.log(lo)) : (v - lo) / (hi - lo); return pad + h * (1 - f); };
  const snap = (k, upto) => Math.min(upto, Math.ceil(k / stride) * stride);

  // pixel step line: flat to the next sample, then straight up or down
  function steps(arr, upto, color, w) {
    ctx.strokeStyle = color; ctx.lineWidth = w * devicePixelRatio; ctx.lineJoin = 'miter'; ctx.lineCap = 'square';
    ctx.beginPath(); ctx.moveTo(X(0), Y(arr[0]));
    let prev = arr[0];
    for (let s = stride; ; s += stride) {
      const k = Math.min(s, upto);
      ctx.lineTo(X(k), Y(prev)); ctx.lineTo(X(k), Y(arr[k])); prev = arr[k];
      if (k >= upto) break;
    }
    ctx.stroke();
  }
  function draw() {
    const i = Math.floor(sim.i), d = devicePixelRatio, W = cv.width, H = cv.height;
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = '#2C2742'; ctx.lineWidth = 2 * d; ctx.setLineDash([8 * d, 8 * d]);
    for (let y = 182 * d; y < H - 20 * d; y += 100 * d) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
    ctx.setLineDash([]); ctx.strokeStyle = '#4A4366'; ctx.beginPath(); ctx.moveTo(0, Y(t.start_cash)); ctx.lineTo(W, Y(t.start_cash)); ctx.stroke();
    // year lines and labels along the bottom, thinned so labels never overlap
    ctx.font = `${10 * d}px "Press Start 2P", monospace`; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
    let lastX = -Infinity;
    years.forEach(([k, y]) => {
      const x = X(k);
      if (k > 0) { ctx.strokeStyle = '#2C2742'; ctx.lineWidth = 2 * d; ctx.beginPath(); ctx.moveTo(x, 70 * d); ctx.lineTo(x, H - 74 * d); ctx.stroke(); }
      if (x - lastX < 56 * d) return;
      ctx.fillStyle = k <= i ? '#C9C3E0' : '#5E5878'; ctx.fillText(y, Math.max(x, 28 * d), H - 58 * d); lastX = x;
    });
    // random crowd band
    ctx.fillStyle = 'rgba(143,136,173,0.18)'; ctx.beginPath();
    for (let k = 0; k <= i; k++) ctx[k ? 'lineTo' : 'moveTo'](X(k), Y(t.random_band.p90[k]));
    for (let k = i; k >= 0; k--) ctx.lineTo(X(k), Y(t.random_band.p10[k]));
    ctx.fill();
    steps(t.hold, i, '#7FD8FF', 6);
    const q = sim.quitAt;
    steps(t.equity, Math.min(i, q ?? i), '#FFC93C', 8);
    if (q != null && i > q) { ctx.setLineDash([6 * d, 6 * d]); ctx.globalAlpha = .45; steps(t.equity, i, '#FFC93C', 4); ctx.globalAlpha = 1; ctx.setLineDash([]); }
    for (let k = 0; k <= i; k++) (tradesAt[k] || []).forEach(x => {
      const s = snap(k, i); ctx.fillStyle = x.side === 'buy' ? '#3DDC84' : '#FF5470'; ctx.fillRect(X(s) - 6 * d, Y(t.equity[s]) - 6 * d, 12 * d, 12 * d);
    });
    // now line, dimmed future, runner
    ctx.strokeStyle = '#F4F1EA'; ctx.setLineDash([6 * d, 6 * d]); ctx.lineWidth = 2 * d; ctx.beginPath(); ctx.moveTo(X(i), 0); ctx.lineTo(X(i), H); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = 'rgba(18,16,28,0.55)'; ctx.fillRect(X(i) + d, 0, W, H);
    if (runner.complete) ctx.drawImage(runner, X(i) - 24 * d, Y(t.equity[i]) - 52 * d, 48 * d, 48 * d);
    const bal = t.equity[i], chg = 100 * (bal / t.start_cash - 1);
    $('#s-date').textContent = niceDate(t.dates[i]);
    $('#s-day').textContent = Math.floor((toMs(t.dates[i]) - t0) / 864e5) + 1;  // real days since the start
    $('#s-bal').textContent = money(bal); $('#s-chg').textContent = pct(Math.round(chg)); $('#s-chg').style.color = chg >= 0 ? 'var(--green)' : 'var(--red)';
    $('#s-speed').textContent = 'x' + sim.speed;
    document.querySelectorAll('[data-speed]').forEach(b => b.classList.toggle('on', +b.dataset.speed === sim.speed));
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
  const play = on => { sim.playing = on; $('#c-play').textContent = on ? 'PAUSE' : 'PLAY'; };
  function showPain() {
    play(false);
    const m = $('#pain'); m.classList.remove('hidden');
    m.innerHTML = `<div class="mh"><span class="tag" style="background:var(--red)">PAIN MOMENT</span><span class="label">PAUSED</span></div>
      <h2>YOU'RE DOWN ${Math.abs(Math.round(pain.drawdown_pct))}%.</h2>
      <p>${esc(n.name)} ${pain.losing_streak ? `just lost ${pain.losing_streak} trade${pain.losing_streak === 1 ? '' : 's'} in a row` : 'is in the deepest hole of the whole run'}. Keep following the rules, or quit now?</p>
      <div class="row"><button class="btn" id="keep">KEEP GOING</button><button class="btn ghost" id="quit">QUIT</button></div>
      <small>After you choose, we show where each path ended.</small>`;
    $('#keep').onclick = () => { m.classList.add('hidden'); play(true); };
    $('#quit').onclick = () => { m.classList.add('hidden'); sim.quitAt = Math.floor(sim.i); play(true); };
  }
  function showEnding() {
    play(false);
    const e = $('#ending'), r = n.results || {}, last = t.equity[N - 1];
    const quitBal = sim.quitAt != null ? t.equity[sim.quitAt] : null;
    e.classList.remove('hidden');
    e.innerHTML = `<div class="mh"><span class="tag gold">THE END</span><span class="label">${niceDate(t.dates[N - 1])}</span></div>
      <h2>${NAME} ENDED WITH ${money(last)}.</h2>
      <div class="res">
        <div><span>${NAME}</span><span style="color:#8A6A10">${money(last)}</span></div>
        ${quitBal != null ? `<div><span>IF YOU QUIT</span><span>${money(quitBal)}</span></div>` : ''}
        <div><span>JUST HOLDING ${coin}</span><span>${money(t.hold[N - 1])}</span></div>
        <div><span>RANDOM TRADERS BETTER</span><span>${r.share_random_better ?? 'N/A'}%</span></div>
        <div><span>VERDICT</span><span class="tag ${vClass(n.verdict)}">${esc(n.verdict).toUpperCase()}</span></div>
      </div>
      <div class="row"><button class="btn" id="again">RACE AGAIN</button><a class="btn ghost" href="#/npc/${id}">BACK</a></div>`;
    $('#again').onclick = restart;
  }
  function restart() { Object.assign(sim, { i: 0, painShown: false, quitAt: null }); $('#ending').classList.add('hidden'); $('#pain').classList.add('hidden'); play(true); }
  $('#c-play').onclick = () => { if (sim.i >= N - 1) return; play(!sim.playing); $('#pain').classList.add('hidden'); };
  document.querySelectorAll('[data-speed]').forEach(b => b.onclick = () => sim.speed = +b.dataset.speed);
  $('#s-speedtile').onclick = () => { sim.speed = SPEEDS[(SPEEDS.indexOf(sim.speed) + 1) % SPEEDS.length]; SFX.click(); };
  $('#c-restart').onclick = restart;
  tick();
}

route();
document.addEventListener('keydown', e => { if (e.key === 'm' && e.target.tagName !== 'INPUT') muted = !muted; });
