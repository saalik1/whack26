"""
agents.py - the two AIs that judge every round.

Both only look at the PUBLIC record of an hour (what the player could also see):
day, time, weather, temperature, event, action, customers. Never the hidden truth.

    naive_agent   - plain average. "More customers than usual? The offer worked!"
                    A bad offer launched at a rush hour fools it every time.
    CarefulAgent  - compares each hour with what that hour SHOULD have looked like
                    (time of day, weekday, weather, temperature, events), then pools the
                    evidence over all offers of the same kind before it says "real".

NOTE (prototype): CarefulAgent is given the shop's baseline model directly, as if it had
learned it from past quiet hours. The statistics here are a stand-in for the real defences
(holdout, permutation test, Benjamini-Hochberg, e-values, STL) that come in stages 2-3.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List

from simulator2 import EVENT_MULT_BY_LABEL, WEEKDAYS, HourRecord, expected_customers

# Naive AI: "worked" if the hour beats the running average by 20%.
NAIVE_LIFT_NEEDED = 0.20

# Careful AI: pooled z-score needed to say REAL (2.33 is roughly a 1% bar),
# and how flat the evidence must look, after a few tries, to say FAKE.
CAREFUL_REAL_Z = 2.33
CAREFUL_FAKE_Z = 0.5
CAREFUL_MIN_TRIES_FOR_FAKE = 3


def baseline_for(record: HourRecord) -> float:
    """What the careful AI expects for the conditions that actually happened."""
    event_mult = EVENT_MULT_BY_LABEL.get(record.event, 1.0) if record.event else 1.0
    return expected_customers(WEEKDAYS.index(record.weekday), record.hour, record.weather,
                              record.temperature_c, event_mult, record.day)


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

@dataclass
class Evidence:
    tries: int = 0
    excess: float = 0.0      # total customers seen minus total expected
    expected: float = 0.0    # total customers expected

    @property
    def pooled_z(self) -> float:
        return self.excess / math.sqrt(self.expected) if self.expected > 0 else 0.0

    @property
    def pooled_lift(self) -> float:
        return self.excess / self.expected if self.expected > 0 else 0.0


class CarefulAgent:
    def __init__(self) -> None:
        self.evidence: Dict[str, Evidence] = {"good": Evidence(), "bad": Evidence()}

    def judge(self, record: HourRecord) -> dict:
        expected = baseline_for(record)
        seen = record.customers
        rush_note = " That hour is normally a rush, so I ignore the crowd." if expected >= 25 else ""
        event_note = f" I allowed for: {record.event}." if record.event else ""

        if record.action == "none":
            return {"verdict": "NO OFFER", "label": "NO OFFER TO JUDGE",
                    "text": f"No offer ran this hour. With everything considered I expected about "
                            f"{expected:.0f} customers and saw {seen}.{event_note}"}

        ev = self.evidence[record.action]
        ev.tries += 1
        ev.excess += seen - expected
        ev.expected += expected
        z = ev.pooled_z

        adjust_note = ""
        if abs(record.forecast - expected) >= 2:   # weather or an event changed what was predicted
            adjust_note = f" (I first predicted {record.forecast:.0f}, then adjusted for the weather and events.)"
        head = f"I expected {expected:.0f} customers and saw {seen}.{adjust_note}{rush_note}{event_note}"
        if z >= CAREFUL_REAL_Z:
            verdict, label = "REAL", "IT WORKED!"
            tail = (f" Across {ev.tries} offers of this kind there are {ev.pooled_lift:+.0%} more customers "
                    f"than expected. That is beyond luck.")
        elif ev.tries >= CAREFUL_MIN_TRIES_FOR_FAKE and z <= CAREFUL_FAKE_Z:
            verdict, label = "FAKE", "NO REAL LIFT"
            tail = (f" After {ev.tries} offers of this kind, the difference ({ev.pooled_lift:+.0%}) "
                    f"is within normal ups and downs.")
        else:
            verdict, label = "NOT SURE YET", "NOT SURE YET"
            tail = (f" {ev.tries} offer{'s' if ev.tries != 1 else ''} of this kind so far "
                    f"{'is' if ev.tries == 1 else 'are'} not enough evidence.")
        return {"verdict": verdict, "label": label, "text": head + tail}
