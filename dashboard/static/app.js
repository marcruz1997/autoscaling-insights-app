/* VPA Insights: interface (PatternFly 6 + Chart.js).
   Cada página tem uma função render*() que recebe o JSON da API e monta o HTML. */
'use strict';

// ======================= utilitários =======================
const $ = id => document.getElementById(id);
const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = (v, d = 0) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('pt-BR', { maximumFractionDigits: d, minimumFractionDigits: d });
const fCpu = m => m == null ? '–' : (Math.abs(m) >= 1000 ? nf(m / 1000, 2) + ' cores' : nf(m) + 'm');
const fMem = mi => mi == null ? '–' : (Math.abs(mi) >= 1024 ? nf(mi / 1024, 2) + ' Gi' : nf(mi) + ' Mi');
const fDisk = mi => mi == null ? '–' : (mi >= 1024 ? nf(mi / 1024, 1) + ' Gi' : nf(mi) + ' Mi');
const signed = (v, f) => v == null ? '–' : (v > 0 ? '+' : v < 0 ? '−' : '') + f(Math.abs(v));
const pctOf = (a, b) => a == null || !b ? null : a / b * 100;

function age(iso) {
  if (!iso) return '–';
  let s = Math.max(0, (Date.now() - new Date(iso)) / 1000);
  const d = Math.floor(s / 86400); s -= d * 86400;
  const h = Math.floor(s / 3600); s -= h * 3600;
  const m = Math.floor(s / 60);
  return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`;
}
function percentile(sorted, p) {
  if (!sorted.length) return null;
  const i = (sorted.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

// ======================= componentes PatternFly =======================
const ICONS = {
  ok: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm-1.2 11.6L3.4 8.2l1.3-1.3 2.1 2.1 4.5-4.5 1.3 1.3z"/></svg>',
  warn: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 .8 0 15h16zm.9 11.9H7.1V11h1.8zm0-2.7H7.1V5.5h1.8z"/></svg>',
  bad: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm.9 12H7.1v-1.8h1.8zm0-3.4H7.1V4h1.8z"/></svg>',
  info: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm.9 12.2H7.1V6.9h1.8zM8 5.6a1.1 1.1 0 1 1 0-2.2 1.1 1.1 0 0 1 0 2.2z"/></svg>',
  wait: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm0 14.2A6.2 6.2 0 1 1 8 1.8a6.2 6.2 0 0 1 0 12.4zM8.9 4H7.1v4.6l3.6 2.2.9-1.5-2.7-1.6z"/></svg>',
  sun: '<svg class="ico" viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.2"/><path d="M7.2 0h1.6v2.4H7.2zm0 13.6h1.6V16H7.2zM0 7.2h2.4v1.6H0zm13.6 0H16v1.6h-2.4zM2.1 3.2l1.1-1.1 1.7 1.7-1.1 1.1zm9 9 1.1-1.1 1.7 1.7-1.1 1.1zM2.1 12.8l1.7-1.7 1.1 1.1-1.7 1.7zm9-9 1.7-1.7 1.1 1.1-1.7 1.7z"/></svg>',
  moon: '<svg class="ico" viewBox="0 0 16 16"><path d="M6.2.4A7.8 7.8 0 1 0 15.6 9.8 6.2 6.2 0 0 1 6.2.4z"/></svg>',
  auto: '<svg class="ico" viewBox="0 0 16 16"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm0 14.2V1.8a6.2 6.2 0 0 1 0 12.4z"/></svg>',
  loading: '<svg class="ico spin" viewBox="0 0 16 16"><path d="M8 0a8 8 0 0 1 8 8h-1.8A6.2 6.2 0 0 0 8 1.8z"/><path opacity=".3" d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm0 14.2A6.2 6.2 0 1 1 8 1.8a6.2 6.2 0 0 1 0 12.4z"/></svg>',
  copy: '<svg class="ico" viewBox="0 0 16 16"><path d="M5 0h9a2 2 0 0 1 2 2v9h-2V2H5zM2 4h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2zm0 2v8h8V6z"/></svg>',
};
const LABEL_STATUS = { ok: 'pf-m-success', warn: 'pf-m-warning', bad: 'pf-m-danger', info: 'pf-m-info', wait: '', loading: 'pf-m-info' };

/** Rótulo de situação: sempre ícone + texto (nunca só cor). */
function label(text, kind = 'wait', title = '') {
  return `<span class="pf-v6-c-label pf-m-filled pf-m-compact ${LABEL_STATUS[kind] || ''}"${title ? ` title="${esc(title)}"` : ''}>
    <span class="pf-v6-c-label__content"><span class="pf-v6-c-label__icon">${ICONS[kind] || ICONS.info}</span>
    <span class="pf-v6-c-label__text">${esc(text)}</span></span></span>`;
}
const ALERT_CLASS = { warn: 'pf-m-warning', bad: 'pf-m-danger', info: 'pf-m-info', ok: 'pf-m-success', loading: 'pf-m-info' };
const ALERT_SR = { warn: 'Alerta de aviso:', bad: 'Alerta de erro:', info: 'Informação:', ok: 'Sucesso:', loading: 'Carregando:' };
function alertBox(kind, title, body = '') {
  return `<div class="pf-v6-c-alert pf-m-inline ${ALERT_CLASS[kind]}">
    <div class="pf-v6-c-alert__icon">${ICONS[kind]}</div>
    <p class="pf-v6-c-alert__title"><span class="pf-v6-screen-reader">${ALERT_SR[kind]}</span> ${title}</p>
    ${body ? `<div class="pf-v6-c-alert__description">${body}</div>` : ''}</div>`;
}
function emptyState(title, body) {
  return `<div class="pf-v6-c-empty-state pf-m-xs"><div class="pf-v6-c-empty-state__content">
    <div class="pf-v6-c-empty-state__header"><div class="pf-v6-c-empty-state__title"><h3 class="pf-v6-c-empty-state__title-text">${title}</h3></div></div>
    <div class="pf-v6-c-empty-state__body">${body}</div></div></div>`;
}
/** Tabela PatternFly compacta. cols: [{ t: 'Título', num: true }], rows: HTML de <tr>. */
function table(cols, rows, label = '') {
  return `<table class="pf-v6-c-table pf-m-compact" role="grid"${label ? ` aria-label="${esc(label)}"` : ''}>
    <thead class="pf-v6-c-table__thead"><tr class="pf-v6-c-table__tr">${cols.map(c =>
      `<th class="pf-v6-c-table__th${c.num ? ' num' : ''}" scope="col">${c.t}</th>`).join('')}</tr></thead>
    <tbody class="pf-v6-c-table__tbody">${rows}</tbody></table>`;
}
const td = (html, cls = '') => `<td class="pf-v6-c-table__td ${cls}">${html}</td>`;
const tdn = (html, cls = '') => td(html, 'num ' + cls);
const sub = t => t ? `<span class="sub">${t}</span>` : '';
function stat(lbl, value, hint = '', cls = '') {
  return `<div class="stat"><div class="stat-label">${lbl}</div><div class="stat-value ${cls}">${value}</div>${hint ? `<div class="stat-hint">${hint}</div>` : ''}</div>`;
}
function meter(pct, warnAt = 80, badAt = 95) {
  if (pct == null) return '';
  const c = pct >= badAt ? cssVar('--vpa-bad') : pct >= warnAt ? cssVar('--vpa-warn') : cssVar('--vpa-ok');
  return `<div class="meter" role="presentation"><span style="width:${Math.min(100, pct).toFixed(1)}%;background:${c}"></span></div>`;
}
function codeBlock(title, text) {
  return `<div class="cmd"><div class="cmd-title">${title}</div>
    <div class="pf-v6-c-code-block"><div class="pf-v6-c-code-block__header"><div class="pf-v6-c-code-block__actions">
      <div class="pf-v6-c-code-block__actions-item"><button class="pf-v6-c-button pf-m-plain" type="button" aria-label="Copiar" title="Copiar" data-copy="${esc(text)}">
        <span class="pf-v6-c-button__icon">${ICONS.copy}</span></button></div></div></div>
    <div class="pf-v6-c-code-block__content"><pre class="pf-v6-c-code-block__pre"><code class="pf-v6-c-code-block__code">${esc(text)}</code></pre></div></div></div>`;
}

// ======================= API =======================
async function getJSON(url) {
  // Se a sessão do login expirar, o oauth-proxy redireciona para o OAuth do cluster:
  // recarregar a página faz o navegador entrar de novo.
  const r = await fetch(url, { redirect: 'manual' });
  if (r.type === 'opaqueredirect' || r.status === 401 || r.status === 403) {
    location.reload();
    throw new Error('sessão expirada, entrando de novo…');
  }
  if (!r.ok) throw new Error(`${url.split('?')[0]}: HTTP ${r.status} ${await r.text()}`);
  return r.json();
}
const errorsBox = {};
function setError(key, msg) {
  if (msg) errorsBox[key] = msg; else delete errorsBox[key];
  const list = Object.values(errorsBox);
  $('errors').innerHTML = list.length ? alertBox('bad', 'Falha ao carregar alguns dados', `<pre class="err">${esc(list.join('\n'))}</pre>`) : '';
}
const errText = (lbl, e) => e ? `${lbl}: ` + Object.entries(e).map(([k, v]) => `${k}: ${v}`).join(' | ') : '';

// ======================= estado e navegação =======================
const PAGES = {
  overview: { title: 'VPA · Overview', desc: 'Todos os deployments com VPA no cluster: usage, requests atuais e recomendação de CPU e memória por pod.', selectors: false },
  deploy: { title: 'VPA · Recommendations', desc: 'Recomendação do VPA, percentis de uso, histórico e métricas do deployment selecionado.', selectors: true },
  'hpa-overview': { title: 'HPA · Overview', desc: 'Todos os HorizontalPodAutoscalers do cluster: replicas, scaling metrics e compatibilidade com o VPA.', selectors: false },
  hpa: { title: 'HPA · Scaling', desc: 'Replicas, utilização × target, events e impacto da recomendação do VPA no HPA do deployment selecionado.', selectors: true },
  pods: { title: 'Pods', desc: 'Pods do deployment selecionado: status, restarts e consumo atual.', selectors: true },
  nodes: { title: 'Nodes', desc: 'Capacidade dos nodes e schedulability de um pod com a recomendação do VPA.', selectors: true },
  storage: { title: 'Storage', desc: 'PersistentVolumeClaims do namespace selecionado.', selectors: true },
  help: { title: 'Manual', desc: 'Referência das métricas, status e conceitos exibidos no dashboard.', selectors: false },
  notice: { title: 'Importante', desc: 'Aviso sobre natureza, suporte e responsabilidade desta aplicação.', selectors: false },
};
let range = '1h', tab = 'overview';
let targets = { deployments: [], vpas: [] };
let sel = { ns: '', deploy: '', container: '' };
const charts = {};

function readHash() {
  const [t, ns, deploy, container] = decodeURIComponent(location.hash.slice(1)).split('/');
  tab = PAGES[t] ? t : 'overview';
  if (ns) sel = { ns, deploy: deploy || '', container: container || '' };
}
function writeHash() {
  const h = `#${tab}/${sel.ns}/${sel.deploy}/${sel.container}`;
  if (location.hash !== h) history.replaceState(null, '', h);
}

const depsIn = ns => targets.deployments.filter(d => d.namespace === ns);
const findDep = (ns, n) => targets.deployments.find(d => d.namespace === ns && d.name === n);
const currentVPA = () => targets.vpas.find(v => v.namespace === sel.ns && v.targetKind === 'Deployment' && v.targetName === sel.deploy);
const currentRec = () => { const v = currentVPA(); return v && v.containers.find(c => c.name === sel.container); };

