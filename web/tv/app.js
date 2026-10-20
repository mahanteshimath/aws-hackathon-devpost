import { api, assetUrl } from '../shared/api.js';
import { FocusManager } from '../shared/tv-focus.js';
import { createRemote } from '../shared/remote.js';
import { narrate, chime } from './narrator.js';

const $ = (sel) => document.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ------------------------------------------------------------------ stage scaling (1920x1080 design) */
const stage = $('#stage');
function fit() {
  const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
  stage.style.transform = `translate(${(window.innerWidth - 1920 * s) / 2}px, ${(window.innerHeight - 1080 * s) / 2}px) scale(${s})`;
}
window.addEventListener('resize', fit);
fit();

/* ------------------------------------------------------------------ state */
const state = {
  screen: 'home',
  householdId: localStorage.getItem('crayon.household') || '',
  session: null,
  seenStories: new Set(),
  story: null,          // latest story doc from the API
  storyId: null,
  path: [],             // page ids in play order
  pageIdx: 0,
  narration: null,
  playToken: 0,         // cancels stale async playback when the user navigates
  heroX: -600,
  demo: false,
};

const focus = new FocusManager({ root: $('#home') });
const remote = createRemote();

function setBedtime(on) {
  document.body.classList.toggle('bedtime', !!on);
}
setBedtime(new Date().getHours() >= 19 || new Date().getHours() < 6);

function show(name) {
  state.screen = name;
  document.body.dataset.screen = name;
  document.querySelectorAll('.screen').forEach((s) => s.classList.toggle('active', s.id === name));
  const scope = name === 'player' ? $('#choice') : $(`#${name}`);
  focus.setRoot(scope, { focus: name !== 'player' });
}

/* ------------------------------------------------------------------ home: pairing + shelf */
async function startSession() {
  try {
    const cfg = await api.config();
    $('#mode-badge').textContent = cfg.mode === 'aws' ? 'Amazon Bedrock · Nova · Polly' : 'Mock mode (no AWS)';
    const session = await api.createSession(state.householdId);
    state.session = session;
    state.householdId = session.household_id;
    localStorage.setItem('crayon.household', session.household_id);
    $('#qr').src = assetUrl(session.qr_url);
    $('#pair-code').textContent = session.code;
    loadShelf();
    pollSession();
  } catch (err) {
    $('#phone-status').textContent = 'Cannot reach the story server. Retrying…';
    setTimeout(startSession, 4000);
  }
}

async function pollSession() {
  const sid = state.session && state.session.session_id;
  if (!sid) return;
  try {
    const info = await api.session(sid);
    $('#phone-dot').classList.toggle('on', info.phone_connected);
    $('#phone-status').textContent = info.phone_connected ? 'Phone connected! Snap a drawing…' : 'Waiting for a phone…';
    const latest = info.latest;
    if (latest && latest.story_id && !state.seenStories.has(latest.story_id)) {
      state.seenStories.add(latest.story_id);
      if (latest.status !== 'ready' || state.screen === 'home') startStory(latest.story_id, { fresh: true });
    }
  } catch (_) {
    /* transient; keep polling */
  }
  setTimeout(pollSession, 1500);
}

async function loadShelf() {
  if (!state.householdId) return;
  try {
    const { stories } = await api.shelf(state.householdId);
    const row = $('#shelf-row');
    row.querySelectorAll('.story-card').forEach((n) => n.remove());
    stories.slice(0, 5).forEach((s) => {
      const card = document.createElement('button');
      card.className = 'shelf-card story-card';
      card.setAttribute('data-focus', '');
      card.setAttribute('data-focus-group', 'shelf');
      card.innerHTML = `<span class="cover-wrap"><img class="cover" alt=""><img class="sprite" alt=""></span><span class="shelf-title"></span>`;
      if (s.cover_url) card.querySelector('.cover').src = assetUrl(s.cover_url);
      else card.querySelector('.cover').remove();
      if (s.sprite_url) card.querySelector('.sprite').src = assetUrl(s.sprite_url);
      card.querySelector('.shelf-title').textContent = s.title || s.hero_name;
      card.addEventListener('click', () => startStory(s.story_id, { fresh: false }));
      row.insertBefore(card, $('#demo-btn'));
    });
    if (state.screen === 'home') focus.focusFirst();
  } catch (_) {
    /* shelf is optional */
  }
}

$('#demo-btn').addEventListener('click', () => startDemo());

/* ------------------------------------------------------------------ story lifecycle */
async function fetchStory() {
  if (state.demo) return state.story;
  state.story = await api.story(state.storyId);
  return state.story;
}

async function startStory(storyId, { fresh }) {
  stopNarration();
  const token = ++state.playToken;
  state.demo = false;
  state.storyId = storyId;
  state.story = null;
  state.path = ['1', '2', '3'];
  state.pageIdx = 0;
  markProgress('casting');
  show('making');
  // Poll until the hero is cast.
  while (token === state.playToken) {
    try {
      const doc = await fetchStory();
      setBedtime(doc.bedtime);
      markProgress(doc.status);
      if (doc.status === 'error') return showError(doc.error);
      if (doc.character) break;
    } catch (err) {
      if (err.status === 404) return showError('That story could not be found.');
    }
    await sleep(800);
  }
  if (token !== state.playToken) return;
  keepPolling(token);
  await reveal(token, fresh);
  if (token === state.playToken) playPage(token);
}

