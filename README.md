# Fool the AI: an AI researcher that can't be fooled by luck

**Brevan Howard track.** Finding patterns is easy; knowing which to trust is hard. Most AI tries
to prove itself right. Ours tries to prove itself **wrong** before believing anything (Karl Popper),
and says **REAL**, **FAKE** or **NOT SURE YET**.

## Play the game
```
pip install -r requirements.txt
uvicorn api:app --reload
```
Open http://localhost:8000 and try to sneak a useless offer past the AI by launching it in a rush hour.
The naive AI (plain average) falls for it; ours compares each hour with what it *expected* and builds up
evidence across rounds with **e-values**, so checking after every click can't fool it.
Tick *Fast-forward* to run each offer for 12 hours.

## The evidence
The **The evidence** button in the game opens `frontend/evidence.html`. Chart 1 (`frontend/evidence.png`):
1,200 simulated shops, 6 cheats, all on fresh games never used for tuning.

| Cheat | Naive AI fooled | Our AI fooled | Our AI finds the real effect |
|---|---|---|---|
| Promos on busy days | 96% | 0% | 96% |
| Fake customers | 100% | 0.5% | 96% |
| Two changes at once | 82% | 0% (says "not sure") | 94% |
| Fishing for luck (20 useless tweaks) | 67% | 7% (5.2% over 800 games) | 98% |
| Riding a sales trend | 52% | 0% | 96% |
| Stopping early | 24% | 0.5% | 82% |

**Live game AI** (`frontend/evidence_game.png`, fresh games):
- Checking after every round (the "stop when it looks good" trap): an ordinary p-value is eventually
  fooled by a useless offer **19%** of the time over 100 rounds; our e-values **1.7%** (budget 2.5%).
  Same AI, same learned baseline; only the decision rule differs. (1,000 games)
- Bad offer launched in rush hours: naive AI fooled in **100%** of games, ours in **0.7%**; ours still
  confirms the good offer in 90% of games (median 27 rounds). (300 games)

Reproduce it yourself (fixed seeds, same numbers every time):
```
python -m backend.benchmark --cheat all --games 200   # ~7 min, writes backend/results.csv
python -m backend.evidence_game                       # ~1 min, writes backend/results_game.json
python -m backend.make_chart                          # redraws both evidence charts
```

## How our AI works
- **Daily engine** (`backend/defender.py`, used for the evidence): trend removal (STL), weekday/payday
  controls, outlier-proof sales, "not sure" when two changes always happen together, permutation tests
  with Holm correction. Settings tuned on separate games from the ones reported.
- **Live game AI** (`backend/agents.py`): learns a normal hour from 8 weeks of past sales (Poisson
  regression, never the simulator's formula), allows for its own uncertainty, and accumulates evidence
  with an anytime-valid e-value, the sequential-testing idea from POPPER (Huang et al., ICML 2025),
  with the 5% error budget split across the two offers.

Honest limits: the live game's good offer is +20% so it resolves during a demo (+8% takes ~3x longer);
everything is tested on simulated shops, where the truth is known. Real data is the next step.

## Files
- `api.py`: FastAPI server for the game
- `backend/`: `simulator2.py` (hourly shop), `agents.py` (the two live AIs), `game.py` (scoring),
  `simulator.py`, `defender.py`, `benchmark.py` (daily engine), `evidence_game.py` (live AI evidence),
  `make_chart.py` (both charts)
- `frontend/`: the game screen

Built on numpy, pandas, scipy, statsmodels, FastAPI. Method inspired by POPPER (ICML 2025).
