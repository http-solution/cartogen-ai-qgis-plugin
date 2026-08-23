const DIRECTUS_URL = process.env.DIRECTUS_URL || 'http://localhost:8055';
const COOKIE_NAME = 'cartogen_session';

function parseCookies(header = '') {
  return Object.fromEntries(header.split(';').map((part) => {
    const index = part.indexOf('=');
    if (index < 0) return ['', ''];
    return [part.slice(0, index).trim(), decodeURIComponent(part.slice(index + 1).trim())];
  }).filter(([key]) => key));
}

function cookieOptions() {
  return [
    'HttpOnly',
    'Path=/',
    'SameSite=Lax',
    ...(process.env.NODE_ENV === 'production' ? ['Secure'] : []),
    'Max-Age=86400',
  ].join('; ');
}

async function directus(path, options = {}) {
  const response = await fetch(`${DIRECTUS_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = body?.errors?.[0]?.message || body?.message || `Directus request failed (${response.status})`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return body;
}

async function login(email, password) {
  return directus('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

async function register({ email, password, first_name, last_name }) {
  return directus('/users/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, first_name, last_name }),
  });
}

async function currentUser(req) {
  const token = parseCookies(req.headers.cookie)[COOKIE_NAME];
  if (!token) return null;
  try {
    const result = await directus('/users/me?fields=id,email,first_name,last_name,status,role', {
      headers: { Authorization: `Bearer ${token}` },
    });
    return { ...result.data, accessToken: token };
  } catch {
    return null;
  }
}

function setSession(res, accessToken) {
  res.setHeader('Set-Cookie', `${COOKIE_NAME}=${encodeURIComponent(accessToken)}; ${cookieOptions()}`);
}

function clearSession(res) {
  res.setHeader('Set-Cookie', `${COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0`);
}

async function requireUser(req, res, next) {
  const user = await currentUser(req);
  if (!user) return res.status(401).json({ error: 'authentication required' });
  req.user = user;
  return next();
}

module.exports = { currentUser, login, register, setSession, clearSession, requireUser };
