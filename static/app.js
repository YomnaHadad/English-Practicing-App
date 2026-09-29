'use strict';
/* Movie Shadowing web app: plain JS, hash routing, no build step.
   All dynamic text goes through html`...`, which escapes every interpolated value. */

// ---------- tiny templating (auto-escapes) ----------
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
class Raw { constructor(s) { this.s = s; } }
const fmt = v => v instanceof Raw ? v.s : Array.isArray(v) ? v.map(fmt).join('') : esc(v);
const html = (strings, ...vals) => new Raw(strings.reduce((out, s, i) => out + s + (i < vals.length ? fmt(vals[i]) : ''), ''));
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const view = $('#view');

// ---------- state ----------
let token = localStorage.getItem('token');
let accent = localStorage.getItem('accent') || 'us';
let user = null;
let navId = 0; // guards against a slow page overwriting a newer one

// ---------- API client ----------
async function api(path, { method = 'GET', json, form, raw = false } = {}) {
  const headers = {};
  if (token) headers.Authorization = 'Bearer ' + token;
  let body;
  if (json !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(json); }
  else if (form) body = form; // FormData / URLSearchParams set their own content type
  const res = await fetch('/api' + path, { method, headers, body });
  if (!res.ok) {
    if (res.status === 401 && token) { logout(); throw new Error('Session expired - please log in again.'); }
    let msg = res.statusText;
    try {
      const d = await res.json();
      msg = typeof d.detail === 'string' ? d.detail : Array.isArray(d.detail) ? d.detail.map(e => e.msg).join('; ') : msg;
    } catch { /* keep statusText */ }
    throw new Error(msg);
  }
  return raw ? res : res.json();
}

function toast(msg) {
  const t = $('#toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, 5000);
}

async function busy(btn, fn) {
  btn.disabled = true;
  try { await fn(); } catch (e) { toast(e.message); } finally { btn.disabled = false; }
}

// ---------- audio: text-to-speech + microphone ----------
const ttsCache = new Map();
let playing = null;
async function speak(text) {
  const key = accent + '|' + text;
  if (!ttsCache.has(key)) {
    const res = await api('/tts', { method: 'POST', json: { text, accent }, raw: true });
    ttsCache.set(key, URL.createObjectURL(await res.blob()));
  }
  if (playing) playing.pause();
  playing = new Audio(ttsCache.get(key));
  await playing.play();
}

async function startRecording() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error('Microphone needs HTTPS (or localhost) and a modern browser.');
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  const rec = new MediaRecorder(stream);
  const chunks = [];
  rec.ondataavailable = e => chunks.push(e.data);
  const finished = new Promise(resolve => {
    rec.onstop = () => { stream.getTracks().forEach(t => t.stop()); resolve(new Blob(chunks, { type: rec.mimeType })); };
  });
  rec.start();
  return { stop: () => { rec.stop(); return finished; } };
}

const audioFile = blob => {
  const ext = blob.type.includes('mp4') ? 'mp4' : blob.type.includes('ogg') ? 'ogg' : 'webm';
  return new File([blob], 'speech.' + ext, { type: blob.type });
};

/* Turns `btn` into a record/stop toggle; calls onAudio(blob) after Stop. */
function bindRecorder(btn, onAudio) {
  let rec = null;
  btn.onclick = async () => {
    if (!rec) {
      try { rec = await startRecording(); } catch (e) { toast(e.message.includes('Permission') ? 'Microphone permission denied.' : e.message); return; }
      btn.textContent = '■ Stop'; btn.classList.add('recording');
    } else {
      const r = rec; rec = null;
      btn.textContent = '🎤 Record'; btn.classList.remove('recording');
      await busy(btn, async () => onAudio(await r.stop()));
    }
  };
}

