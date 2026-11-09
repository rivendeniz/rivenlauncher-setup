'use strict';

/* ------------------------------------------------------------ yardımcılar */
const TOKEN = document.querySelector('meta[name="riven-token"]').content;
const COLORS = [['#facc15', '#f59e0b'], ['#60a5fa', '#2563eb'], ['#f472b6', '#a855f7'], ['#fb7185', '#e11d48'],
  ['#34d399', '#059669'], ['#a78bfa', '#6d28d9'], ['#fb923c', '#ea580c'], ['#22d3ee', '#0891b2']];
const grad = (i) => `linear-gradient(135deg, ${COLORS[i % 8][0]}, ${COLORS[i % 8][1]})`;
const TYPES = {
  mods: { label: 'Modlar', ptype: 'mod' },
  resourcepacks: { label: 'Resource Pack', ptype: 'resourcepack' },
  shaders: { label: 'Shader', ptype: 'shader' },
};
const $ = (sel, root = document) => root.querySelector(sel);

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, opts = {}) {
  const res = await fetch('/api' + path, {
    method: opts.method || 'GET',
    headers: { 'X-Riven-Token': TOKEN, 'Content-Type': 'application/json' },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    keepalive: !!opts.keepalive,
  });
  let data = {};
  try { data = await res.json(); } catch (_) { /* boş yanıt */ }
  if (!res.ok) throw new Error(data.error || 'Hata ' + res.status);
  return data;
}

const ICONS = {
  home: '<path d="M3 11l9-8 9 8v9a2 2 0 0 1-2 2h-4v-6H9v6H5a2 2 0 0 1-2-2z"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
  terminal: '<path d="M4 17l6-5-6-5M12 19h8"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  play: '<path d="M7 4l13 8-13 8z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  download: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  upload: '<path d="M12 16V5M7 9l5-5 5 5M5 20h14"/>',
  package: '<path d="M21 8l-9-5-9 5v8l9 5 9-5zM3 8l9 5 9-5M12 13v8"/>',
  chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3M14 9l2 2"/>',
};
const INSTANCE_ICONS = {
  diamond: '<path d="M12 3L19 9L12 21L5 9Z"/><path d="M5 9H19M9 3L12 9L15 3" stroke-width="1.4"/>',
  star: '<path d="M12 2l2.9 6.6 7.1.6-5.4 4.7 1.7 7-6.3-3.9L5.7 21l1.7-7-5.4-4.7 7.1-.6z"/>',
  heart: '<path d="M12 21s-7.5-4.6-10-9.3C.6 8.1 2.6 5 6 5c2 0 3.5 1.1 4.3 2.4C11 6.1 12.5 5 14.5 5c3.4 0 5.4 3.1 4 6.7C19.5 16.4 12 21 12 21z"/>',
  sword: '<path d="M4 20L15 9M13 3l6 6-2.3 2.3-6-6zM4 20l-1.5 1.5M9 15l-2-2" stroke-width="2"/>',
  shield: '<path d="M12 2l8 3v6c0 5-3.4 8.7-8 11-4.6-2.3-8-6-8-11V5z"/>',
  skull: '<circle cx="12" cy="10" r="7"/><circle cx="9" cy="10" r="1.3" fill="#000" stroke="none"/><circle cx="15" cy="10" r="1.3" fill="#000" stroke="none"/><path d="M9 20h6l-1 2h-4z"/>',
  potion: '<path d="M10 2h4v4l3 4v9a2 2 0 01-2 2h-6a2 2 0 01-2-2v-9l3-4z" /><path d="M9 10h6" stroke-width="1.4"/>',
  chest: '<rect x="3" y="9" width="18" height="11" rx="2"/><path d="M3 13h18M10 9V6a2 2 0 012-2 2 2 0 012 2v3" stroke-width="1.6"/>',
  bolt: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  compass: '<circle cx="12" cy="12" r="9"/><path d="M15.5 8.5l-2 5-5 2 2-5z"/>',
  pickaxe: '<path d="M3 8c5-5 13-5 18 0-5 2-7 2-10 5l-3 3-2-2 3-3c3-3 3-5 5-10M6 15l3 3-3 4-4-4z" stroke-width="1.6"/>',
  anvil: '<path d="M5 8h4l2-3h2l2 3h4l2 3H3zM9 11h6v3H9z"/><rect x="8" y="14" width="8" height="3" rx="1"/>',
};
const ICON_KEYS = Object.keys(INSTANCE_ICONS);

function icon(name, size = 20, fill = false) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24');
  s.setAttribute('width', size);
  s.setAttribute('height', size);
  s.setAttribute('class', 'ic' + (fill ? ' fill' : ''));
  s.innerHTML = ICONS[name]; // yalnızca yukarıdaki sabit metinler
  return s;
}

const initial = (name) => ([...String(name).trim()][0] || '?').toUpperCase();
const hashColor = (s) => [...String(s)].reduce((a, c) => a + c.charCodeAt(0), 0) % 8;
const fmtNum = (n) => (n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K' : String(n));
const loaderName = (l) => (l === 'fabric' ? 'Fabric' : l === 'optifine' ? 'OptiFine' : 'Vanilla');
const cvars = (i) => `--c1:${COLORS[i % 8][0]};--c2:${COLORS[i % 8][1]}`;
const capitalize = (t) => String(t).charAt(0).toUpperCase() + String(t).slice(1);
const THEMES = { green: ['Yeşil', '#22c55e'], blue: ['Mavi', '#3b82f6'], purple: ['Mor', '#a855f7'],
  pink: ['Pembe', '#ec4899'], orange: ['Turuncu', '#f97316'] };
let currentTheme = '';
function applyTheme(name, accent) {
  currentTheme = (THEMES[name] || name === 'custom') ? name : 'green';
  document.documentElement.setAttribute('data-theme', currentTheme);
  applyAccent(currentTheme === 'custom' && /^#[0-9a-f]{6}$/i.test(accent || '') ? accent : '');
}
function timeAgo(ts) {
  if (!ts) return 'Hiç oynanmadı';
  const d = Math.max(0, Date.now() / 1000 - ts);
  if (d < 90) return 'Az önce';
  if (d < 3600) return `${Math.round(d / 60)} dk önce`;
  if (d < 86400) return `${Math.round(d / 3600)} sa önce`;
  return `${Math.round(d / 86400)} gün önce`;
}

function toast(msg, type = 'ok') {
  const t = h('div', { class: 'toast' + (type === 'error' ? ' error' : '') }, msg);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), type === 'error' ? 6500 : 3500);
}

function openModal(title, content, actions = []) {
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey); };
  const backdrop = h('div', { class: 'backdrop', onmousedown: (e) => { if (e.target === backdrop) close(); } },
    h('div', { class: 'modal' }, h('h3', {}, title), content,
      actions.length ? h('div', { class: 'modal-actions' }, actions.map((a) =>
        h('button', { class: 'btn ' + (a.cls || ''), onclick: () => a.fn(close) }, a.label))) : null));
  document.addEventListener('keydown', onKey);
  $('#modal-root').append(backdrop);
  return close;
}

function confirmDialog(text, okLabel = 'Evet') {
  return new Promise((resolve) => {
    openModal('Emin misin?', h('p', { class: 'muted' }, text), [
      { label: 'Vazgeç', fn: (close) => { close(); resolve(false); } },
      { label: okLabel, cls: 'danger', fn: (close) => { close(); resolve(true); } },
    ]);
  });
}

/* ------------------------------------------------------------ durum / anket */
let S = { status: 'Bağlanıyor...', progress: 0, running: [], preparing: null,
  account: { name: 'Oyuncu', mode: 'offline' } };
let logIdx = 0;
const logLines = [];
let lastKey = '';
let pollTimer = null;
let consoleEl = null;
const CACHE = { instances: [] };

function appendConsole(text) {
  if (!consoleEl || !consoleEl.isConnected) return;
  const nearBottom = consoleEl.scrollHeight - consoleEl.scrollTop - consoleEl.clientHeight < 80;
  consoleEl.append(document.createTextNode(text));
  if (nearBottom) consoleEl.scrollTop = consoleEl.scrollHeight;
}

/* Otomatik güncelleme çubuğu */
function renderUpdateBar(u) {
  let bar = document.getElementById('update-bar');
  const active = u && ['downloading', 'waiting', 'installing', 'available'].includes(u.state);
  if (!active) { if (bar) bar.remove(); return; }
  if (!bar) { bar = h('div', { id: 'update-bar', class: 'update-bar' }); document.body.append(bar); }
  const pct = Math.round((u.progress || 0) * 100);
  const text = u.state === 'downloading' ? `Yeni sürüm ${u.version} indiriliyor... %${pct}`
    : u.state === 'installing' ? `Sürüm ${u.version} kuruluyor, launcher yeniden açılacak...`
    : u.state === 'waiting' ? `Sürüm ${u.version} hazır, oyun kapanınca güncellenecek.`
    : (u.message || `Yeni sürüm ${u.version} mevcut.`);
  bar.textContent = '';
  bar.append(h('span', {}, text));
  if (u.state === 'downloading') bar.append(h('i', { style: `width:${pct}%` }));
}

async function pollOnce() {
  try {
    const s = await api('/state?since=' + logIdx);
    S = s;
    logIdx = s.log_idx;
    if (s.theme && (s.theme !== currentTheme || (s.theme === 'custom' && s.accent !== currentAccent))) applyTheme(s.theme, s.accent);
    for (const l of s.logs) {
      logLines.push(l.t);
      if (logLines.length > 3000) logLines.shift();
    }
    if (s.logs.length) appendConsole(s.logs.map((l) => l.t).join('\n') + '\n');
    renderStatus();
    renderTopbar();
    renderUpdateBar(s.update);
    const key = JSON.stringify([s.running, s.preparing]);
    if (key !== lastKey) {
      const first = lastKey === '';
      lastKey = key;
      renderRail();
      if (!first && ['home', 'instance'].includes(currentRoute.name)) route();
    }
  } catch (_) {
    S.status = 'Bağlantı kesildi';
    renderStatus();
  }
}

function schedulePoll() {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    await pollOnce();
    schedulePoll();
  }, (S.preparing || S.running.length) ? 600 : 1500);
}

let whoKey = '';
function renderTopbar() {
  const a = S.account || {};
  const key = `${a.name}|${a.mode}|${typeof skinRev === 'undefined' ? 0 : skinRev}`;
  const bar = $('#topbar');
  if (key === whoKey && bar.children.length) return;
  whoKey = key;
  bar.replaceChildren(
    h('button', { class: 'who', title: 'Hesap ayarları', onclick: () => { location.hash = '#/account'; } },
      h('span', { class: 'mini' }, skinHead(skinFor(a.name || ''), 26)), h('span', {}, a.name || 'Oyuncu')),
    h('button', { class: 'fps-btn', title: '1.21.11 için en iyi FPS modlarını otomatik kur', onclick: fpsBoost },
      icon('bolt', 15, true), 'FPS'));
}

function buildStatusbar() {
  $('#statusbar').replaceChildren(
    h('span', { id: 'sb-dot', class: 'dot' }), h('span', { id: 'sb-text' }, 'Hazır'),
    h('div', { class: 'bar' }, h('div', { class: 'fill', id: 'sb-fill' })), h('span', { id: 'sb-run' }));
}

function renderStatus() {
  $('#sb-text').textContent = S.status;
  $('#sb-fill').style.width = Math.round((S.progress || 0) * 100) + '%';
  $('#sb-dot').className = 'dot' + ((S.running.length || S.preparing) ? ' on' : '');
  $('#sb-run').textContent = S.running.length ? `${S.running.length} oyun açık` : '';
}

/* ---------------------------------------------------------------- yönlendirme */
const NAV = [['browse', 'compass', 'Keşfet (Modrinth / CurseForge)'], ['console', 'terminal', 'Konsol'],
  ['chat', 'chat', 'Mesajlar'], ['account', 'user', 'Hesap ve Discord']];
let currentRoute = { name: 'home' };
let routeSeq = 0;
let lastRendered = null;

async function loadInstances() {
  const res = await api('/instances');
  CACHE.instances = res.instances;
  renderRail();
  return res.instances;
}

/* Sol çubuk: varsayılan olarak ilk 4 instance görünür; çizgiye basınca hepsi açılır, alttaki menü kayıp kapanır */
let RAIL_OPEN = false;
const RAIL_PREVIEW = 4;

function railInstButtons() {
  const activeId = currentRoute.name === 'instance' ? currentRoute.arg : null;
  const list = RAIL_OPEN ? CACHE.instances : CACHE.instances.slice(0, RAIL_PREVIEW);
  return list.map((inst) =>
    h('button', { class: 'rail-inst' + (inst.id === activeId ? ' active' : '') + (inst.custom_icon ? ' has-img' : ''),
      title: `${inst.name} • ${inst.mc_version}`, style: `background:${grad(inst.color)}`,
      onclick: () => { location.hash = '#/instance/' + inst.id; } },
    instanceGlyph(inst, 46), S.running.includes(inst.id) ? h('span', { class: 'live' }) : null));
}

