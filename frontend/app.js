import { startGame, tick, launchOffer, triggerEvent, dismissPopup } from './api.js';

const $ = (id) => document.getElementById(id);

/* ---------- weather icon (static markup only) ---------- */
const sun = '<g stroke="#2b2420" stroke-width="2.6" stroke-linecap="round"><circle cx="20" cy="20" r="8" fill="#ffd84d"/><path d="M20 4v5M20 31v5M4 20h5M31 20h5M8.500 8.500l3.500 3.500M28 28l3.500 3.500M8.500 31.500L12 28M28 12l3.500-3.500" fill="none"/></g>';
const cloud = '<path d="M11 30a7 7 0 0 1 0-14 9 9 0 0 1 17-2 7.500 7.500 0 0 1 1 16Z" fill="#fff" stroke="#2b2420" stroke-width="2.600" stroke-linejoin="round"/>';
const rain = cloud.replace('M11 30', 'M11 26') + '<path d="M13 32l-2 5M21 32l-2 5M29 32l-2 5" stroke="#2f6ea6" stroke-width="2.800" stroke-linecap="round"/>';
function showWeatherIcon(weather) {
  const w = String(weather).toLowerCase();
  const icon = /sun|clear|fine/.test(w) ? sun : /rain|shower|storm|drizzle/.test(w) ? rain : cloud;
  $('weather-icon').innerHTML = icon;
}
showWeatherIcon('Sunny');

/* ---------- store picture: the event's picture, otherwise day or night ---------- */
// Keys match the server's events (backend/simulator2.py). The server decides what happens
// and for how long; this table only says which picture goes with which event.
const eventImages = {
  leicester_win: 'leicester_win_store.png',
  whack_hackathon: 'whack_hackathon_store.jpg',
  wifi_outage: 'wifi_outage_store.png',
  tiktok_viral: 'tiktok_viral_store.png',
  roadworks: 'roadworks_store.png',
};
const storeRules = [
  { when: (hour) => hour >= 7 && hour < 18, image: 'store.png' },   // daytime
  { when: () => true,                     image: 'night_store.png' }, // night
];
function hourFrom(timeText) {
  const m = /(\d{1,2}):(\d{2})\s*([AaPp][Mm])?/.exec(String(timeText));
  if (!m) return null;
  let hour = Number(m[1]) % 24;
  if (m[3]) hour = (hour % 12) + (/p/i.test(m[3]) ? 12 : 0);
  return hour;
}
function showStore(data) {
  const img = $('scene');
  if (!img) return;
  let src = eventImages[data.eventKey];
  if (!src) {
    const hour = hourFrom(data.time);
    if (hour === null) return;
    src = storeRules.find((rule) => rule.when(hour)).image;
  }
  if (img.getAttribute('src') !== src) img.setAttribute('src', src);
}
$('scene').addEventListener('error', () => {
  if ($('scene').getAttribute('src') !== 'store.png') $('scene').setAttribute('src', 'store.png');
});

/* ---------- small helpers ---------- */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function showError(message) {
  $('error').textContent = message;
  $('error').hidden = !message;
  const top = $('clock-msg');          // also shown right under the clock so it cannot be missed
  if (top) { top.textContent = message; top.hidden = !message; }
}
function log(text) {
  const list = $('rounds');
  if (list.dataset.empty !== 'no') { list.replaceChildren(); list.dataset.empty = 'no'; }
  list.prepend(el('li', '', text));
  while (list.children.length > 6) list.lastElementChild.remove();
}
const offerName = (kind) => (kind === 'good' ? 'Good Offer' : 'Bad Offer');