// ---------- small helpers ----------
const fmtTime = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const fmtDate = s => new Date(s + 'Z').toLocaleDateString(); // server sends naive UTC
const SKILLS = [['vocab', 'Vocabulary'], ['grammar', 'Grammar'], ['reading', 'Reading'], ['listening', 'Listening']];
const ACTIONS = {
  assessment: ['#/assessment', 'Take the test'],
  review: ['#/review', 'Start review'],
  shadowing: ['#/movies', 'Open movies'],
  tutor: ['#/tutor', 'Start talking'],
};
const delta = d => d > 0 ? html`<span class="up">▲ ${d}</span>` : d < 0 ? html`<span class="down">▼ ${-d}</span>` : '';
const bar = (label, value, prev) => html`<div class="skill"><span>${label}</span><div class="bar"><div style="width:${value}%"></div></div><span>${value}/100 ${prev == null ? '' : delta(value - prev)}</span></div>`;

/* Render a page unless the user already navigated elsewhere. Returns false if stale. */
function show(tpl, id) {
  if (id !== navId) return false;
  view.innerHTML = tpl.s;
  return true;
}

// ---------- auth ----------
async function login(username, password) {
  const r = await api('/auth/token', { method: 'POST', form: new URLSearchParams({ username, password }) });
  token = r.access_token;
  localStorage.setItem('token', token);
  user = await api('/users/me');
}

function logout() {
  token = null; user = null;
  localStorage.removeItem('token');
  location.hash = '#/login';
  route();
}

async function loginPage(id) {
  show(html`
    <section class="card narrow">
      <h1>🎬 Movie Shadowing</h1>
      <p class="muted">Learn English from movie dialogue: listen, look up words, speak, and track your progress.</p>
      <div class="tabs"><button data-tab="login" class="active">Log in</button><button data-tab="register">Sign up</button></div>
      <form id="login-form" class="stack">
        <input name="username" placeholder="Username" autocomplete="username" required>
        <input name="password" type="password" placeholder="Password" autocomplete="current-password" required>
        <button class="btn primary">Log in</button>
      </form>
      <form id="register-form" class="stack" hidden>
        <input name="full_name" placeholder="Full name" autocomplete="name">
        <input name="username" placeholder="Username (3+ characters)" autocomplete="username" minlength="3" required>
        <input name="email" type="email" placeholder="Email" autocomplete="email" required>
        <input name="password" type="password" placeholder="Password (8+ characters)" autocomplete="new-password" minlength="8" required>
        <button class="btn primary">Create account</button>
      </form>
      <p id="form-error" class="error"></p>
    </section>`, id);

  const err = $('#form-error');
  $$('.tabs button').forEach(b => b.onclick = () => {
    $$('.tabs button').forEach(x => x.classList.toggle('active', x === b));
    $('#login-form').hidden = b.dataset.tab !== 'login';
    $('#register-form').hidden = b.dataset.tab !== 'register';
    err.textContent = '';
  });
  const submit = (form, fn) => form.onsubmit = async e => {
    e.preventDefault(); err.textContent = '';
    const data = Object.fromEntries(new FormData(form));
    await busy($('button.primary', form), async () => {
      try { await fn(data); } catch (ex) { err.textContent = ex.message; }
    });
  };
  submit($('#login-form'), async d => { await login(d.username, d.password); location.hash = '#/'; });
  submit($('#register-form'), async d => {
    await api('/auth/register', { method: 'POST', json: d });
    await login(d.username, d.password);
    location.hash = '#/assessment'; // new users start with the placement test
  });
}

// ---------- home ----------
async function homePage(id) {
  const [p, recs] = await Promise.all([api('/progress'), api('/recommendations')]);
  const weak = p.weakest_skill ? `weakest: ${p.weakest_skill}` : 'take the test to find out';
  show(html`
    <h1>Welcome${user ? ', ' + (user.full_name || user.username) : ''} 👋</h1>
    <div class="grid">
      <div class="card stat"><span class="big">${p.cefr_level || '–'}</span><span class="muted">Your level (${weak})</span></div>
      <div class="card stat"><span class="big">${p.vocab.total}</span><span class="muted">Words saved</span></div>
      <div class="card stat"><span class="big">${p.pronunciation.average_recent ?? '–'}</span><span class="muted">Pronunciation avg</span></div>
      <div class="card stat"><span class="big">${p.movies.chapters_completed}</span><span class="muted">Chapters done</span></div>
    </div>
    <h2>Recommended next</h2>
    ${recs.map(r => html`
      <div class="card rec">
        <div><b>${r.title}</b><p class="muted">${r.reason}</p></div>
        <a class="btn primary" href="${ACTIONS[r.action][0]}">${ACTIONS[r.action][1]}</a>
      </div>`)}`, id);
}

