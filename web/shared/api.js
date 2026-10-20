/** Small API client shared by the TV and phone apps. Same-origin by default; override with ?api=https://... */

const params = new URLSearchParams(location.search);
export const API_BASE = (params.get('api') || '').replace(/\/$/, '');

async function request(method, path, { json, body, headers } = {}) {
  const init = { method, headers: { ...(headers || {}) } };
  if (json !== undefined) {
    init.body = JSON.stringify(json);
    init.headers['content-type'] = 'application/json';
  } else if (body !== undefined) {
    init.body = body;
  }
  const res = await fetch(API_BASE + path, init);
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) {
    const err = new Error(data.error || `HTTP ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return data;
}

/** Resolve URLs returned by the API (local dev returns root-relative /files/... paths). */
export function assetUrl(url) {
  if (!url) return url;
  return /^https?:|^data:|^blob:/.test(url) ? url : API_BASE + url;
}

export const api = {
  config: () => request('GET', '/api/config'),
  createSession: (householdId) => request('POST', '/api/sessions', { json: { household_id: householdId } }),
  session: (sid) => request('GET', `/api/sessions/${sid}`),
  hello: (sid) => request('POST', `/api/sessions/${sid}/hello`),
  code: (code) => request('GET', `/api/codes/${encodeURIComponent(code)}`),
  createStory: (sid, blob, { kidName, theme, bedtime }) =>
    request(
      'POST',
      `/api/sessions/${sid}/stories?` + new URLSearchParams({ kid_name: kidName || '', theme: theme || 'surprise', bedtime: bedtime ? '1' : '0' }),
      { body: blob, headers: { 'content-type': blob.type || 'image/jpeg' } },
    ),
  story: (id) => request('GET', `/api/stories/${id}`),
  choose: (id, option) => request('POST', `/api/stories/${id}/choice`, { json: { option } }),
  shelf: (hid) => request('GET', `/api/households/${hid}/shelf`),
};
