# whack26: an AI researcher that refuses to be fooled by luck

Brevan Howard track. A simulated shop hides a few real effects among noise; an attacker
tries to trick the AI into declaring fake discoveries. The Popper researcher tries to prove
every idea wrong before believing it, and gives one of three verdicts: real, fake, not sure.

## Run
```
pip install -r requirements.txt
python benchmark.py                          # demo + pure-noise check + benchmark
python benchmark.py --cheat fake_customers   # one cheat
python benchmark.py --cheat all --games 200  # every cheat, saves results.csv (~3 min)
python benchmark.py --tune                   # tune exploration settings
```
Cheats: `confounder`, `seasonality`, `promo_timing`, `fake_customers`, `peeking`
(plus the default: 20 meaningless tweaks hoping one looks lucky).

## Files
- `simulator.py`: shop simulator, hidden truth, attacker cheats
- `defender.py`: naive researcher vs Popper researcher
- `benchmark.py`: demo, noise check, benchmarks
- `stage1version1.py`: original Stage 1 prototype

## Stage 2 results (200 fresh games per cheat, never used for tuning)
| Cheat | Naive fooled by the cheat | Popper fooled by the cheat (95% CI) | Popper finds the real discount |
|---|---|---|---|
| none (fishing for luck) | 67% | 7.0% (4.2-11.4%) | 97.5% |
| confounder | 83% | 0% (0-1.9%), says "not sure" | 94.5% |
| seasonality | 53% | 0% (0-1.9%) | 96.5% |
| promo timing | 96% | 0% (0-1.9%) | 96.5% |
| fake customers | 100% | 0.5% (0.1-2.8%) | 96.0% |
| peeking | 24% | 0.5% (0.1-2.8%) | 82.0% |

Games with ANY fake discovery (from the 20 random tweaks) are held at the 5% design level
by Holm correction: 5.2% over 800 fresh games. The 7% above is sampling noise in the first 200.

Default design is "preregistered": every tweak is a hypothesis fixed before seeing the data,
so all 90 days are used for one severe test each. `design="split"` (explore, then re-test on
unseen days) is kept for hypotheses generated from the data; it is stricter but finds the
real effect only ~75% of the time.

Settings were tuned on separate games (seeds 1000+); results use seeds 50000+.

Built on: numpy, pandas, scipy, statsmodels (BH correction, STL).