function fillSelectors() {
  // Na página de escalonamento do HPA, só entram projetos e deployments que têm HPA.
  const onlyHpa = tab === 'hpa';
  const pool = onlyHpa ? targets.deployments.filter(d => d.hasHPA) : targets.deployments;
  const inNs = ns => pool.filter(d => d.namespace === ns);
  const namespaces = [...new Set(pool.map(d => d.namespace))];
  const preferred = d => tab.startsWith('hpa') ? d.hasHPA : d.hasVPA;
  if (!namespaces.includes(sel.ns)) { const w = pool.find(preferred) || pool.find(d => d.hasVPA || d.hasHPA); sel.ns = w ? w.namespace : (namespaces[0] || ''); }
  $('selNs').innerHTML = namespaces.map(ns => {
    const v = inNs(ns).filter(d => d.hasVPA).length, h = inNs(ns).filter(d => d.hasHPA).length;
    const tags = onlyHpa ? `${h} HPA` : [v ? `${v} VPA` : '', h ? `${h} HPA` : ''].filter(Boolean).join(', ');
    return `<option value="${esc(ns)}"${ns === sel.ns ? ' selected' : ''}>${esc(ns)}${tags ? ` (${tags})` : ''}</option>`;
  }).join('') || `<option value="">${onlyHpa ? 'nenhum namespace com HPA' : 'nenhum namespace'}</option>`;
  const deps = inNs(sel.ns);
  if (!deps.some(d => d.name === sel.deploy)) { const w = deps.find(preferred) || deps.find(d => d.hasVPA || d.hasHPA); sel.deploy = w ? w.name : (deps[0] ? deps[0].name : ''); }
  $('selDep').innerHTML = deps.map(d => `<option value="${esc(d.name)}"${d.name === sel.deploy ? ' selected' : ''}>${esc(d.name)} · ${d.ready}/${d.replicas} pods${d.hasVPA ? ' · VPA' : ''}${d.hasHPA ? ' · HPA' : ''}</option>`).join('') || `<option value="">${onlyHpa ? 'nenhum deployment com HPA' : 'nenhum deployment'}</option>`;
  const dep = findDep(sel.ns, sel.deploy), cts = dep ? dep.containers : [];
  if (!cts.includes(sel.container)) sel.container = cts[0] || '';
  $('selCt').innerHTML = cts.map(c => `<option value="${esc(c)}"${c === sel.container ? ' selected' : ''}>${esc(c)}</option>`).join('');
  writeHash();
}
function select(ns, deploy, container) { sel = { ns, deploy, container: container || '' }; fillSelectors(); refreshTab(); }

function showTab(t) {
  tab = t;
  document.querySelectorAll('.pf-v6-c-nav__link').forEach(a => {
    const on = a.dataset.tab === t;
    a.classList.toggle('pf-m-current', on);
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  document.querySelectorAll('.tab').forEach(s => { s.hidden = s.id !== 'tab-' + t; });
  $('pageTitle').textContent = PAGES[t].title;
  $('pageDesc').textContent = PAGES[t].desc;
  $('selectors').hidden = !PAGES[t].selectors;
  $('rangeWrap').hidden = ['help', 'notice'].includes(t);
  if (targets.deployments.length) fillSelectors();  // a lista muda conforme a página (ex.: só HPA)
  writeHash();
  if (window.innerWidth < 1200) setSidebar(false);
  refreshTab();
}

// ======================= tema e menu lateral =======================
function themePref() { try { return localStorage.getItem('vpa-theme') || 'system'; } catch (e) { return 'system'; } }
function applyTheme() {
  const pref = themePref();
  const dark = pref === 'dark' || (pref === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('pf-v6-theme-dark', dark);
  $('themeIcon').innerHTML = ICONS[pref === 'system' ? 'auto' : pref === 'dark' ? 'moon' : 'sun'];
  $('themeBtn').title = { system: 'Tema: automático', light: 'Tema: claro', dark: 'Tema: escuro' }[pref];
  if (Object.keys(charts).length) refreshTab();
}
function setSidebar(open) {
  $('sidebar').classList.toggle('pf-m-expanded', open);
  $('sidebar').classList.toggle('pf-m-collapsed', !open);
  $('navToggle').setAttribute('aria-expanded', String(open));
}

// ======================= gráficos =======================
const SERIES = ['--vpa-s1', '--vpa-s2', '--vpa-s3', '--vpa-s4', '--vpa-s5', '--vpa-s6'];
const seriesColor = i => cssVar(SERIES[i % SERIES.length]);
const WINDOWS = { '15m': 9e5, '1h': 36e5, '6h': 216e5, '24h': 864e5, '7d': 6048e5 };
const RANGE_LABEL = { '15m': '15 min', '1h': '1 h', '6h': '6 h', '24h': '24 h', '7d': '7 d' };
const winLbl = () => RANGE_LABEL[range];

function fmtTime(ms) {
  const o = range === '7d' ? { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }
    : range === '6h' || range === '24h' ? { hour: '2-digit', minute: '2-digit' } : { hour: '2-digit', minute: '2-digit', second: '2-digit' };
  return new Date(ms).toLocaleString('pt-BR', o);
}
const shortPod = n => { const p = n.split('-'); return p.length > 2 ? p.slice(-2).join('-') : n; };

function makeChart(id, unit) {
  charts[id] = new Chart($(id), {
    type: 'line', data: { datasets: [] },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false, parsing: false,
      interaction: { mode: 'nearest', axis: 'x', intersect: false },
      elements: { point: { radius: 0, hoverRadius: 4 }, line: { borderWidth: 2, tension: 0.2 } },
      scales: {
        x: { type: 'linear', ticks: { maxTicksLimit: 7, callback: v => fmtTime(v) }, border: { display: false } },
        y: { beginAtZero: true, ticks: {}, title: { display: true, text: unit }, border: { display: false } },
      },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 14, boxHeight: 2, usePointStyle: false } },
        tooltip: { callbacks: {
          title: it => it.length ? new Date(it[0].parsed.x).toLocaleString('pt-BR') : '',
          label: c => `${c.dataset.label}: ${nf(c.parsed.y, 1)} ${unit}`,
        } },
      },
    },
  });
}
// O upper bound do VPA pode ser enorme com pouco histórico e achatar o resto: se passar
// muito do maior valor das outras séries, a escala é cortada e o valor vai para a legenda.
function setChart(id, datasets, xs) {
  const c = charts[id];
  const ds = datasets.filter(Boolean);
  let rest = 0, upper = 0;
  for (const d of ds) for (const p of d.data) { if (/upper/i.test(d.label)) upper = Math.max(upper, p.y); else rest = Math.max(rest, p.y); }
  const clip = upper > 0 && rest > 0 && upper > rest * 2;
  c.options.scales.y.max = clip ? Math.ceil(rest * 1.3) : undefined;
  if (clip) for (const d of ds) if (/upper/i.test(d.label)) d.label += ` (off-scale: ${nf(upper)})`;
  const text = cssVar('--vpa-subtle'), grid = cssVar('--vpa-border');
  for (const ax of ['x', 'y']) {
    c.options.scales[ax].ticks.color = text;
    c.options.scales[ax].grid = { color: grid, lineWidth: 0.5 };
  }
  c.options.scales.y.title.color = text;
  c.options.plugins.legend.labels.color = text;
  c.options.scales.x.min = xs && xs.length ? xs[0] : undefined;
  c.options.scales.x.max = xs && xs.length ? xs[1] : undefined;
  c.data.datasets = ds;
  c.update('none');
}
const pts = s => s.points.map(p => ({ x: p[0], y: p[1] }));
const podDS = (list, extra = {}) => (list || []).map((s, i) => ({ label: shortPod(s.name), data: pts(s), borderColor: seriesColor(i), backgroundColor: seriesColor(i), ...extra }));
function refDS(lbl, list, colorVar) {
  const s = (list || [])[0], c = cssVar(colorVar);
  return s && s.points.length ? { label: lbl, data: pts(s), borderColor: c, backgroundColor: c, borderDash: [6, 4], borderWidth: 1.5, tension: 0 } : null;
}
function stepDS(lbl, entries, pick, colorVar, dash, width, xs) {
  const data = [], c = cssVar(colorVar);
  for (const e of entries) { const v = pick(e); if (v != null) data.push({ x: Math.max(e.t, xs.length ? xs[0] : e.t), y: v }); }
  if (!data.length) return null;
  data.push({ x: xs.length ? xs[1] : Date.now(), y: data[data.length - 1].y });
  return { label: lbl, data, borderColor: c, backgroundColor: c, borderDash: dash, borderWidth: width, stepped: 'before', tension: 0 };
}
function constDS(lbl, v, xs, colorVar) {
  const c = cssVar(colorVar);
  return v == null || !xs.length ? null : { label: lbl, data: [{ x: xs[0], y: v }, { x: xs[1], y: v }], borderColor: c, backgroundColor: c, borderDash: [2, 3], borderWidth: 2, tension: 0 };
}
function extent(...lists) {
  let lo = Infinity, hi = -Infinity;
  for (const l of lists) for (const s of (l || [])) for (const p of s.points) { if (p[0] < lo) lo = p[0]; if (p[0] > hi) hi = p[0]; }
  return lo === Infinity ? [] : [lo, hi];
}
// Séries de pods que ainda existem (último ponto perto do fim da janela). Pods apagados
// continuam nos gráficos como histórico, mas não entram nos números "agora".
function live(list, stepSec) {
  const l = list || [];
  let end = 0;
  for (const s of l) if (s.points.length) end = Math.max(end, s.points[s.points.length - 1][0]);
  const tol = Math.max(90, (stepSec || 30) * 2.5) * 1000;
  return l.filter(s => s.points.length && s.points[s.points.length - 1][0] >= end - tol);
}
const lastSum = l => { let s = 0, a = false; for (const x of (l || [])) if (x.points.length) { s += x.points[x.points.length - 1][1]; a = true; } return a ? s : null; };
const lastVal = l => { const s = (l || [])[0]; return s && s.points.length ? s.points[s.points.length - 1][1] : null; };
const allVals = l => (l || []).flatMap(s => s.points.map(p => p[1])).sort((a, b) => a - b);

// ======================= VISÃO GERAL =======================
let ovRows = [];
const hpaOf = (ns, deploy) => (targets.hpas || []).find(h => h.namespace === ns && h.targetKind === 'Deployment' && h.targetName === deploy);
function hpaConflictLabel(ns, deploy) {
  const h = hpaOf(ns, deploy);
  return h && h.vpa && h.vpa.kind === 'conflict' ? label('HPA conflict', 'bad', `HPA ${h.name} escala por ${h.vpa.resources.join(' e ')}`) : '';
}
function rowStatus(row) {
  const r = row.rec, out = [];
  if (!r || !r.target) return label('Pending', 'wait');
  if (row.cpuReq == null && row.memReq == null) out.push(label('No request', 'warn'));
  if (row.cpuReq != null && r.lowerBound && row.cpuReq < r.lowerBound.cpu_m) out.push(label('CPU under-provisioned', 'warn'));
  if (row.cpuReq != null && r.upperBound && row.cpuReq > r.upperBound.cpu_m) out.push(label('CPU over-provisioned', 'bad'));
  if (row.memReq != null && r.lowerBound && row.memReq < r.lowerBound.mem_mib) out.push(label('Memory under-provisioned', 'warn'));
  if (row.memReq != null && r.upperBound && row.memReq > r.upperBound.mem_mib) out.push(label('Memory over-provisioned', 'bad'));
  return out.length ? out.join('') : label('Right-sized', 'ok');
}
function condLabels(conds) {
  const out = [];
  for (const c of conds || []) {
    if (c.status !== 'True') continue;
    if (c.type === 'LowConfidence') out.push(label('Low confidence', 'info', 'Histórico insuficiente'));
    else if (c.type === 'NoPodsMatched') out.push(label('No pods matched', 'bad'));
    else if (c.type === 'ConfigUnsupported' || c.type === 'ConfigDeprecated') out.push(label(c.type, 'bad'));
  }
  return out.join('');
}
const deltaCls = v => v == null || Math.abs(v) < 1 ? '' : v > 0 ? 't-bad' : 't-warn';
const isOutside = r => r.rec && r.rec.target && !rowStatus(r).includes('Right-sized');

