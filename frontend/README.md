# Fool the AI frontend

Run from this folder with `python -m http.server 5173`, then visit http://localhost:5173.
No build step or JavaScript dependencies are required. Fonts load from Google Fonts with local fallbacks.

All three actions are native, keyboard-accessible buttons. The demo advances the hour, updates the shop conditions, compares two simple AI verdicts, tracks scores, and keeps the five latest rounds. Demo state resets on reload.

## Backend integration

`api.js` is the integration boundary. Set `config.apiUrl` to your round endpoint to replace the local simulation with a POST request. Each request sends `{ offer, state }`, where offer is `good`, `bad`, or `random`. Return `{ customers, nextPrediction, weather }`. Failed requests show a message and leave the current round intact. Buttons are disabled while requests run to prevent duplicate submissions.

The current verdict thresholds in `app.js` are illustrative. When connecting a real backend, move simulation, verdicts, and scoring to the server and extend the response contract accordingly. The existing Python statistical prototype is not connected to this interface.