async function startDemo() {
  stopNarration();
  const token = ++state.playToken;
  const res = await fetch('./demo/story.json');
  const doc = await res.json();
  const base = './demo/';
  const fix = (u) => (u && !/^https?:/.test(u) ? base + u : u);
  doc.character.sprite_url = fix(doc.character.sprite_url);
  doc.character.greeting_audio_url = fix(doc.character.greeting_audio_url);
  Object.values(doc.pages).forEach((p) => { p.bg_url = fix(p.bg_url); p.audio_url = fix(p.audio_url); });
  state.demo = true;
  state.story = doc;
  state.storyId = doc.story_id;
  state.path = ['1', '2', '3'];
  state.pageIdx = 0;
  setBedtime(doc.bedtime);
  await reveal(token, true);
  if (token === state.playToken) playPage(token);
}

function keepPolling(token) {
  (async () => {
    while (token === state.playToken && !state.demo) {
      try {
        const doc = await fetchStory();
        if (doc.status === 'ready' || doc.status === 'error') return;
      } catch (_) { /* retry */ }
      await sleep(1000);
    }
  })();
}

function markProgress(status) {
  const order = ['casting', 'cast', 'writing', 'rendering', 'ready'];
  const at = order.indexOf(status);
  document.querySelectorAll('#progress li').forEach((li) => {
    const i = order.indexOf(li.dataset.step);
    li.classList.toggle('done', i < at);
    li.classList.toggle('active', i === at);
  });
}

/* ------------------------------------------------------------------ reveal */
async function reveal(token, fresh) {
  const ch = state.story.character;
  $('#reveal-sprite').src = assetUrl(ch.sprite_url);
  $('#reveal-name').textContent = ch.name;
  $('#reveal-greeting').textContent = '';
  $('#reveal-hint').textContent = 'Writing your story…';
  confetti();
  show('reveal');
  chime('sparkle');
  await sleep(fresh ? 1500 : 900);
  if (token !== state.playToken) return;
  state.narration = narrate($('#reveal-greeting'), {
    text: ch.greeting,
    words: ch.greeting_words || [],
    audioUrl: assetUrl(ch.greeting_audio_url),
  });
  await state.narration.done;
  // Wait until page 1 is ready (hides generation latency behind the reveal).
  const minUntil = Date.now() + (fresh ? 1500 : 600);
  while (token === state.playToken) {
    const p1 = state.story.pages && state.story.pages['1'];
    if (p1 && p1.status === 'ready' && Date.now() >= minUntil) break;
    if (state.story.status === 'error') return showError(state.story.error);
    $('#reveal-hint').textContent = state.story.title ? `“${state.story.title}” is almost ready…` : 'Writing your story…';
    await sleep(400);
  }
}

function confetti() {
  const box = $('#confetti');
  box.textContent = '';
  const colours = ['#f2603a', '#2f6fe4', '#2e9e5b', '#ffc23a', '#7a4fd6', '#f0568c'];
  for (let i = 0; i < 36; i++) {
    const c = document.createElement('i');
    c.style.left = `${Math.random() * 100}%`;
    c.style.background = colours[i % colours.length];
    c.style.animationDuration = `${2.2 + Math.random() * 2}s`;
    c.style.animationDelay = `${Math.random() * 0.8}s`;
    box.appendChild(c);
  }
}

/* ------------------------------------------------------------------ player */
const HERO_SPOTS = [240, 1180, 640, 1260, 360, 980, 520];
let bgFront = $('#bg-a');
let bgBack = $('#bg-b');

function stopNarration() {
  if (state.narration) state.narration.stop();
  state.narration = null;
  $('#player').classList.remove('paused');
}

async function playPage(token) {
  if (token !== state.playToken) return;
  stopNarration();
  const pid = state.path[state.pageIdx];
  const story = state.story;
  if (state.screen !== 'player') {
    show('player');
    $('#story-title').textContent = story.title || '';
    $('#hero-img').src = assetUrl(story.character.sprite_url);
  }
  $('#choice').classList.remove('show');
  renderDots();

  // Wait for this page (keep the previous art on screen with a painting indicator).
  let page = story.pages[pid];
  while (token === state.playToken && !(page && page.status === 'ready')) {
    $('#painting').classList.add('show');
    if (state.story.status === 'error') return showError(state.story.error);
    await sleep(400);
    page = state.story.pages[pid];
  }
  $('#painting').classList.remove('show');
  if (token !== state.playToken) return;

  // Background crossfade + hero movement.
  await swapBackground(assetUrl(page.bg_url));
  if (token !== state.playToken) return;
  moveHero(state.pageIdx, page.motion || story.character.motion);
  chime('page');

  state.narration = narrate($('#page-text'), {
    text: page.text,
    words: page.words || [],
    audioUrl: assetUrl(page.audio_url),
  });
  await state.narration.done;
  if (token !== state.playToken) return;
  await sleep(story.bedtime ? 1800 : 1200);
  if (token !== state.playToken) return;
  advance(token);
}