function renderOverview(data) {
  setError('overview', data.error ? 'Overview: ' + data.error : errText('Overview', data.errors));
  ovRows = data.rows || [];
  let cpuRes = 0, cpuRec = 0, memRes = 0, memRec = 0, outside = 0, low = 0;
  const byNs = {};
  for (const r of ovRows) {
    const t = r.rec && r.rec.target, p = r.pods || 0;
    r.cpuDelta = t && r.cpuReq != null ? (r.cpuReq - t.cpu_m) * p : null;
    r.memDelta = t && r.memReq != null ? (r.memReq - t.mem_mib) * p : null;
    const ns = byNs[r.namespace] ||= { deps: new Set(), cpuRes: 0, cpuRec: 0, memRes: 0, memRec: 0 };
    ns.deps.add(r.deployment);
    if (t) {
      ns.cpuRes += (r.cpuReq || 0) * p; ns.cpuRec += t.cpu_m * p; ns.memRes += (r.memReq || 0) * p; ns.memRec += t.mem_mib * p;
      cpuRes += (r.cpuReq || 0) * p; cpuRec += t.cpu_m * p; memRes += (r.memReq || 0) * p; memRec += t.mem_mib * p;
    }
    if (isOutside(r)) outside++;
    if ((r.conditions || []).some(c => c.type === 'LowConfidence' && c.status === 'True')) low++;
  }
  const depCount = new Set(ovRows.map(r => r.namespace + '/' + r.deployment)).size;
  const diffHint = (d, f) => Math.abs(d) < 1 ? 'requests iguais ao target' : d > 0 ? `${f(d)} over-provisioned` : `${f(-d)} under-provisioned`;
  $('ovStats').innerHTML =
    stat('Deployments com VPA', nf(depCount), `${Object.keys(byNs).length} namespace(s)`) +
    stat('CPU requests → VPA target', `${fCpu(cpuRes)} → ${fCpu(cpuRec)}`, diffHint(cpuRes - cpuRec, fCpu)) +
    stat('Memory requests → VPA target', `${fMem(memRes)} → ${fMem(memRec)}`, diffHint(memRes - memRec, fMem)) +
    stat('Fora dos bounds do VPA', nf(outside), outside ? label('Review required', 'warn') : label('All right-sized', 'ok')) +
    stat('Low confidence', nf(low), 'VPAs com histórico insuficiente');

  if (!ovRows.length) {
    const notInstalled = data.error && /HTTP 404/.test(data.error);
    $('ovTable').innerHTML = emptyState(notInstalled ? 'VPA não instalado' : 'Nenhum VPA encontrado', notInstalled
      ? 'A API autoscaling.k8s.io não respondeu. Instale o VerticalPodAutoscaler Operator pelo Software Catalog.'
      : 'Crie um VerticalPodAutoscaler para um deployment e ele aparece aqui. As demais páginas funcionam para qualquer deployment.');
    $('ovNs').innerHTML = emptyState('Sem dados', 'Nenhum namespace com VPA.');
    return;
  }
  $('ovNs').innerHTML = table(
    [{ t: 'Namespace' }, { t: 'Deployments', num: 1 }, { t: 'CPU requests', num: 1 }, { t: 'CPU target', num: 1 }, { t: 'Delta', num: 1 },
     { t: 'Memory requests', num: 1 }, { t: 'Memory target', num: 1 }, { t: 'Delta', num: 1 }],
    Object.entries(byNs).map(([ns, v]) => `<tr class="pf-v6-c-table__tr">${td(esc(ns), 'strong')}${tdn(v.deps.size)}
      ${tdn(fCpu(v.cpuRes))}${tdn(fCpu(v.cpuRec))}${tdn(signed(v.cpuRes - v.cpuRec, fCpu), deltaCls(v.cpuRes - v.cpuRec))}
      ${tdn(fMem(v.memRes))}${tdn(fMem(v.memRec))}${tdn(signed(v.memRes - v.memRec, fMem), deltaCls(v.memRes - v.memRec))}</tr>`).join(''),
    'Totais por namespace');

  const band = (r, k, f) => r && r.lowerBound && r.upperBound ? sub(`${f(r.lowerBound[k])} – ${f(r.upperBound[k])}`) : '';
  $('ovTable').innerHTML = table(
    [{ t: 'Namespace' }, { t: 'Deployment' }, { t: 'Container' }, { t: 'Update mode' }, { t: 'Pods', num: 1 },
     { t: 'CPU usage', num: 1 }, { t: `CPU P90 · ${winLbl()}`, num: 1 }, { t: 'CPU request', num: 1 }, { t: 'CPU target', num: 1 }, { t: 'CPU delta', num: 1 },
     { t: 'Memory usage', num: 1 }, { t: `Memory peak · ${winLbl()}`, num: 1 }, { t: 'Memory request', num: 1 }, { t: 'Memory target', num: 1 }, { t: 'Memory delta', num: 1 },
     { t: 'Status' }],
    ovRows.map((r, i) => {
      const t = r.rec && r.rec.target;
      return `<tr class="pf-v6-c-table__tr pf-m-clickable" data-i="${i}" tabindex="0">
        ${td(esc(r.namespace))}${td(`<a href="#deploy/${esc(r.namespace)}/${esc(r.deployment)}/${esc(r.container)}">${esc(r.deployment)}</a>`)}${td(esc(r.container))}${td(esc(r.mode))}${tdn(r.pods)}
        ${tdn(fCpu(r.cpuUse))}${tdn(fCpu(r.cpuP90))}${tdn(fCpu(r.cpuReq))}${tdn(`<span class="strong">${t ? fCpu(t.cpu_m) : '–'}</span>${band(r.rec, 'cpu_m', fCpu)}`)}${tdn(signed(r.cpuDelta, fCpu), deltaCls(r.cpuDelta))}
        ${tdn(fMem(r.memUse))}${tdn(fMem(r.memMax))}${tdn(fMem(r.memReq))}${tdn(`<span class="strong">${t ? fMem(t.mem_mib) : '–'}</span>${band(r.rec, 'mem_mib', fMem)}`)}${tdn(signed(r.memDelta, fMem), deltaCls(r.memDelta))}
        ${td(`<span class="labels">${rowStatus(r)}${condLabels(r.conditions)}${hpaConflictLabel(r.namespace, r.deployment)}</span>`)}</tr>`;
    }).join(''), 'Deployments com VPA');
  $('ovTable').querySelectorAll('tr.pf-m-clickable').forEach(tr => {
    const open = e => {
      if (e.target.closest('a')) return;
      const r = ovRows[+tr.dataset.i];
      sel = { ns: r.namespace, deploy: r.deployment, container: r.container };
      fillSelectors(); showTab('deploy');
    };
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', e => { if (e.key === 'Enter') open(e); });
  });
}

// ======================= DEPLOYMENT =======================
function reqVsTarget(req, tgt, f) {
  if (req == null || tgt == null) return '';
  const d = req - tgt;
  if (Math.abs(d) < 1) return 'request igual ao target';
  return d > 0 ? `request ${f(d)} acima do target` : `request ${f(-d)} abaixo do target`;
}

// Quadro "aplicado hoje × recomendado": por recurso, o valor atual, o recomendado, a mudança e a ação.
function compareTable(vpa, rec, cur, pods) {
  if (!vpa) return emptyState('Sem VPA', 'Crie um VerticalPodAutoscaler com update mode Off para este deployment para exibir a comparação.');
  const t = rec && rec.target;
  if (!t) return emptyState('Aguardando recomendação', `O VPA <b>${esc(vpa.name)}</b> ainda não gerou recomendação para este container. Isso leva alguns minutos.`);
  const pol = vpa.policies.find(p => p.container === sel.container) || vpa.policies.find(p => p.container === '*');
  const reqOnly = pol && pol.values === 'RequestsOnly';
  const controlled = pol && pol.controlled && pol.controlled.length ? pol.controlled : ['cpu', 'memory'];
  const pct = (a, b) => a == null || b == null || !a ? '' : ` (${b > a ? '+' : '−'}${nf(Math.abs(b - a) / a * 100)}%)`;
  const change = (a, b, f) => a == null || b == null ? '–' : Math.abs(b - a) < 1 ? 'igual' : signed(b - a, f) + pct(a, b);
  const action = (now, next, lo, up) => {
    if (now == null) return label('Set request', 'warn', 'Sem request definido: pod com QoS BestEffort/Burstable sujeito a eviction');
    if (next == null || Math.abs(next - now) < 1) return label('Keep', 'ok');
    if (lo != null && up != null && now >= lo && now <= up) return label('Keep', 'ok', 'Valor atual entre lower e upper bound') + sub('within bounds');
    return next > now ? label('Increase', 'bad', 'Under-provisioned: risco de CPU throttling ou OOMKilled') : label('Decrease', 'warn', 'Over-provisioned: capacidade reservada e ociosa');
  };
  const rows = [];
  const add = (res, k, f, req, lim) => {
    if (!controlled.includes(res)) {
      rows.push(`<tr class="pf-v6-c-table__tr">${td((res === 'cpu' ? 'CPU' : 'Memory') + ' request', 'strong')}${tdn(f(req))}${tdn('–')}${tdn('–')}${td(label('Not controlled', 'wait', 'Recurso fora de controlledResources na resourcePolicy'))}</tr>`);
      return;
    }
    const lo = rec.lowerBound && rec.lowerBound[k], up = rec.upperBound && rec.upperBound[k];
    const nreq = Math.ceil(t[k]);
    const inBand = req != null && lo != null && up != null && req >= lo && req <= up;
    let nlim = null, limNote = '';
    if (lim == null) limNote = 'sem limit definido';
    else if (reqOnly) { nlim = lim; limNote = 'controlledValues: RequestsOnly (limit inalterado)'; }
    else if (req) nlim = Math.ceil(nreq * lim / req);
    const nm = res === 'cpu' ? 'CPU' : 'Memory';
    rows.push(`<tr class="pf-v6-c-table__tr">${td(nm + ' request', 'strong')}${tdn(f(req))}${tdn(`<span class="strong">${f(nreq)}</span>`)}${tdn(change(req, nreq, f))}${td(action(req, nreq, lo, up))}</tr>`);
    rows.push(`<tr class="pf-v6-c-table__tr">${td(nm + ' limit', 'strong')}${tdn(f(lim))}${tdn(nlim == null ? '–' : f(nlim))}${tdn(nlim == null ? '–' : change(lim, nlim, f))}${td(nlim == null || reqOnly ? sub(limNote) : inBand || Math.abs(nlim - lim) < 1 ? label('Keep', 'ok') : label('Scales with request', 'info'))}</tr>`);
  };
  add('cpu', 'cpu_m', fCpu, cur.cr, cur.cl);
  add('memory', 'mem_mib', fMem, cur.mr, cur.ml);
  let total = '';
  const n = Math.max(pods || 0, 1);
  if (cur.cr != null || cur.mr != null) {
    const cNow = (cur.cr || 0) * n, cNext = Math.ceil(t.cpu_m) * n, mNow = (cur.mr || 0) * n, mNext = Math.ceil(t.mem_mib) * n;
    total = `<p class="card-desc">Impacto com ${nf(n)} pod(s): CPU requests de <b>${fCpu(cNow)}</b> para <b>${fCpu(cNext)}</b> (${signed(cNext - cNow, fCpu)})
      e memory requests de <b>${fMem(mNow)}</b> para <b>${fMem(mNext)}</b> (${signed(mNext - mNow, fMem)}).</p>`;
  }
  const low = vpa.conditions.some(c => c.type === 'LowConfidence' && c.status === 'True');
  return `<div class="table-wrap">${table([{ t: 'Resource' }, { t: 'Current', num: 1 }, { t: 'Recommended', num: 1 }, { t: 'Delta', num: 1 }, { t: 'Action' }],
      rows.join(''), 'Configuração atual × recomendação do VPA')}</div>${total}`
    + (low ? alertBox('info', 'Recomendação com Low confidence', 'O VPA reportou a condition LowConfidence: aguarde a recomendação convergir antes de aplicar.') : '');
}

// Conformidade: todo recurso controlado pelo VPA com request entre lower e upper bound.
function compliance(vpa, rec, cr, mr) {
  const pol = vpa && (vpa.policies.find(p => p.container === sel.container) || vpa.policies.find(p => p.container === '*'));
  const controlled = pol && pol.controlled && pol.controlled.length ? pol.controlled : ['cpu', 'memory'];
  const items = [];
  const add = (res, name, k, req, fmt) => {
    if (!controlled.includes(res) || !rec) return;
    const lo = rec.lowerBound && rec.lowerBound[k], up = rec.upperBound && rec.upperBound[k];
    if (lo == null || up == null) return;
    items.push({ name, req, lo, up, fmt, ok: req != null && req >= lo && req <= up });
  };
  add('cpu', 'CPU', 'cpu_m', cr, fCpu);
  add('memory', 'Memory', 'mem_mib', mr, fMem);
  return { ok: items.length > 0 && items.every(i => i.ok), items };
}

