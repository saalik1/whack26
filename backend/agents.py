"""
agents.py - the two AIs that judge every round.

Both only look at the PUBLIC record of an hour (what the player could also see):
day, time, weather, temperature, event, action, customers. Never the hidden truth.

    naive_agent   - plain average. "More customers than usual? The offer worked!"
                    A bad offer launched at a rush hour fools it every time.
    CarefulAgent  - Popper-style: tries to prove each offer WRONG before believing it.
        1. Learns what a normal hour looks like from the shop's past sales (no offers):
           a Poisson regression on hour, weekday, weather, temperature, events and trend.
           It is never shown the simulator's formula, and it allows for its own
           uncertainty in what it learned (that error repeats every hour, so it adds up).
        2. For every offer hour, measures how far customers beat that expectation.
        3. Builds up evidence across rounds with an e-value (anytime-valid): checking
           after every round cannot manufacture a false "REAL", unlike a p-value.
           This is the sequential-testing idea used by POPPER (Huang et al., ICML 2025).
        4. Splits its error budget across the two offers it tests (Bonferroni), so the
           chance of ever wrongly calling an offer REAL is at most 5% in total.
        5. Says FAKE only when its anytime-valid confidence range rules out a lift worth
           having; otherwise NOT SURE YET.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import statsmodels.api as sm

from .simulator2 import WEEKDAYS, HourRecord

# Naive AI: "worked" if the hour beats the running average by 20%.
NAIVE_LIFT_NEEDED = 0.20



# --------------------------------------------------------------------------- #
# Naive AI
# --------------------------------------------------------------------------- #

def naive_agent(record: HourRecord, past: List[HourRecord]) -> dict:
    avg = sum(r.customers for r in past) / len(past) if past else float(record.customers)
    lift = record.customers / avg - 1 if avg else 0.0
    verdict = "REAL" if lift > NAIVE_LIFT_NEEDED else "FAKE"
    label = "IT WORKED!" if verdict == "REAL" else "NO REAL LIFT"
    lead = "No offer was running, but " if record.action == "none" else ""
    if verdict == "REAL":
        text = (f"{lead}I saw {record.customers} customers against an average hour of {avg:.0f}. "
                f"Above average, so I think it worked!")
    else:
        text = (f"{lead}I saw {record.customers} customers against an average hour of {avg:.0f}. "
                f"I do not see an increase in sales.")
    if text[0].islower():
        text = text[0].upper() + text[1:]
    return {"verdict": verdict, "label": label, "text": text}


# --------------------------------------------------------------------------- #
# Careful AI
# --------------------------------------------------------------------------- #

ALPHA = 0.05                 # total chance of ever wrongly saying REAL, across both offers
OFFERS = ("good", "bad")
E_THRESHOLD = len(OFFERS) / ALPHA     # 40: evidence needed per offer (Bonferroni split)
TAU = 0.5                    # spread of the mixture over plausible effect sizes (z units/hour)
MIN_WORTHWHILE_LIFT = 0.10   # FAKE = confidently below a +10% lift


def _features(rec: dict, event_labels: List[str]) -> List[float]:
    """Public facts about an hour -> regression inputs (no hidden truth)."""
    hours = list(range(9, 21))
    x = [1.0]
    x += [1.0 if rec["hour"] == h else 0.0 for h in hours[1:]]
    x += [1.0 if WEEKDAYS.index(rec["weekday"]) >= 5 else 0.0]
    x += [1.0 if rec["weather"] == w else 0.0 for w in ("Cloudy", "Rainy")]
    x += [float(rec["temperature_c"]), float(rec["day"])]
    x += [1.0 if rec["event"] == lab else 0.0 for lab in event_labels]
    return x


class BaselineModel:
    """What a normal hour looks like, learned from past no-offer hours only."""

    def __init__(self, records: List[dict]):
        quiet = [r for r in records if r["action"] == "none"]
        self.event_labels = sorted({r["event"] for r in quiet if r["event"]})
        X = np.array([_features(r, self.event_labels) for r in quiet])
        y = np.array([r["customers"] for r in quiet], dtype=float)
        self.n_hours = len(quiet)
        self.fit = sm.GLM(y, X, family=sm.families.Poisson()).fit()
        self.cov = np.asarray(self.fit.cov_params())          # uncertainty in what it learned
        self.dispersion = max(1.0, float(self.fit.pearson_chi2 / self.fit.df_resid))

    def x(self, rec: dict) -> np.ndarray:
        return np.array(_features(rec, self.event_labels))

    def expected(self, rec: dict) -> float:
        return float(np.exp(self.x(rec) @ self.fit.params))


def _e_value(S: float, n: int, tau: float = TAU) -> float:
    """One-sided normal-mixture e-process for 'the offer raises customers'.
    S = sum of standardised excess customers over n offer hours."""
    v = 1 + n * tau * tau
    return 2.0 / math.sqrt(v) * math.exp(tau * tau * S * S / (2 * v)) * _norm_cdf(tau * S / math.sqrt(v))


def _norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _anytime_upper(S: float, n: int, alpha: float, tau: float = TAU) -> float:
    """Upper end of an anytime-valid confidence range for the per-hour effect (z units)."""
    v = 1 + n * tau * tau
    radius = math.sqrt(v * (2 * math.log(1 / alpha) + math.log(v))) / (n * tau)
    return S / n + radius


@dataclass
class Evidence:
    tries: int = 0
    S: float = 0.0           # sum of (seen - expected) / sqrt(expected)
    excess: float = 0.0      # customers seen minus expected, summed
    expected: float = 0.0    # customers expected, summed
    a: Optional[np.ndarray] = None   # sum of sqrt(expected) * features: how baseline errors add up
    inflation: float = 1.0   # variance of S per hour relative to pure Poisson noise

    @property
    def lift(self) -> float:
        return self.excess / self.expected if self.expected > 0 else 0.0

    @property
    def S_eff(self) -> float:
        """S rescaled so it also allows for (1) noise beyond Poisson and (2) the baseline
        itself being estimated: that error repeats every hour, so it does NOT average out."""
        return self.S / math.sqrt(self.inflation)

    @property
    def e(self) -> float:
        return _e_value(self.S_eff, self.tries) if self.tries else 1.0

    def lift_upper(self, alpha: float) -> float:
        """Largest lift still compatible with the evidence (anytime-valid)."""
        if not self.tries:
            return float("inf")
        mean_expected = self.expected / self.tries
        return _anytime_upper(self.S_eff, self.tries, alpha) * math.sqrt(self.inflation) / math.sqrt(mean_expected)


class CarefulAgent:
    def __init__(self, past_records: Optional[List[HourRecord]] = None) -> None:
        past = [r.public() for r in (past_records or [])]
        self.model = BaselineModel(past) if len([r for r in past if r["action"] == "none"]) >= 50 else None
        self.evidence: Dict[str, Evidence] = {o: Evidence() for o in OFFERS}

    def _expected(self, rec: dict) -> float:
        if self.model is None:                      # no past data: fall back to the shop's forecast
            return max(1.0, float(rec["forecast"]))
        return max(1.0, self.model.expected(rec))

    def judge(self, record: HourRecord) -> dict:
        rec = record.public()
        expected = self._expected(rec)
        seen = rec["customers"]
        rush_note = " That hour is normally a rush, so a crowd alone proves nothing." if expected >= 25 else ""
        event_note = f" I allowed for: {rec['event']}." if rec["event"] else ""
        head = f"I expected about {expected:.0f} customers and saw {seen}.{rush_note}{event_note}"

        if rec["action"] == "none":
            return {"verdict": "NO OFFER", "label": "NO OFFER TO JUDGE",
                    "text": f"No offer ran this hour. {head}"}

        ev = self.evidence[rec["action"]]
        ev.tries += 1
        ev.S += (seen - expected) / math.sqrt(expected)
        ev.excess += seen - expected
        ev.expected += expected
        if self.model is not None:
            xa = math.sqrt(expected) * self.model.x(rec)
            ev.a = xa if ev.a is None else ev.a + xa
            bias_var = float(ev.a @ self.model.cov @ ev.a)
            ev.inflation = self.model.dispersion + bias_var / ev.tries
        e, upper = ev.e, ev.lift_upper(ALPHA / len(OFFERS))
        hours = f"{ev.tries} hour{'s' if ev.tries != 1 else ''}"

        if e >= E_THRESHOLD:
            verdict, label = "REAL", "IT WORKED!"
            tail = (f" Over {hours} with this offer, customers are {ev.lift:+.0%} above what I expected. "
                    f"Evidence {e:.0f} beats the {E_THRESHOLD:.0f} I need, so this is beyond luck.")
        elif upper < MIN_WORTHWHILE_LIFT:
            verdict, label = "FAKE", "NO REAL LIFT"
            tail = (f" Over {hours} with this offer, any lift is at most {max(upper, 0):+.0%}: "
                    f"too small to be worth it.")
        else:
            verdict, label = "NOT SURE YET", "NOT SURE YET"
            tail = (f" Over {hours}: {ev.lift:+.0%} vs expected. Evidence {e:.1f} of the "
                    f"{E_THRESHOLD:.0f} I need. Checking every round can't fool me, so I keep waiting.")
        return {"verdict": verdict, "label": label, "text": head + tail,
                "evidence": round(e, 2), "evidenceNeeded": E_THRESHOLD,
                "liftSoFar": round(ev.lift, 3), "hours": ev.tries}