function toggleRail() {
  RAIL_OPEN = !RAIL_OPEN;
  const rail = $('#rail');
  rail.classList.toggle('expanded', RAIL_OPEN);
  const box = rail.querySelector('.rail-instances');
  box.replaceChildren(...railInstButtons());
  box.scrollTop = 0;
  const t = rail.querySelector('.rail-toggle');
  if (t) t.title = RAIL_OPEN ? 'Küçült' : 'Tüm instance\'ları göster';
}

function renderRail() {
  if (CACHE.instances.length <= RAIL_PREVIEW) RAIL_OPEN = false;
  const prev = $('#rail .rail-instances');
  const prevTop = prev ? prev.scrollTop : 0;
  $('#rail').classList.toggle('expanded', RAIL_OPEN);
  $('#rail').replaceChildren(
    h('button', { class: 'logo', title: 'Ana sayfa', onclick: () => { location.hash = '#/home'; } },
      h('img', { src: '/favicon-180.png', alt: 'Riven', class: 'logo-img' })),
    h('div', { class: 'rail-sep' }),
    h('div', { class: 'rail-instances' }, railInstButtons()),
    h('button', { class: 'rail-add', title: 'Yeni instance oluştur', onclick: newInstanceModal }, icon('plus', 20)),
    CACHE.instances.length > RAIL_PREVIEW
      ? h('button', { class: 'rail-toggle', title: RAIL_OPEN ? 'Küçült' : 'Tüm instance\'ları göster', onclick: toggleRail }, h('i'))
      : null,
    h('div', { class: 'rail-bottom' }, NAV.map(([name, ic, label]) =>
      h('button', { class: 'rail-btn' + (currentRoute.name === name ? ' active' : ''), title: label,
        onclick: () => { location.hash = '#/' + name; } }, icon(ic, 21),
      name === 'chat' && chatUnreadTotal() ? h('span', { class: 'rail-badge' }, String(Math.min(chatUnreadTotal(), 9))) : null))));
  if (RAIL_OPEN) $('#rail .rail-instances').scrollTop = prevTop;
}

function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [path, qstr = ''] = raw.split('?');
  const parts = path.split('/');
  return { name: parts[0] || 'home', arg: parts[1], q: Object.fromEntries(new URLSearchParams(qstr)) };
}

async function route() {
  currentRoute = parseHash();
  if (!['browse', 'project'].includes(currentRoute.name)) B.appliedHash = null;
  const my = ++routeSeq;
  const view = $('#view');
  const top = view.scrollTop;
  CHAT.onUpdate = null;
  renderRail();
  consoleEl = null;
  let nodes;
  try {
    switch (currentRoute.name) {
      case 'home': nodes = await pageHome(); break;
      case 'instance': nodes = await pageInstance(currentRoute.arg); break;
      case 'browse': nodes = await pageBrowse(currentRoute.q); break;
      case 'project': nodes = await pageProject(currentRoute.arg, currentRoute.q); break;
      case 'console': nodes = pageConsole(); break;
      case 'chat': nodes = await pageChat(); break;
      case 'account': nodes = await pageAccount(); break;
      default: location.hash = '#/home'; return;
    }
  } catch (e) {
    nodes = h('div', { class: 'panel empty' }, h('h3', {}, 'Bir şeyler ters gitti'),
      h('p', { class: 'muted' }, e.message));
  }
  if (my !== routeSeq) return;
  const navigated = location.hash !== lastRendered;
  lastRendered = location.hash;
  view.classList.remove('enter');
  if (navigated) {
    view.classList.add('enter');
    setTimeout(() => view.classList.remove('enter'), 900);
  }
  view.replaceChildren(...[nodes].flat());
  view.scrollTop = navigated ? 0 : top;
}

/* ---------------------------------------------------------------- oyun / instance */
function playState(inst) {
  if (S.running.includes(inst.id)) return { label: 'Çalışıyor', disabled: true };
  if (S.preparing === inst.id) return { label: 'Hazırlanıyor…', disabled: true };
  if (S.preparing) return { label: 'Meşgul', disabled: true };
  return { label: 'Oyna', disabled: false };
}

async function launch(id, repair = false) {
  try {
    await api(`/instances/${id}/launch`, { method: 'POST', body: { repair } });
    toast('Başlatılıyor…');
    await pollOnce();
  } catch (e) { toast(e.message, 'error'); }
}

function playButton(inst, big) {
  const st = playState(inst);
  return h('button', { class: 'btn primary' + (big ? ' big' : ''), disabled: st.disabled,
    onclick: () => launch(inst.id) }, icon('play', big ? 20 : 16, true), st.label);
}

function instanceGlyph(inst, size) {
  if (inst.custom_icon) {
    return h('img', { class: 'tile-img', src: `/instance-icon/${inst.id}.png?v=${inst.icon_rev || 0}`, alt: '',
      style: `width:${size}px;height:${size}px` });
  }
  const svg = icon('bolt', Math.round(size * 0.52), true);
  svg.innerHTML = INSTANCE_ICONS[inst.icon_key] || INSTANCE_ICONS.diamond;
  svg.style.color = 'rgba(255,255,255,.95)';
  svg.style.filter = 'drop-shadow(0 2px 3px rgba(0,0,0,.35))';
  return svg;
}

function art(inst, extra, size = 64) {
  return h('div', { class: 'tile-art' + (inst.custom_icon ? ' has-img' : ''), style: `background:${grad(inst.color)};${cvars(inst.color)}` },
    instanceGlyph(inst, size), extra);
}

function stat(label, value) {
  return h('div', { class: 'stat' }, h('div', { class: 'stat-l' }, label), h('div', { class: 'stat-v' }, String(value)));
}

function heroStats(inst) {
  return h('div', { class: 'stats' }, stat('Sürüm', inst.mc_version), stat('Loader', loaderName(inst.loader)),
    inst.loader === 'fabric' ? stat('Mod', inst.counts.mods) : null,
    stat('RAM', `${(inst.ram / 1024).toFixed(1).replace('.0', '')} GB`), stat('Son oyun', timeAgo(inst.last_played)));
}

function tile(inst) {
  const st = playState(inst);
  const play = h('button', { class: 'tile-play', title: st.label, disabled: st.disabled,
    onclick: (e) => { e.stopPropagation(); launch(inst.id); } }, icon('play', 18, true));
  return h('div', { class: 'tile', style: cvars(inst.color), onclick: () => { location.hash = '#/instance/' + inst.id; } },
    art(inst, play), h('div', { class: 'tile-name' }, inst.name),
    h('div', { class: 'tile-meta' }, `${inst.mc_version} • ${loaderName(inst.loader)} • ${inst.counts.mods} mod`));
}

function newTile() {
  return h('div', { class: 'tile new', onclick: newInstanceModal },
    h('div', { class: 'tile-art' }, '+'), h('div', { class: 'tile-name' }, 'Yeni instance'),
    h('div', { class: 'tile-meta' }, 'Farklı modlarla ayrı bir dünya'));
}

async function pageHome() {
  const instances = await loadInstances();
  const nodes = [h('header', { class: 'page-head' },
    h('div', {}, h('h1', {}, `Merhaba, ${S.account.name}`), h('p', { class: 'sub' }, 'Bugün hangi dünyaya dalıyoruz?')),
    h('button', { class: 'btn primary', onclick: newInstanceModal }, icon('plus', 18), 'Yeni instance'))];

  if (!instances.length) {
    nodes.push(h('div', { class: 'panel empty' }, h('div', { class: 'empty-orb' }, icon('plus', 34)),
      h('h3', {}, 'İlk instance\'ını oluştur'),
      h('p', { class: 'muted' }, 'Her instance\'ın kendi modları, dünyaları ve ayarları olur. İstediğin kadar kur.'),
      h('button', { class: 'btn primary', onclick: newInstanceModal }, icon('plus', 18), 'Instance oluştur')));
    return nodes;
  }
  const last = [...instances].sort((a, b) => (b.last_played || 0) - (a.last_played || 0))[0];
  nodes.push(h('div', { class: 'panel hero', style: cvars(last.color) }, art(last),
    h('div', { class: 'hero-info' },
      h('div', { class: 'eyebrow' }, last.last_played ? 'SON OYNANAN' : 'BAŞLAMAYA HAZIR'),
      h('h3', {}, last.name), heroStats(last),
      h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap;margin-top:20px' }, playButton(last, true),
        h('button', { class: 'btn big', onclick: () => { location.hash = '#/instance/' + last.id; } }, 'Aç')))));
  nodes.push(h('h2', {}, 'INSTANCE\'LARIN', h('span', { class: 'count' }, String(instances.length))));
  nodes.push(h('div', { class: 'grid' }, instances.map(tile), newTile()));
  return nodes;
}

function swatchPicker(initialColor, onPick) {
  const wrap = h('div', { class: 'swatches' });
  COLORS.forEach((_, i) => {
    const s = h('div', { class: 'swatch' + (i === initialColor ? ' sel' : ''), style: `background:${grad(i)}`,
      onclick: () => {
        wrap.querySelectorAll('.swatch').forEach((x) => x.classList.remove('sel'));
        s.classList.add('sel');
        onPick(i);
      } });
    wrap.append(s);
  });
  return wrap;
}

async function newInstanceModal() {
  let versions, def;
  try { ({ versions, default: def } = await api('/versions')); } catch (e) { toast(e.message, 'error'); return; }
  // Fabric yalnızca 1.14 ve üstünü destekler; 1.14 altında varsayılan OptiFine olur (Vanilla seçilirse Vanilla kalır)
  const fabricOk = (v) => { const p = String(v).split('.').map(Number); return p[0] > 1 || (p[0] === 1 && (p[1] || 0) >= 14); };
  let loader = fabricOk(def) ? 'fabric' : 'optifine';
  let color = Math.floor(Math.random() * 8);
  const name = h('input', { class: 'input', value: 'Yeni Instance', maxlength: 32 });
  const ver = h('select', { class: 'select' }, versions.map((v) => h('option', { value: v, selected: v === def }, v)));
  const segFabric = h('button', { class: 'sel', onclick: () => pick('fabric') }, 'Fabric (mod destekli)');
  const segOpti = h('button', { onclick: () => pick('optifine') }, 'OptiFine');
  const segVanilla = h('button', { onclick: () => pick('vanilla') }, 'Vanilla');
  function pick(l) {
    loader = l;
    segFabric.classList.toggle('sel', l === 'fabric');
    segOpti.classList.toggle('sel', l === 'optifine');
    segVanilla.classList.toggle('sel', l === 'vanilla');
  }
  function syncLoader() {
    const ok = fabricOk(ver.value);
    segFabric.disabled = !ok;
    segFabric.title = ok ? '' : 'Fabric 1.14 ve üstü sürümlerde kullanılabilir';
    segOpti.disabled = ok;
    segOpti.title = ok ? 'OptiFine seçeneği 1.14 öncesi sürümler içindir' : '';
    segFabric.style.display = ok ? '' : 'none';
    segOpti.style.display = ok ? 'none' : '';
    if (loader !== 'vanilla') pick(ok ? 'fabric' : 'optifine');   // Vanilla bilinçli seçimdir, korunur
    else pick('vanilla');
  }
  ver.addEventListener('change', syncLoader);
  syncLoader();
  const body = h('div', { class: 'form', style: 'padding:0;gap:16px' },
    h('label', {}, 'Ad', name), h('label', {}, 'Minecraft sürümü', ver),
    h('label', {}, 'Loader', h('div', { class: 'seg' }, segFabric, segOpti, segVanilla)),
    h('label', {}, 'Renk', swatchPicker(color, (i) => { color = i; })));
  openModal('Yeni instance', body, [
    { label: 'Vazgeç', fn: (close) => close() },
    { label: 'Oluştur', cls: 'primary', fn: async (close) => {
      try {
        const r = await api('/instances', { method: 'POST',
          body: { name: name.value, mc_version: ver.value, loader, color } });
        close();
        location.hash = '#/instance/' + r.instance.id;
      } catch (e) { toast(e.message, 'error'); }
    } },
  ]);
}

let instTab = 'mods';

async function localInfoModal(id, type, it) {
  const body = h('div', { class: 'muted' }, 'Yükleniyor…');
  openModal(it.title, body, [{ label: 'Kapat', fn: (close) => close() }]);
  try {
    const d = await api(`/instances/${id}/content/info?` + new URLSearchParams({ type, filename: it.filename }));
    const links = [['Web sitesi', d.homepage], ['Kaynak kodu', d.sources]].filter(([, u]) => u && /^https:\/\//i.test(u));
    const MB = (d.size / 1048576).toFixed(2);
    body.replaceChildren(
      h('div', { class: 'row', style: 'gap:14px;align-items:center;margin-bottom:14px' }, thumb(it),
        h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, d.title),
          h('div', { class: 'row-sub', style: 'white-space:normal' },
            [d.version, (d.authors || []).join(', '), `${MB} MB`].filter(Boolean).join(' • ')))),
      h('p', { style: 'margin:0 0 14px;line-height:1.55;white-space:pre-wrap' },
        d.description || 'Bu dosya açıklama içermiyor ve Modrinth\'te eşleşen bir proje bulunamadı.'),
      links.length ? h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, links.map(([l, u]) =>
        h('button', { class: 'btn small', onclick: () => openExternal(u) }, icon('link', 14), l))) : null,
      h('div', { class: 'row-sub', style: 'margin-top:12px;white-space:normal' }, d.filename));
  } catch (e) { body.textContent = e.message; }
}