function renderDeploy(m, h) {
  const vpa = currentVPA(), rec = currentRec(), t = rec && rec.target;
  const entries = (h && h.entries) || [];
  setError('metrics', errText('Métricas', m && m.errors));
  if (!m) return;
  const xs = extent(m.cpu, m.memory, m.netRx);
  const cr = lastVal(m.cpuReq), mr = lastVal(m.memReq), cl = lastVal(m.cpuLim), ml = lastVal(m.memLim);
  const liveCpu = live(m.cpu, m.stepSeconds), liveMem = live(m.memory, m.stepSeconds);
  const pods = Math.max(liveCpu.length, liveMem.length);
  const podsWindow = Math.max((m.cpu || []).length, (m.memory || []).length);
  const restarts = lastSum(live(m.restarts, m.stepSeconds));
  const low = vpa && vpa.conditions.some(c => c.type === 'LowConfidence' && c.status === 'True');

  $('dStats').innerHTML =
    stat('Running pods', nf(pods), [restarts ? label(`${nf(restarts)} restart(s)`, 'bad') : 'no restarts', podsWindow > pods ? `${podsWindow} no time range` : ''].filter(Boolean).join(' · ')) +
    stat('CPU usage (total)', fCpu(lastSum(liveCpu)), `request/pod ${fCpu(cr)} · limit ${fCpu(cl)}`) +
    stat('Memory usage (total)', fMem(lastSum(liveMem)), `request/pod ${fMem(mr)} · limit ${fMem(ml)}`) +
    stat('VPA target · CPU', t ? fCpu(t.cpu_m) : '–', reqVsTarget(cr, t && t.cpu_m, fCpu)) +
    stat('VPA target · memory', t ? fMem(t.mem_mib) : '–', reqVsTarget(mr, t && t.mem_mib, fMem)) +
    stat('VPA update mode', vpa ? esc(vpa.updateMode) : 'sem VPA',
      vpa ? (low ? label('Low confidence', 'info') : t ? label('Recommendation provided', 'ok') : label('Pending', 'wait')) : 'crie um VPA para gerar recomendações');

  const thr = (m.throttle || []).flatMap(s => s.points.map(p => p[1]));
  const maxThr = thr.length ? Math.max(...thr) : 0;
  const banners = [];
  if (low) banners.push(alertBox('info', 'Histórico insuficiente para este deployment (LowConfidence)', 'O target e os bounds lower/upper ainda vão variar conforme a carga real.'));
  if (restarts) banners.push(alertBox('bad', `${nf(restarts)} restart(s) neste deployment`, 'Veja o termination reason na página Pods. OOMKilled indica memory limit excedido.'));
  if (maxThr > 25) banners.push(alertBox('warn', `CPU throttling atingiu ${nf(maxThr)}% no time range`, 'O CPU limit está restringindo o container.'));
  const hp = hpaOf(sel.ns, sel.deploy);
  if (hp && hp.vpa && hp.vpa.kind === 'conflict') banners.push(alertBox('bad', `Conflito com o HPA ${esc(hp.name)}`,
    `O VPA (update mode ${esc(hp.vpa.mode)}) altera o request de ${esc(hp.vpa.resources.join(' e '))}, e o HPA escala pela utilização desse mesmo request. <a href="#hpa/${esc(sel.ns)}/${esc(sel.deploy)}/${esc(sel.container)}">Ver scaling</a>`));
  else if (hp) banners.push(alertBox('info', `Este deployment também tem o HPA ${esc(hp.name)}`,
    `<a href="#hpa/${esc(sel.ns)}/${esc(sel.deploy)}/${esc(sel.container)}">Ver o impacto da recomendação no scaling</a>`));
  $('dBanner').innerHTML = banners.join('');

  // Aplicado hoje × recomendado
  $('dCompare').innerHTML = compareTable(vpa, rec, { cr, cl, mr, ml }, pods);

  // Recomendação × request
  if (!vpa) $('dRec').innerHTML = emptyState('Sem VPA', 'Este deployment não possui VerticalPodAutoscaler.');
  else if (!rec) $('dRec').innerHTML = emptyState('Aguardando recomendação', `O VPA <b>${esc(vpa.name)}</b> ainda não gerou recomendação para o container <b>${esc(sel.container)}</b>. Isso leva alguns minutos.`);
  else {
    const row = (lbl, k, f, req) => {
      const lo = rec.lowerBound && rec.lowerBound[k], up = rec.upperBound && rec.upperBound[k];
      const st = req == null ? label('No request', 'warn') : lo != null && req < lo ? label('Under-provisioned', 'warn') : up != null && req > up ? label('Over-provisioned', 'bad') : label('Right-sized', 'ok');
      return `<tr class="pf-v6-c-table__tr">${td(lbl, 'strong')}${tdn(f(req))}${tdn(f(lo))}${tdn(`<span class="strong">${f(rec.target && rec.target[k])}</span>`)}${tdn(f(up))}${tdn(f(rec.uncappedTarget && rec.uncappedTarget[k]))}${td(st)}</tr>`;
    };
    const capped = rec.uncappedTarget && rec.target && (rec.uncappedTarget.cpu_m !== rec.target.cpu_m || rec.uncappedTarget.mem_mib !== rec.target.mem_mib);
    $('dRec').innerHTML = table([{ t: '' }, { t: 'Current request', num: 1 }, { t: 'Lower bound', num: 1 }, { t: 'Target', num: 1 }, { t: 'Upper bound', num: 1 }, { t: 'Uncapped', num: 1 }, { t: 'Status' }],
      row('CPU', 'cpu_m', fCpu, cr) + row('Memory', 'mem_mib', fMem, mr), 'Recommendation bounds')
      + (capped ? alertBox('warn', 'A resourcePolicy está limitando a recomendação', 'Uncapped target difere do target por causa de minAllowed/maxAllowed.') : '');
  }

  // Estado e política
  if (!vpa) $('dCond').innerHTML = emptyState('Sem VPA', 'Crie um VerticalPodAutoscaler para este deployment.');
  else {
    const pol = vpa.policies.find(p => p.container === sel.container) || vpa.policies.find(p => p.container === '*');
    const conds = vpa.conditions.length ? vpa.conditions.map(c => {
      const kind = c.status !== 'True' ? 'wait' : c.type === 'RecommendationProvided' ? 'ok' : c.type === 'LowConfidence' ? 'info' : 'bad';
      return `<tr class="pf-v6-c-table__tr">${td(esc(c.type))}${td(label(c.status, kind))}${td(esc(c.reason || '') + sub(esc(c.message || '')))}${td(c.since ? 'há ' + age(c.since) : '')}</tr>`;
    }).join('') : `<tr class="pf-v6-c-table__tr">${td('nenhuma condition reportada')}${td('')}${td('')}${td('')}</tr>`;
    $('dCond').innerHTML = `<dl class="kv">
        <dt>VPA</dt><dd>${esc(vpa.name)} · age ${age(vpa.created)}</dd>
        <dt>Update mode</dt><dd>${esc(vpa.updateMode)}</dd>
        <dt>Resource policy</dt><dd>${pol ? `${esc(pol.container)}${pol.mode ? ' · mode ' + esc(pol.mode) : ''}${pol.controlled ? ' · controlledResources: ' + esc(pol.controlled.join(', ')) : ''}${pol.values ? ' · ' + esc(pol.values) : ''}
          ${sub(`minAllowed ${fCpu(pol.minAllowed.cpu_m)} / ${fMem(pol.minAllowed.mem_mib)} · maxAllowed ${fCpu(pol.maxAllowed.cpu_m)} / ${fMem(pol.maxAllowed.mem_mib)}`)}` : 'default (sem restrições)'}</dd>
      </dl>
      <div class="table-wrap">${table([{ t: 'Condition' }, { t: 'Status' }, { t: 'Reason' }, { t: 'Last transition' }], conds, 'Conditions do VPA')}</div>`;
  }

  // Percentis
  const cv = allVals(m.cpu), mv = allVals(m.memory);
  const prow = (lbl, v, f, tgt, req) => `<tr class="pf-v6-c-table__tr">${td(lbl, 'strong')}${[0.5, 0.9, 0.95, 0.99].map(p => tdn(f(percentile(v, p)))).join('')}
    ${tdn(f(v.length ? v[v.length - 1] : null))}${tdn(`<span class="strong">${f(tgt)}</span>`)}${tdn(f(req))}</tr>`;
  $('dPct').innerHTML = cv.length || mv.length
    ? table([{ t: '' }, { t: 'P50', num: 1 }, { t: 'P90', num: 1 }, { t: 'P95', num: 1 }, { t: 'P99', num: 1 }, { t: 'Max', num: 1 }, { t: 'VPA target', num: 1 }, { t: 'Request', num: 1 }],
        prow('CPU', cv, fCpu, t && t.cpu_m, cr) + prow('Memory', mv, fMem, t && t.mem_mib, mr), 'Percentis de uso')
      + sub(`Time range ${winLbl()}: ${nf(cv.length)} amostras de CPU e ${nf(mv.length)} de memória (step de ${nf(m.stepSeconds)} s).`)
    : emptyState('Sem dados de uso', 'Nenhuma amostra no time range selecionado.');

  // Gráficos de uso
  const lineVPA = (k, x) => entries.length ? [
    stepDS('VPA target', entries, e => e.tg && e.tg[k], '--vpa-vpa', [2, 3], 2, x),
    stepDS('VPA lower', entries, e => e.lo && e.lo[k], '--vpa-vpa', [1, 4], 1, x),
    stepDS('VPA upper', entries, e => e.up && e.up[k], '--vpa-vpa', [1, 4], 1, x),
  ] : [constDS('VPA target', t && t[k], x, '--vpa-vpa')];
  setChart('cCpu', [...podDS(m.cpu), refDS('request', m.cpuReq, '--vpa-request'), refDS('limit', m.cpuLim, '--vpa-limit'), ...lineVPA('cpu_m', xs)], xs);
  setChart('cMem', [...podDS(m.memory), refDS('request', m.memReq, '--vpa-request'), refDS('limit', m.memLim, '--vpa-limit'), ...lineVPA('mem_mib', xs)], xs);
  setChart('cThr', podDS(m.throttle), xs);
  setChart('cRst', podDS(m.restarts, { stepped: 'before', tension: 0 }), xs);
  setChart('cRss', [...podDS(m.memory, { borderWidth: 1, borderDash: [4, 3] }).map(d => ({ ...d, label: d.label + ' (working set)' })), ...podDS(m.memRss)], xs);
  setChart('cNet', [...podDS(m.netRx).map(d => ({ ...d, label: d.label + ' rx' })), ...podDS(m.netTx, { borderDash: [5, 4] }).map(d => ({ ...d, label: d.label + ' tx' }))], xs);

  // Histórico da recomendação
  const now = Date.now(), hx = [now - WINDOWS[range], now];
  const histSets = (k, reqList) => [
    stepDS('target', entries, e => e.tg && e.tg[k], '--vpa-vpa', [], 2.5, hx),
    stepDS('lower bound', entries, e => e.lo && e.lo[k], '--vpa-s1', [6, 4], 1.5, hx),
    stepDS('upper bound', entries, e => e.up && e.up[k], '--vpa-limit', [6, 4], 1.5, hx),
    stepDS('uncapped', entries, e => e.un && e.un[k], '--vpa-request', [2, 3], 1, hx),
    refDS('current request', reqList, '--vpa-s3'),
  ];
  setChart('cHCpu', histSets('cpu_m', m.cpuReq), hx);
  setChart('cHMem', histSets('mem_mib', m.memReq), hx);
  const since = h && h.since ? `coletado desde ${new Date(h.since).toLocaleString('pt-BR')}` : 'sem registros ainda (coleta a cada minuto)';
  const pers = h && h.persistent === false ? ' · somente em memória (perdido no restart)' : '';
  $('hCpuDesc').textContent = `millicores · ${since}${pers}`;
  $('hMemDesc').textContent = `MiB · ${since}${pers}`;

  // Comandos para aplicar
  if (!t) { $('dCmd').innerHTML = emptyState('Sem recomendação', 'Não há recomendação do VPA para este container.'); return; }
  const comp = compliance(vpa, rec, cr, mr);
  if (comp.ok) {
    $('dCmd').innerHTML = alertBox('ok', 'Compliant with VPA recommendation',
      `Os requests atuais estão entre o lower e o upper bound do VPA (${comp.items.map(i => `${i.name} ${i.fmt(i.req)} em ${i.fmt(i.lo)} – ${i.fmt(i.up)}`).join(' · ')}). Nenhuma ação necessária.`);
    return;
  }
  const outOf = comp.items.filter(i => !i.ok);
  const cpuT = Math.ceil(t.cpu_m), memT = Math.ceil(t.mem_mib);
  const base = `oc -n ${sel.ns} set resources deployment/${sel.deploy} -c ${sel.container}`;
  const cmdReq = `${base} \\\n  --requests=cpu=${cpuT}m,memory=${memT}Mi`;
  const limParts = [];
  if (cl != null && cr) limParts.push(`cpu=${Math.ceil(cpuT * cl / cr)}m`);
  if (ml != null && mr) limParts.push(`memory=${Math.ceil(memT * ml / mr)}Mi`);
  const yaml = `resources:\n  requests:\n    cpu: ${cpuT}m\n    memory: ${memT}Mi${limParts.length ? '\n  limits:\n' + limParts.map(p => '    ' + p.replace('=', ': ')).join('\n') : ''}`;
  $('dCmd').innerHTML = alertBox('warn', 'Non-compliant with VPA recommendation',
      outOf.map(i => i.req == null ? `${i.name}: sem request definido` : `${i.name} request ${i.fmt(i.req)} ${i.req < i.lo ? 'abaixo do lower bound' : 'acima do upper bound'} (${i.fmt(i.lo)} – ${i.fmt(i.up)})`).join('<br>'))
    + codeBlock('Somente requests (o que o VPA ajusta)', cmdReq)
    + (limParts.length ? codeBlock('Requests e limits, preservando o ratio limit/request atual', `${cmdReq} \\\n  --limits=${limParts.join(',')}`) : '')
    + codeBlock('YAML equivalente', yaml)
    + (vpa && vpa.updateMode !== 'Off' ? alertBox('warn', 'Este VPA não está em update mode Off', 'O próprio VPA ajusta os pods; uma alteração manual pode ser sobrescrita.') : '');
}

