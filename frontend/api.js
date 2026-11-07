/** Backend boundary: the server owns the simulation AND both AIs' verdicts.
 *  POST /api/start                          -> first screen
 *  POST /api/round { offer, hours, state }  -> one round (hours > 1 fast-forwards)
 */
export const config = { apiUrl: '/api/round', startUrl: '/api/start' };

async function post(url, body) {
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin', body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) throw new Error('The shop could not complete this round. Please try again.');
  return response.json();
}

export async function startGame() {
  return post(config.startUrl, {});
}

export async function runRound(offer, state, hours = 1, event = null) {
  if (!['good', 'bad', 'random'].includes(offer)) throw new Error('Unknown offer');
  const result = await post(config.apiUrl, { offer, hours, state, ...(event ? { event } : {}) });
  if (!Number.isFinite(result.customers) || !Number.isFinite(result.nextPrediction)
      || typeof result.weather !== 'string' || !result.careful || !result.naive) {
    throw new Error('The shop returned an invalid round. Please try again.');
  }
  return result;
}