function thumb(item) {
  if (item.icon) {
    const img = h('img', { class: 'thumb', src: item.icon, alt: '' });
    img.addEventListener('error', () => img.replaceWith(h('div', { class: 'thumb', style: `background:${grad(hashColor(item.title))}` }, initial(item.title))));
    return img;
  }
  return h('div', { class: 'thumb', style: `background:${grad(hashColor(item.title))}` }, initial(item.title));
}

async function pageInstance(id) {
  const instances = await loadInstances();
  const inst = instances.find((i) => i.id === id);
  if (!inst) { location.hash = '#/home'; return []; }
  if (inst.loader !== 'fabric' && instTab === 'mods') instTab = 'resourcepacks';
  const { items } = await api(`/instances/${id}/content?type=${instTab}`);

  const tabs = Object.entries(TYPES).filter(([k]) => !(k === 'mods' && inst.loader !== 'fabric'))
    .map(([k, t]) => h('button', { class: 'tab' + (k === instTab ? ' active' : ''),
      onclick: () => { instTab = k; route(); } }, t.label, h('span', { class: 'tab-n' }, String(inst.counts[k]))));

  const rows = items.map((it) => {
    const href = indexedProjectHref(it.project_id, id, TYPES[instTab].ptype);
    const go = href ? () => { location.hash = href; } : () => localInfoModal(id, instTab, it);
    return h('div', { class: 'panel row' + (it.enabled ? '' : ' off') }, 
    h('div', { class: 'clickable', onclick: go, title: 'Detayları aç' }, thumb(it)),
    h('div', { class: 'row-main clickable', onclick: go, title: href ? 'Açıklama, bağlantı ve sürüm değiştirme' : 'Dosya bilgileri' },
      h('div', { class: 'row-title' }, it.title),
      h('div', { class: 'row-sub' }, it.version ? `${it.version} • ${it.filename}` : it.filename)),
    h('button', { class: 'btn small', title: href ? 'Açıklama, web sitesi bağlantısı ve sürüm değiştirme' : 'Dosya bilgileri', onclick: go },
      icon('compass', 14), href ? 'Detay / Sürüm' : 'Detay'),
    h('button', { class: 'toggle' + (it.enabled ? ' on' : ''), title: it.enabled ? 'Kapat' : 'Aç',
      onclick: async () => {
        try { await api(`/instances/${id}/content/toggle`, { method: 'POST', body: { type: instTab, filename: it.filename } }); route(); }
        catch (e) { toast(e.message, 'error'); }
      } }),
    h('button', { class: 'icon-btn', title: 'Sil', onclick: async () => {
      if (!(await confirmDialog(`"${it.title}" silinsin mi?`, 'Sil'))) return;
      try { await api(`/instances/${id}/content/delete`, { method: 'POST', body: { type: instTab, filename: it.filename } }); route(); }
      catch (e) { toast(e.message, 'error'); }
    } }, icon('trash', 17)));
  });

  return [
    h('button', { class: 'btn small', style: 'margin-bottom:16px', onclick: () => { location.hash = '#/home'; } },
      icon('back', 15), 'Geri'),
    h('div', { class: 'panel hero', style: cvars(inst.color) }, art(inst),
      h('div', { class: 'hero-info' }, h('div', { class: 'eyebrow' }, 'INSTANCE'), h('h3', {}, inst.name),
        heroStats(inst),
        h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap;margin-top:20px' }, playButton(inst, true),
          h('button', { class: 'btn big', onclick: () => api(`/instances/${id}/folder`, { method: 'POST' }).catch((e) => toast(e.message, 'error')) },
            icon('folder', 18), 'Klasör'),
          h('button', { class: 'btn big', onclick: () => settingsModal(inst) }, icon('gear', 18), 'Ayarlar')))),
    h('div', { class: 'tabs' }, tabs),
    h('div', { style: 'display:flex;justify-content:flex-end;margin-bottom:12px' },
      h('button', { class: 'btn primary small', onclick: () => {
        location.hash = `#/browse?instance=${id}&type=${TYPES[instTab].ptype}`;
      } }, icon('compass', 15), 'Keşfet\'ten ekle')),
    items.length ? h('div', { class: 'list' }, rows)
      : h('div', { class: 'panel empty' }, h('p', { class: 'muted' }, 'Burada henüz bir şey yok. Modrinth veya CurseForge\'dan ekleyebilirsin.')),
  ];
}

function resizeImageFile(file, size = 256) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Dosya okunamadı'));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error('Resim açılamadı'));
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        const ctx = canvas.getContext('2d');
        const s = Math.min(img.width, img.height);
        ctx.drawImage(img, (img.width - s) / 2, (img.height - s) / 2, s, s, 0, 0, size, size);
        resolve(canvas.toDataURL('image/png'));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

function iconPicker(inst, onPickBuiltin) {
  let liveInst = { ...inst };
  const preview = h('div', { class: 'icon-preview' + (liveInst.custom_icon ? ' has-img' : ''), style: `background:${grad(inst.color)}` }, instanceGlyph(liveInst, 64));
  const refreshPreview = () => { preview.classList.toggle('has-img', !!liveInst.custom_icon); preview.replaceChildren(instanceGlyph(liveInst, 64)); };
  function choiceGlyph(key) {
    const s = icon('bolt', 20, true);
    s.innerHTML = INSTANCE_ICONS[key];
    return s;
  }
  const grid = h('div', { class: 'icon-grid' }, ICON_KEYS.map((key) =>
    h('button', { class: 'icon-choice' + (key === inst.icon_key && !inst.custom_icon ? ' sel' : ''), title: key,
      onclick: (e) => {
        grid.querySelectorAll('.icon-choice').forEach((b) => b.classList.remove('sel'));
        e.currentTarget.classList.add('sel');
        liveInst = { ...liveInst, icon_key: key, custom_icon: false };
        refreshPreview();
        onPickBuiltin(key);
      } }, choiceGlyph(key))));
  const fileInput = h('input', { type: 'file', accept: 'image/*', style: 'display:none' });
  const uploadBtn = h('button', { class: 'btn small', onclick: () => fileInput.click() }, 'Resim yükle');
  const resetBtn = h('button', { class: 'btn small', style: inst.custom_icon ? '' : 'display:none',
    onclick: async () => {
      try {
        const r = await api(`/instances/${inst.id}/icon/reset`, { method: 'POST' });
        liveInst = r.instance; refreshPreview(); resetBtn.style.display = 'none';
        toast('Yüklenen resim kaldırıldı');
      } catch (e) { toast(e.message, 'error'); }
    } }, 'Yüklenen resmi kaldır');
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;
    try {
      const dataUrl = await resizeImageFile(file);
      const r = await api(`/instances/${inst.id}/icon`, { method: 'POST', body: { data_url: dataUrl } });
      liveInst = r.instance; refreshPreview();
      resetBtn.style.display = '';
      toast('İkon güncellendi');
    } catch (e) { toast(e.message, 'error'); }
  });
  return h('div', { style: 'display:flex;flex-direction:column;gap:12px' },
    h('div', { style: 'display:flex;gap:14px;align-items:center' }, preview,
      h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, uploadBtn, resetBtn, fileInput)),
    grid);
}

function settingsModal(inst) {
  let color = inst.color;
  let iconKey = null;  // sadece kullanıcı hazır bir ikon seçerse doldurulur
  const name = h('input', { class: 'input', value: inst.name, maxlength: 32 });
  const ramLabel = h('span', {}, `${(inst.ram / 1024).toFixed(1)} GB`);
  const ram = h('input', { type: 'range', min: 1024, max: 16384, step: 512, value: inst.ram,
    oninput: () => { ramLabel.textContent = `${(ram.value / 1024).toFixed(1)} GB`; } });
  const body = h('div', { class: 'form', style: 'padding:0;gap:16px' },
    h('label', {}, 'Ad', name), h('label', {}, h('span', {}, 'RAM: ', ramLabel), ram),
    h('label', {}, 'İkon', iconPicker(inst, (key) => { iconKey = key; })),
    h('label', {}, 'Renk', swatchPicker(color, (i) => { color = i; })),
    h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap' },
      h('button', { class: 'btn small', onclick: () => { launch(inst.id, true); } }, 'Dosyaları onar ve başlat'),
      h('button', { class: 'btn small danger', onclick: async () => {
        if (!(await confirmDialog(`"${inst.name}" ve içindeki tüm dünyalar/modlar kalıcı olarak silinecek.`, 'Sil'))) return;
        try { await api(`/instances/${inst.id}/delete`, { method: 'POST' }); closeAll(); location.hash = '#/home'; }
        catch (e) { toast(e.message, 'error'); }
      } }, 'Instance\'ı sil')));
  let closeAll = () => {};
  closeAll = openModal('Instance ayarları', body, [
    { label: 'Vazgeç', fn: (close) => close() },
    { label: 'Kaydet', cls: 'primary', fn: async (close) => {
      try {
        const payload = { name: name.value, ram: Number(ram.value), color };
        if (iconKey) payload.icon_key = iconKey;
        await api(`/instances/${inst.id}/update`, { method: 'POST', body: payload });
        close();
        route();
      } catch (e) { toast(e.message, 'error'); }
    } },
  ]);
}

/* ------------------------------------------------------- Keşfet: Modrinth + CurseForge */
const SOURCES = { modrinth: 'Modrinth', curseforge: 'CurseForge' };
const BTYPES = [['mod', 'Modlar'], ['modpack', 'Modpack\'ler'], ['resourcepack', 'Resource Pack'], ['shader', 'Shader']];
const SORTS = [['relevance', 'İlgili'], ['downloads', 'En çok indirilen'], ['updated', 'Son güncellenen'], ['newest', 'En yeni']];
const B = { source: 'modrinth', q: '', type: 'mod', instance: null, sort: 'relevance', mc: '', offset: 0,
  hits: [], total: 0, seq: 0, ui: null, timer: null, cf: { configured: false } };

const openExternal = (url) => api('/open-external', { method: 'POST', body: { url } })
  .catch((e) => toast(e.message, 'error'));

function skeletons(n) {
  return Array.from({ length: n }, () => h('div', { class: 'panel card' },
    h('div', { class: 'card-top' }, h('div', { class: 'thumb skel-box' }),
      h('div', { class: 'row-main' }, h('div', { class: 'skel-line w60' }), h('div', { class: 'skel-line w40' }))),
    h('div', { class: 'skel-line' }), h('div', { class: 'skel-line w80' })));
}

/* CurseForge API anahtarı formu (Keşfet ve Hesap sayfasında ortak) */
function cfKeyForm(st, onDone) {
  if (st.baked) return h('p', { class: 'muted', style: 'margin:0' }, 'Bu launcher\'a yerleşik bir CurseForge anahtarı tanımlı; ek bir şey yapman gerekmiyor.');
  const input = h('input', { class: 'input', type: 'password', autocomplete: 'off', spellcheck: 'false',
    placeholder: st.configured ? '•••••••• (kayıtlı; değiştirmek için yeni anahtarı yapıştır)' : 'CurseForge API anahtarını yapıştır' });
  const save = h('button', { class: 'btn primary', onclick: async () => {
    if (!input.value.trim()) { toast('Önce anahtarı yapıştır.', 'error'); return; }
    save.disabled = true; save.textContent = 'Deneniyor…';
    try { await api('/curseforge/key', { method: 'POST', body: { key: input.value.trim() } }); toast('CurseForge bağlandı'); onDone(); }
    catch (e) { toast(e.message, 'error'); save.disabled = false; save.textContent = 'Kaydet ve dene'; }
  } }, 'Kaydet ve dene');
  const getKey = h('button', { class: 'btn', onclick: () => openExternal('https://console.curseforge.com/') },
    icon('link', 15), 'Anahtar al (ücretsiz)');
  const remove = st.configured ? h('button', { class: 'btn danger', onclick: async () => {
    try { await api('/curseforge/key', { method: 'POST', body: { key: '' } }); toast('Anahtar silindi'); onDone(); }
    catch (e) { toast(e.message, 'error'); }
  } }, 'Kaldır') : null;
  return h('div', { class: 'form-col' }, input, h('div', { class: 'row-actions' }, save, getKey, remove));
}