// ======================= PODS =======================
function renderPods(data) {
  setError('pods', errText('Pods', data.errors));
  const pods = data.pods || [];
  if (!pods.length) { $('pTable').innerHTML = emptyState('Nenhum pod', 'Nenhum pod encontrado para este deployment.'); $('pBanner').innerHTML = ''; return; }
  const ooms = [];
  let rows = '';
  for (const p of pods) {
    p.containers.forEach((c, i) => {
      const lt = c.lastTermination;
      if (lt && lt.reason === 'OOMKilled') ooms.push(`${p.name}/${c.name}`);
      const stKind = c.state === 'Running' ? 'ok' : /CrashLoop|Error|OOM/.test(c.state) ? 'bad' : 'warn';
      const cpuP = pctOf(c.cpuUse, c.requests.cpu_m), memP = pctOf(c.memUse, c.requests.mem_mib), memLP = pctOf(c.memUse, c.limits.mem_mib);
      const n = p.containers.length;
      rows += `<tr class="pf-v6-c-table__tr${c.name === sel.container ? ' pf-m-selected' : ''}">
        ${i === 0 ? `<td class="pf-v6-c-table__td" rowspan="${n}"><span class="strong">${esc(shortPod(p.name))}</span>${sub(esc(p.name))}</td>
          <td class="pf-v6-c-table__td" rowspan="${n}">${esc(p.node || '–')}${sub(esc(p.podIP || ''))}</td>
          <td class="pf-v6-c-table__td" rowspan="${n}">${label(`${p.phase}${p.ready ? '' : ' · NotReady'}`, p.phase === 'Running' && p.ready ? 'ok' : 'warn')}${sub('QoS ' + esc(p.qos))}</td>
          <td class="pf-v6-c-table__td num" rowspan="${n}">${age(p.started)}</td>` : ''}
        ${td(esc(c.name))}${td(label(c.state || '–', stKind))}${tdn(`${nf(c.restarts)}${sub(c.restartsWin != null ? `${nf(c.restartsWin)} em ${winLbl()}` : '')}`, c.restartsWin ? 't-bad' : '')}
        ${td(lt ? `${label(lt.reason, lt.reason === 'OOMKilled' ? 'bad' : 'warn')} ${sub(`exit code ${lt.exitCode} · há ${age(lt.finishedAt)}`)}` : '–')}
        ${tdn(`${fCpu(c.cpuUse)}${sub(cpuP != null ? nf(cpuP) + '% do request' : '')}${meter(cpuP, 90, 100)}${sub(c.cpuMax != null ? `peak ${winLbl()}: ${fCpu(c.cpuMax)}` : '')}`)}
        ${tdn(`${fCpu(c.requests.cpu_m)} / ${fCpu(c.limits.cpu_m)}`)}
        ${tdn(`${fMem(c.memUse)}${sub([memP != null ? nf(memP) + '% do request' : '', memLP != null ? nf(memLP) + '% do limit' : ''].filter(Boolean).join(' · '))}${meter(memLP != null ? memLP : memP)}${sub(c.memMax != null ? `peak ${winLbl()}: ${fMem(c.memMax)}` : '')}`)}
        ${tdn(`${fMem(c.requests.mem_mib)} / ${fMem(c.limits.mem_mib)}`)}</tr>`;
    });
  }
  $('pBanner').innerHTML = ooms.length ? alertBox('bad', `OOMKilled detectado em: ${ooms.map(esc).join(', ')}`,
    'O container foi finalizado por exceder o memory limit. Avalie o target de memória do VPA ou aumente o limit.') : '';
  $('pTable').innerHTML = table([{ t: 'Pod' }, { t: 'Node' }, { t: 'Phase' }, { t: 'Age', num: 1 }, { t: 'Container' }, { t: 'State' }, { t: `Restarts · total / ${winLbl()}`, num: 1 },
    { t: 'Last termination' }, { t: 'CPU usage', num: 1 }, { t: 'CPU request / limit', num: 1 }, { t: 'Memory usage', num: 1 }, { t: 'Memory request / limit', num: 1 }], rows, 'Pods');
}

// ======================= NÓS =======================
function renderNodes(data, podsData) {
  setError('nodes', errText('Nodes', data.errors));
  const nodes = data.nodes || [], rec = currentRec(), t = rec && rec.target, up = rec && rec.upperBound;
  const hosting = new Set(((podsData && podsData.pods) || []).map(p => p.node));
  const schedulable = n => n.ready && !n.unschedulable && !n.taints.some(x => /:NoSchedule$|:NoExecute$/.test(x));
  const fits = (n, r) => r && n.reqCpu_m != null && n.reqMem_mib != null && (n.allocCpu_m - n.reqCpu_m) >= r.cpu_m && (n.allocMem_mib - n.reqMem_mib) >= r.mem_mib;
  let fitT = 0, fitU = 0, cand = 0, aCpu = 0, rCpu = 0, aMem = 0, rMem = 0;
  for (const n of nodes) {
    aCpu += n.allocCpu_m; rCpu += n.reqCpu_m || 0; aMem += n.allocMem_mib; rMem += n.reqMem_mib || 0;
    if (schedulable(n)) { cand++; if (fits(n, t)) fitT++; if (fits(n, up)) fitU++; }
  }
  $('nStats').innerHTML =
    stat('Nodes', nf(nodes.length), `${cand} schedulable para workloads`) +
    stat('CPU requests do cluster', `${nf(pctOf(rCpu, aCpu))}%`, `${fCpu(rCpu)} de ${fCpu(aCpu)}${meter(pctOf(rCpu, aCpu))}`) +
    stat('Memory requests do cluster', `${nf(pctOf(rMem, aMem))}%`, `${fMem(rMem)} de ${fMem(aMem)}${meter(pctOf(rMem, aMem))}`) +
    stat('Nodes com capacidade (target)', t ? `${fitT} de ${cand}` : '–', t ? `${fCpu(t.cpu_m)} · ${fMem(t.mem_mib)} (${esc(sel.deploy)})` : 'selecione um deployment com VPA') +
    stat('Nodes com capacidade (upper bound)', up ? `${fitU} de ${cand}` : '–', up ? `${fCpu(up.cpu_m)} · ${fMem(up.mem_mib)}` : '');
  $('nTable').innerHTML = nodes.length ? table(
    [{ t: 'Node' }, { t: 'Roles' }, { t: 'Status' }, { t: 'CPU allocatable', num: 1 }, { t: 'CPU requested', num: 1 }, { t: 'CPU usage', num: 1 }, { t: 'CPU available', num: 1 },
     { t: 'Memory allocatable', num: 1 }, { t: 'Memory requested', num: 1 }, { t: 'Memory usage', num: 1 }, { t: 'Memory available', num: 1 }, { t: 'Pods', num: 1 }, { t: 'Fits target?' }],
    nodes.map(n => {
      const fc = n.reqCpu_m != null ? n.allocCpu_m - n.reqCpu_m : null, fm = n.reqMem_mib != null ? n.allocMem_mib - n.reqMem_mib : null;
      const rcp = pctOf(n.reqCpu_m, n.allocCpu_m), ucp = pctOf(n.useCpu_m, n.allocCpu_m), rmp = pctOf(n.reqMem_mib, n.allocMem_mib), ump = pctOf(n.useMem_mib, n.allocMem_mib);
      const fit = !t ? '–' : !schedulable(n) ? sub('unschedulable (taint/cordon)') : fits(n, t) ? label(fits(n, up) ? 'Yes, até upper bound' : 'Yes', 'ok') : label('No', 'bad');
      return `<tr class="pf-v6-c-table__tr${hosting.has(n.name) ? ' pf-m-selected' : ''}">
        ${td(`<span class="strong">${esc(n.name)}</span>${sub([n.instanceType, n.zone, hosting.has(n.name) ? 'executa pods do deployment' : ''].filter(Boolean).map(esc).join(' · '))}`)}
        ${td(esc(n.roles.join(', ') || '–'))}
        ${td(label(n.ready ? (n.unschedulable ? 'Ready, SchedulingDisabled' : 'Ready') : 'NotReady', n.ready ? (n.unschedulable ? 'warn' : 'ok') : 'bad') + (n.taints.length ? sub(`<span title="${esc(n.taints.join('\n'))}">${n.taints.length} taint(s)</span>`) : ''))}
        ${tdn(fCpu(n.allocCpu_m))}${tdn(fCpu(n.reqCpu_m) + sub(nf(rcp) + '%') + meter(rcp))}${tdn(fCpu(n.useCpu_m) + sub(nf(ucp) + '%') + meter(ucp) + sub(n.useCpuMax_m != null ? `peak ${winLbl()}: ${fCpu(n.useCpuMax_m)}` : ''))}${tdn(fCpu(fc))}
        ${tdn(fMem(n.allocMem_mib))}${tdn(fMem(n.reqMem_mib) + sub(nf(rmp) + '%') + meter(rmp))}${tdn(fMem(n.useMem_mib) + sub(nf(ump) + '%') + meter(ump) + sub(n.useMemMax_mib != null ? `peak ${winLbl()}: ${fMem(n.useMemMax_mib)}` : ''))}${tdn(fMem(fm))}
        ${tdn(`${nf(n.pods)} / ${n.allocPods}`)}${td(fit)}</tr>`;
    }).join(''), 'Nodes') : emptyState('Nenhum node', 'A API não retornou nodes.');
}

// ======================= ARMAZENAMENTO =======================
function renderStorage(data) {
  setError('storage', errText('Storage', data.errors));
  const pvcs = (data.pvcs || []).sort((a, b) => b.mounted - a.mounted || a.name.localeCompare(b.name));
  $('sTable').innerHTML = pvcs.length ? table(
    [{ t: 'Name' }, { t: 'Status' }, { t: 'StorageClass' }, { t: 'Access modes' }, { t: 'Capacity', num: 1 }, { t: 'Used', num: 1 }, { t: 'Available', num: 1 }, { t: 'Inodes', num: 1 }],
    pvcs.map(p => {
      const cap = p.statsCapacity_mib || p.capacity_mib, up = pctOf(p.used_mib, cap), ip = pctOf(p.inodesUsed, p.inodes);
      return `<tr class="pf-v6-c-table__tr${p.mounted ? ' pf-m-selected' : ''}">
        ${td(`<span class="strong">${esc(p.name)}</span>${p.mounted ? sub('montado pelo deployment') : ''}`)}${td(label(p.phase, p.phase === 'Bound' ? 'ok' : 'warn'))}
        ${td(esc(p.storageClass || '–'))}${td(esc((p.accessModes || []).join(', ')))}${tdn(fDisk(p.capacity_mib))}
        ${tdn(fDisk(p.used_mib) + sub(up != null ? nf(up, 1) + '%' : 'sem métrica') + meter(up) + sub(p.growth_mib != null ? `${p.growth_mib >= 0 ? '+' : '−'}${fDisk(Math.abs(p.growth_mib))} em ${winLbl()}` : ''))}
        ${tdn(p.used_mib != null && cap ? fDisk(cap - p.used_mib) : '–')}${tdn((ip != null ? nf(ip, 1) + '%' : '–') + meter(ip))}</tr>`;
    }).join(''), 'PVCs') : emptyState('Nenhum PVC', 'Este namespace não possui PersistentVolumeClaims.');
  $('sChartDesc').textContent = `MiB usados por PVC · time range ${winLbl()}`;
  const s = data.usedSeries || [];
  setChart('cPvc', podDS(s).map((d, i) => ({ ...d, label: s[i].name })), extent(s));
}

// ======================= HPA: utilitários =======================
const condOf = (h, type) => (h.conditions || []).find(c => c.type === type);
// ScalingActive=False logo após um scale (pods novos ainda sem amostra no metrics-server) é
// transitório: mostra "Loading metrics". Se passar de METRICS_GRACE_S ou for outro motivo
// (ex.: container sem request), continua como erro.
const METRICS_GRACE_S = 300;
function metricsState(h) {
  const c = condOf(h, 'ScalingActive');
  if (!c || c.status !== 'False') return 'ok';
  const transient = /no metrics returned|unable to get metrics|did not receive metrics|unable to fetch metrics|no recommendation/i.test(c.message || '')
    && !/missing request/i.test(c.message || '');
  const recent = !!c.since && (Date.now() - new Date(c.since)) / 1000 < METRICS_GRACE_S;
  return transient && recent ? 'loading' : 'error';
}
const METRIC_NAMES = { cpu: 'CPU', memory: 'Memory' };
const metricLabel = m => (METRIC_NAMES[m.name] || m.name) + (m.container ? ` (${m.container})` : '') + (['Pods', 'Object', 'External'].includes(m.type) ? ` · ${m.type}` : '');