function swapBackground(url) {
  return new Promise((resolve) => {
    if (!url) return resolve();
    const img = bgBack;
    img.onload = () => {
      img.classList.add('show');
      bgFront.classList.remove('show');
      [bgFront, bgBack] = [bgBack, bgFront];
      resolve();
    };
    img.onerror = () => resolve();
    img.classList.remove('show');
    img.src = url;
  });
}

function moveHero(idx, motion) {
  const hero = $('#hero');
  const x = HERO_SPOTS[idx % HERO_SPOTS.length];
  hero.classList.toggle('flip', x < state.heroX);
  hero.className = hero.className.replace(/\bm-\w+/g, '').trim();
  hero.classList.add(`m-${motion || 'walk'}`);
  hero.style.transform = `translateX(${x}px)`;
  state.heroX = x;
}

function renderDots() {
  const total = 6;
  const dots = $('#page-dots');
  dots.innerHTML = '';
  for (let i = 0; i < total; i++) {
    const d = document.createElement('i');
    if (i === state.pageIdx) d.className = 'on';
    else if (i < state.pageIdx) d.className = 'done';
    dots.appendChild(d);
  }
}

function advance(token) {
  const atChoice = state.path.length === 3 && state.pageIdx === 2 && state.story.choice;
  if (atChoice) return showChoice();
  if (state.pageIdx < state.path.length - 1) {
    state.pageIdx += 1;
    return playPage(token);
  }
  showEnd();
}

function showChoice() {
  stopNarration();
  const choice = state.story.choice;
  $('#choice-prompt').textContent = choice.prompt;
  $('#choice-a .label').textContent = choice.options[0].label;
  $('#choice-b .label').textContent = choice.options[1].label;
  $('#choice').classList.add('show');
  focus.setRoot($('#choice'));
  chime('choice');
}

async function choose(optionId) {
  const opt = state.story.choice.options.find((o) => o.id === optionId);
  $('#choice').classList.remove('show');
  focus.setRoot($('#choice'), { focus: false });
  focus.focus(null);
  state.path = ['1', '2', '3', ...opt.path];
  state.pageIdx = 3;
  if (!state.demo) api.choose(state.storyId, optionId).catch(() => {});
  playPage(state.playToken);
}
$('#choice-a').addEventListener('click', () => choose('a'));
$('#choice-b').addEventListener('click', () => choose('b'));

function showEnd() {
  stopNarration();
  $('#end-sprite').src = assetUrl(state.story.character.sprite_url);
  $('#end-title').textContent = state.story.title || '';
  $('#end .saved').hidden = state.demo;
  show('end');
  chime('sparkle');
  if (!state.demo) setTimeout(loadShelf, 1500);
}
$('#again-btn').addEventListener('click', () => {
  if (state.demo) return startDemo();
  state.path = ['1', '2', '3'];
  state.pageIdx = 0;
  const token = ++state.playToken;
  playPage(token);
});
$('#new-btn').addEventListener('click', goHome);
$('#oops-btn').addEventListener('click', goHome);

function showError(message) {
  stopNarration();
  $('#oops-text').textContent = message || "Let's try that drawing again.";
  show('oops');
}

function goHome() {
  state.playToken++;
  stopNarration();
  setBedtime(new Date().getHours() >= 19 || new Date().getHours() < 6);
  show('home');
  loadShelf();
}

/* ------------------------------------------------------------------ remote */
remote.on((action) => {
  const screen = state.screen;
  if (action === 'back') {
    if (screen === 'home') return false; // let the Fire TV shell exit the app
    goHome();
    return true;
  }
  const choiceOpen = $('#choice').classList.contains('show');
  if (screen === 'player' && !choiceOpen) {
    if (action === 'select' || action === 'playpause') {
      const n = state.narration;
      if (!n) return true;
      if (n.paused) { n.resume(); $('#player').classList.remove('paused'); }
      else { n.pause(); $('#player').classList.add('paused'); }
      return true;
    }
    if (action === 'right' || action === 'next') {
      const token = ++state.playToken;
      advance(token);
      return true;
    }
    if (action === 'left' || action === 'prev') {
      if (state.pageIdx > 0) {
        state.pageIdx -= 1;
        if (state.pageIdx < 3) state.path = ['1', '2', '3'];
        playPage(++state.playToken);
      }
      return true;
    }
    return true;
  }
  if (screen === 'reveal' && (action === 'select' || action === 'right')) {
    return true; // reveal advances by itself once page 1 is ready
  }
  if (['up', 'down', 'left', 'right'].includes(action)) {
    focus.move(action);
    return true;
  }
  if (action === 'select') return focus.select();
  return false;
});

show('home');
startSession();