// ---------- placement test ----------
async function assessmentPage(id) {
  const questions = await api('/assessments/questions');
  const byId = Object.fromEntries(questions.map(q => [q.id, q]));
  if (!show(html`
    <h1>Placement test</h1>
    <p class="muted">${questions.length} multiple-choice questions, about 10 minutes. It estimates your CEFR level (A1-C2) and tailors your practice. Skip anything you don't know.</p>
    <form id="quiz">
      ${SKILLS.map(([skill, label]) => html`
        <section class="card"><h2>${label}</h2>
          ${questions.filter(q => q.skill === skill).map((q, n) => html`
            <fieldset class="q">
              <legend>${n + 1}. ${q.prompt}</legend>
              ${q.passage ? html`<blockquote>${q.passage}</blockquote>` : ''}
              ${q.audio_text ? html`<p><button type="button" class="btn small" data-listen="${q.id}">▶ Listen</button></p>` : ''}
              ${q.options.map((o, i) => html`<label class="opt"><input type="radio" name="${q.id}" value="${i}"> ${o}</label>`)}
            </fieldset>`)}
        </section>`)}
      <button class="btn primary">Submit test</button>
    </form>`, id)) return;

  $$('[data-listen]').forEach(b => b.onclick = () => busy(b, () => speak(byId[b.dataset.listen].audio_text)));
  $('#quiz').onsubmit = async e => {
    e.preventDefault();
    const answers = {};
    $$('#quiz input:checked').forEach(i => { answers[i.name] = Number(i.value); });
    const blank = questions.length - Object.keys(answers).length;
    if (blank && !confirm(`${blank} question(s) are unanswered. Submit anyway?`)) return;
    await busy($('#quiz button.primary'), async () => {
      await api('/assessments/', { method: 'POST', json: { answers } });
      const history = await api('/assessments/me'); // newest first
      showAssessmentResult(history[0], history[1]);
    });
  };
}

function showAssessmentResult(now, before) {
  window.scrollTo(0, 0);
  view.innerHTML = html`
    <h1>Your level: ${now.cefr_level}</h1>
    <div class="card">
      ${SKILLS.map(([s, label]) => bar(label, now[s + '_score'], before ? before[s + '_score'] : null))}
      <p class="muted">${before
        ? `Previous result (${fmtDate(before.created_at)}): ${before.cefr_level}. Arrows show change since then.`
        : "This is your first result. Retake the test later and we'll show your progress."}</p>
      <p class="muted">This is a quick placement estimate, not an official exam.</p>
    </div>
    <a class="btn primary" href="#/">See my recommendations</a>`.s;
}