/** Situação do HPA como rótulos (ícone + texto). */
function hpaStatus(h) {
  const out = [];
  const active = condOf(h, 'ScalingActive'), able = condOf(h, 'AbleToScale'), limited = condOf(h, 'ScalingLimited');
  if (able && able.status === 'False') out.push(label('Unable to scale', 'bad', able.message));
  const ms = metricsState(h);
  if (ms === 'loading') out.push(label('Loading metrics', 'loading', 'Aguardando as métricas dos pods novos no metrics-server'));
  else if (ms === 'error') out.push(label('Metrics unavailable', 'bad', active.message));
  if (h.maxReplicas && h.currentReplicas >= h.maxReplicas) out.push(label('At maxReplicas', 'warn', limited ? limited.message : ''));
  else if (h.desiredReplicas && h.desiredReplicas !== h.currentReplicas) out.push(label(h.desiredReplicas > h.currentReplicas ? 'Scaling up' : 'Scaling down', 'info'));
  else if (h.currentReplicas <= h.minReplicas && !out.length) out.push(label('At minReplicas', 'wait'));
  return out.length ? out.join('') : label('Stable', 'ok');
}
function vpaRelationLabel(rel) {
  if (!rel || rel.kind === 'none') return '<span class="sub">sem VPA</span>';
  if (rel.kind === 'conflict') return label('VPA conflict', 'bad', `VPA ${rel.vpa} (${rel.mode}) altera ${rel.resources.join(' e ')}`);
  if (rel.kind === 'recommend') return label('VPA recommendation only', 'info', `VPA ${rel.vpa} em update mode ${rel.mode}`);
  return label('VPA + custom metric', 'ok', `VPA ${rel.vpa} (${rel.mode}) e HPA por outra métrica`);
}
/** Posição das réplicas atuais dentro de mínimo–máximo. */
function replicaMeter(h) {
  if (!h.maxReplicas || h.maxReplicas <= h.minReplicas) return '';
  const pct = (h.currentReplicas - h.minReplicas) / (h.maxReplicas - h.minReplicas) * 100;
  return meter(Math.max(0, pct), 100, 1000);
}
/** Tendência de uma métrica de utilização (o HPA ignora até 10% de diferença). */
function trend(m) {
  if (m.currentUtil == null || !m.targetUtil) return '';
  const r = m.currentUtil / m.targetUtil;
  return r > 1.1 ? label('Above target', 'warn') : r < 0.9 ? label('Below target', 'info') : label('On target', 'ok');
}

// ======================= HPA: VISÃO GERAL =======================
let hoRows = [];
function renderHpaOverview(data) {
  setError('hpaOverview', errText('HPA', data.errors));
  hoRows = data.hpas || [];
  const atMax = hoRows.filter(h => h.maxReplicas && h.currentReplicas >= h.maxReplicas).length;
  const noMetric = hoRows.filter(h => metricsState(h) === 'error').length;
  const loadingMetric = hoRows.filter(h => metricsState(h) === 'loading').length;
  const conflicts = hoRows.filter(h => h.vpa && h.vpa.kind === 'conflict').length;
  const cur = hoRows.reduce((a, h) => a + (h.currentReplicas || 0), 0), max = hoRows.reduce((a, h) => a + (h.maxReplicas || 0), 0);
  $('hoStats').innerHTML =
    stat('HPAs', nf(hoRows.length), `${new Set(hoRows.map(h => h.namespace)).size} namespace(s)`) +
    stat('Running replicas', nf(cur), `de ${nf(max)} (soma de maxReplicas)${meter(pctOf(cur, max), 80, 95)}`) +
    stat(`Scaling events · ${winLbl()}`, nf(hoRows.filter(h => h.windowChanges > 0).length), `${nf(hoRows.reduce((a, h) => a + (h.windowChanges || 0), 0))} alteração(ões) de replicas`) +
    stat('At maxReplicas', nf(atMax), atMax ? label('Sem headroom para scale up', 'warn') : label('Headroom disponível', 'ok')) +
    stat('Metrics unavailable', nf(noMetric), noMetric ? label('ScalingActive=False', 'bad') : loadingMetric ? label(`Loading metrics (${loadingMetric})`, 'loading') : label('Metrics OK', 'ok')) +
    stat('VPA conflicts', nf(conflicts), conflicts ? label('Review required', 'bad') : 'nenhum');
  $('hoBanner').innerHTML = conflicts ? alertBox('bad', `${conflicts} HPA(s) em conflito com VPA`,
    'O VPA ativo altera o request de CPU/memória e o HPA escala pela utilização desse mesmo request. Consulte o Manual para as combinações suportadas.') : '';
  if (!hoRows.length) {
    $('hoTable').innerHTML = emptyState('Nenhum HPA encontrado', 'Crie um HorizontalPodAutoscaler para um deployment e ele aparece aqui.');
    return;
  }
  $('hoTable').innerHTML = table(
    [{ t: 'Namespace' }, { t: 'HPA' }, { t: 'Scale target' }, { t: 'Replicas', num: 1 }, { t: 'Min – max', num: 1 }, { t: 'Metrics (current / target)' },
     { t: `Replicas · ${winLbl()}`, num: 1 }, { t: 'Last scale', num: 1 }, { t: 'Status' }, { t: 'VPA' }],
    hoRows.map((h, i) => {
      const clickable = h.targetKind === 'Deployment';
      const metrics = h.metrics.length ? h.metrics.map(m => `<div>${esc(metricLabel(m))}: <span class="strong">${esc(m.current ?? '?')}</span> / ${esc(m.target ?? '?')}</div>`).join('') : '–';
      return `<tr class="pf-v6-c-table__tr${clickable ? ' pf-m-clickable' : ''}" data-i="${i}"${clickable ? ' tabindex="0"' : ''}>
        ${td(esc(h.namespace))}${td(`<span class="strong">${esc(h.name)}</span>`)}
        ${td(clickable ? `<a href="#hpa/${esc(h.namespace)}/${esc(h.targetName)}">${esc(h.targetName)}</a>${sub('Deployment')}` : `${esc(h.targetName)}${sub(esc(h.targetKind))}`)}
        ${tdn(`${nf(h.currentReplicas)}${h.desiredReplicas !== h.currentReplicas ? ` → ${nf(h.desiredReplicas)}` : ''}`)}
        ${tdn(`${nf(h.minReplicas)} – ${nf(h.maxReplicas)}${replicaMeter(h)}`)}
        ${td(metrics)}${tdn(h.windowMin != null ? `${nf(h.windowMin)} – ${nf(h.windowMax)}${sub(`${nf(h.windowChanges)} alteração(ões)`)}` : '–')}${tdn(h.lastScaleTime ? 'há ' + age(h.lastScaleTime) : '–')}
        ${td(`<span class="labels">${hpaStatus(h)}</span>`)}${td(vpaRelationLabel(h.vpa))}</tr>`;
    }).join(''), 'HorizontalPodAutoscalers');
  $('hoTable').querySelectorAll('tr.pf-m-clickable').forEach(tr => {
    const open = e => {
      if (e.target.closest('a')) return;
      const h = hoRows[+tr.dataset.i];
      sel = { ns: h.namespace, deploy: h.targetName, container: '' };
      fillSelectors(); showTab('hpa');
    };
    tr.addEventListener('click', open);
    tr.addEventListener('keydown', e => { if (e.key === 'Enter') open(e); });
  });
}