/* ---------- what the screen shows ---------- */
function showConditions(data) {
  showStore(data);
  $('time').textContent = data.time;
  $('weather').textContent = data.weather;
  $('customers').textContent = data.customers;
  $('prediction').textContent = data.nextPrediction;
  $('rush').textContent = data.nextIsRush ? 'rush hour' : 'quieter hour';
  showWeatherIcon(data.weather);
}
function showScores(scores) {
  $('careful-score').textContent = `${scores.carefulFooled} / ${scores.offersJudged}`;
  $('naive-score').textContent = `${scores.naiveFooled} ${scores.naiveFooled === 1 ? 'time' : 'times'}`;
}
function showVerdict(prefix, verdict) {
  const label = $(`${prefix}-verdict`);
  label.textContent = verdict.label;
  label.dataset.verdict = verdict.verdict;
  $(`${prefix}-description`).textContent = verdict.text;
}
function showWaiting(prefix, label, text) {
  const node = $(`${prefix}-verdict`);
  node.textContent = label;
  node.dataset.verdict = 'NO OFFER';
  $(`${prefix}-description`).textContent = text;
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
function showBanner(data) {
  let text = 'Shop is open!';
  if (data.activeEvent) text = `${data.activeEvent} · ${data.eventHoursLeft}h to go`;
  else if (data.offer) text = `${offerName(data.offer.kind)} running`;
  $('event-text').textContent = text;
}

/* ---------- offers: locked while one is running ---------- */
function showOffer(data) {
  const offer = data.offer;
  document.querySelectorAll('[data-offer="good"], [data-offer="bad"]').forEach((b) => {
    b.disabled = !data.canLaunchOffer;
    b.title = data.canLaunchOffer ? '' : (offer ? `Locked until ${offer.unlocksAt}` : 'Close the pop-up first');
  });
  const random = document.querySelector('[data-offer="random"]');
  random.disabled = !data.canTriggerEvent;
  random.title = data.canTriggerEvent ? '' : (data.activeEvent ? 'An event is already happening' : 'Close the pop-up first');
  if (offer) {
    $('offer-status').textContent =
      `${offerName(offer.kind)} running: ${offer.hoursLeft} hour${offer.hoursLeft === 1 ? '' : 's'} left. Next offer from ${offer.unlocksAt}.`;
    const done = `${offer.hoursDone} of ${offer.hoursDone + offer.hoursLeft} hours done`;
    showWaiting('careful', 'WATCHING', `I am watching the offer (${done}). I will give my verdict at ${offer.unlocksAt}, after looking at everything that happened.`);
    showWaiting('naive', 'WAITING', `Offer running (${done}). I will compare it with the average hour when it ends.`);
  } else {
    $('offer-status').textContent = 'No offer running. Pick one, then press Play.';
  }
}

function apply(data) {
  if (data.ok === false) showError(data.error); else showError('');
  showConditions(data);
  showScores(data.scores);
  showRatio(data.customers, data.expected);
  showBanner(data);
  showOffer(data);
  if (data.popups.length) openPopup(data.popups[0]); else closePopup();
}

/* ---------- the clock: pause / play / double play ---------- */
// The browser calls /api/tick once per shop hour. How long that takes comes from the server
// (SECONDS_PER_HOUR in backend/game.py), so the speed is changed in one place only.
let speeds = { pause: 0, play: 2, double: 1 };
let speed = 'pause';
let speedBeforePopup = 'pause';
let timer = null;
let inFlight = null;
let popupOpen = false;
let verdictLogged = false;

function setSpeed(name) {
  const was = speed;
  speed = name;
  document.querySelectorAll('.clock-btn').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.speed === name)));
  $('speed-note').textContent = name === 'pause' ? 'Time is stopped' : `1 hour = ${speeds[name]} s`;
  const state = $('clock-state');
  state.dataset.state = name;
  state.textContent = { pause: 'PAUSED', play: 'PLAYING', double: 'DOUBLE SPEED' }[name];
  clearTimeout(timer);
  timer = null;
  if (name !== 'pause' && was === 'pause') runTick();   // start moving straight away
  else schedule();
}
function schedule() {
  clearTimeout(timer);
  timer = null;
  const seconds = speeds[speed];
  if (!seconds || popupOpen) return;
  timer = setTimeout(runTick, seconds * 1000);
}
async function runTick() {
  timer = null;
  if (inFlight || popupOpen || !speeds[speed]) return;
  inFlight = tick();
  try {
    apply(await inFlight);
  } catch (error) {
    setSpeed('pause');
    if (error.status === 404) {
      // The server forgot this game (it was restarted). Start a fresh shop instead of getting stuck.
      try {
        const fresh = await startGame();
        apply(fresh);
        showError('The server restarted, so a new shop was started. Press Play.');
      } catch (again) { showError(`${again.message} (clock paused)`); }
    } else {
      showError(`${error.message} (clock paused)`);
    }
    $('clock-state').textContent = 'PAUSED (error)';
  } finally {
    inFlight = null;
    schedule();
  }
}
const idle = async () => { if (inFlight) { try { await inFlight; } catch { /* handled by the timer */ } } };

document.querySelectorAll('.clock-btn').forEach((b) => {
  b.addEventListener('click', () => { if (!popupOpen) setSpeed(b.dataset.speed); });
});