function cfSetupPanel() {
  return h('div', { class: 'panel setup', style: 'grid-column:1/-1' },
    h('div', { class: 'empty-orb' }, icon('key', 30)),
    h('h3', {}, 'CurseForge\'u bağla'),
    h('p', { class: 'muted', style: 'margin:0 0 6px;line-height:1.55;max-width:520px' },
      'CurseForge, üçüncü taraf launcher\'ların kişisel bir API anahtarı kullanmasını ister. Anahtar ücretsizdir: ' +
      'console.curseforge.com adresinde giriş yap, "API Keys" bölümünden anahtarı kopyalayıp aşağı yapıştır. ' +
      'Anahtar bu bilgisayarda, sistem kimlik deposunda tutulur.'),
    cfKeyForm(B.cf, () => route()));
}

/* Yazarı launcher indirmesine izin vermeyen dosyalar için elle indirme listesi */
function manualList(items) {
  return h('div', { class: 'list', style: 'margin-top:12px' }, items.map((it) => h('div', { class: 'panel row' },
    h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, it.title)),
    it.url ? h('button', { class: 'btn small', onclick: () => openExternal(it.url) }, icon('link', 14), 'Sayfayı aç') : null)));
}

function jobReport(st) {
  const parts = [];
  if (st.manual && st.manual.length) {
    parts.push(h('div', { class: 'notice', style: 'margin:0' },
      `${st.manual.length} dosyanın yazarı launcher'dan indirmeye izin vermiyor. Sayfalarından elle indirip instance'ın mods klasörüne koy:`),
    manualList(st.manual));
  }
  if (st.failed && st.failed.length) {
    parts.push(h('p', { class: 'muted', style: 'margin:14px 0 4px;font-weight:700' }, `${st.failed.length} dosya indirilemedi:`),
      h('div', { class: 'job-fail' }, st.failed.slice(0, 8).map((f) => h('div', {}, f)),
        st.failed.length > 8 ? h('div', {}, `… ve ${st.failed.length - 8} tane daha`) : null));
  }
  if (!parts.length) return;
  const actions = [{ label: 'Kapat', fn: (c) => c() }];
  if (st.instance) actions.unshift({ label: 'Klasörü aç', fn: () => api(`/instances/${st.instance}/folder`, { method: 'POST' })
    .catch((e) => toast(e.message, 'error')) });
  openModal('Kurulum özeti', h('div', {}, parts), actions);
}

function watchJob() {
  const msg = h('div', { class: 'job-msg' }, 'Başlıyor…');
  const fill = h('div', { class: 'pfill' });
  const body = h('div', {}, h('p', { class: 'muted', style: 'margin:0 0 16px;line-height:1.5' },
    'Pencereyi kapatabilirsin; kurulum arka planda sürer. Alttaki çubuktan ilerlemeyi izleyebilirsin.'),
  msg, h('div', { class: 'pbar' }, fill));
  const close = openModal('Paket kuruluyor', body, [{ label: 'Arka planda devam et', fn: (c) => c() }]);
  const tick = async () => {
    let st;
    try { st = await api('/modpack/status'); } catch (_) { setTimeout(tick, 2000); return; }
    msg.textContent = st.message || '';
    fill.style.width = Math.round((st.progress || 0) * 100) + '%';
    if (st.state === 'running') { setTimeout(tick, 900); return; }
    const open = body.isConnected;
    close();
    await loadInstances();
    if (st.state === 'done') {
      toast('Paket kuruldu');
      if (open) location.hash = '#/instance/' + st.instance;
      jobReport(st);
    } else if (st.state === 'error') {
      openModal('Kurulum başarısız', h('div', {}, h('div', { class: 'notice', style: 'margin:0' }, st.error || 'Bilinmeyen hata'),
        st.manual && st.manual.length ? manualList(st.manual) : null), [{ label: 'Kapat', fn: (c) => c() }]);
    }
  };
  tick();
}

function modpackModal(hit, source) {
  const name = h('input', { class: 'input', value: hit.title.slice(0, 32), maxlength: 32 });
  openModal(`${hit.title}`, h('div', { class: 'form-col' },
    h('p', { class: 'muted', style: 'margin:0;line-height:1.55' },
      `Paket (${SOURCES[source]}) yeni bir instance olarak kurulur: Minecraft sürümü, modlar ve ayarlar otomatik hazırlanır. ` +
      'Dosya sayısına göre birkaç dakika sürebilir. Şimdilik yalnızca Fabric paketleri desteklenir.'),
    h('label', { class: 'lbl' }, 'Instance adı', name)),
  [{ label: 'Vazgeç', fn: (c) => c() }, { label: 'Paketi kur', cls: 'primary', fn: async (c) => {
    try {
      await api('/modpack/install', { method: 'POST', body: { source, project_id: hit.project_id, name: name.value } });
      c(); watchJob();
    } catch (e) { toast(e.message, 'error'); }
  } }]);
}

const PREFETCHED = new Set();
function prefetchProject(source, hit, pack) {  // fareyle üstüne gelince sayfa verisi arka planda ısıtılır
  const k = `${source}:${hit.project_id}:${B.instance}`;
  if (PREFETCHED.has(k) || PREFETCHED.size > 60) return;
  PREFETCHED.add(k);
  const p = new URLSearchParams({ source, id: hit.project_id, type: B.type });
  if (!pack && B.instance) p.set('instance', B.instance);
  api('/project/info?' + p).catch(() => PREFETCHED.delete(k));
}

function resultCard(hit) {
  const source = B.source, pack = B.type === 'modpack';
  const label = (installed) => pack ? [icon('package', 15), 'Paketi kur']
    : installed ? [icon('check', 15), 'Kurulu'] : [icon('download', 15), 'Kur'];
  const btn = h('button', { class: 'btn small' + (hit.installed && !pack ? '' : ' primary'), disabled: hit.installed && !pack },
    label(hit.installed));
  btn.addEventListener('click', async () => {
    if (pack) { modpackModal(hit, source); return; }
    btn.disabled = true;
    btn.textContent = 'Kuruluyor…';
    try {
      const r = await api(`/${source}/install`, { method: 'POST', body: { instance: B.instance, type: B.type, project_id: hit.project_id } });
      hit.installed = !(r.manual && r.manual.length && !r.installed.length);
      btn.className = 'btn small' + (hit.installed ? '' : ' primary');
      btn.disabled = hit.installed;
      btn.replaceChildren(...label(hit.installed));
      if (r.manual && r.manual.length) {
        openModal('Elle indirmen gerekiyor', h('div', {}, h('div', { class: 'notice', style: 'margin:0' },
          'Bu dosyanın yazarı üçüncü taraf launcher\'dan indirmeye izin vermiyor. Sayfasından indirip instance klasörüne koy:'),
        manualList(r.manual)), [{ label: 'Klasörü aç', fn: () => api(`/instances/${B.instance}/folder`, { method: 'POST' }).catch((e) => toast(e.message, 'error')) },
          { label: 'Kapat', fn: (c) => c() }]);
      } else toast(r.skipped ? 'Zaten kurulu.' : `Kuruldu: ${r.installed.join(', ')}`);
    } catch (e) {
      btn.disabled = false;
      btn.className = 'btn small primary';
      btn.replaceChildren(...label(false));
      toast(e.message, 'error');
    }
  });
  return h('div', { class: 'panel card' },
    h('div', { class: 'card-top clickable', title: 'Detayları aç', onmouseenter: () => prefetchProject(source, hit, pack), onclick: () => {
      location.hash = projectHref(source, hit.project_id, pack ? null : B.instance, B.type); } },
      hit.icon ? h('img', { class: 'thumb', src: hit.icon, alt: '' })
        : h('div', { class: 'thumb', style: `background:${grad(hashColor(hit.title))}` }, initial(hit.title)),
      h('div', { class: 'row-main' }, h('div', { class: 'row-title', title: hit.title }, hit.title),
        h('div', { class: 'row-sub' }, `${hit.author} • ${fmtNum(hit.downloads)} indirme`))),
    h('div', { class: 'card-desc clickable', onclick: () => {
      location.hash = projectHref(source, hit.project_id, pack ? null : B.instance, B.type); } }, hit.description),
    h('div', { class: 'card-foot' },
      h('div', { class: 'cats' }, (hit.categories || []).map((c) => h('span', { class: 'chip tiny' }, capitalize(c)))),
      h('div', { class: 'card-btns' },
        hit.url ? h('button', { class: 'icon-btn link', title: `${SOURCES[source]} sayfasını aç`, onclick: () => openExternal(hit.url) }, icon('link', 15)) : null,
        btn)));
}

async function runSearch(reset) {
  const ui = B.ui;
  if (!ui) return;
  const note = (node) => { ui.cards.replaceChildren(node); ui.more.style.display = 'none'; };
  if (B.source === 'curseforge' && !B.cf.configured) { note(cfSetupPanel()); return; }
  const pack = B.type === 'modpack';
  const inst = CACHE.instances.find((i) => i.id === B.instance);
  if (!pack) {
    if (!inst) { note(h('div', { class: 'panel empty', style: 'grid-column:1/-1' }, h('p', { class: 'muted' }, 'Önce ana sayfadan bir instance oluştur.'))); return; }
    if (B.type === 'mod' && inst.loader !== 'fabric') {
      note(h('div', { class: 'notice', style: 'grid-column:1/-1' },
        `Bu instance ${loaderName(inst.loader)}, mod kurulamaz. Resource pack / shader seçebilir ya da Fabric (1.14+) bir instance oluşturabilirsin.`));
      return;
    }
  }
  if (reset) { B.offset = 0; B.hits = []; ui.cards.replaceChildren(...skeletons(8)); }
  const my = ++B.seq;
  try {
    const params = new URLSearchParams({ q: B.q, type: B.type, offset: B.offset, sort: B.sort });
    if (pack) { if (B.mc) params.set('mc', B.mc); } else params.set('instance', B.instance);
    const r = await api(`/${B.source}/search?${params}`);
    if (my !== B.seq) return;
    B.hits = reset ? r.hits : B.hits.concat(r.hits);
    B.total = r.total;
    B.offset = B.hits.length;
    ui.count.textContent = B.total ? `${fmtNum(B.total)} sonuç` : '';
    ui.cards.replaceChildren(...(B.hits.length ? B.hits.map(resultCard)
      : [h('p', { class: 'muted', style: 'grid-column:1/-1' }, 'Sonuç bulunamadı.')]));
    ui.more.style.display = B.offset < B.total ? '' : 'none';
  } catch (e) {
    if (my !== B.seq) return;
    ui.cards.replaceChildren(h('div', { class: 'notice', style: 'grid-column:1/-1' }, e.message,
      h('div', { style: 'margin-top:12px' },
        h('button', { class: 'btn small', onclick: diagnoseModal }, 'Bağlantıyı test et'))));
  }
}

async function diagnoseModal() {
  const body = h('div', { class: 'muted' }, 'Test ediliyor…');
  openModal('Bağlantı testi', body, [{ label: 'Kapat', fn: (close) => close() }]);
  try {
    const r = await api('/diagnose');
    body.replaceChildren(
      h('div', { class: 'list' }, r.steps.map((st) => h('div', { class: 'panel row' },
        h('span', { class: 'chip' + (st.ok ? ' green' : '') }, st.ok ? 'OK' : 'HATA'),
        h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, st.name),
          h('div', { class: 'row-sub', style: 'white-space:normal' }, st.detail))))),
      h('p', { style: 'margin:14px 0 0;line-height:1.5' }, r.summary));
  } catch (e) { body.textContent = e.message; }
}

