import { runRound, startGame } from './api.js';

const $ = (id) => document.getElementById(id);
const INK = '#2b2420';
const colors = ['#e8624a', '#3d7de0', '#ffd84d', '#6fbf73', '#9950dc', '#e9549c', '#14a3a7'];
const skins = ['#f5c592', '#dfa768', '#a86e47', '#ffdab1'];
const hairs = ['#5a3a22', '#2b2420', '#c9772e', '#e8c15a', '#8a4b2a'];
const state = { round: 0, hour: 11, customers: 26, prediction: 43, weather: 'Sunny', carefulFooled: 0, naiveFooled: 0 };
const svgNS = 'http://www.w3.org/2000/svg';

function shape(tag, attrs, parent) {
  const element = document.createElementNS(svgNS, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  parent.append(element);
  return element;
}

/* ---------- weather icon (static markup only) ---------- */
const sun = '<g stroke="#2b2420" stroke-width="2.6" stroke-linecap="round"><circle cx="20" cy="20" r="8" fill="#ffd84d"/><path d="M20 4v5M20 31v5M4 20h5M31 20h5M8.500 8.500l3.500 3.500M28 28l3.500 3.500M8.500 31.500L12 28M28 12l3.500-3.500" fill="none"/></g>';
const cloud = '<path d="M11 30a7 7 0 0 1 0-14 9 9 0 0 1 17-2 7.500 7.500 0 0 1 1 16Z" fill="#fff" stroke="#2b2420" stroke-width="2.600" stroke-linejoin="round"/>';
const rain = cloud.replace('M11 30', 'M11 26') + '<path d="M13 32l-2 5M21 32l-2 5M29 32l-2 5" stroke="#2f6ea6" stroke-width="2.800" stroke-linecap="round"/>';
function showWeatherIcon(weather) {
  const w = String(weather).toLowerCase();
  const icon = /sun|clear|fine/.test(w) ? sun : /rain|shower|storm|drizzle/.test(w) ? rain : cloud;
  $('weather-icon').innerHTML = icon; // fixed internal strings only
}

showWeatherIcon(state.weather);

/* ---------- store picture changes with the time / event ---------- */
// Add more rules here later (first match wins), e.g. { when: (hour) => ..., image: 'rainy_store.png' }
const storeRules = [
  { when: (hour) => hour >= 7 && hour < 18, image: 'store.png' },   // 7:00 - 17:59 daytime
  { when: () => true,                        image: 'night_store.png' }, // otherwise night
];
function hourFrom(timeText) {
  const m = /(\d{1,2}):(\d{2})\s*([AaPp][Mm])?/.exec(String(timeText));
  if (!m) return null;
  let hour = Number(m[1]) % 24;
  if (m[3]) hour = (hour % 12) + (/p/i.test(m[3]) ? 12 : 0);
  return hour;
}

/* ---------- random events (keys match the backend EVENTS table) ---------- */
const events = {
  leicester_win:   { label: 'LCFC wins a dramatic match!',                  hours: 3, image: 'leicester_win_store.png' },
  whack_hackathon: { label: 'WHACK Warwick Hackathon is happening today!',  hours: 6, image: 'whack_hackathon_store.jpg' },
  wifi_outage:     { label: 'City-wide card machine crash',                 hours: 2, image: 'wifi_outage_store.png' },
  tiktok_viral:    { label: 'A food reviewer goes viral on TikTok!',        hours: 1, image: 'tiktok_viral_store.png' },
  roadworks:       { label: 'Emergency roadworks outside',                  hours: 5, image: 'roadworks_store.png' },
};
let activeEvent = null;      // { key, label, image, remaining } while an event is running
let lastAction = 'Shop is open!';
let lastTime = null;

const randomEventKey = () => { const keys = Object.keys(events); return keys[Math.floor(Math.random() * keys.length)]; };
function eventKeyFrom(value) {            // accepts "tiktok_viral" or { key: "tiktok_viral" } from the server
  const key = typeof value === 'string' ? value : value?.key;
  return Object.hasOwn(events, key) ? key : null;
}
function startEvent(key) {
  if (!key) return;
  const e = events[key];
  activeEvent = { key, label: e.label, image: e.image, remaining: e.hours };
}
function tickEvent(hours) {               // time passes; the event ends when its hours run out
  if (!activeEvent) return;
  activeEvent.remaining -= hours;
  if (activeEvent.remaining <= 0) activeEvent = null;
}
function renderBanner() {
  $('event-text').textContent = activeEvent ? `${activeEvent.label} · ${activeEvent.remaining}h to go` : lastAction;
}

function showStore(timeText) {
  if (timeText !== undefined) lastTime = timeText;
  const img = $('scene');
  if (!img) return;
  let src;
  if (activeEvent) {
    src = activeEvent.image;              // an event's picture wins over day/night
  } else {
    const hour = hourFrom(lastTime);
    if (hour === null) return;
    src = storeRules.find((rule) => rule.when(hour)).image;
  }
  if (img.getAttribute('src') !== src) img.setAttribute('src', src);
}
// If an image file is missing, fall back to the daytime store instead of a broken picture.
$('scene').addEventListener('error', () => {
  if ($('scene').getAttribute('src') !== 'store.png') $('scene').setAttribute('src', 'store.png');
});

function showConditions(data) {
  showStore(data.time);
  $('time').textContent = data.time;
  $('weather').textContent = data.weather;
  $('customers').textContent = data.customers;
  $('prediction').textContent = data.nextPrediction;
  $('rush').textContent = data.nextIsRush ? 'rush hour' : 'quieter hour';
  showWeatherIcon(data.weather);
}

function showScores(scores) {
  $('careful-score').textContent = `${scores.carefulFooled} / ${scores.rounds}`;
  $('naive-score').textContent = `${scores.naiveFooled} ${scores.naiveFooled === 1 ? 'time' : 'times'}`;
}

function showVerdict(prefix, verdict) {
  const label = $(`${prefix}-verdict`);
  label.textContent = verdict.label;
  label.dataset.verdict = verdict.verdict;            // REAL | FAKE | NOT SURE YET | NO OFFER
  $(`${prefix}-description`).textContent = verdict.text;
}

function showChecks(verdict) {
  document.querySelectorAll('#checks li').forEach((li) => li.classList.toggle('on', li.dataset.key === verdict));
}

function showRatio(customers, expected) {
  if (!Number.isFinite(expected) || expected <= 0) return;
  const ratio = customers / expected;
  $('ratio-text').textContent = `${Math.round(ratio * 100)}% of expected`;
  $('ratio-fill').style.width = `${Math.max(2, Math.min(100, ratio * 50))}%`;
}

function showBanner(name, hours) {
  lastAction = `${name}${hours > 1 ? ` × ${hours} hours` : ''}`;
  renderBanner();
}

// A fresh shop (with 8 weeks of past sales for the careful AI) when the page opens.
startGame().then((data) => {
  Object.assign(state, { round: 0, customers: data.customers, prediction: data.nextPrediction, weather: data.weather });
  showConditions(data);
  showScores(data.scores);
}).catch(() => {
  $('error').textContent = 'Could not reach the shop server. Start it with: uvicorn api:app --reload';
  $('error').hidden = false;
});

let pending = false;
document.querySelectorAll('[data-offer]').forEach((button) => {
  button.addEventListener('click', async () => {
    if (pending) return;
    pending = true;
    document.querySelectorAll('[data-offer]').forEach((item) => { item.disabled = true; });
    $('error').hidden = true;
    try {
      const offer = button.dataset.offer;
      const offerName = button.querySelector('strong').textContent.trim();
      const hours = offer !== 'random' && $('fast-forward')?.checked ? 12 : 1;
      const picked = offer === 'random' ? randomEventKey() : null;
      const result = await runRound(offer, { ...state }, hours, picked);
      state.round++;
      showVerdict('careful', result.careful);
      showVerdict('naive', result.naive);
      showChecks(result.careful.verdict);
      showRatio(result.customers, result.expected);
      if (offer === 'random') startEvent(eventKeyFrom(result.event) ?? picked); else tickEvent(hours);
      showBanner(offerName, hours);
      $('naive-badge').textContent = result.naive.tag || 'Round complete';
      if (state.round === 1) $('rounds').replaceChildren();
      const entry = document.createElement('li');
      const ran = hours > 1 ? ` x ${hours} hours` : '';
      const naiveNote = result.naive.fooled ? 'Naive AI fooled!' : '';
      const ourNote = result.careful.fooled ? 'Our AI fooled!' : `Our AI: ${result.careful.label.toLowerCase()}`;
      const what = offer === 'random' && activeEvent ? `Random Event: ${activeEvent.label}` : `${offerName}${ran}`;
      entry.textContent = `Round ${state.round} · ${what} · ` +
        `${result.customers} customers (expected ${result.expected}) · ${[naiveNote, ourNote].filter(Boolean).join(' · ')}`;
      $('rounds').prepend(entry);
      while ($('rounds').children.length > 5) $('rounds').lastElementChild.remove();
      Object.assign(state, { customers: result.customers, prediction: result.nextPrediction, weather: result.weather });
      showConditions(result);
      showScores(result.scores);
    } catch (error) {
      $('error').textContent = error.message || 'Something went wrong. Please try again.';
      $('error').hidden = false;
    } finally {
      pending = false;
      document.querySelectorAll('[data-offer]').forEach((item) => { item.disabled = false; });
    }
  });
});