/* ---------- pop-ups: time is frozen while one is open ---------- */
function openPopup(popup) {
  if (!popupOpen) {
    popupOpen = true;
    speedBeforePopup = speed;
    setSpeed('pause');
    document.querySelectorAll('.clock-btn').forEach((b) => { b.disabled = true; });
    $('speed-note').textContent = 'Paused: read the pop-up';
    $('clock-state').textContent = 'PAUSED (pop-up)';
  }
  $('popup-title').textContent = popup.title;
  const body = $('popup-body');
  body.replaceChildren();
  if (popup.type === 'verdict') {
    if (!verdictLogged) { verdictLogged = true; recordVerdict(popup); }
    body.append(el('p', 'popup-reveal', `You launched a ${offerName(popup.offer).toUpperCase()} (${popup.offer === 'good' ? 'it really lifts sales' : 'it does nothing at all'}).`));
    const row = el('div', 'popup-ais');
    for (const [key, name] of [['naive', 'Naive AI'], ['careful', 'Careful AI']]) {
      const v = popup[key];
      const card = el('div', `popup-ai ${key}`);
      card.append(el('h3', '', name));
      const label = el('span', 'verdict-label', v.label);
      label.dataset.verdict = v.verdict;
      card.append(label, el('span', 'badge', v.tag), el('p', '', v.text));
      row.append(card);
    }
    body.append(row);
  } else {
    body.append(el('p', '', popup.text));
  }
  $('popup').hidden = false;
  $('popup').scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function closePopup() {
  if (!popupOpen) return;
  popupOpen = false;
  verdictLogged = false;
  $('popup').hidden = true;
  document.querySelectorAll('.clock-btn').forEach((b) => { b.disabled = false; });
  setSpeed(speedBeforePopup);
}
function recordVerdict(popup) {
  const { careful, naive } = popup;
  showVerdict('careful', careful);
  showVerdict('naive', naive);
  showChecks(careful.verdict);
  $('naive-badge').textContent = naive.tag || 'Verdict';
  if (careful.explanation && $('ai-explanation')) $('ai-explanation').textContent = careful.explanation;
  log(`Verdict on your ${offerName(popup.offer)} · Naive AI: ${naive.label}${naive.fooled ? ' (fooled!)' : ''}`
    + ` · Careful AI: ${careful.label}${careful.fooled ? ' (fooled!)' : ''}`);
}
$('popup-close').addEventListener('click', async () => {
  $('popup-close').disabled = true;
  try {
    await idle();
    apply(await dismissPopup());
  } catch (error) {
    showError(error.message);
  } finally {
    $('popup-close').disabled = false;
  }
});
/* ---------- the three buttons ---------- */
document.querySelectorAll('[data-offer]').forEach((button) => {
  button.addEventListener('click', async () => {
    if (button.disabled) return;
    const kind = button.dataset.offer;
    document.querySelectorAll('[data-offer]').forEach((b) => { b.disabled = true; });
    try {
      await idle();
      const data = kind === 'random' ? await triggerEvent('random') : await launchOffer(kind);
      if (data.ok === false) { apply(data); return; }
      if (kind === 'random') {
        log(`${data.time} · Random event: ${data.activeEvent} (${data.eventHoursLeft} hours)`);
      } else {
        log(`${data.nextTime} · Launched a ${offerName(kind)}. Locked until ${data.offer.unlocksAt}.`);
      }
      apply(data);
    } catch (error) {
      showError(error.message);
      try { /* re-enable whatever the last good state allowed */ document.querySelectorAll('[data-offer]').forEach((b) => { b.disabled = false; }); } catch { /* ignore */ }
    }
  });
});

/* ---------- start ---------- */
startGame().then((data) => {
  if (data.config?.speeds) speeds = data.config.speeds;
  setSpeed('pause');
  document.querySelectorAll('.clock-btn').forEach((b) => {
    const s = speeds[b.dataset.speed];
    if (s) b.title = `One shop hour every ${s} second${s === 1 ? '' : 's'}`;
  });
  apply(data);
}).catch((error) => {
  // Say what actually went wrong (old server still running, wrong folder, offline...).
  $('error').textContent = `Could not start the shop: ${error.message} Restart the server (uvicorn api:app --reload) with the new api.py and backend files, then hard-refresh this page (Ctrl+Shift+R).`;
  $('error').hidden = false;
  $('speed-note').textContent = 'Not connected';
  $('clock-state').textContent = 'NOT CONNECTED';
});