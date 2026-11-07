/** Backend boundary. Set apiUrl to the round endpoint when the backend is ready.
 * POST body: { offer: 'good' | 'bad' | 'random', state: ShopState }
 * Response: { customers: number, nextPrediction: number, weather: string }
 * The backend should own the simulation and verdicts in the production game.
 */
export const config = { apiUrl: null };

export async function runRound(offer, state) {
  if (!['good', 'bad', 'random'].includes(offer)) throw new Error('Unknown offer');
  if (config.apiUrl) {
    const response = await fetch(config.apiUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ offer, state }),
    });
    if (!response.ok) throw new Error('The shop could not complete this round. Please try again.');
    const result = await response.json();
    if (!Number.isFinite(result.customers) || result.customers < 0 || !Number.isFinite(result.nextPrediction) || result.nextPrediction < 0 || typeof result.weather !== 'string') {
      throw new Error('The shop returned an invalid round. Please try again.');
    }
    return result;
  }
  // Local demonstration only. Replace by connecting the endpoint above.
  const variation = Math.floor(Math.random() * 7) - 3;
  const lift = offer === 'good' ? 12 : offer === 'random' ? Math.floor(Math.random() * 25) - 12 : 0;
  return {
    customers: Math.max(3, state.prediction + lift + variation),
    nextPrediction: [43, 48, 36, 25, 19, 14, 22, 30][(state.round + 1) % 8],
    weather: offer === 'random' ? ['Sunny', 'Cloudy', 'Rainy'][Math.floor(Math.random() * 3)] : state.weather,
  };
}
