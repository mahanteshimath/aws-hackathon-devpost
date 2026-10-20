/** Narration with read-along word highlighting.
 *
 * Sources, in order of preference:
 *  1. Amazon Polly mp3 + word speech marks (exact sync)
 *  2. Browser speechSynthesis boundary events (mock mode in a desktop browser)
 *  3. Estimated timings, silent (offline / no TTS available)
 */

export function renderReadAlong(el, text, words) {
  el.textContent = '';
  const spans = [];
  let cursor = 0;
  (words || []).forEach((w, i) => {
    if (w.s > cursor) el.appendChild(document.createTextNode(text.slice(cursor, w.s)));
    const span = document.createElement('span');
    span.className = 'w';
    span.textContent = text.slice(w.s, w.e);
    span.dataset.i = String(i);
    el.appendChild(span);
    spans.push(span);
    cursor = w.e;
  });
  if (cursor < text.length) el.appendChild(document.createTextNode(text.slice(cursor)));
  return spans;
}

function highlighter(spans) {
  let last = -1;
  return (idx) => {
    if (idx === last) return;
    for (let i = 0; i < spans.length; i++) {
      spans[i].classList.toggle('on', i === idx);
      spans[i].classList.toggle('read', i < idx);
    }
    last = idx;
  };
}

/**
 * Speak `text` and highlight words inside `el`. Returns a controller:
 *   { done: Promise<void>, pause(), resume(), stop(), paused }
 */
export function narrate(el, { text, words, audioUrl, rate = 1 }) {
  const spans = renderReadAlong(el, text, words);
  const mark = highlighter(spans);
  let raf = 0;
  let stopped = false;
  let resolveDone;
  const done = new Promise((r) => (resolveDone = r));
  const finish = () => {
    if (stopped) return;
    stopped = true;
    cancelAnimationFrame(raf);
    mark(spans.length); // everything read
    resolveDone();
  };
  const indexAt = (ms) => {
    let idx = -1;
    for (let i = 0; i < words.length; i++) if (words[i].t <= ms) idx = i;
    return idx;
  };

  const ctl = { done, paused: false, pause() {}, resume() {}, stop: finish };

  // 1. Polly audio with speech marks
  if (audioUrl) {
    const audio = new Audio(audioUrl);
    audio.playbackRate = 1;
    const tick = () => {
      mark(indexAt(audio.currentTime * 1000));
      if (!stopped) raf = requestAnimationFrame(tick);
    };
    audio.addEventListener('ended', finish);
    audio.addEventListener('error', () => fallbackTimer());
    audio.play().then(tick).catch(() => fallbackTimer());
    ctl.pause = () => { audio.pause(); ctl.paused = true; };
    ctl.resume = () => { audio.play().catch(() => {}); ctl.paused = false; };
    ctl.stop = () => { audio.pause(); finish(); };
    return ctl;
  }

  // 2. Browser TTS (desktop mock mode)
  if ('speechSynthesis' in window && window.SpeechSynthesisUtterance && !/AFT/.test(navigator.userAgent)) {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95 * rate;
    u.pitch = 1.1;
    let boundaryWorks = false;
    u.onboundary = (e) => {
      if (e.name && e.name !== 'word') return;
      boundaryWorks = true;
      const idx = words.findIndex((w) => e.charIndex >= w.s && e.charIndex < w.e + 1);
      if (idx >= 0) mark(idx);
    };
    u.onend = () => {
      // Some browsers "finish" instantly when no voices are installed - fall back to timed highlighting.
      const expected = words.length ? words[words.length - 1].t : 0;
      if (!boundaryWorks && performance.now() - startedAt < expected * 0.4) fallbackTimer();
      else finish();
    };
    u.onerror = () => fallbackTimer();
    speechSynthesis.cancel();
    const startedAt = performance.now();
    speechSynthesis.speak(u);
    setTimeout(() => { if (!boundaryWorks && !stopped && !speechSynthesis.speaking) fallbackTimer(); }, 1500);
    ctl.pause = () => { speechSynthesis.pause(); ctl.paused = true; };
    ctl.resume = () => { speechSynthesis.resume(); ctl.paused = false; };
    ctl.stop = () => { speechSynthesis.cancel(); finish(); };
    return ctl;
  }

  fallbackTimer();
  return ctl;

  // 3. Silent estimated timings
  function fallbackTimer() {
    if (stopped) return;
    cancelAnimationFrame(raf);
    const endAt = (words.length ? words[words.length - 1].t : 0) + 900;
    let elapsed = 0;
    let lastNow = performance.now();
    const tick = (now) => {
      if (!ctl.paused) elapsed += (now - lastNow) / rate;
      lastNow = now;
      mark(indexAt(elapsed));
      if (elapsed >= endAt) return finish();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    ctl.pause = () => { ctl.paused = true; };
    ctl.resume = () => { ctl.paused = false; };
    ctl.stop = finish;
  }
}

/** Tiny copyright-free sound effects made with WebAudio. */
let audioCtx = null;
export function chime(kind = 'sparkle') {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const notes = kind === 'page' ? [660, 880] : kind === 'choice' ? [523, 659, 784] : [784, 988, 1175, 1568];
    const t0 = audioCtx.currentTime;
    notes.forEach((f, i) => {
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'triangle';
      osc.frequency.value = f;
      gain.gain.setValueAtTime(0.0001, t0 + i * 0.09);
      gain.gain.exponentialRampToValueAtTime(0.12, t0 + i * 0.09 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.09 + 0.5);
      osc.connect(gain).connect(audioCtx.destination);
      osc.start(t0 + i * 0.09);
      osc.stop(t0 + i * 0.09 + 0.55);
    });
  } catch (_) {
    /* sound is optional */
  }
}