async function pageBrowse(q) {
  const instances = await loadInstances();
  // Adresteki ?type=... yalnızca bu adrese yeni gelindiğinde uygulanır; yoksa sekmeye (Resource Pack, Shader...)
  // tıklayınca route() adresi yeniden okuyup seçimi geri "mod"a çeviriyordu.
  if (B.appliedHash !== location.hash) {
    B.appliedHash = location.hash;
    if (q.source && SOURCES[q.source]) B.source = q.source;
    if (q.instance && instances.some((i) => i.id === q.instance)) B.instance = q.instance;
    if (q.type && BTYPES.some(([t]) => t === q.type)) B.type = q.type;
  }
  if (!instances.some((i) => i.id === B.instance)) B.instance = instances[0] ? instances[0].id : null;
  if (B.source === 'curseforge') {
    try { B.cf = await api('/curseforge/status'); } catch (_) { B.cf = { configured: false }; }
  }
  const pack = B.type === 'modpack';
  const versions = pack ? (await api('/versions').catch(() => ({ versions: [] }))).versions : [];

  const input = h('input', { class: 'input', placeholder: `${SOURCES[B.source]}'de ara…`, value: B.q,
    oninput: () => { clearTimeout(B.timer); B.timer = setTimeout(() => { B.q = input.value.trim(); runSearch(true); }, 350); } });
  const sort = h('select', { class: 'select', title: 'Sıralama', onchange: () => { B.sort = sort.value; runSearch(true); } },
    SORTS.map(([v, l]) => h('option', { value: v, selected: v === B.sort }, l)));
  const target = pack
    ? h('select', { class: 'select', title: 'Minecraft sürümü', onchange: () => { B.mc = target.value; runSearch(true); } },
      h('option', { value: '' }, 'Tüm sürümler'), versions.map((v) => h('option', { value: v, selected: v === B.mc }, v)))
    : (instances.length ? h('select', { class: 'select', title: 'Hedef instance', onchange: () => { B.instance = target.value; runSearch(true); } },
      instances.map((i) => h('option', { value: i.id, selected: i.id === B.instance }, `${i.name} (${i.mc_version})`))) : null);

  const seg = h('div', { class: 'src-seg' }, Object.entries(SOURCES).map(([k, l]) =>
    h('button', { class: 'src-btn' + (B.source === k ? ' active' : ''), onclick: () => { B.source = k; B.offset = 0; route(); } }, l)));
  const tabs = BTYPES.map(([t, label]) =>
    h('button', { class: 'tab' + (B.type === t ? ' active' : ''), onclick: () => { B.type = t; route(); } }, label));
  const count = h('span', { class: 'muted', style: 'font-size:13px;margin-left:auto' });
  const cards = h('div', { class: 'cards' });
  const more = h('button', { class: 'btn', style: 'display:none;margin:18px auto 0', onclick: () => runSearch(false) }, 'Daha fazla göster');
  B.ui = { cards, more, count };
  setTimeout(() => runSearch(true), 0);

  const sub = pack
    ? 'Hazır modpack\'i tek tıkla yeni bir instance olarak kur. Sürüm, modlar ve ayarlar otomatik hazırlanır.'
    : 'Seçili instance\'ın sürümüne uyumlu olanlar listelenir. Gerekli bağımlılıklar (Fabric API gibi) otomatik kurulur.';
  return [
    h('header', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Keşfet'), h('p', { class: 'sub' }, sub)), seg),
    h('div', { class: 'searchbar' }, h('div', { class: 'search-wrap' }, icon('search', 18), input), sort, target),
    h('div', { class: 'tabs', style: 'margin-top:4px' }, tabs, count),
    cards, h('div', { style: 'display:flex' }, more),
  ];
}

/* ------------------------------------------------------- Proje sayfası (Modrinth / CurseForge) */
/* Açıklama gösterimi: markdown -> HTML -> beyaz liste temizleyici (script/iframe/olay yok) */
function mdToHtml(src) {
  const esc = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const attr = (t) => String(t).replace(/"/g, '&quot;');
  const inline = (t) => {
    const codes = [];
    t = t.replace(/`([^`\n]+)`/g, (_, c) => { codes.push(esc(c)); return `\u0000${codes.length - 1}\u0000`; });
    t = t.replace(/!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)/g, (_, a, u) => `<img alt="${attr(a)}" src="${attr(u)}">`);
    t = t.replace(/\[([^\]]+)\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)/g, (_, a, u) => `<a href="${attr(u)}">${a}</a>`);
    t = t.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>').replace(/(^|[\s(])__([^_\n]+)__(?=[\s).,!?:;]|$)/g, '$1<strong>$2</strong>');
    t = t.replace(/(^|[^*])\*([^*\s][^*\n]*)\*(?!\*)/g, '$1<em>$2</em>').replace(/(^|[\s(])_([^_\n]+)_(?=[\s).,!?:;]|$)/g, '$1<em>$2</em>');
    t = t.replace(/~~([^~\n]+)~~/g, '<del>$1</del>');
    return t.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[+i]}</code>`);
  };
  const lines = String(src || '').replace(/\r\n?/g, '\n').split('\n');
  const out = [];
  let para = [];
  const stack = [];
  const flushPara = () => { if (para.length) { out.push(`<p>${inline(para.join(' '))}</p>`); para = []; } };
  const closeLists = () => { while (stack.length) out.push(`</li></${stack.pop().tag}>`); };
  const RAW = /^<\/?(div|p|center|table|thead|tbody|tr|td|th|img|a|h[1-6]|details|summary|ul|ol|li|br|hr|blockquote|pre|span|b|i|u|strong|em|picture|source|kbd|sup|sub|code)\b/i;
  const isListLine = (l) => /^\s*([-*+]|\d+[.)])\s+\S/.test(l);
  const cells = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*```/.test(line)) {
      flushPara(); closeLists();
      const buf = [];
      for (i++; i < lines.length && !/^\s*```/.test(lines[i]); i++) buf.push(lines[i]);
      out.push(`<pre><code>${esc(buf.join('\n'))}</code></pre>`);
      continue;
    }
    if (!line.trim()) {
      flushPara();
      if (stack.length) { let j = i + 1; while (j < lines.length && !lines[j].trim()) j++; if (!(j < lines.length && isListLine(lines[j]))) closeLists(); }
      continue;
    }
    const lm = line.match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
    if (lm && !/^\s*(\*{3,}|-{3,})\s*$/.test(line)) {
      flushPara();
      const indent = lm[1].replace(/\t/g, '  ').length, tag = /\d/.test(lm[2]) ? 'ol' : 'ul';
      if (!stack.length || indent > stack[stack.length - 1].indent) { out.push(`<${tag}><li>`); stack.push({ indent, tag }); }
      else {
        while (stack.length > 1 && indent < stack[stack.length - 1].indent) out.push(`</li></${stack.pop().tag}>`);
        if (stack[stack.length - 1].tag !== tag) { out.push(`</li></${stack.pop().tag}><${tag}><li>`); stack.push({ indent, tag }); }
        else out.push('</li><li>');
      }
      out.push(inline(lm[3]));
      continue;
    }
    closeLists();
    const hm = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (hm) { flushPara(); out.push(`<h${hm[1].length}>${inline(hm[2])}</h${hm[1].length}>`); continue; }
    if (/^\s*(\*{3,}|-{3,}|_{3,})\s*$/.test(line)) { flushPara(); out.push('<hr>'); continue; }
    if (/^\s*>/.test(line)) {
      flushPara();
      const buf = [];
      for (; i < lines.length && /^\s*>/.test(lines[i]); i++) buf.push(lines[i].replace(/^\s*>\s?/, ''));
      i--; out.push(`<blockquote>${mdToHtml(buf.join('\n'))}</blockquote>`);
      continue;
    }
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      flushPara();
      const head = cells(line);
      let html = `<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>`;
      for (i += 2; i < lines.length && lines[i].includes('|') && lines[i].trim(); i++)
        html += `<tr>${cells(lines[i]).map((c) => `<td>${inline(c)}</td>`).join('')}</tr>`;
      i--; out.push(html + '</tbody></table>');
      continue;
    }
    if (RAW.test(line.trim())) { flushPara(); out.push(line); continue; }
    para.push(line.trim());
  }
  flushPara(); closeLists();
  return out.join('\n');
}

const RICH_OK = new Set(['p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'strong', 'b', 'em', 'i', 'u', 's', 'del',
  'strike', 'code', 'pre', 'blockquote', 'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'div', 'span', 'details', 'summary',
  'center', 'sup', 'sub', 'kbd']);
const RICH_DROP = new Set(['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'link', 'meta',
  'svg', 'video', 'audio', 'canvas', 'noscript', 'template', 'base', 'head', 'title']);

