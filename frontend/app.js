import { runRound, startGame } from './api.js';

const $ = (id) => document.getElementById(id);
const colors = ['#e95628', '#2e82e5', '#f7bd00', '#25b266', '#9950dc', '#e9549c', '#14a3a7'];
const state = { round: 0, hour: 11, customers: 26, prediction: 43, weather: 'Sunny', carefulFooled: 0, naiveFooled: 0 };
const svgNS = 'http://www.w3.org/2000/svg';
function shape(tag, attrs, parent) {
  const element = document.createElementNS(svgNS, tag);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
  parent.append(element);
  return element;
}
for (let row = 0; row < 2; row++) {
  for (let index = 0; index < 8; index++) {
    shape('rect', { x: 229 + index * (row ? 42 : 46), y: row ? 163 : 95, width: row ? 30 : 34, height: row ? 49 : 40, rx: row ? 10 : 5, fill: colors[(index + row * 2) % colors.length], stroke: '#342019', 'stroke-width': 2.3 }, $('products'));
  }
}
function drawCustomers(count) {
  $('crowd').replaceChildren();
  for (let index = 0; index < Math.min(count, 26); index++) {
    const x = 33 + index * 29;
    const y = 334 - [0, 10, 7, 4, 0, 10][index % 6];
    const person = shape('g', { stroke: '#342019', 'stroke-width': 2.2 }, $('crowd'));
    shape('path', { d: `M${x - 12} 368V${y + 21}Q${x - 12} ${y + 10} ${x} ${y + 10}Q${x + 12} ${y + 10} ${x + 12} ${y + 21}V368Z`, fill: colors[(index + 0) % colors.length] }, person);
    shape('circle', { cx: x, cy: y, r: 10.5, fill: ['#f5c592', '#dfa768', '#a86e47', '#ffdab1'][index % 4] }, person);
    for (const offset of [-3.5, 3.5]) shape('circle', { cx: x + offset, cy: y - 1, r: 1.3, fill: '#342019', stroke: 'none' }, person);
  }
}
drawCustomers(state.customers);

function showConditions(data) {
  $('time').textContent = data.time;
  $('weather').textContent = data.weather;
  $('customers').textContent = data.customers;
  $('prediction').textContent = data.nextPrediction;
  $('rush').textContent = data.nextIsRush ? 'rush hour' : 'quieter hour';
  drawCustomers(data.customers);
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
      const hours = offer !== 'random' && $('fast-forward')?.checked ? 12 : 1;
      const result = await runRound(offer, { ...state }, hours);
      state.round++;
      showVerdict('careful', result.careful);
      showVerdict('naive', result.naive);
      $('naive-badge').textContent = result.naive.tag || 'Round complete';
      if (state.round === 1) $('rounds').replaceChildren();
      const entry = document.createElement('li');
      const ran = hours > 1 ? ` x ${hours} hours` : '';
      const naiveNote = result.naive.fooled ? 'Naive AI fooled!' : '';
      const ourNote = result.careful.fooled ? 'Our AI fooled!' : `Our AI: ${result.careful.label.toLowerCase()}`;
      entry.textContent = `Round ${state.round} · ${button.querySelector('strong').textContent}${ran} · ` +
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