// ---------- movies ----------
const WORD = /([A-Za-z]+(?:'[A-Za-z]+)?)/;
const BASIC = new Set(('a an the and or but if of to in on at by for with from as is are was were be been am i you he she it we they ' +
  'me him her us them my your his its our their this that these those do does did not no so just what who how there here will would ' +
  'can could should have has had').split(' '));
const lineWords = text => text.split(WORD).map((tok, i) =>
  i % 2 ? html`<span class="w${BASIC.has(tok.toLowerCase()) ? ' basic' : ''}" data-w="${tok}">${tok}</span>` : tok);

async function moviesPage(id) {
  if (!show(html`
    <h1>Movies</h1>
    <div class="card">
      <form id="search" class="row">
        <input name="q" placeholder="Movie name, e.g. Spider-Man: No Way Home" minlength="2" required>
        <button class="btn primary">Find subtitles</button>
        <label class="muted">Voice <select id="accent"><option value="us">American</option><option value="gb">British</option></select></label>
      </form>
      <div id="results" class="result-list"></div>
    </div>
    <div id="dialogue"></div>`, id)) return;

  $('#accent').value = accent;
  $('#accent').onchange = e => { accent = e.target.value; localStorage.setItem('accent', accent); };

  $('#search').onsubmit = async e => {
    e.preventDefault();
    const box = $('#results');
    box.innerHTML = '<p class="muted">Searching…</p>';
    await busy($('#search button'), async () => {
      const results = await api('/movies/search?q=' + encodeURIComponent(new FormData(e.target).get('q')));
      box.innerHTML = results.length ? results.map((r, i) => html`
        <div class="result"><span>${r.title} (${r.year}) <span class="muted">- ${r.release_name || 'release n/a'}</span></span>
          <button class="btn small" data-i="${i}">Load dialogue</button></div>`.s).join('')
        : '<p class="muted">No English subtitles found. Try a more exact title.</p>';
      $$('button[data-i]', box).forEach(b => b.onclick = () => busy(b, () => loadMovie(results[b.dataset.i])));
    });
  };
}

async function loadMovie(movie) {
  const box = $('#dialogue');
  box.innerHTML = '<p class="muted">Downloading subtitles…</p>';
  try {
    const [data, done] = await Promise.all([
      api('/movies/' + movie.file_id),
      api('/movies/completed?movie_title=' + encodeURIComponent(movie.title)),
    ]);
    renderDialogue(box, movie.title, data.chapters, new Set(done));
  } catch (e) { box.innerHTML = ''; throw e; }
}

function renderDialogue(box, title, chapters, done) {
  const total = chapters.reduce((n, c) => n + c.lines.length, 0);
  box.innerHTML = html`
    <h2>${title}</h2>
    <p class="muted">${total} lines. Click any word for an explanation (it's saved for review), ▶ to listen, 🎤 to practise saying the line.</p>
    ${chapters.map((c, ci) => html`
      <details class="chapter" data-ch="${ci}">
        <summary>${done.has(ci) ? '✓ ' : ''}${c.title} · ${fmtTime(c.start)} · ${c.lines.length} lines</summary>
        <div class="lines"></div>
      </details>`)}`.s;

  $$('details.chapter', box).forEach(d => d.addEventListener('toggle', () => {
    if (!d.open || d.dataset.ready) return;
    d.dataset.ready = '1'; // fill lazily: a movie has ~1000 lines
    const ci = Number(d.dataset.ch);
    $('.lines', d).innerHTML = html`
      <button class="btn small" data-complete>Mark chapter complete</button>
      ${chapters[ci].lines.map((l, li) => html`
        <div class="line" data-ch="${ci}" data-i="${li}">
          <div class="line-main">
            <span class="ts">${fmtTime(l.start)}</span>
            <span class="text">${lineWords(l.text)}</span>
            <button class="icon" data-act="play" title="Listen">▶</button>
            <button class="icon" data-act="practice" title="Practise speaking">🎤</button>
          </div>
          <div class="panel" hidden></div>
        </div>`)}`.s;
  }));

  box.onclick = async e => { // one delegated handler (assigned, so reloading a movie never stacks handlers)
    const complete = e.target.closest('[data-complete]');
    if (complete) {
      const ci = Number(complete.closest('details').dataset.ch);
      return busy(complete, async () => {
        await api('/chapters/complete', { method: 'POST', json: { movie_title: title, chapter_idx: ci } });
        const s = complete.closest('details').querySelector('summary');
        if (!s.textContent.startsWith('✓')) s.textContent = '✓ ' + s.textContent;
        toast('Chapter marked complete 🎉');
      });
    }
    const lineEl = e.target.closest('.line');
    if (!lineEl) return;
    const line = chapters[lineEl.dataset.ch].lines[lineEl.dataset.i];
    const panel = $('.panel', lineEl);
    const word = e.target.closest('.w');
    const act = e.target.closest('[data-act]');

    if (act?.dataset.act === 'play') return busy(act, () => speak(line.text));
    if (act?.dataset.act === 'practice') { openPanel(panel, line, title); panel.hidden = !panel.hidden; return; }
    if (word) {
      openPanel(panel, line, title); panel.hidden = false;
      const out = $('.lookup', panel);
      out.textContent = `Looking up “${word.dataset.w}”…`;
      try {
        const r = await api('/vocab/explain', { method: 'POST', json: { word: word.dataset.w, sentence: line.text, movie_title: title } });
        out.innerHTML = html`<b>${word.dataset.w}</b> = ${r.easy_word}<br>${r.meaning_in_sentence}<br><small class="muted">✓ Saved to your review list</small>`.s;
      } catch (ex) { out.textContent = ex.message; }
    }
  };
}

/* Builds the lookup + recording area for a line the first time it is opened. */
function openPanel(panel, line, movieTitle) {
  if (panel.dataset.ready) return;
  panel.dataset.ready = '1';
  panel.innerHTML = html`
    <div class="lookup muted">Click a word above to see what it means here.</div>
    <div class="row" style="margin-top:.6rem"><button class="btn rec-btn">🎤 Record</button><span class="muted">Say the line, then press Stop.</span></div>
    <div class="feedback"></div>`.s;
  bindRecorder($('.rec-btn', panel), async blob => {
    const fd = new FormData();
    fd.append('audio', audioFile(blob));
    fd.append('target', line.text);
    fd.append('movie_title', movieTitle);
    const r = await api('/pronunciation', { method: 'POST', form: fd });
    $('.feedback', panel).innerHTML = html`
      <p><span class="score">${r.score}/100</span> ${r.feedback}</p>
      ${r.unclear_words.length ? html`<p>Words to review: ${r.unclear_words.map(w => html`<span class="chip">${w}</span>`)}</p>` : ''}
      <p class="muted">We heard: “${r.transcript}”</p>
      <audio controls src="${URL.createObjectURL(blob)}"></audio>`.s;
  });
}

// ---------- vocabulary review ----------
async function reviewPage(id) {
  const exercises = await api('/review/exercises?n=8');
  if (!exercises.length) {
    show(html`<h1>Vocabulary review</h1><div class="card"><p>Your review list needs at least two saved words.</p>
      <p>Click words while reading <a href="#/movies">movie dialogue</a> and they're added automatically.</p></div>`, id);
    return;
  }
  if (!show(html`<h1>Vocabulary review</h1><div id="quiz" class="card"></div>`, id)) return;
  const box = $('#quiz');
  let i = 0, right = 0;

  const next = () => {
    if (i >= exercises.length) {
      box.innerHTML = html`<h2>Done: ${right} / ${exercises.length} correct</h2>
        <p class="muted">Words you miss come back first next time.</p>
        <a class="btn primary" href="#/review" id="again">Practise again</a> <a class="btn" href="#/progress">See progress</a>`.s;
      $('#again').onclick = () => setTimeout(route, 0);
      return;
    }
    const q = exercises[i];
    box.innerHTML = html`
      <p class="muted">Question ${i + 1} of ${exercises.length}: choose the missing word</p>
      <p class="cloze">${q.sentence}</p>
      <div class="options">${q.options.map(o => html`<button class="btn" data-o="${o}">${o}</button>`)}</div>
      <p style="margin-top:1rem"><button class="btn primary" id="next" hidden>Next</button></p>`.s;
    $$('[data-o]', box).forEach(b => b.onclick = async () => {
      $$('[data-o]', box).forEach(x => { x.disabled = true; });
      try {
        const r = await api('/review/answer', { method: 'POST', json: { vocab_id: q.vocab_id, answer: b.dataset.o } });
        b.classList.add(r.correct ? 'right' : 'wrong');
        if (!r.correct) $$('[data-o]', box).find(x => x.dataset.o === r.answer)?.classList.add('right');
        right += r.correct ? 1 : 0;
        $('#next').hidden = false;
        $('#next').onclick = () => { i++; next(); };
      } catch (e) { toast(e.message); $$('[data-o]', box).forEach(x => { x.disabled = false; }); }
    });
  };
  next();
}

// ---------- AI speaking tutor ----------
const TOPICS = [['', 'Free conversation'], ['Movies and TV', 'Movies and TV'], ['Daily life', 'Daily life'],
  ['Travel', 'Travel'], ['Work and study', 'Work and study'], ['Food and cooking', 'Food and cooking'], ['Hobbies', 'Hobbies']];

async function tutorPage(id) {
  const p = await api('/progress');
  if (!show(html`
    <h1>AI speaking tutor</h1>
    <div class="card">
      <p>Have a spoken conversation. The tutor adapts to your level (<b>${p.cefr_level || 'A2 - take the placement test to personalise it'}</b>),
      weaves in words you're studying, and gives feedback on your mistakes at the end.</p>
      <div class="row"><label>Topic <select id="topic">${TOPICS.map(([v, l]) => html`<option value="${v}">${l}</option>`)}</select></label>
        <button class="btn primary" id="start">Start session</button></div>
      <p class="muted">Tip: use headphones so the microphone doesn't pick up the tutor's voice.</p>
    </div>`, id)) return;
  $('#start').onclick = e => busy(e.target, () => startChat($('#topic').value));
}

async function startChat(topic) {
  const messages = [];
  view.innerHTML = html`
    <h1>Conversation${topic ? ': ' + topic : ''}</h1>
    <div id="log"></div>
    <div class="row">
      <button class="btn primary rec-btn" id="mic">🎤 Record</button>
      <form id="say" class="row" style="flex:1"><input name="text" placeholder="…or type your answer" autocomplete="off"><button class="btn">Send</button></form>
      <button class="btn" id="finish">Finish &amp; get feedback</button>
    </div>`.s;
  const log = $('#log');
  const controls = $$('#mic, #say button, #finish');
  const setBusy = on => controls.forEach(c => { c.disabled = on; });

  const add = (role, text) => {
    messages.push({ role, text });
    log.insertAdjacentHTML('beforeend', html`<div class="msg ${role}"><span>${text}</span>${role === 'assistant' ? html`<button class="icon" data-say>▶</button>` : ''}</div>`.s);
    log.scrollTop = log.scrollHeight;
  };
  log.onclick = e => { const b = e.target.closest('[data-say]'); if (b) busy(b, () => speak(b.previousElementSibling.textContent)); };

  async function send({ text, blob } = {}) {
    setBusy(true);
    log.insertAdjacentHTML('beforeend', '<div class="msg assistant" id="thinking"><span class="muted">…</span></div>');
    try {
      const fd = new FormData();
      fd.append('transcript', JSON.stringify(messages));
      fd.append('topic', topic);
      if (text) fd.append('text', text);
      if (blob) fd.append('audio', audioFile(blob));
      const r = await api('/tutor/turn', { method: 'POST', form: fd });
      $('#thinking')?.remove();
      if (r.user_text) add('user', r.user_text);
      add('assistant', r.reply);
      speak(r.reply).catch(() => { /* autoplay may be blocked; ▶ still works */ });
    } catch (e) { $('#thinking')?.remove(); toast(e.message); }
    finally { setBusy(false); }
  }

  bindRecorder($('#mic'), blob => send({ blob }));
  $('#say').onsubmit = e => {
    e.preventDefault();
    const text = e.target.elements.text.value.trim();
    if (text) { e.target.reset(); send({ text }); }
  };
  $('#finish').onclick = e => busy(e.target, async () => {
    if (!messages.some(m => m.role === 'user')) { toast('Say something first, then finish the session.'); return; }
    showTutorFeedback(await api('/tutor/finish', { method: 'POST', json: { topic, transcript: messages } }));
  });
  send(); // the tutor opens the conversation
}

function showTutorFeedback({ session, next_steps }) {
  window.scrollTo(0, 0);
  view.innerHTML = html`
    <h1>Session feedback</h1>
    <div class="card"><p>${session.summary}</p></div>
    <h2>Mistakes to learn from</h2>
    <div class="card">${session.mistakes.length ? session.mistakes.map(m => html`
      <div class="mistake"><s>${m.said}</s> → <b>${m.correction}</b><br><span class="muted">${m.explanation}</span></div>`)
      : html`<p>No significant mistakes. Well done! 🎉</p>`}</div>
    <h2>Suggested next</h2>
    ${next_steps.map(r => html`<div class="card rec"><div><b>${r.title}</b><p class="muted">${r.reason}</p></div>
      <a class="btn primary" href="${ACTIONS[r.action][0]}">${ACTIONS[r.action][1]}</a></div>`)}
    <a class="btn" href="#/tutor" id="again">New session</a>`.s;
  $('#again').onclick = () => setTimeout(route, 0);
}

// ---------- progress ----------
async function progressPage(id) {
  const [p, sessions] = await Promise.all([api('/progress'), api('/tutor/sessions')]);
  const rows = p.assessments.map((a, i) => ({ a, prev: p.assessments[i - 1] })).reverse();
  show(html`
    <h1>Your progress</h1>
    <h2>Level & assessments</h2>
    <div class="card">${rows.length ? html`
      <table><tr><th>Date</th><th>Level</th>${SKILLS.map(([, l]) => html`<th>${l}</th>`)}</tr>
        ${rows.map(({ a, prev }) => html`<tr><td>${fmtDate(a.created_at)}</td><td><b>${a.cefr_level}</b></td>
          ${SKILLS.map(([s]) => html`<td>${a[s + '_score']} ${prev ? delta(a[s + '_score'] - prev[s + '_score']) : ''}</td>`)}</tr>`)}
      </table>` : html`<p>No assessment yet.</p>`}
      <p><a class="btn small" href="#/assessment">${rows.length ? 'Retake the test' : 'Take the test'}</a></p></div>

    <h2>Areas to improve</h2>
    <div class="card">
      ${p.weak_areas.length ? html`<ul>${p.weak_areas.map(a => html`<li>${a}</li>`)}</ul>` : html`<p>Nothing flagged yet - keep practising!</p>`}
      ${p.pronunciation.weak_words.length ? html`<p>Words you often say unclearly: ${p.pronunciation.weak_words.map(w => html`<span class="chip">${w}</span>`)}</p>` : ''}
      ${p.tutor.recent_mistakes.map(m => html`<div class="mistake"><s>${m.said}</s> → <b>${m.correction}</b> <span class="muted">${m.explanation}</span></div>`)}
    </div>

    <div class="grid">
      <div class="card"><h2 style="margin-top:0">Vocabulary</h2>
        <p>${p.vocab.total} saved · ${p.vocab.mastered} mastered · ${p.vocab.due} due</p>
        <p class="muted">Review accuracy: ${p.vocab.review_accuracy == null ? '–' : p.vocab.review_accuracy + '%'}</p></div>
      <div class="card"><h2 style="margin-top:0">Pronunciation</h2>
        <p>${p.pronunciation.attempts} attempts</p>
        <p class="muted">Recent average: ${p.pronunciation.average_recent ?? '–'}/100</p></div>
      <div class="card"><h2 style="margin-top:0">Movies</h2>
        <p>${p.movies.chapters_completed} chapters completed</p>
        <p class="muted">${p.movies.movies.join(', ') || 'None yet'}</p></div>
    </div>

    <h2>Speaking sessions (${p.tutor.sessions})</h2>
    <div class="card">${sessions.length ? sessions.map(s => html`
      <div class="mistake"><b>${s.topic || 'Free conversation'}</b> <span class="muted">· ${fmtDate(s.created_at)} · ${s.cefr_level}</span><br>${s.summary}</div>`)
      : html`<p>No sessions yet. <a href="#/tutor">Talk to the tutor</a>.</p>`}</div>`, id);
}

// ---------- router ----------
const routes = { '/': homePage, '/login': loginPage, '/assessment': assessmentPage, '/movies': moviesPage,
  '/review': reviewPage, '/tutor': tutorPage, '/progress': progressPage };

async function route() {
  const path = location.hash.slice(1) || '/';
  const id = ++navId;
  if (!token && path !== '/login') { location.hash = '#/login'; return; }
  if (token && path === '/login') { location.hash = '#/'; return; }
  if (token && !user) {
    try { user = await api('/users/me'); } catch { return; }
  }
  $('#topbar').hidden = !token;
  $('#who').textContent = user ? user.username : '';
  $$('nav a').forEach(a => a.classList.toggle('active', a.dataset.route === path));
  view.innerHTML = '<p class="muted">Loading…</p>';
  try { await (routes[path] || homePage)(id); }
  catch (e) { if (id === navId) view.innerHTML = html`<div class="card"><p class="error">${e.message}</p></div>`.s; }
}

$('#logout').onclick = logout;
window.addEventListener('hashchange', route);
route();
