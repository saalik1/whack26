const $ = (id) => document.getElementById(id);
let csvText = null;                // null = use the built-in data
let info = null;

async function post(url, body) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) {
    let detail = '';
    try { detail = (await res.json()).detail; } catch { /* no body */ }
    const err = new Error(typeof detail === 'string' && detail ? detail : `The server answered ${res.status}. Is the new api.py running?`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}
function showError(message) { $('test-error').textContent = message || ''; $('test-error').hidden = !message; }
const hourLabel = (h) => `${h}:00`;

/* ---------- the three inputs: a date, a number of days, a total ---------- */
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const niceDate = (iso) => {
  const d = new Date(`${iso}T12:00:00`);
  return Number.isNaN(d.getTime()) ? '' : `${WEEKDAYS[d.getDay()]} ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}`;
};
function syncLabels() {
  $('v-weekday').textContent = niceDate($('d-offer').value) || 'pick a date';
  $('v-days').textContent = $('s-days').value;
  $('v-extra').textContent = $('s-extra').value;
  if (info) {
    const normal = info.avgPerDay * Number($('s-days').value);
    $('v-extra-pct').textContent = `(about ${Math.round($('s-extra').value / normal * 100)}% more than a normal ${Number($('s-days').value) === 1 ? 'day' : 'stretch'})`;
  }
}
function setRanges() {
  $('d-offer').min = info.earliestOffer;
  $('d-offer').max = info.lastDate;
  if (fresh) {                                   // sensible start: about 60% of the way through the data
    const a = new Date(`${info.firstDate}T12:00:00`), b = new Date(`${info.lastDate}T12:00:00`);
    const pick = new Date(a.getTime() + (b - a) * 0.6);
    $('d-offer').value = pick.toISOString().slice(0, 10);
    fresh = false;
  }
  // the total slider scales with how long you watched: up to 60% of normal sales
  $('s-extra').max = Math.max(50, Math.round((info.avgPerDay * Number($('s-days').value) * 0.6) / 5) * 5);
  if (Number($('s-extra').value) > Number($('s-extra').max)) $('s-extra').value = $('s-extra').max;
  syncLabels();
}
let fresh = true;
$('d-offer').addEventListener('input', syncLabels);
$('s-days').addEventListener('input', () => { if (info) setRanges(); else syncLabels(); });
$('s-extra').addEventListener('input', syncLabels);

/* ---------- data ---------- */
async function loadSummary() {
  showError('');
  try {
    info = await post('/api/test_ai/summary', { csv: csvText });
    fresh = true;
    $('data-summary').textContent =
      `${info.source}: ${info.rows} open hours over ${info.days} days, about ${info.avgCustomers} customers an hour`
      + `, ${niceDate(info.firstDate)} to ${niceDate(info.lastDate)}`
      + (info.skippedRows ? ` (${info.skippedRows} rows outside 9:00-20:00 were ignored)` : '')
      + (info.datesAssumed ? '. Your file has no dates, so I numbered the days from a Monday' : '') + '.';
    setRanges();
    $('run').disabled = false;
  } catch (error) {
    info = null;
    $('run').disabled = true;
    $('data-summary').textContent = '';
    showError(error.message);
    if (csvText) { csvText = null; $('csv-clear').hidden = true; $('file-name').textContent = 'That file could not be used, so nothing is loaded. Choose another file or use ours.'; }
  }
}
$('csv-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 8_000_000) { showError('That file is too big (limit about 8 MB).'); return; }
  csvText = await file.text();
  $('file-name').textContent = `Using ${file.name}`;
  $('csv-clear').hidden = false;
  $('result').hidden = true;
  await loadSummary();
});
$('csv-clear').addEventListener('click', async () => {
  csvText = null;
  $('csv-file').value = '';
  $('csv-clear').hidden = true;
  $('file-name').textContent = 'Using our built-in data.';
  $('result').hidden = true;
  await loadSummary();
});