function richUrl(v) {
  v = String(v || '').trim();
  if (v.startsWith('//')) v = 'https:' + v;
  return /^https:\/\/[^\s"'<>]+$/i.test(v) ? v : '';
}

function cleanInto(node, out) {
  for (const n of node.childNodes) {
    if (n.nodeType === 3) { out.append(document.createTextNode(n.nodeValue)); continue; }
    if (n.nodeType !== 1) continue;
    const tag = n.tagName.toLowerCase();
    if (RICH_DROP.has(tag)) continue;
    if (!RICH_OK.has(tag)) { cleanInto(n, out); continue; }
    const el = document.createElement(tag === 'center' ? 'div' : tag);
    if (tag === 'center') el.style.textAlign = 'center';
    if (tag === 'a') {
      const href = richUrl(n.getAttribute('href'));
      if (href) { el.setAttribute('href', href); el.dataset.ext = href; }
    } else if (tag === 'img') {
      const src = richUrl(n.getAttribute('src') || n.getAttribute('data-src'));
      if (!src) continue;
      el.setAttribute('src', src);
      el.setAttribute('alt', (n.getAttribute('alt') || '').slice(0, 200));
      el.setAttribute('loading', 'lazy');
      el.setAttribute('referrerpolicy', 'no-referrer');
      const w = parseInt(n.getAttribute('width'), 10);
      if (w > 0 && w <= 1200) el.style.width = w + 'px';
    } else if (tag === 'td' || tag === 'th') {
      for (const k of ['colspan', 'rowspan']) { const v = parseInt(n.getAttribute(k), 10); if (v > 0 && v < 20) el.setAttribute(k, v); }
    }
    if (n.getAttribute && n.getAttribute('align') === 'center' && tag !== 'img') el.style.textAlign = 'center';
    cleanInto(n, el);
    out.append(el);
  }
}

function richContent(text, format) {
  const html = format === 'markdown' ? mdToHtml(text) : String(text || '');
  const doc = new DOMParser().parseFromString(html, 'text/html'); // inert: görsel/script yüklenmez
  const box = h('div', { class: 'rich' });
  cleanInto(doc.body, box);
  box.addEventListener('click', (e) => {
    const a = e.target.closest('a');
    if (!a) return;
    e.preventDefault();
    if (a.dataset.ext) api('/open-link', { method: 'POST', body: { url: a.dataset.ext } }).catch((er) => toast(er.message, 'error'));
  });
  if (!box.childNodes.length) box.append(h('p', { class: 'muted' }, 'Bu proje için açıklama yok.'));
  return box;
}

function projectHref(source, id, instance, type) {
  const p = new URLSearchParams();
  if (instance) p.set('instance', instance);
  if (type) p.set('type', type);
  return `#/project/${source}:${id}?${p}`;
}

/* instance içeriğindeki kayıtlı project_id ("cf:123" ya da Modrinth ID) -> proje sayfası bağlantısı */
function indexedProjectHref(projectId, instance, ptype) {
  if (!projectId) return null;
  return String(projectId).startsWith('cf:')
    ? projectHref('curseforge', String(projectId).slice(3), instance, ptype)
    : projectHref('modrinth', projectId, instance, ptype);
}

const VTYPE = { release: ['Release', 'green'], beta: ['Beta', ''], alpha: ['Alpha', ''] };
let projTab = 'desc';
let projKey = '';

async function pageProject(arg, q) {
  const [source, id] = String(arg || '').split(':');
  if (!SOURCES[source] || !id) { location.hash = '#/browse'; return []; }
  const instances = CACHE.instances.length ? CACHE.instances : await loadInstances();
  let instId = q.instance && instances.some((i) => i.id === q.instance) ? q.instance : null;
  if (!instId && q.type !== 'modpack' && instances[0]) instId = instances[0].id;
  // anahtar kontrolü ve proje bilgisi aynı anda istenir
  const cfCheck = source === 'curseforge'
    ? api('/curseforge/status').catch(() => ({ configured: false })) : Promise.resolve({ configured: true });
  const infoReq = api('/project/info?' + new URLSearchParams({ source, id, type: q.type || 'mod', ...(instId ? { instance: instId } : {}) }));
  infoReq.catch(() => {});
  B.cf = await cfCheck;
  if (!B.cf.configured) return [h('button', { class: 'btn small', onclick: () => { location.hash = '#/browse?source=curseforge'; } }, icon('back', 15), 'Geri'), cfSetupPanel()];
  const info = await infoReq;
  const key = `${source}:${id}`;
  if (key !== projKey) { projKey = key; projTab = 'desc'; }
  const inst = instances.find((i) => i.id === instId);
  const pack = info.type === 'modpack';
  const canInstall = !pack && inst && info.type in { mod: 1, resourcepack: 1, shader: 1 }
    && !(info.type === 'mod' && inst.loader !== 'fabric');
  const cur = info.installed;
  const isCur = (v) => cur && (v.filename === cur.filename || (cur.version_id && String(cur.version_id) === String(v.id)));
  const curVer = cur ? (info.versions.find(isCur) || {}).name || cur.version || cur.filename : null;

  const content = h('div', {});
  const tabsEl = h('div', { class: 'tabs', style: 'margin-top:4px' });

  const afterChange = async () => { await loadInstances(); route(); };

  const versionBtn = (v) => {
    const current = isCur(v);
    const btn = h('button', { class: 'btn small' + (current ? '' : ' primary'), disabled: current },
      current ? [icon('check', 15), 'Kurulu'] : cur ? 'Bu sürüme geç' : [icon('download', 15), 'Kur']);
    btn.addEventListener('click', async () => {
      btn.disabled = true; btn.textContent = 'Kuruluyor…';
      try {
        const r = await api('/project/version', { method: 'POST',
          body: { source, project_id: id, instance: instId, type: info.type, version_id: v.id } });
        if (r.manual && r.manual.length) {
          btn.disabled = false; btn.textContent = 'Tekrar dene';
          openModal('Elle indirmen gerekiyor', h('div', {}, h('div', { class: 'notice', style: 'margin:0' },
            'Bu dosyanın yazarı üçüncü taraf launcher\'dan indirmeye izin vermiyor. Sayfasından indirip instance klasörüne koy (eski sürüm silinmedi):'),
          manualList(r.manual)), [{ label: 'Klasörü aç', fn: () => api(`/instances/${instId}/folder`, { method: 'POST' }).catch((e) => toast(e.message, 'error')) },
            { label: 'Kapat', fn: (c) => c() }]);
          return;
        }
        toast(r.replaced ? `Sürüm değiştirildi: ${v.name}` : `Kuruldu: ${info.title}`);
        await afterChange();
      } catch (e) {
        toast(e.message, 'error');
        btn.disabled = false; btn.textContent = cur ? 'Bu sürüme geç' : 'Kur';
      }
    });
    return btn;
  };

  const versionsView = () => {
    if (pack) return h('div', { class: 'panel empty' }, h('p', { class: 'muted' },
      'Modpack kurulurken Minecraft sürümüne uyan en yeni sürüm otomatik seçilir.'));
    if (!inst) return h('div', { class: 'panel empty' }, h('p', { class: 'muted' }, 'Sürümleri görmek için bir instance seç.'));
    if (info.type === 'mod' && inst.loader !== 'fabric') return h('div', { class: 'notice' },
      `Bu instance ${loaderName(inst.loader)}, mod kurulamaz. Fabric bir instance seç.`);
    if (!info.versions.length) return h('div', { class: 'panel empty' }, h('p', { class: 'muted' },
      `${inst.mc_version} için uyumlu sürüm bulunamadı.`));
    const newest = info.versions.find((v) => v.type === 'release') || info.versions[0];
    return h('div', { class: 'list' }, info.versions.map((v) => h('div', { class: 'panel row' + (isCur(v) ? ' cur' : '') },
      h('div', { class: 'row-main' },
        h('div', { class: 'row-title' }, v.name || v.number, ' ',
          h('span', { class: 'chip tiny' + (VTYPE[v.type] && VTYPE[v.type][1] ? ' green' : '') }, (VTYPE[v.type] || [v.type])[0]),
          v === newest ? h('span', { class: 'chip tiny green', style: 'margin-left:6px' }, 'En yeni') : null,
          v.restricted ? h('span', { class: 'chip tiny', style: 'margin-left:6px', title: 'Yazar launcher indirmesine izin vermiyor olabilir' }, 'Elle indirme') : null),
        h('div', { class: 'row-sub' }, [(v.mc || []).join(', '), v.date ? new Date(v.date).toLocaleDateString('tr-TR') : '', v.filename]
          .filter(Boolean).join(' • '))),
      versionBtn(v))));
  };

  const galleryView = () => h('div', { class: 'gallery' }, info.gallery.map((u) =>
    h('img', { src: u, alt: '', loading: 'lazy', referrerpolicy: 'no-referrer' })));

  const TABS = [['desc', 'Açıklama'], ['versions', `Sürümler${info.versions.length ? ' (' + info.versions.length + ')' : ''}`],
    ...(info.gallery.length ? [['gallery', 'Galeri']] : [])];
  const draw = () => {
    tabsEl.replaceChildren(...TABS.map(([k, l]) => h('button', { class: 'tab' + (projTab === k ? ' active' : ''),
      onclick: () => { projTab = k; draw(); } }, l)));
    content.replaceChildren(projTab === 'versions' ? versionsView()
      : projTab === 'gallery' ? galleryView() : h('div', { class: 'panel rich-wrap' }, richContent(info.body, info.body_format)));
  };
  draw();

  const instSel = (!pack && instances.length) ? h('select', { class: 'select', title: 'Hedef instance', onchange: () => {
    location.hash = projectHref(source, id, instSel.value, info.type);
  } }, instances.map((i) => h('option', { value: i.id, selected: i.id === instId }, `${i.name} (${i.mc_version})`))) : null;

  const actions = [];
  if (pack) {
    actions.push(h('button', { class: 'btn primary', onclick: () => modpackModal({ title: info.title, project_id: id }, source) },
      icon('package', 16), 'Paketi kur'));
  } else if (cur) {
    actions.push(h('button', { class: 'btn primary', onclick: () => { projTab = 'versions'; draw(); content.scrollIntoView({ behavior: 'smooth' }); } },
      icon('bolt', 16), 'Sürüm değiştir'));
  } else if (canInstall) {
    const b = h('button', { class: 'btn primary' }, icon('download', 16), 'Kur (en yeni)');
    b.addEventListener('click', async () => {
      b.disabled = true; b.textContent = 'Kuruluyor…';
      try {
        const r = await api(`/${source}/install`, { method: 'POST', body: { instance: instId, type: info.type, project_id: id } });
        if (r.manual && r.manual.length && !r.installed.length) {
          openModal('Elle indirmen gerekiyor', h('div', {}, h('div', { class: 'notice', style: 'margin:0' },
            'Bu dosyanın yazarı üçüncü taraf launcher\'dan indirmeye izin vermiyor. Sayfasından indirip instance klasörüne koy:'), manualList(r.manual)),
          [{ label: 'Kapat', fn: (c) => c() }]);
          b.disabled = false; b.textContent = 'Tekrar dene';
          return;
        }
        toast(r.skipped ? 'Zaten kurulu.' : `Kuruldu: ${r.installed.join(', ')}`);
        await afterChange();
      } catch (e) { toast(e.message, 'error'); b.disabled = false; b.replaceChildren(icon('download', 16), 'Kur (en yeni)'); }
    });
    actions.push(b);
  }
  if (info.url) actions.push(h('button', { class: 'btn', onclick: () => openExternal(info.url) },
    icon('link', 16), `${SOURCES[source]}'te aç`));

  return [
    h('button', { class: 'btn small', style: 'margin-bottom:16px', onclick: () => {
      if (history.length > 1) history.back(); else location.hash = '#/browse';
    } }, icon('back', 15), 'Geri'),
    h('div', { class: 'panel proj-hero' },
      info.icon ? h('img', { class: 'proj-icon', src: info.icon, alt: '' })
        : h('div', { class: 'proj-icon', style: `background:${grad(hashColor(info.title))}` }, initial(info.title)),
      h('div', { class: 'proj-info' },
        h('div', { class: 'eyebrow' }, `${SOURCES[source].toUpperCase()} • ${capitalize(info.type)}`),
        h('h3', {}, info.title),
        h('div', { class: 'row-sub', style: 'white-space:normal' }, [info.author, `${fmtNum(info.downloads)} indirme`].filter(Boolean).join(' • ')),
        h('p', { class: 'proj-sum' }, info.summary),
        h('div', { class: 'chips', style: 'margin:0 0 14px' }, [
          cur ? h('span', { class: 'chip green' }, `Kurulu • ${curVer}${cur.enabled ? '' : ' (kapalı)'}`) : null,
          ...(info.categories || []).map((c) => h('span', { class: 'chip tiny' }, capitalize(c)))]),
        h('div', { class: 'proj-actions' }, actions, instSel))),
    tabsEl, content,
  ];
}

/* ---------------------------------------------------------------- FPS BOOST */
function fpsRow(st) {
  const marks = { pending: h('span', { class: 'fps-dot' }), installing: h('span', { class: 'spin' }),
    ok: icon('check', 16), skip: h('span', { class: 'fps-skip' }, '–') };
  return h('div', { class: 'fps-row ' + st.state }, h('div', { class: 'fps-ic' }, marks[st.state]),
    h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, st.title),
      h('div', { class: 'row-sub', style: 'white-space:normal' }, st.detail ? `${st.desc} • ${st.detail}` : st.desc)));
}

async function fpsBoost() {
  let st;
  try { st = await api('/fps-boost', { method: 'POST' }); } catch (e) { toast(e.message, 'error'); return; }
  const list = h('div', { class: 'list fps-list' });
  const summary = h('p', { style: 'margin:14px 0 0;line-height:1.5' });
  const instId = st.instance;
  openModal('FPS BOOST', h('div', {},
    h('p', { class: 'muted', style: 'margin:0 0 14px;line-height:1.5' },
      '1.21.11 (Fabric) için en çok önerilen FPS modları "FPS BOOST" adlı ayrı bir instance\'a kuruluyor. Diğer instance\'larına dokunulmaz.'),
    list, summary), [
    { label: 'Kapat', fn: (close) => close() },
    { label: 'FPS BOOST\'u aç', cls: 'primary', fn: (close) => { close(); location.hash = '#/instance/' + instId; } },
  ]);
  const render = (s) => {
    if (!list.isConnected) return;
    list.replaceChildren(...s.steps.map(fpsRow));
    summary.className = s.status === 'error' ? 'notice' : 'muted';
    summary.textContent = s.status === 'running' ? 'Kuruluyor, birkaç dakika sürebilir…' : s.message;
  };
  render(st);
  for (let i = 0; i < 600 && st.status === 'running'; i++) {
    await new Promise((r) => setTimeout(r, 800));
    try { st = await api('/fps-boost'); } catch (_) { break; }
    render(st);
  }
  await loadInstances().catch(() => {});
  if (['home', 'instance'].includes(currentRoute.name)) route();
  toast(st.status === 'done' ? 'FPS BOOST hazır!' : 'FPS BOOST tamamlanamadı', st.status === 'done' ? 'ok' : 'error');
}

/* ---------------------------------------------------------------- konsol & hesap */
function pageConsole() {
  consoleEl = h('div', { class: 'panel console' }, logLines.length ? logLines.join('\n') + '\n' : '');
  setTimeout(() => { consoleEl.scrollTop = consoleEl.scrollHeight; }, 0);
  return [h('header', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Konsol'),
    h('p', { class: 'sub' }, 'Kurulum ve oyun çıktıları burada görünür.')),
  h('button', { class: 'btn small', onclick: () => { logLines.length = 0; consoleEl.textContent = ''; } }, 'Temizle')),
  consoleEl];
}

/* ---------------------------------------------------------------- Skin yöneticisi */
async function skinSection(a) {
  let data = await api('/skins');
  const fig = mcFigure(9);
  const refreshFigure = () => {
    skinRev = Date.now();
    fig.setSkin(skinFor(a.name));
    whoKey = ''; renderTopbar();
  };
  skinRev = Date.now();
  fig.setSkin(skinFor(a.name));

  const grid = h('div', { class: 'skin-grid' });
  const libCount = h('span', { class: 'muted' });
  const ms = a.mode === 'microsoft';

  async function act(fn, okMsg) {
    try { data = await fn(); refreshFigure(); renderGrid(); if (okMsg) toast(okMsg); }
    catch (e) { toast(e.message, 'error'); }
  }
  const select = (id) => act(() => api('/skins/select', { method: 'POST', body: { id } }), id ? 'Skin seçildi' : 'Hesap skinine dönüldü');

  function tile(sk) {
    const del = h('button', { class: 'icon-btn st-del', title: 'Sil', onclick: async (e) => {
      e.stopPropagation();
      if (!(await confirmDialog(`"${sk.name}" skini kütüphaneden silinsin mi?`, 'Sil'))) return;
      act(() => api('/skins/delete', { method: 'POST', body: { id: sk.id } }), 'Skin silindi');
    } }, icon('trash', 15));
    return h('div', { class: 'skin-tile' + (data.active === sk.id ? ' active' : ''), role: 'button', tabindex: 0,
      onclick: () => select(sk.id), onkeydown: (e) => { if (e.key === 'Enter') select(sk.id); } },
    skinHead(`/skinlib/${sk.id}.png`, 64), h('div', { class: 'st-name', title: sk.name }, sk.name),
    h('div', { class: 'st-sub' }, sk.slim ? 'Alex • ince kol' : 'Steve • klasik'),
    data.active === sk.id ? h('span', { class: 'st-badge' }, 'Aktif') : null, del);
  }
  function renderGrid() {
    const def = h('div', { class: 'skin-tile' + (data.active === null ? ' active' : ''), role: 'button', tabindex: 0,
      onclick: () => select(null), onkeydown: (e) => { if (e.key === 'Enter') select(null); } },
    h('div', { class: 'skin-head ph' }, icon('user', 28)), h('div', { class: 'st-name' }, 'Hesap skini'),
    h('div', { class: 'st-sub' }, 'Mojang / varsayılan'), data.active === null ? h('span', { class: 'st-badge' }, 'Aktif') : null);
    grid.replaceChildren(def, ...data.items.map(tile));
    libCount.textContent = `${data.items.length} skin`;
  }
  renderGrid();

  async function addFile(file) {
    try {
      const data_url = await readFileAsDataUrl(file);
      data = await api('/skins/add', { method: 'POST', body: { data_url, name: file.name.replace(/\.png$/i, '') } });
      refreshFigure(); renderGrid(); toast('Skin eklendi ve seçildi');
    } catch (e) { toast(e.message, 'error'); }
  }
  const file = h('input', { type: 'file', accept: 'image/png', style: 'display:none' });
  file.addEventListener('change', () => { if (file.files[0]) addFile(file.files[0]); file.value = ''; });
  const drop = h('div', { class: 'dropzone', tabindex: 0, role: 'button', onclick: () => file.click(),
    onkeydown: (e) => { if (e.key === 'Enter') file.click(); } },
  icon('upload', 24), h('div', { class: 'dz-main' }, 'Skin PNG\'sini buraya sürükle'),
  h('div', { class: 'dz-sub' }, 'ya da tıklayıp seç • 64×64 veya 64×32'), file);
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', (e) => { const f = e.dataTransfer && e.dataTransfer.files[0]; if (f) addFile(f); });

  const uname = h('input', { class: 'input', placeholder: 'Premium oyuncu adı', maxlength: 16, spellcheck: 'false' });
  const importBtn = h('button', { class: 'btn', onclick: async () => {
    if (!uname.value.trim()) return;
    importBtn.disabled = true;
    await act(() => api('/skins/import', { method: 'POST', body: { username: uname.value.trim() } }), `${uname.value.trim()} skini eklendi`);
    importBtn.disabled = false; uname.value = '';
  } }, icon('download', 15), 'Adından al');
  uname.addEventListener('keydown', (e) => { if (e.key === 'Enter') importBtn.click(); });

  const apply = ms ? h('button', { class: 'btn primary', onclick: async () => {
    if (!data.active) { toast('Önce kütüphaneden bir skin seç.', 'error'); return; }
    if (!(await confirmDialog('Seçili skin Microsoft hesabına yüklenecek. Oyunda ve sunucularda herkes bu skini görür.', 'Hesabıma uygula'))) return;
    try { await api('/skins/apply', { method: 'POST', body: { id: data.active } }); toast('Skin hesabına yüklendi'); }
    catch (e) { toast(e.message, 'error'); }
  } }, icon('upload', 15), 'Hesabıma uygula') : null;

  const stage = h('div', { class: 'panel skin-stage' },
    h('div', { class: 'stage-glow' }), fig.el,
    h('div', { class: 'stage-name' }, a.name),
    h('span', { class: 'chip' + (ms ? ' green' : '') }, ms ? 'Microsoft hesabı' : 'Çevrimdışı mod'),
    h('div', { class: 'login-hint', style: 'position:static;margin-top:2px' }, 'Sürükle, karakterini döndür'),
    apply);

  const library = h('div', { class: 'panel skin-lib' },
    h('div', { class: 'lib-head' }, h('h3', { class: 'section-title' }, 'Skin kütüphanem'),
      libCount),
    drop,
    h('div', { class: 'import-row' }, uname, importBtn),
    grid,
    h('p', { class: 'muted', style: 'margin:2px 0 0;font-size:12.5px;line-height:1.5' }, ms
      ? 'Burada seçtiğin skin launcher\'da görünür. Oyunda herkesin görmesi için "Hesabıma uygula" ile Mojang hesabına yükle.'
      : 'Çevrimdışı modda skin yalnızca launcher\'da görünür; oyun içi skin için Microsoft hesabıyla giriş yapıp "Hesabıma uygula"yı kullanabilirsin.'));
  return h('div', { class: 'acc-top' }, stage, library);
}

