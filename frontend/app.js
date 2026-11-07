import { runRound } from './api.js';

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

let pending = false;
document.querySelectorAll('[data-offer]').forEach((button) => {
  button.addEventListener('click', async () => {
    if (pending) return;
    pending = true;
    document.querySelectorAll('[data-offer]').forEach((item) => { item.disabled = true; });
    $('error').hidden = true;
    try {
      const offer = button.dataset.offer;
      const result = await runRound(offer, { ...state });
      const carefulPositive = result.customers >= state.prediction + 7;
      const naivePositive = result.customers > 30;
      const fooledCareful = offer === 'bad' && carefulPositive;
      const fooledNaive = offer === 'bad' && naivePositive;
      state.round++;
      state.carefulFooled += Number(fooledCareful);
      state.naiveFooled += Number(fooledNaive);
      $('careful-verdict').textContent = carefulPositive ? 'IT WORKED!' : 'NO REAL LIFT';
      $('naive-verdict').textContent = naivePositive ? 'IT WORKED!' : 'NO REAL LIFT';
      $('naive-badge').textContent = fooledNaive ? 'Fooled!' : 'Round complete';
      $('careful-description').textContent = `I expected ${state.prediction} customers and saw ${result.customers}. ${carefulPositive ? 'That is a lift beyond the expected rush.' : 'The offer did not beat my expectation by enough.'}`;
      $('naive-description').textContent = `I saw ${result.customers} customers against an average of 30. ${naivePositive ? 'Above average — I think the offer worked!' : 'I do not see an increase in sales.'}`;
      if (state.round === 1) $('rounds').replaceChildren();
      const entry = document.createElement('li');
      entry.textContent = `Round ${state.round} · ${button.querySelector('strong').textContent} · ${result.customers} customers (expected ${state.prediction}) · ${fooledNaive ? 'Naive AI fooled!' : 'Verdicts recorded.'}`;
      $('rounds').prepend(entry);
      while ($('rounds').children.length > 5) $('rounds').lastElementChild.remove();
      Object.assign(state, { hour: state.hour + 1, customers: result.customers, prediction: result.nextPrediction, weather: result.weather });
      const days = ['Saturday', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];
      $('time').textContent = `${days[Math.floor(state.hour / 24) % 7]} ${String(state.hour % 24).padStart(2, '0')}:00`;
      $('customers').textContent = state.customers;
      $('prediction').textContent = state.prediction;
      $('weather').textContent = state.weather;
      $('rush').textContent = state.prediction >= 35 ? 'rush hour' : 'quieter hour';
      $('careful-score').textContent = `${state.carefulFooled} / ${state.round}`;
      $('naive-score').textContent = `${state.naiveFooled} ${state.naiveFooled === 1 ? 'time' : 'times'}`;
      drawCustomers(state.customers);
    } catch (error) {
      $('error').textContent = error.message || 'Something went wrong. Please try again.';
      $('error').hidden = false;
    } finally {
      pending = false;
      document.querySelectorAll('[data-offer]').forEach((item) => { item.disabled = false; });
    }
  });
});