/* ---------- run ---------- */
const make = (name, attrs) => { const n = document.createElementNS('http://www.w3.org/2000/svg', name); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; };
function drawChart(series) {
  const svg = $('chart');
  svg.replaceChildren();
  const W = 700, H = 230, L = 40, R = 8, T = 10, B = 34;
  const max = Math.max(...series.map((p) => Math.max(p.customers, p.expected))) * 1.1 || 1;
  const x = (i) => L + (i / Math.max(1, series.length - 1)) * (W - L - R);
  const y = (v) => T + (1 - v / max) * (H - T - B);
  const first = series.findIndex((p) => p.offer);
  svg.append(make('rect', { x: x(first) - 4, y: T, width: W - R - x(first) + 4, height: H - T - B, fill: '#ffd84d', opacity: '0.28' }));
  for (let g = 0; g <= 4; g++) {
    const v = (max / 4) * g;
    svg.append(make('line', { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: '#2b2420', 'stroke-opacity': '0.12' }));
    const t = make('text', { x: L - 6, y: y(v) + 4, 'text-anchor': 'end', 'font-size': '11', fill: '#2b2420' });
    t.textContent = String(Math.round(v));
    svg.append(t);
  }
  const every = Math.ceil(series.length / 10);
  series.forEach((p, i) => {
    if (i % every !== 0) return;
    const t = make('text', { x: x(i), y: H - 12, 'text-anchor': 'middle', 'font-size': '10', fill: '#2b2420' });
    t.textContent = p.label;
    svg.append(t);
  });
  const line = (key, stroke, dash) => svg.append(make('polyline', {
    points: series.map((p, i) => `${x(i)},${y(p[key])}`).join(' '),
    fill: 'none', stroke, 'stroke-width': '2.5', 'stroke-linejoin': 'round', ...(dash ? { 'stroke-dasharray': '6 5' } : {}),
  }));
  line('customers', '#2f6ea6');
  line('expected', '#2b2420', true);
}
function showEvents(r) {
  const list = $('events-list');
  list.replaceChildren();
  $('events-note').textContent = r.events.length
    ? `Near ${r.location}. I gave these to the careful AI as events, so it expects those days to be busier (or quieter) before judging the offer.`
    : (r.eventsNote === 'events from DeepSeek' ? `DeepSeek found no significant events near ${r.location} on those days.` : r.eventsNote);
  for (const e of r.events) {
    const li = document.createElement('li');
    const sign = e.effect >= 0 ? '+' : '';
    const strong = document.createElement('strong');
    strong.textContent = `${e.date} · ${e.name}: ${sign}${Math.round(e.effect * 100)}% sales`;
    const why = document.createElement('span');
    why.textContent = ` ${e.why} (confidence ${Math.round(e.confidence * 100)}%)`;
    li.append(strong, why);
    list.append(li);
  }
}
function fill(prefix, v, extra) {
  const label = $(`r-${prefix}`);
  label.textContent = v.answer === 'GOOD' ? 'GOOD OFFER' : 'BAD OFFER';
  label.dataset.verdict = v.answer === 'GOOD' ? 'REAL' : 'FAKE';
  $(`r-${prefix}-text`).textContent = v.text + (extra || '');
}
$('run').addEventListener('click', async () => {
  showError('');
  $('run').disabled = true;
  try {
    const r = await post('/api/test_ai/run', {
      csv: csvText, offerDate: $('d-offer').value, days: Number($('s-days').value), extra: Number($('s-extra').value), location: $('location').value,
    });
    fill('careful', r.careful, ` (Confidence ${Math.round((r.careful.confidence ?? 0) * 100)}%.)`);
    showEvents(r);
    $('chart-total').textContent = `In the ${r.days} day${r.days === 1 ? '' : 's'} from ${r.offerStart}: the AI expected about ${r.expectedTotal} customers and you saw ${r.seenTotal}.`;
    drawChart(r.daily);
    $('result').hidden = false;
    $('result').scrollIntoView({ behavior: 'smooth', block: 'center' });
  } catch (error) {
    showError(error.message);
  } finally {
    $('run').disabled = !info;
  }
});

loadSummary();