async function hudCard() {
  return h('div', { class: 'panel form', style: 'max-width:none' },
    h('h3', { class: 'section-title' }, 'Oyun içi mod menüsü'),
    h('p', { class: 'muted', style: 'margin:0;line-height:1.55' },
      'Oyundayken Sağ Shift tuşuna bas: Riven mod menüsü açılır. FPS, tuş göstergesi, CPS, koordinat, ping, hız, saat, ' +
      'RAM, zırh durumu gibi göstergeleri açıp kapatabilir, renk/arka plan/opaklık/gölge ayarlayabilir ve ' +
      'fareyle sürükleyip istediğin yere koyabilirsin. Ayarlar instance\'ın config/riven-hud.json dosyasında saklanır. ' +
      'Sadece Fabric 1.21.11 instance\'larında çalışır.'));
}

async function connectionsCard() {
  let st;
  try { st = await api('/curseforge/status'); } catch (_) { st = { configured: false }; }
  return h('div', { class: 'panel form', style: 'max-width:none' },
    h('div', { style: 'display:flex;align-items:center;gap:10px;justify-content:space-between;flex-wrap:wrap' },
      h('h3', { class: 'section-title' }, 'CurseForge bağlantısı'),
      h('span', { class: 'chip' + (st.configured ? ' green' : '') }, st.configured ? 'Bağlı' : 'Bağlı değil')),
    h('p', { class: 'muted', style: 'margin:0;line-height:1.55' },
      'Keşfet sayfasında CurseForge mod ve modpack\'lerini arayıp kurabilmek için ücretsiz bir API anahtarı gerekir. ' +
      'Modrinth için anahtar gerekmez.'),
    cfKeyForm(st, () => route()));
}

async function pageAccount() {
  const a = await api('/account');
  const offName = h('input', { class: 'input', value: a.offline_name, maxlength: 16 });
  const offline = h('div', { class: 'panel form' }, h('h3', { class: 'section-title' }, 'Çevrimdışı oyuncu'),
    h('p', { class: 'muted', style: 'margin:0' }, 'Tek kişilik dünyalar ve çevrimdışı sunucular için. Hesap gerekmez.'),
    h('label', {}, 'Oyuncu adı', offName),
    h('button', { class: 'btn primary', style: 'align-self:flex-start', onclick: async () => {
      try { const r = await api('/account/offline', { method: 'POST', body: { name: offName.value } }); S.account = r; toast('Kaydedildi'); route(); }
      catch (e) { toast(e.message, 'error'); }
    } }, 'Kaydet'));

  let ms;
  if (a.mode === 'microsoft') {
    ms = h('div', { class: 'panel form' }, h('h3', { class: 'section-title' }, 'Microsoft hesabı'),
      h('p', { style: 'margin:0' }, [h('span', { class: 'chip green' }, 'Bağlı'), ` ${a.name}`]),
      h('button', { class: 'btn danger', style: 'align-self:flex-start', onclick: async () => {
        try { await api('/account/logout', { method: 'POST' }); route(); } catch (e) { toast(e.message, 'error'); }
      } }, 'Çıkış yap'));
  } else {
    const cid = a.client_id_baked ? null
      : h('input', { class: 'input', value: a.client_id, placeholder: 'Azure uygulama (Client) ID' });
    const codeBox = h('div', { style: 'display:none;flex-direction:column;gap:14px;align-items:flex-start' });
    const msg = h('p', { class: 'muted', style: 'margin:0' });
    let timer = null;
    async function watch() {
      if (currentRoute.name !== 'account') return;
      try {
        const st = await api('/account/device-status');
        if (st.status === 'ok') { toast(`Giriş yapıldı: ${st.message}`); route(); return; }
        if (st.status === 'error') {
          msg.className = 'notice';
          msg.textContent = st.message;
          codeBox.style.display = 'none';
          return;
        }
      } catch (e) { msg.textContent = e.message; return; }
      timer = setTimeout(watch, 2000);
    }
    const start = h('button', { class: 'btn primary', style: 'align-self:flex-start', onclick: async () => {
      try {
        const r = await api('/account/device-start', { method: 'POST', body: { client_id: cid ? cid.value : '' } });
        codeBox.replaceChildren(
          h('div', { class: 'muted' }, 'Açılan sayfada bu kodu gir ve Microsoft hesabınla giriş yap:'),
          h('div', { class: 'devcode' }, r.user_code),
          h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap' },
            h('button', { class: 'btn small', onclick: () => {
              if (typeof navigator !== 'undefined' && navigator.clipboard) navigator.clipboard.writeText(r.user_code);
              toast('Kod kopyalandı');
            } }, 'Kodu kopyala'),
            h('button', { class: 'btn small', onclick: () => api('/account/device-open', { method: 'POST' })
              .catch((e) => toast(e.message, 'error')) }, `${r.display_uri} sayfasını aç`)));
        codeBox.style.display = 'flex';
        msg.className = 'muted';
        msg.textContent = 'Giriş bekleniyor…';
        clearTimeout(timer);
        watch();
      } catch (e) { toast(e.message, 'error'); }
    } }, 'Microsoft ile giriş yap');
    ms = h('div', { class: 'panel form' }, h('h3', { class: 'section-title' }, 'Microsoft ile giriş'),
      h('div', { class: 'notice', style: 'margin:0' },
        'Premium sunuculara girmek için gerekir. Giriş, bir kod yazarak yapılır (adres yapıştırmak yok). Ama Minecraft API\'sini kullanabilmesi için Azure uygulamanın Microsoft tarafından onaylanmış olması gerekir (form: aka.ms/mce-reviewappid). Onay gelene kadar giriş "AzureAppNotPermitted" hatası verir. Çevrimdışı mod buna gerek duymaz.'),
      cid ? h('label', {}, 'Client ID', cid) : null, start, codeBox, msg);
  }

  const skins = await skinSection(a);
  const themes = themePanel();
  const connections = await connectionsCard();
  const hud = await hudCard();
  const discord = await discordCard();
  const friends = await friendsCard();
  return [h('header', { class: 'page-head' }, h('div', {}, h('h1', {}, 'Hesap ve Discord'),
    h('p', { class: 'sub' }, 'Token\'lar ve API anahtarları düz dosyaya yazılmaz, sistem kimlik deposunda tutulur.'))),
  h('div', { style: 'display:flex;flex-direction:column;gap:18px' }, skins, themes,
    h('div', { class: 'acc-cols' }, offline, ms), hud, connections, friends, discord)];
}

async function friendsCard() {
  let data;
  try { data = await api('/friends'); } catch (e) { data = { friends: [] }; }
  const input = h('input', { class: 'input', placeholder: 'Minecraft kullanıcı adı', maxlength: 16 });
  const list = h('div', { class: 'list' });
  const offlineBox = h('input', { type: 'checkbox' });
  function friendRow(f) {
    const removeBtn = h('button', { class: 'icon-btn', title: 'Kaldır' }, icon('trash', 17));
    removeBtn.addEventListener('click', async () => {
      try { const r = await api('/friends/remove', { method: 'POST', body: { uuid: f.uuid } }); renderList(r.friends); }
      catch (e) { toast(e.message, 'error'); }
    });
    return h('div', { class: 'panel row' },
      h('div', { class: 'thumb', style: `background:${grad(hashColor(f.name))}` }, initial(f.name)),
      h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, f.name),
        h('div', { class: 'row-sub' }, f.premium === false ? 'Korsan / çevrimdışı hesap' : 'Premium hesap')),
      removeBtn);
  }
  const renderList = (items) => {
    if (!items.length) { list.replaceChildren(h('p', { class: 'muted', style: 'margin:0' }, 'Henüz kimseyi eklemedin.')); return; }
    list.replaceChildren(...items.map(friendRow));
  };
  renderList(data.friends);
  const addBtn = h('button', { class: 'btn primary', onclick: async () => {
    const name = input.value.trim();
    if (!name) return;
    addBtn.disabled = true;
    try {
      const r = await api('/friends', { method: 'POST', body: { name, offline: offlineBox.checked } });
      renderList(r.friends);
      input.value = '';
      toast(r.added ? `${name} eklendi (${r.premium ? 'premium' : 'korsan/çevrimdışı'})` : `${name} zaten listede`);
    } catch (e) { toast(e.message, 'error'); } finally { addBtn.disabled = false; }
  } }, 'Ekle');
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') addBtn.click(); });
  return h('div', { class: 'panel form' }, h('h3', { class: 'section-title' }, 'Riven arkadaşların'),
    h('p', { class: 'muted', style: 'margin:0;line-height:1.5' },
      'Oyunda eklediğin kişinin isminin yanında senin ekranında küçük bir Riven rozeti çıkar. Premium da, korsan (çevrimdışı) da olsa eklenebilir: '
      + 'Mojang\'da bulunamayan isimler otomatik çevrimdışı hesap olarak eklenir. Rozeti görmek için Minecraft 1.21.11 (Fabric) oynaman yeterli, launcher modu kendisi ekliyor. '
      + 'Rozet kişiye göre senin ekranında yerel olarak çizilir, karşı tarafın da seni görmesi için o da seni kendi listesine eklemeli.'),
    h('div', { style: 'display:flex;gap:10px' }, input, addBtn),
    h('label', { style: 'flex-direction:row;align-items:center;gap:8px;font-weight:400;color:var(--text)' }, offlineBox,
      'Korsan (çevrimdışı) hesap olarak ekle, Mojang\'a bakma'), list);
}


