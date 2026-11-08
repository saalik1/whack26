/** Backend boundary: the server owns the simulation, the clock rules and both AIs' verdicts.
 *  POST /api/start           -> first screen + config (clock speeds, offer lock, events)
 *  POST /api/tick            -> ONE shop hour passes (the browser calls this on a timer)
 *  POST /api/offer {kind}    -> start a good or bad offer (locks for a day)
 *  POST /api/trigger_event   -> add an event ("random" or a key)
 *  POST /api/dismiss         -> close the pop-up that is open
 *  Every call returns the same shape: the latest hour, what the player can do now,
 *  any open pop-ups and the scores. ok=false + error means "not allowed right now".
 */
export const config = {
  startUrl: '/api/start', tickUrl: '/api/tick', offerUrl: '/api/offer',
  eventUrl: '/api/trigger_event', friendsUrl: '/api/call_friends', dismissUrl: '/api/dismiss',
};

async function post(url, body) {
  const response = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin', body: JSON.stringify(body ?? {}),
  });
  if (!response.ok) {
    let detail = '';
    try { detail = (await response.json()).detail; } catch { /* no JSON body */ }
    const err = new Error(typeof detail === 'string' && detail ? detail : `The server answered ${response.status} for ${url}. Is the new api.py running?`);
    err.status = response.status;
    throw err;
  }
  const data = await response.json();
  if (!Number.isFinite(data.customers) || !Number.isFinite(data.nextPrediction)
      || typeof data.weather !== 'string' || !Array.isArray(data.popups)) {
    throw new Error('The shop returned an invalid answer. Please try again.');
  }
  return data;
}

export const startGame = () => post(config.startUrl, {});
export const tick = () => post(config.tickUrl, {});
export const dismissPopup = () => post(config.dismissUrl, {});
export const launchOffer = (kind) => {
  if (!['good', 'bad'].includes(kind)) throw new Error('Unknown offer');
  return post(config.offerUrl, { kind });
};
export const callFriends = () => post(config.friendsUrl, {});
export const triggerEvent = (event = 'random') => post(config.eventUrl, { event });