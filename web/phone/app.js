import { api, assetUrl } from '../shared/api.js';

const $ = (s) => document.querySelector(s);
const params = new URLSearchParams(location.search);
let sid = params.get('s');
let photoBlob = null;

const hour = new Date().getHours();
$('#bedtime').checked = hour >= 19 || hour < 6;

function showOnly(id) {
  ['join', 'capture', 'status'].forEach((s) => ($(`#${s}`).hidden = s !== id));
}

async function connect() {
  try {
    await api.hello(sid);
    showOnly('capture');
  } catch (err) {
    sid = null;
    showOnly('join');
    $('#join-error').textContent = 'That TV link has expired. Enter the code shown on the TV.';
  }
}

$('#join-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('#join-error').textContent = '';
  try {
    const { session_id } = await api.code($('#join-code').value.trim());
    sid = session_id;
    history.replaceState(null, '', `?s=${sid}`);
    connect();
  } catch (_) {
    $('#join-error').textContent = "Hmm, that code didn't work. Check the TV and try again.";
  }
});

/** Downscale on the phone: faster upload, and image models work best at about 1 megapixel. */
async function resize(file, maxSide = 1280) {
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((resolve, reject) => {
      const i = new Image();
      i.onload = () => resolve(i);
      i.onerror = reject;
      i.src = url;
    });
    const scale = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.88));
  } finally {
    URL.revokeObjectURL(url);
  }
}

$('#photo').addEventListener('change', async (e) => {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  $('#error').textContent = '';
  try {
    photoBlob = await resize(file);
  } catch (_) {
    $('#error').textContent = "We couldn't read that photo. Try taking it again.";
    return;
  }
  const preview = $('#preview');
  preview.src = URL.createObjectURL(photoBlob);
  preview.hidden = false;
  $('#snap-text').hidden = true;
  $('#snap-label').classList.add('has-photo');
  $('#go').disabled = false;
});

$('#go').addEventListener('click', async () => {
  if (!photoBlob) return;
  $('#go').disabled = true;
  $('#go').textContent = 'Sending to the TV…';
  $('#error').textContent = '';
  try {
    const { story_id } = await api.createStory(sid, photoBlob, {
      kidName: $('#kid-name').value.trim(),
      theme: document.querySelector('input[name=theme]:checked').value,
      bedtime: $('#bedtime').checked,
    });
    $('#status-art').src = URL.createObjectURL(photoBlob);
    showOnly('status');
    watch(story_id);
  } catch (err) {
    $('#error').textContent = err.status === 429 ? "That's a lot of stories! Refresh the TV to start a new session." : 'Something went wrong sending the photo. Please try again.';
  } finally {
    $('#go').disabled = false;
    $('#go').textContent = 'Bring it to life';
  }
});

async function watch(storyId) {
  const text = {
    casting: 'Looking at your drawing…',
    cast: 'Your hero jumped off the paper!',
    writing: "Writing tonight's story…",
    rendering: 'Painting the world…',
    ready: 'Enjoy the show! Use the remote to choose what happens next.',
    error: 'The story machine hiccuped. Please try again.',
  };
  for (;;) {
    try {
      const doc = await api.story(storyId);
      $('#status-text').textContent = text[doc.status] || '';
      if (doc.character) {
        $('#status-title').textContent = `Meet ${doc.character.name}!`;
        $('#status-art').src = assetUrl(doc.character.sprite_url);
      }
      if (doc.status === 'ready' || doc.status === 'error') break;
    } catch (_) { /* retry */ }
    await new Promise((r) => setTimeout(r, 1500));
  }
  $('#another').hidden = false;
}

$('#another').addEventListener('click', () => {
  photoBlob = null;
  $('#preview').hidden = true;
  $('#snap-text').hidden = false;
  $('#snap-label').classList.remove('has-photo');
  $('#photo').value = '';
  $('#go').disabled = true;
  $('#another').hidden = true;
  showOnly('capture');
});

if (sid) connect();
else showOnly('join');
