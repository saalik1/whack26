# Fool the AI: an AI researcher that can't be fooled by luck

**Brevan Howard track.** Finding patterns is easy; knowing which to trust is hard. Most AI tries
to prove itself right. Ours tries to prove itself **wrong** before believing anything (Karl Popper),
and says **REAL**, **FAKE** or **NOT SURE YET**.

## Play the game
```
pip install -r requirements.txt
uvicorn api:app --reload
```
Open http://localhost:8000. Launch a good or a bad offer; it runs for two shop days, then both AIs give
a verdict. Try to sneak a useless offer past them: launch it before a busy weekend, add an event, call
your friends in. The naive AI (plain average) falls for it; ours compares every hour with what it
*expected* and only says REAL when the evidence passes an e-value bar, so it is almost never fooled.

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

**Live game AI** (`frontend/evidence_game.png`): 40 games x 16 offers per player
strategy, each offer runs two shop days and gets a forced, blind verdict. Cells: useless offers called REAL /
good offers called REAL.

Good offer +20%:

| Method | Random player | Cheater | Switcher |
|---|---|---|---|
| Naive AI (plain average) | 13% / 53% | 16% / 23% | 27% / 63% |
| Gut feeling (learns your habits) | 4.4% / 99% | 4.0% / 98% | 4.7% / 98% |
| **Our AI (evidence only)** | 0.3% / 90% | 0.3% / 89% | 0.3% / 91% |

Good offer +8% (the honest cost: small effects need longer tests):

| Method | Random player | Cheater | Switcher |
|---|---|---|---|
| Naive AI (plain average) | 15% / 28% | 13% / 4.7% | 31% / 43% |
| Gut feeling (learns your habits) | 16% / 67% | 8.6% / 57% | 11% / 58% |
| **Our AI (evidence only)** | 0.3% / 20% | 0.0% / 13% | 0.3% / 17% |

Reproduce it yourself (fixed seeds, same numbers every time):
```
python -m backend.benchmark --cheat all --games 200   # ~7 min, writes backend/results.csv
python -m backend.evidence_game                       # ~1 min, writes backend/results_game.json
python -m backend.make_chart                          # redraws both evidence charts
```

## Tests
```
python -m pytest -q        # 85 tests, ~1.5 min
```
They check both simulators, both AIs, the game loop, the API and the screen wiring, including:
pure noise finds nothing; every cheat fools the naive AI but not ours; the careful AI never reads
the hidden truth and is never told which offer it is judging (we corrupt the truth and swap the
labels, and the verdict doesn't change); its verdict depends on the evidence alone, never on the
player's habits; the e-value bar keeps useless offers below 5%; the screen shows the server's verdicts.

## How our AI works
- **Daily engine** (`backend/defender.py`, used for the evidence): trend removal (STL), weekday/payday
  controls, outlier-proof sales, "not sure" when two changes always happen together, permutation tests
  with Holm correction. Settings tuned on separate games from the ones reported.
- **Live game AI** (`backend/agents.py`): learns a normal hour from 6 months of past sales (Poisson
  regression, never the simulator's formula), allows for its own uncertainty, and judges each offer blind.
  It decides with an e-value (mixture likelihood ratio, bar 20 = 5% error), the idea behind POPPER
  (Huang et al., ICML 2025). A habit-learning "gut feeling" is shown as commentary only.

Honest limits: the live game's good offer is +20% so it resolves during a demo (+8% needs longer tests);
everything is tested on simulated shops, where the truth is known. Real data is the next step.

## Files
- `api.py`: FastAPI server for the game
- `backend/`: `simulator2.py` (hourly shop), `agents.py` (the two live AIs), `game.py` (scoring),
  `simulator.py`, `defender.py`, `benchmark.py` (daily engine), `evidence_game.py` (live AI evidence),
  `make_chart.py` (both charts)
- `frontend/`: the game screen

Built on numpy, pandas, scipy, statsmodels, FastAPI. Method inspired by POPPER (ICML 2025).