// ======================= HPA: ESCALONAMENTO =======================
function renderHpa(data) {
  setError('hpa', errText('HPA', data.errors));
  const h = data.hpa;
  $('hBody').hidden = !h;
  if (!h) {
    const others = (data.others || []).filter(o => o.targetKind === 'Deployment');
    $('hStats').innerHTML = ''; $('hBanner').innerHTML = '';
    $('hEmpty').innerHTML = data.none
      ? `<div class="pf-v6-c-card"><div class="pf-v6-c-card__body">${emptyState('Nenhum deployment com HPA', 'Crie um HorizontalPodAutoscaler para um deployment e ele aparece aqui.')}</div></div>`
      : `<div class="pf-v6-c-card"><div class="pf-v6-c-card__body">${emptyState('Este deployment não possui HPA',
      others.length ? `HPAs neste namespace: ${others.map(o => `<a href="#hpa/${esc(o.namespace)}/${esc(o.targetName)}">${esc(o.targetName)}</a>`).join(', ')}.`
        : 'Nenhum HPA neste namespace. Veja todos em HPA · Overview.')}</div></div>`;
    return;
  }
  $('hEmpty').innerHTML = '';
  const cpuM = h.metrics.find(m => m.type === 'Resource' && m.name === 'cpu');
  const memM = h.metrics.find(m => m.type === 'Resource' && m.name === 'memory');
  const lastCpuU = lastVal(data.cpuUtil), lastMemU = lastVal(data.memUtil);
  const utilStat = (title, m, last) => {
    if (m && m.targetUtil != null) return stat(title, m.currentUtil != null ? `${nf(m.currentUtil)}%` : '–', `target ${nf(m.targetUtil)}% ${trend(m)}`);
    if (m) return stat(title, esc(m.current ?? '–'), `target ${esc(m.target ?? '–')} por pod (AverageValue)${last != null ? ` · ${nf(last)}% do request` : ''}`);
    return stat(title, last != null ? `${nf(last)}%` : '–', 'do request · métrica não usada pelo HPA');
  };
  const scaling = h.desiredReplicas !== h.currentReplicas;
  $('hStats').innerHTML =
    stat('Replicas', nf(h.currentReplicas), [scaling ? label(`desired: ${h.desiredReplicas}`, 'info') : 'current = desired',
      (() => { const v = allVals((data.current || []).some(x => x.points.length) ? data.current : data.available); return v.length ? `${winLbl()}: ${nf(v[0])} a ${nf(v[v.length - 1])}` : ''; })()].filter(Boolean).join(' · ')) +
    stat('minReplicas – maxReplicas', `${nf(h.minReplicas)} – ${nf(h.maxReplicas)}`, replicaMeter(h) || '&nbsp;') +
    utilStat('CPU utilization', cpuM, lastCpuU) +
    utilStat('Memory utilization', memM, lastMemU) +
    stat('Last scale', h.lastScaleTime ? 'há ' + age(h.lastScaleTime) : '–', h.lastScaleTime ? new Date(h.lastScaleTime).toLocaleString('pt-BR') : 'nenhum scaling registrado') +
    stat('Status', `<span class="labels">${hpaStatus(h)}</span>`, vpaRelationLabel(h.vpa));

  // avisos
  const banners = [];
  const able = condOf(h, 'AbleToScale'), active = condOf(h, 'ScalingActive'), limited = condOf(h, 'ScalingLimited');
  if (able && able.status === 'False') banners.push(alertBox('bad', 'AbleToScale=False: o HPA não consegue alterar o scale do deployment', esc(able.message)));
  const mstate = metricsState(h);
  if (mstate === 'loading') banners.push(alertBox('loading', 'Loading new metrics',
    'O HPA está aguardando as primeiras amostras dos pods recém-criados no metrics-server. É normal durante um scale e costuma levar de 30 s a 2 min.'));
  else if (mstate === 'error') banners.push(alertBox('bad', 'ScalingActive=False: o HPA não consegue obter as métricas',
    `${esc(active.message)}${/request/i.test(active.message) ? '<br>Utilization (%) exige request definido em todos os containers do pod.' : ''}`));
  if (h.maxReplicas && h.currentReplicas >= h.maxReplicas) banners.push(alertBox('warn', `HPA em maxReplicas (${h.maxReplicas})`,
    `${limited ? esc(limited.message) + '. ' : ''}A carga exige mais replicas do que o permitido: aumente maxReplicas ou ajuste o request (veja o card Compatibilidade VPA × HPA).`));
  if (h.vpa && h.vpa.kind === 'conflict') banners.push(alertBox('bad', `Conflito com o VPA ${esc(h.vpa.vpa)} (update mode ${esc(h.vpa.mode)})`,
    `Ambos atuam sobre ${esc(h.vpa.resources.join(' e '))}: o VPA altera o request e o HPA escala pela % desse request. Configure o VPA com update mode Off ou o HPA com outra métrica.`));
  $('hBanner').innerHTML = banners.join('');

  // métricas
  $('hMetrics').innerHTML = h.metrics.length ? table(
    [{ t: 'Metric' }, { t: 'Target type' }, { t: 'Target', num: 1 }, { t: 'Current', num: 1 }, { t: 'Current ÷ target', num: 1 }, { t: 'Trend' }],
    h.metrics.map(m => {
      const ratio = m.currentUtil != null && m.targetUtil ? m.currentUtil / m.targetUtil * 100 : null;
      return `<tr class="pf-v6-c-table__tr">${td(`<span class="strong">${esc(metricLabel(m))}</span>`)}${td(esc(m.targetType === 'Utilization' ? 'Utilization (% do request)' : m.targetType === 'AverageValue' ? 'AverageValue (por pod)' : m.targetType))}
        ${tdn(esc(m.target ?? '–'))}${tdn(esc(m.current ?? '–'))}${tdn(ratio != null ? `${nf(ratio)}%${meter(ratio, 100, 150)}` : '–')}${td(trend(m) || '–')}</tr>`;
    }).join(''), 'Metrics do HPA') : emptyState('Sem métricas', 'Este HPA não possui métricas configuradas.');

  // configuração e condições
  const b = h.behavior, sideTxt = (x, up) => `${x.window ? `stabilizationWindowSeconds: ${x.window}` : (up ? 'imediato' : 'sem stabilization window')}${x.policies.length ? ' · ' + x.policies.join('; ') : ''}`;
  const conds = h.conditions.length ? h.conditions.map(c => {
    const kind = c.type === 'ScalingLimited' ? (c.status === 'True' ? 'warn' : 'ok') : c.type === 'ScalingActive' && mstate === 'loading' ? 'loading' : (c.status === 'True' ? 'ok' : 'bad');
    return `<tr class="pf-v6-c-table__tr">${td(esc(c.type))}${td(label(c.status, kind))}${td(esc(c.reason) + sub(esc(c.message)))}${td(c.since ? 'há ' + age(c.since) : '')}</tr>`;
  }).join('') : `<tr class="pf-v6-c-table__tr">${td('nenhuma condition reportada')}${td('')}${td('')}${td('')}</tr>`;
  $('hConfig').innerHTML = `<dl class="kv">
      <dt>HPA</dt><dd>${esc(h.name)} · age ${age(h.created)}</dd>
      <dt>scaleTargetRef</dt><dd>${esc(h.targetKind)}/${esc(h.targetName)}</dd>
      <dt>Replicas</dt><dd>minReplicas ${nf(h.minReplicas)} · maxReplicas ${nf(h.maxReplicas)}</dd>
      <dt>Scale up</dt><dd>${esc(sideTxt(b.scaleUp, true))}</dd>
      <dt>Scale down</dt><dd>${esc(sideTxt(b.scaleDown, false))}${b.custom ? '' : sub('behavior padrão do Kubernetes')}</dd>
    </dl>
    <div class="table-wrap">${table([{ t: 'Condition' }, { t: 'Status' }, { t: 'Reason' }, { t: 'Last transition' }], conds, 'Conditions do HPA')}</div>`;

  // projeção com a recomendação do VPA
  const vpa = currentVPA();
  const recs = vpa ? vpa.containers.filter(c => c.target) : [];
  const dep = findDep(sel.ns, sel.deploy);
  const allRecommended = vpa && dep && recs.length && dep.containers.every(n => recs.some(r => r.name === n));
  const vpaCpu = allRecommended ? recs.reduce((a, r) => a + r.target.cpu_m, 0) : null;
  const vpaMem = allRecommended ? recs.reduce((a, r) => a + r.target.mem_mib, 0) : null;
  const avgCpu = lastVal(data.cpuAvg), avgMem = lastVal(data.memAvg);
  const projection = (m, avg, vpaReq, f, lastU) => {
    if (!m || m.targetUtil == null || avg == null || !vpaReq) return null;
    const curU = m.currentUtil != null ? m.currentUtil : lastU;
    const reqNow = curU ? avg / (curU / 100) : null;
    const projU = avg / vpaReq * 100;
    // réplicas estimadas; mostra quantas o HPA pediria quando passa do máximo ou fica abaixo do mínimo
    const estimate = u => {
      if (u == null) return '–';
      const ratio = u / m.targetUtil;
      const raw = Math.abs(ratio - 1) <= 0.1 ? h.currentReplicas : Math.ceil(h.currentReplicas * ratio);
      const n = Math.min(h.maxReplicas, Math.max(h.minReplicas, raw));
      return nf(n) + (raw > h.maxReplicas ? sub(`calculado ${nf(raw)} (maxReplicas ${nf(h.maxReplicas)})`) : raw < h.minReplicas ? sub(`calculado ${nf(raw)} (minReplicas ${nf(h.minReplicas)})`) : '');
    };
    return `<tr class="pf-v6-c-table__tr">${td(`<span class="strong">${METRIC_NAMES[m.name]}</span>${sub(`target do HPA ${m.targetUtil}%`)}`)}
      ${tdn(f(reqNow))}${tdn(curU != null ? nf(curU) + '%' : '–')}${tdn(estimate(curU))}
      ${tdn(`<span class="strong">${f(vpaReq)}</span>`)}${tdn(nf(projU) + '%')}${tdn(`<span class="strong">${estimate(projU)}</span>`)}</tr>`;
  };
  let vpaHtml;
  if (!vpa) vpaHtml = emptyState('Sem VPA', 'Crie um VPA com update mode Off para este deployment e veja aqui o impacto da recomendação no scaling.');
  else if (h.vpa && h.vpa.kind === 'conflict') vpaHtml = alertBox('bad', 'VPA ativo e HPA pela mesma métrica',
    'Configure o VPA com update mode Off para usar a recomendação apenas como referência, ou configure o HPA com custom metric.');
  else if (!allRecommended) vpaHtml = emptyState('Aguardando recomendação', `O VPA ${esc(vpa.name)} ainda não gerou recomendação para todos os containers.`);
  else {
    const rows = [projection(cpuM, avgCpu, vpaCpu, fCpu, lastCpuU), projection(memM, avgMem, vpaMem, fMem, lastMemU)].filter(Boolean).join('');
    vpaHtml = rows
      ? `<p class="card-desc">Projeção de utilization e replicas, com o uso médio atual por pod, caso o request recomendado pelo VPA (${esc(vpa.name)}, update mode ${esc(vpa.updateMode)}) seja aplicado.</p>
         ${table([{ t: '' }, { t: 'Current request/pod', num: 1 }, { t: 'Utilization', num: 1 }, { t: 'Replicas', num: 1 },
                  { t: 'VPA request', num: 1 }, { t: 'Utilization', num: 1 }, { t: 'Replicas', num: 1 }], rows, 'Projeção')}
         ${sub('Estimativa: desiredReplicas = ⌈currentReplicas × utilization ÷ target⌉, limitado a minReplicas–maxReplicas, com tolerance de 10%.')}`
      : (cpuM || memM)
        ? alertBox('info', 'O HPA usa target do tipo AverageValue', 'Esse target não depende do request, portanto aplicar a recomendação do VPA não altera o número de replicas.')
        : alertBox('info', 'O HPA não escala por CPU nem memória', `Com custom/external metrics, o HPA e o VPA (${esc(vpa.name)}) podem atuar juntos sem conflito.`);
  }
  $('hVpa').innerHTML = vpaHtml;

  // gráficos
  const xs = extent(data.current, data.available, data.cpuUtil, data.memUtil);
  const stepped = { stepped: 'before', tension: 0 };
  const one = (lbl, list, colorVar, extra = {}) => { const s = (list || [])[0]; const c = cssVar(colorVar);
    return s && s.points.length ? { label: lbl, data: pts(s), borderColor: c, backgroundColor: c, ...stepped, ...extra } : null; };
  const hasHpaSeries = (data.current || []).some(s => s.points.length);
  setChart('cHRep', [
    hasHpaSeries ? one('current', data.current, '--vpa-s1', { borderWidth: 2.5 }) : one('available (deployment)', data.available, '--vpa-s1', { borderWidth: 2.5 }),
    one('desired', data.desired, '--vpa-s4', { borderDash: [5, 3] }),
    one('minReplicas', data.min, '--vpa-request', { borderDash: [6, 4], borderWidth: 1.5 }) || constDS('minReplicas', h.minReplicas, xs, '--vpa-request'),
    one('maxReplicas', data.max, '--vpa-limit', { borderDash: [6, 4], borderWidth: 1.5 }) || constDS('maxReplicas', h.maxReplicas, xs, '--vpa-limit'),
  ], xs);
  // utilização projetada com o request do VPA (mesma série de uso, dividida pelo request recomendado)
  const projSeries = (avgList, vpaReq) => {
    const s = (avgList || [])[0];
    if (!s || !vpaReq || (h.vpa && h.vpa.kind === 'conflict')) return null;
    const c = cssVar('--vpa-vpa');
    return { label: 'com request do VPA', data: s.points.map(p => ({ x: p[0], y: p[1] / vpaReq * 100 })), borderColor: c, backgroundColor: c, borderDash: [2, 3], borderWidth: 1.5 };
  };
  setChart('cHCpuU', [one('utilization', data.cpuUtil, '--vpa-s1', { stepped: false, tension: 0.2 }),
    cpuM && cpuM.targetUtil != null ? constDS('target do HPA', cpuM.targetUtil, xs, '--vpa-request') : null,
    projSeries(data.cpuAvg, vpaCpu)], xs);
  setChart('cHMemU', [one('utilization', data.memUtil, '--vpa-s2', { stepped: false, tension: 0.2 }),
    memM && memM.targetUtil != null ? constDS('target do HPA', memM.targetUtil, xs, '--vpa-request') : null,
    projSeries(data.memAvg, vpaMem)], xs);

  // eventos
  const ev = data.events || [];
  $('hEvents').innerHTML = ev.length ? table([{ t: 'Last seen', num: 1 }, { t: 'Type' }, { t: 'Reason' }, { t: 'Message' }, { t: 'Count', num: 1 }],
    ev.map(e => `<tr class="pf-v6-c-table__tr">${tdn(e.time ? 'há ' + age(e.time) : '–')}${td(label(e.type || '–', e.type === 'Warning' ? 'warn' : 'ok'))}
      ${td(`<span class="strong">${esc(e.reason)}</span>`)}<td class="pf-v6-c-table__td wrap">${esc(e.message)}</td>${tdn(nf(e.count))}</tr>`).join(''), 'Events do HPA')
    : emptyState('Nenhum evento recente', 'O HPA não registrou events na última hora.');
}

// ======================= atualização =======================
// Uma atualização por vez; pedidos que chegam no meio são reexecutados ao final.
let loading = false, pending = false;
async function refreshTab() {
  if (loading) { pending = true; return; }
  loading = true;
  pending = false;
  const q = `ns=${encodeURIComponent(sel.ns)}&deploy=${encodeURIComponent(sel.deploy)}`;
  const qc = `${q}&container=${encodeURIComponent(sel.container)}&range=${range}`;
  const want = JSON.stringify(sel) + tab + range;
  const same = () => want === JSON.stringify(sel) + tab + range;
  try {
    if (tab === 'overview') {
      const o = await getJSON('api/overview?range=' + range);
      if (same()) renderOverview(o);
    } else if (tab === 'hpa-overview') {
      const o = await getJSON('api/hpa/overview?range=' + range);
      if (same()) renderHpaOverview(o);
    } else if (!sel.ns || !sel.deploy) {
      // Nenhum deployment selecionável (ex.: cluster sem HPA na página de escalonamento).
      if (tab === 'hpa') renderHpa({ hpa: null, others: [], none: true });
    } else {
      // Páginas que dependem do deployment selecionado.
      if (tab === 'hpa') {
        const d = await getJSON(`api/hpa/detail?${q}&range=${range}`);
        if (same()) renderHpa(d);
      } else if (tab === 'deploy' && sel.container) {
        const [m, h] = await Promise.all([getJSON('api/metrics?' + qc), getJSON('api/history?' + qc).catch(() => null)]);
        if (same()) renderDeploy(m, h);
      } else if (tab === 'pods') {
        const p = await getJSON(`api/pods?${q}&range=${range}`);
        if (same()) renderPods(p);
      } else if (tab === 'nodes') {
        const [n, p] = await Promise.all([getJSON('api/nodes?range=' + range), getJSON(`api/pods?${q}&range=${range}`).catch(() => null)]);
        if (same()) renderNodes(n, p);
      } else if (tab === 'storage') {
        const st = await getJSON(`api/storage?${q}&range=${range}`);
        if (same()) renderStorage(st);
      }
    }
    setError('fetch', '');
  } catch (e) {
    setError('fetch', 'Erro ao carregar: ' + e.message);
  } finally {
    loading = false;
    if (pending) refreshTab();
  }
}

async function refreshAll() {
  try {
    targets = await getJSON('api/targets');
    setError('targets', errText('Deployments/VPAs', targets.errors));
    if (targets.historyPersistent === false && !$('helpHist').dataset.warned) {
      $('helpHist').dataset.warned = '1';
      $('helpHist').textContent += ' Atenção: o volume do histórico não está gravável; os dados ficam somente em memória e são perdidos no restart do pod.';
    }
    fillSelectors();
    await refreshTab();
    $('updated').textContent = `Atualizado às ${new Date().toLocaleTimeString('pt-BR')} · ${targets.deployments.length} deployments · ${targets.vpas.length} VPAs`;
  } catch (e) {
    $('updated').textContent = 'Erro ao atualizar: ' + e.message;
  }
}