async function discordCard() {
  const d = await api('/discord');
  const cid = h('input', { class: 'input', value: d.client_id, placeholder: 'Discord Application ID (sadece rakam)' });
  const enabled = h('input', { type: 'checkbox', checked: d.enabled });
  const showName = h('input', { type: 'checkbox', checked: d.show_name });
  const row = 'flex-direction:row;align-items:center;gap:10px;font-weight:400;color:var(--text)';
  const status = d.connected ? h('span', { class: 'chip green' }, 'Discord\'a bağlı')
    : h('span', { class: 'chip' }, d.error || 'Bağlı değil');
  return h('div', { class: 'panel form' }, h('h3', { class: 'section-title' }, 'Discord durumu'),
    h('p', { class: 'muted', style: 'margin:0;line-height:1.5' },
      'Profilinde "Riven Launcher oynuyor" ve hangi instance\'ta olduğun görünür. Kurulum (bir kere): discord.com/developers/applications → New Application → adı "Riven Launcher" yap → "Application ID"yi kopyalayıp aşağı yapıştır. İstersen Rich Presence → Art Assets bölümüne zip\'teki discord_logo.png dosyasını "riven" adıyla yükle. Discord masaüstü uygulaması açık olmalı.'),
    h('label', {}, 'Application ID', cid),
    h('label', { style: row }, enabled, 'Discord\'da göster'),
    h('label', { style: row }, showName, 'Instance adını göster (kapalıysa sadece "Minecraft oynuyor")'),
    h('div', { style: 'display:flex;gap:12px;align-items:center;flex-wrap:wrap' },
      h('button', { class: 'btn primary', onclick: async () => {
        try {
          await api('/discord', { method: 'POST', body: { client_id: cid.value, enabled: enabled.checked, show_name: showName.checked } });
          toast('Kaydedildi, Discord\'a bağlanılıyor…');
          setTimeout(() => { if (currentRoute.name === 'account') route(); }, 4500);
        } catch (e) { toast(e.message, 'error'); }
      } }, 'Kaydet'), status));
}

/* ---------------------------------------------------------------- mesajlaşma */
const CHAT = { configured: false, me: '', msgs: [], last: 0, active: null, timer: null, first: true,
  busy: false, error: '', onUpdate: null };
const chatOther = (m) => (m.from.toLowerCase() === CHAT.me.toLowerCase() ? m.to : m.from);
const chatReadKey = () => 'riven_chat_read_' + CHAT.me.toLowerCase();
function chatReadMap() {
  try { return JSON.parse(localStorage.getItem(chatReadKey()) || '{}') || {}; } catch (_) { return {}; }
}
function chatSaveRead(map) { try { localStorage.setItem(chatReadKey(), JSON.stringify(map)); } catch (_) { /* depolama kapalı */ } }
function chatUnread(name) {
  const read = chatReadMap()[name.toLowerCase()] || 0;
  return CHAT.msgs.filter((m) => m.from.toLowerCase() === name.toLowerCase() && m.id > read).length;
}
const chatUnreadTotal = () => {
  const names = new Set(CHAT.msgs.filter((m) => m.from.toLowerCase() !== CHAT.me.toLowerCase()).map((m) => m.from));
  return [...names].reduce((a, n) => a + chatUnread(n), 0);
};
function chatMarkRead(name) {
  const ids = CHAT.msgs.filter((m) => m.from.toLowerCase() === name.toLowerCase()).map((m) => m.id);
  if (!ids.length) return;
  const map = chatReadMap();
  map[name.toLowerCase()] = Math.max(map[name.toLowerCase()] || 0, ...ids);
  chatSaveRead(map);
}
function chatChanged() {
  renderRail();
  if (CHAT.onUpdate) CHAT.onUpdate();
}

async function chatPoll() {
  if (!CHAT.configured || CHAT.busy) return;
  CHAT.busy = true;
  try {
    const r = await api('/chat/poll?since=' + CHAT.last);
    CHAT.error = '';
    if (r.me !== CHAT.me) { // hesap değişti: başka kullanıcının mesajları
      Object.assign(CHAT, { me: r.me, msgs: [], last: 0, first: true });
      return;
    }
    const known = new Set(CHAT.msgs.map((m) => m.id));
    const fresh = r.messages.filter((m) => !known.has(m.id));
    CHAT.msgs.push(...fresh);
    CHAT.last = Math.max(CHAT.last, r.last_id || 0);
    if (CHAT.first) {
      CHAT.first = false;
      if (localStorage.getItem(chatReadKey()) === null) { // ilk kurulum: eski mesajlar okunmuş sayılır
        const map = {};
        for (const m of CHAT.msgs) if (m.from.toLowerCase() !== CHAT.me.toLowerCase()) map[m.from.toLowerCase()] = Math.max(map[m.from.toLowerCase()] || 0, m.id);
        chatSaveRead(map);
      }
    } else {
      for (const m of fresh) {
        if (m.from.toLowerCase() === CHAT.me.toLowerCase()) continue;
        const watching = currentRoute.name === 'chat' && CHAT.active && CHAT.active.toLowerCase() === m.from.toLowerCase();
        if (watching) chatMarkRead(m.from);
        else toast(`${m.from}: ${m.text.length > 60 ? m.text.slice(0, 60) + '…' : m.text}`);
      }
    }
    if (fresh.length || CHAT.msgs.length === 0) chatChanged();
  } catch (e) {
    const changed = CHAT.error !== e.message;
    CHAT.error = e.message;
    if (changed && CHAT.onUpdate) CHAT.onUpdate();
  } finally { CHAT.busy = false; }
}

function chatStart() {
  CHAT.configured = true;
  if (!CHAT.timer) CHAT.timer = setInterval(chatPoll, 4000);
  chatPoll();
}
function chatStop() {
  CHAT.configured = false;
  clearInterval(CHAT.timer);
  Object.assign(CHAT, { timer: null, msgs: [], last: 0, first: true, active: null, error: '' });
}
async function chatBoot() {
  try {
    const st = await api('/chat/status');
    CHAT.me = st.me;
    if (st.configured) chatStart();
  } catch (_) { /* mesajlaşma isteğe bağlı */ }
}

function chatSetupPanel(st) {
  const server = h('input', { class: 'input', placeholder: 'http://192.168.1.20:8780', value: st.server || '', spellcheck: 'false' });
  const pass = h('input', { class: 'input', type: 'password', autocomplete: 'off', placeholder: 'Sunucu şifresi (varsa)' });
  const go = h('button', { class: 'btn primary', onclick: async () => {
    if (!server.value.trim()) { toast('Sunucu adresini yaz.', 'error'); return; }
    go.disabled = true; go.textContent = 'Bağlanılıyor…';
    try {
      await api('/chat/setup', { method: 'POST', body: { server: server.value.trim(), password: pass.value } });
      toast('Mesaj sunucusuna bağlandı'); chatStop(); await chatBoot(); route();
    } catch (e) { toast(e.message, 'error'); go.disabled = false; go.textContent = 'Bağlan'; }
  } }, 'Bağlan');
  return h('div', { class: 'panel setup', style: 'grid-column:1/-1' },
    h('div', { class: 'empty-orb' }, icon('chat', 30)),
    h('h3', {}, 'Mesaj sunucusuna bağlan'),
    h('p', { class: 'muted', style: 'margin:0 0 6px;line-height:1.55;max-width:560px' },
      'Mesajlar, arkadaşlarınla ortak kullandığınız küçük bir Riven mesaj sunucusu üzerinden gider. ' +
      'Sunucuyu biri (sen ya da bir arkadaşın) kurar: launcher klasöründeki chat_server/Sunucu_Baslat.bat dosyasını çalıştırması yeterli. ' +
      'Sunucu penceresinde yazan adresi gir (aynı bilgisayardaysa http://127.0.0.1:8780; 0.0.0.0 yazma). Sonra herkes aynı adresi ve şifreyi buraya girer. Premium da korsan da fark etmez; ' +
      'mesaj atabilmen için karşıdaki kişiyi Hesap sayfasından arkadaş olarak eklemiş olman gerekir.'),
    h('div', { class: 'form-col' }, server, pass, h('div', { class: 'row-actions' }, go)));
}

async function pageChat() {
  const st = await api('/chat/status');
  CHAT.me = st.me;
  const head = (sub, extra) => h('header', { class: 'page-head' },
    h('div', {}, h('h1', {}, 'Mesajlar'), h('p', { class: 'sub' }, sub)), extra || null);
  if (!st.configured) return [head('Arkadaşlarınla launcher içinden yaz.'), chatSetupPanel(st)];
  if (!CHAT.timer) chatStart();
  const friends = (await api('/friends')).friends;
  const leave = h('button', { class: 'btn small', onclick: async () => {
    try { await api('/chat/reset', { method: 'POST' }); chatStop(); route(); } catch (e) { toast(e.message, 'error'); }
  } }, 'Sunucudan ayrıl');
  const header = head(`${st.me} olarak bağlısın • ${st.server}`, leave);
  if (!friends.length) {
    return [header, h('div', { class: 'panel empty' }, h('p', { class: 'muted' },
      'Henüz arkadaşın yok. Hesap ve Discord sayfasındaki "Riven arkadaşların" bölümünden ekle; adı mesaj sunucusundaki adıyla aynı olmalı.'),
    h('button', { class: 'btn primary', onclick: () => { location.hash = '#/account'; } }, 'Arkadaş ekle'))];
  }
  if (!CHAT.active || !friends.some((f) => f.name === CHAT.active)) {
    const withUnread = friends.find((f) => chatUnread(f.name) > 0);
    CHAT.active = (withUnread || friends[0]).name;
  }

  const list = h('div', { class: 'chat-list panel' });
  const title = h('div', { class: 'chat-title' });
  const msgs = h('div', { class: 'chat-msgs' });
  const err = h('div', { class: 'notice', style: 'margin:0 14px 10px;display:none' });
  const input = h('input', { class: 'input', placeholder: 'Mesaj yaz…', maxlength: 500, autocomplete: 'off' });
  const send = h('button', { class: 'btn primary', onclick: async () => {
    const text = input.value.trim();
    if (!text) return;
    send.disabled = true;
    try {
      const r = await api('/chat/send', { method: 'POST', body: { to: CHAT.active, text } });
      input.value = '';
      if (!CHAT.msgs.some((m) => m.id === r.message.id)) CHAT.msgs.push(r.message);
      renderConv(true);
    } catch (e) { toast(e.message, 'error'); } finally { send.disabled = false; input.focus(); }
  } }, 'Gönder');
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send.click(); } });

  function renderList() {
    list.replaceChildren(...friends.map((f) => {
      const n = chatUnread(f.name);
      const last = [...CHAT.msgs].reverse().find((m) => chatOther(m).toLowerCase() === f.name.toLowerCase());
      return h('button', { class: 'chat-item' + (f.name === CHAT.active ? ' active' : ''),
        onclick: () => { CHAT.active = f.name; chatMarkRead(f.name); renderList(); renderConv(true); chatChanged(); } },
      h('div', { class: 'thumb', style: `background:${grad(hashColor(f.name))}` }, initial(f.name)),
      h('div', { class: 'row-main' }, h('div', { class: 'row-title' }, f.name),
        h('div', { class: 'row-sub' }, last ? last.text : (f.premium === false ? 'Korsan hesap' : 'Premium hesap'))),
      n ? h('span', { class: 'chat-dot' }, n > 9 ? '9+' : String(n)) : null);
    }));
  }
  function renderConv(forceBottom) {
    const near = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 80;
    const mine = (m) => m.from.toLowerCase() === CHAT.me.toLowerCase();
    const convo = CHAT.msgs.filter((m) => chatOther(m).toLowerCase() === CHAT.active.toLowerCase()).sort((a, b) => a.id - b.id);
    chatMarkRead(CHAT.active);
    title.textContent = CHAT.active;
    msgs.replaceChildren(...(convo.length ? convo.map((m) => h('div', { class: 'msg ' + (mine(m) ? 'mine' : 'theirs') },
      h('div', { class: 'msg-text' }, m.text),
      h('div', { class: 'msg-time' }, new Date(m.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))))
      : [h('p', { class: 'muted', style: 'margin:auto;text-align:center' }, `${CHAT.active} ile henüz mesajın yok. İlk mesajı sen yaz.`)]));
    err.style.display = CHAT.error ? '' : 'none';
    err.textContent = CHAT.error;
    if (forceBottom || near) msgs.scrollTop = msgs.scrollHeight;
  }
  CHAT.onUpdate = () => { if (!list.isConnected) { CHAT.onUpdate = null; return; } renderList(); renderConv(false); };
  renderList();
  setTimeout(() => { renderConv(true); input.focus(); }, 0);
  const conv = h('div', { class: 'chat-conv panel' }, title, msgs, err, h('div', { class: 'chat-input' }, input, send));
  return [header, h('div', { class: 'chat-wrap' }, list, conv)];
}

/* ---------------------------------------------------------------- açılış */
(async function boot() {
  renderRail();
  buildStatusbar();
  const instancesReady = loadInstances().catch(() => {});   // durum ve instance'lar paralel yüklensin
  await pollOnce();
  renderTopbar();
  startScene();
  showLogin();
  await instancesReady;
  chatBoot();
  window.addEventListener('hashchange', route);
  window.addEventListener('pagehide', () => { api('/bye', { method: 'POST', keepalive: true }).catch(() => {}); });
  schedulePoll();
  if (!location.hash) location.hash = '#/home';
  else route();
})();