// ======================= início =======================
// ======================= dicas (?) =======================
// Os textos explicativos dos cards (p.card-desc fixos no HTML) viram um ícone "?" ao lado do
// título; o texto aparece ao passar o mouse ou focar o ícone. O <p> original continua no DOM
// (escondido), então o que o código atualiza nele (ex.: hCpuDesc) aparece na dica.
const HELP_ICON = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm.9 12.6H7.1v-1.8h1.8zm1.6-5.3c-.4.5-.9.8-1.3 1.1-.4.3-.4.5-.4 1v.3H7.1V9.2c0-.9.4-1.4 1-1.8.5-.4 1-.7 1-1.4 0-.6-.5-1-1.1-1-.7 0-1.2.4-1.3 1.2l-1.7-.3C5.2 4.3 6.4 3.4 8 3.4c1.8 0 3 1 3 2.5 0 .6-.2 1-.5 1.4z"/></svg>';
let tipEl = null;
function showTip(btn) {
  const src = btn._src;
  if (!src || !src.textContent.trim()) return;
  if (!tipEl) { tipEl = document.createElement('div'); tipEl.className = 'help-pop'; tipEl.setAttribute('role', 'tooltip'); tipEl.id = 'helpPop'; document.body.appendChild(tipEl); }
  tipEl.innerHTML = src.innerHTML;
  tipEl.hidden = false;
  btn.setAttribute('aria-describedby', 'helpPop');
  const r = btn.getBoundingClientRect(), w = Math.min(380, window.innerWidth - 24);
  tipEl.style.maxWidth = w + 'px';
  const tw = tipEl.offsetWidth, th = tipEl.offsetHeight;
  let left = Math.min(Math.max(12, r.left + r.width / 2 - tw / 2), window.innerWidth - tw - 12);
  let top = r.bottom + 8;
  if (top + th > window.innerHeight - 8) top = r.top - th - 8;
  tipEl.style.left = left + window.scrollX + 'px';
  tipEl.style.top = top + window.scrollY + 'px';
}
function hideTip(btn) { if (tipEl) tipEl.hidden = true; if (btn) btn.removeAttribute('aria-describedby'); }
function initHelpTips() {
  document.querySelectorAll('.pf-v6-c-card__body > p.card-desc').forEach(p => {
    const card = p.closest('.pf-v6-c-card'), title = card && card.querySelector('.pf-v6-c-card__title-text');
    if (!title) return;
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'help-tip'; btn.setAttribute('aria-label', 'Mais informações'); btn.innerHTML = HELP_ICON;
    btn._src = p;
    p.hidden = true;
    title.appendChild(btn);
    btn.addEventListener('mouseenter', () => showTip(btn));
    btn.addEventListener('mouseleave', () => hideTip(btn));
    btn.addEventListener('focus', () => showTip(btn));
    btn.addEventListener('blur', () => hideTip(btn));
    btn.addEventListener('click', e => { e.preventDefault(); tipEl && !tipEl.hidden ? hideTip(btn) : showTip(btn); });
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') hideTip(); });
  window.addEventListener('scroll', () => hideTip(), true);
}

// ======================= Export report (opções) =======================
// Escopo: deployments com VPA ou HPA. Namespaces e deployments começam todos marcados.
const rm = { ns: new Set(), dep: new Set(), lastFocus: null };
const rmDeps = () => targets.deployments.filter(d => d.hasVPA || d.hasHPA);
const rmNamespaces = () => [...new Set(rmDeps().map(d => d.namespace))].sort();
function rmRender() {
  const nsQ = $('rmNsSearch').value.trim().toLowerCase(), depQ = $('rmDepSearch').value.trim().toLowerCase();
  const nss = rmNamespaces();
  $('rmNsList').innerHTML = nss.filter(n => n.toLowerCase().includes(nsQ)).map(n => {
    const ds = rmDeps().filter(d => d.namespace === n);
    return `<label class="rm-item"><input type="checkbox" data-ns="${esc(n)}"${rm.ns.has(n) ? ' checked' : ''}>
      <span>${esc(n)}</span><small>${ds.length} deploy${ds.length > 1 ? 's' : ''}</small></label>`;
  }).join('') || '<p class="rm-empty">Nenhum namespace com VPA ou HPA.</p>';
  const deps = rmDeps().filter(d => rm.ns.has(d.namespace) && `${d.namespace}/${d.name}`.toLowerCase().includes(depQ));
  let lastNs = '';
  $('rmDepList').innerHTML = deps.map(d => {
    const key = `${d.namespace}/${d.name}`;
    const head = d.namespace !== lastNs ? `<p class="rm-group">${esc(d.namespace)}</p>` : '';
    lastNs = d.namespace;
    return `${head}<label class="rm-item"><input type="checkbox" data-dep="${esc(key)}"${rm.dep.has(key) ? ' checked' : ''}>
      <span>${esc(d.name)}</span><small>${[d.hasVPA ? 'VPA' : '', d.hasHPA ? 'HPA' : ''].filter(Boolean).join(' · ')}</small></label>`;
  }).join('') || `<p class="rm-empty">${rm.ns.size ? 'Nenhum deployment encontrado.' : 'Selecione ao menos um namespace.'}</p>`;
  const inScope = rmDeps().filter(d => rm.ns.has(d.namespace));
  const selDeps = inScope.filter(d => rm.dep.has(`${d.namespace}/${d.name}`));
  $('rmNsCount').textContent = `${rm.ns.size} de ${nss.length}`;
  $('rmDepCount').textContent = `${selDeps.length} de ${inScope.length}`;
  const secs = [...document.querySelectorAll('input[name="rmSec"]:checked')];
  const err = !rm.ns.size ? 'Selecione ao menos um namespace.' : !selDeps.length ? 'Selecione ao menos um deployment.'
    : !secs.length ? 'Selecione ao menos uma seção.' : '';
  // sem VPA/HPA no cluster ainda dá para gerar só Nodes
  const onlyCluster = !nss.length && secs.length && secs.every(x => x.value === 'nodes' || x.value === 'summary');
  $('rmError').textContent = onlyCluster ? '' : err;
  $('rmError').hidden = onlyCluster || !err;
  $('rmGenerate').disabled = !onlyCluster && !!err;
}
function openReportModal() {
  rm.lastFocus = document.activeElement;
  rm.ns = new Set(rmNamespaces());
  rm.dep = new Set(rmDeps().map(d => `${d.namespace}/${d.name}`));
  $('rmRange').value = range;
  $('rmNsSearch').value = ''; $('rmDepSearch').value = '';
  rmRender();
  $('reportModal').hidden = false;
  document.body.classList.add('rm-open');
  setTimeout(() => $('rmRange').focus(), 0);
}
function closeReportModal() {
  $('reportModal').hidden = true;
  document.body.classList.remove('rm-open');
  if (rm.lastFocus) rm.lastFocus.focus();
}
function initReportModal() {
  const m = $('reportModal');
  m.addEventListener('click', e => {
    if (e.target.closest('[data-rm-close]') || e.target === m || e.target.classList.contains('pf-v6-l-bullseye')) { closeReportModal(); return; }
    const all = e.target.closest('[data-rm-all]'), none = e.target.closest('[data-rm-none]');
    if (all || none) {
      const which = (all || none).dataset.rmAll || (none && none.dataset.rmNone);
      const q = $(which === 'ns' ? 'rmNsSearch' : 'rmDepSearch').value.trim().toLowerCase();
      if (which === 'ns') rmNamespaces().filter(n => n.toLowerCase().includes(q)).forEach(n => {
        if (all) { rm.ns.add(n); rmDeps().filter(d => d.namespace === n).forEach(d => rm.dep.add(`${d.namespace}/${d.name}`)); } else rm.ns.delete(n);
      });
      else rmDeps().filter(d => rm.ns.has(d.namespace) && `${d.namespace}/${d.name}`.toLowerCase().includes(q))
        .forEach(d => { const k = `${d.namespace}/${d.name}`; if (all) rm.dep.add(k); else rm.dep.delete(k); });
      rmRender();
    }
  });
  m.addEventListener('change', e => {
    const t = e.target;
    if (t.dataset.ns) {
      if (t.checked) { rm.ns.add(t.dataset.ns); rmDeps().filter(d => d.namespace === t.dataset.ns).forEach(d => rm.dep.add(`${d.namespace}/${d.name}`)); }
      else rm.ns.delete(t.dataset.ns);
    }
    if (t.dataset.dep) { if (t.checked) rm.dep.add(t.dataset.dep); else rm.dep.delete(t.dataset.dep); }
    rmRender();
  });
  $('rmNsSearch').addEventListener('input', rmRender);
  $('rmDepSearch').addEventListener('input', rmRender);
  document.addEventListener('keydown', e => {
    if (m.hidden) return;
    if (e.key === 'Escape') closeReportModal();
    if (e.key === 'Tab') {  // mantém o foco dentro da janela
      const f = [...m.querySelectorAll('button:not([disabled]), input, select')].filter(x => x.offsetParent !== null);
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    }
  });
  $('rmGenerate').addEventListener('click', () => {
    const nss = rmNamespaces(), inScope = rmDeps().filter(d => rm.ns.has(d.namespace));
    const selDeps = inScope.filter(d => rm.dep.has(`${d.namespace}/${d.name}`));
    const p = new URLSearchParams({ range: $('rmRange').value, tz: String(new Date().getTimezoneOffset()) });
    if (rm.ns.size && rm.ns.size < nss.length) p.set('ns', [...rm.ns].sort().join(','));
    if (selDeps.length < inScope.length) p.set('deploy', selDeps.map(d => `${d.namespace}/${d.name}`).join(','));
    const secs = [...document.querySelectorAll('input[name="rmSec"]:checked')].map(x => x.value);
    if (secs.length < 6) p.set('sections', secs.join(','));
    if ($('rmAttention').checked) p.set('attention', '1');
    window.open('report?' + p.toString(), '_blank', 'noopener');
    closeReportModal();
  });
}

function init() {
  initHelpTips();
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  const units = { cCpu: 'm', cHCpu: 'm', cMem: 'Mi', cHMem: 'Mi', cRss: 'Mi', cThr: '%', cRst: 'restarts', cNet: 'KiB/s', cPvc: 'MiB',
                  cHRep: 'replicas', cHCpuU: '%', cHMemU: '%' };
  Object.keys(units).forEach(id => makeChart(id, units[id]));

  $('helpOk').innerHTML = label('Right-sized', 'ok');
  $('helpLow').innerHTML = label('Under-provisioned', 'warn');
  $('helpHigh').innerHTML = label('Over-provisioned', 'bad');
  $('helpConflict').innerHTML = label('VPA conflict', 'bad');
  $('helpRecommend').innerHTML = label('VPA recommendation only', 'info');
  $('helpCombined').innerHTML = label('VPA + custom metric', 'ok');

  $('selNs').addEventListener('change', e => select(e.target.value, '', ''));
  $('selDep').addEventListener('change', e => select(sel.ns, e.target.value, ''));
  $('selCt').addEventListener('change', e => select(sel.ns, sel.deploy, e.target.value));
  document.querySelectorAll('.pf-v6-c-nav__link').forEach(a => a.addEventListener('click', e => { e.preventDefault(); showTab(a.dataset.tab); }));
  document.querySelectorAll('[data-tab-link]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); showTab(a.dataset.tabLink); }));
  document.querySelectorAll('#rangeGroup button').forEach(b => b.addEventListener('click', () => {
    range = b.dataset.range;
    document.querySelectorAll('#rangeGroup button').forEach(x => x.classList.toggle('pf-m-selected', x === b));
    refreshTab();
  }));
  $('reportBtn').addEventListener('click', openReportModal);
  initReportModal();
  $('navToggle').addEventListener('click', () => setSidebar(!$('sidebar').classList.contains('pf-m-expanded')));
  $('themeBtn').addEventListener('click', () => {
    const next = { system: 'light', light: 'dark', dark: 'system' }[themePref()];
    try { localStorage.setItem('vpa-theme', next); } catch (e) { /* sem armazenamento: só nesta visita */ }
    applyTheme();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-copy]');
    if (!b) return;
    try { await navigator.clipboard.writeText(b.dataset.copy); b.title = 'Copiado'; } catch (err) { b.title = 'Selecione e copie'; }
  });
  window.addEventListener('hashchange', () => { readHash(); fillSelectors(); showTab(tab); });
  if (window.innerWidth < 1200) setSidebar(false);

  getJSON('api/config').then(c => {
    document.title = c.title;
    $('appTitle').textContent = c.title;
    if (c.version) {
      const v = /^\d/.test(c.version) ? 'v' + c.version : c.version;
      $('appVersion').textContent = ' · ' + v;
      $('sidebarVersion').textContent = `${c.title} · version ${c.version}`;
      $('sidebarVersion').hidden = false;
      document.title = `${c.title} ${v}`;
    }
    document.querySelectorAll('.app-name').forEach(e => { e.textContent = c.title; });
    if (c.user) { $('userName').textContent = c.user; $('userMenu').hidden = false; }
    if (c.hasLogo) {
      const img = $('logo');
      // Logo quase quadrado também vira o ícone da aba; logos largos ficariam ilegíveis em 16 px.
      img.addEventListener('load', () => {
        const ratio = img.naturalWidth / Math.max(1, img.naturalHeight);
        if (ratio > 0.75 && ratio < 1.35) { const f = $('favicon'); f.removeAttribute('type'); f.href = 'logo'; }
      }, { once: true });
      img.src = 'logo';
    }
  }).catch(() => {});

  applyTheme();
  readHash();
  showTab(tab);
  refreshAll();
  setInterval(refreshAll, 15000);
}
document.addEventListener('DOMContentLoaded', init);
