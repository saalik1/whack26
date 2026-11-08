"""
agents.py - the two AIs that judge every offer.

Both only look at what the player could also see: day, time, weather, temperature, event,
customers, and whether an offer is running. Neither is ever told WHICH offer the player
picked (good or bad), and never the hidden truth.

An offer runs for a whole lock period (one day of shop hours). When it ends, each AI gives
ONE verdict on everything that happened during it.

    naive_window   - plain average. "More customers than an average hour? It worked!"
                     A bad offer launched on a busy day, or during a big event, fools it.
    CarefulAgent   - works out how likely it is that the offer was a good one.
        1. Baseline. It learns what a normal hour looks like from the shop's past sales (a
           Poisson regression on hour, weekday, weather, temperature, trend AND events). It
           has seen every kind of event before, so it has learned how much each one lifts
           or cuts sales. It keeps refitting on every no-offer hour it sees afterwards.
        2. Evidence. Over the whole offer period it compares customers seen with customers
           expected, allowing for its own uncertainty (including the size of each event's
           effect), and asks with Bayes' rule: how likely is this if the offer lifts sales
           by some amount, versus if it does nothing?
        3. Memory of the player. Every judged offer goes into a notebook, together with when it
           started, whether an event was running and what the AI concluded about the offer
           before. Without ever being told the right answers (EM algorithm) the AI learns
             - which lift sizes look real, and
             - the player's habits, e.g. "bad offers tend to come on weekends".
           Several predictors, one per kind of habit, guess the offer before the evidence is
           looked at, and the AI trusts the ones that have been right lately.
        4. It ALWAYS answers, and it decides on the EVIDENCE alone: REAL only if the customers
           seen are at least 20 times likelier if the offer works than if it does nothing (an
           e-value, the method behind POPPER, ICML 2025). So at most 5% of useless offers are
           ever called real, whatever the player does. Points 2-3 are a "gut feeling" shown as
           commentary; they never decide, so the player can't train the AI into a mistake.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, List, Optional

import numpy as np

try:                                   # statsmodels is used when it is installed
    import statsmodels.api as sm
except ImportError:                    # otherwise a small numpy version of the same regression
    sm = None

from .simulator2 import WEEKDAYS, HourRecord


class _PoissonFit:
    """Poisson regression by iteratively reweighted least squares (same model as
    statsmodels' GLM with the Poisson family), used only when statsmodels is missing."""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        beta = np.zeros(X.shape[1])
        beta[0] = math.log(max(y.mean(), 1e-9))
        for _ in range(50):
            mu = np.exp(np.clip(X @ beta, -30, 30))
            z = X @ beta + (y - mu) / mu
            xtwx = X.T @ (X * mu[:, None]) + 1e-9 * np.eye(X.shape[1])
            new = np.linalg.solve(xtwx, X.T @ (mu * z))
            done = np.max(np.abs(new - beta)) < 1e-9
            beta = new
            if done:
                break
        mu = np.exp(np.clip(X @ beta, -30, 30))
        self.params = beta
        self._cov = np.linalg.inv(X.T @ (X * mu[:, None]) + 1e-9 * np.eye(X.shape[1]))
        self.pearson_chi2 = float(np.sum((y - mu) ** 2 / mu))
        self.df_resid = X.shape[0] - X.shape[1]

    def cov_params(self) -> np.ndarray:
        return self._cov

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


def naive_window(window: List[HourRecord], past: List[HourRecord]) -> dict:
    """The naive AI's one verdict on a whole offer period: compare the average hour of the
    offer with the average hour of everything that came before."""
    hours = len(window)
    avg_window = sum(r.customers for r in window) / hours
    avg = sum(r.customers for r in past) / len(past) if past else avg_window
    lift = avg_window / avg - 1 if avg else 0.0
    verdict = "REAL" if lift > NAIVE_LIFT_NEEDED else "FAKE"
    label = "IT WORKED!" if verdict == "REAL" else "NO REAL LIFT"
    if verdict == "REAL":
        text = (f"Hours with the offer averaged {avg_window:.1f} customers against {avg:.1f} for an "
                f"average hour ({lift:+.0%}). Above average, so I think it worked!")
    else:
        text = (f"Hours with the offer averaged {avg_window:.1f} customers against {avg:.1f} for an "
                f"average hour ({lift:+.0%}). I do not see an increase in sales.")
    return {"verdict": verdict, "label": label, "text": text, "lift": round(lift, 3)}


# --------------------------------------------------------------------------- #
# Careful AI
# --------------------------------------------------------------------------- #

# Lifts a good offer might plausibly give. The AI starts with no idea which is the real
# one; it learns how likely each size is from the offers it has judged (see PlayerMemory).
LIFT_GRID = (0.06, 0.08, 0.10, 0.13, 0.16, 0.20, 0.25, 0.30)
REAL_BAR = 0.5               # the habit-based "gut feeling" (commentary only, never decides)
E_BAR = 20.0                 # evidence needed to say REAL: 1 / 0.05 (at most 5% of useless offers pass)
SHARE = 0.02                 # keeps every habit predictor alive, so a change of style is noticed
HABITS = ("weekend", "event", "block", "previous")   # kinds of habit the AI keeps track of
EM_ITERS = 10
MEMORY_HALF_LIFE = 8         # offers after which an older offer counts half as much
HABIT_PULL = 1.0             # pseudo-offers pulling a habit towards the player's overall average
MIN_OFFERS_TO_LEARN = 3
UNKNOWN_EVENT_SD = 0.4       # how wrong the AI allows itself to be about an event it has never seen
BASELINE_REFIT_EVERY = 48    # refit the baseline after this many new no-offer hours


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
        self.fit = (sm.GLM(y, X, family=sm.families.Poisson()).fit() if sm is not None
                    else _PoissonFit(X, y))
        self.cov = np.asarray(self.fit.cov_params())          # uncertainty in what it learned
        self.dispersion = max(1.0, float(self.fit.pearson_chi2 / self.fit.df_resid))

    def x(self, rec: dict) -> np.ndarray:
        return np.array(_features(rec, self.event_labels))

    def expected(self, rec: dict) -> float:
        return float(np.exp(self.x(rec) @ self.fit.params))

    def event_effect(self, label: str):
        """How much the baseline has learned this kind of event changes sales (None: never seen)."""
        if label not in self.event_labels:
            return None
        base = len(_features({"hour": 9, "weekday": "Monday", "weather": "Sunny",
                              "temperature_c": 14.0, "day": 0, "event": None}, []))
        return float(math.exp(self.fit.params[base + self.event_labels.index(label)]) - 1)

    def inflation(self, rec: dict, expected: float) -> float:
        """How much noisier an hour is than pure Poisson luck: extra spread in the data,
        plus the error in the baseline itself (it matters more in busy hours)."""
        x = self.x(rec)
        return self.dispersion + expected * float(x @ self.cov @ x)



def _log_lik_ratios(seen: int, expected: float, inflation: float) -> np.ndarray:
    """For each plausible lift: log of P(seen | offer lifts sales by that much) divided by
    P(seen | offer does nothing), softened by `inflation` (noisier data = weaker evidence)."""
    lifts = np.array(LIFT_GRID)
    return np.clip((seen * np.log1p(lifts) - lifts * expected) / inflation, -30.0, 30.0)


def _e_value(L: np.ndarray) -> float:
    """Mixture likelihood ratio over the lift grid with equal weights fixed in advance."""
    return float(np.mean(np.exp(L)))


def _fmt_e(e: float) -> str:
    return "over 1,000" if e >= 1000 else (f"{e:.0f}" if e >= 10 else f"{e:.1f}")


class PlayerMemory:
    """The AI's notebook about the player: one line per judged offer (how the customer count
    compared with each plausible lift, and the situation the offer was launched in). It learns
    from the notebook WITHOUT ever being told which offers were good (EM algorithm):
      lift_weights   how likely each lift size is, given everything seen so far
      share_good     overall share of the player's offers that look good
      habits         the same share for each situation, e.g. weekend starts vs weekday starts
    Older offers fade, so a player who changes style is eventually noticed.
    """

    def __init__(self) -> None:
        self.L: List[np.ndarray] = []
        self.ctx: List[dict] = []
        k = len(LIFT_GRID)
        self.lift_weights = np.full(k, 1.0 / k)
        self.share_good = 0.5
        self.habits = {name: {} for name in HABITS}      # habit -> situation -> share good
        self.counts = {name: {} for name in HABITS}      # habit -> situation -> offers seen

    def add(self, L: np.ndarray, ctx: dict) -> None:
        self.L.append(L)
        self.ctx.append(ctx)

    def good_ratio(self, L: np.ndarray) -> float:
        """How many times likelier this offer period is if the offer is good than if it is useless."""
        return float(np.dot(self.lift_weights, np.exp(L)))

    def priors(self, ctx: dict) -> list:
        """Each habit predictor's guess, before looking at the customers, that the offer is good."""
        clip = lambda v: min(0.97, max(0.03, v))
        return [clip(self.share_good)] + [clip(self.habits[h].get(str(ctx[h]), self.share_good)) for h in HABITS]

    def refit(self) -> None:
        n = len(self.L)
        if n < MIN_OFFERS_TO_LEARN:
            return
        A = np.exp(np.array(self.L))                     # (offers, lifts)
        k = A.shape[1]
        wt = 0.5 ** (np.arange(n)[::-1] / MEMORY_HALF_LIFE)
        # Every good offer lifts sales by the SAME unknown amount, so learn one shared lift size:
        # for each candidate lift, how often are offers good and how well does that explain the
        # notebook? The candidates that explain it best get the most weight.
        pis = np.full(k, self.share_good)
        for _ in range(EM_ITERS + 5):
            post = pis * A / (pis * A + 1 - pis)
            pis = ((post * wt[:, None]).sum(axis=0) + 1) / (wt.sum() + 2)
        loglik = (wt[:, None] * np.log(pis * A + 1 - pis)).sum(axis=0)
        g = np.exp(loglik - loglik.max())
        g = g / g.sum()
        pi = float(np.dot(g, pis))
        self.lift_weights, self.share_good = g, pi
        ratio = A @ g
        for h in HABITS:
            keys = np.array([str(c[h]) for c in self.ctx])
            for key in set(keys.tolist()):
                idx = keys == key
                w, p = wt[idx], pi
                for _ in range(EM_ITERS):
                    post = p * ratio[idx] / (p * ratio[idx] + 1 - p)
                    p = ((post * w).sum() + HABIT_PULL * pi) / (w.sum() + HABIT_PULL)
                self.habits[h][key] = float(p)
                self.counts[h][key] = int(idx.sum())

    def lift_estimate(self) -> float:
        return float(np.dot(self.lift_weights, LIFT_GRID))


class CarefulAgent:
    def __init__(self, past_records: Optional[List[HourRecord]] = None) -> None:
        past = [r.ai_view() for r in (past_records or [])]
        self._quiet = [r for r in past if r["action"] == "none"]      # no-offer hours seen so far
        self._fresh_quiet = 0
        self.model = BaselineModel(self._quiet) if len(self._quiet) >= 50 else None
        self.memory = PlayerMemory()
        self._weights = [1 / (len(HABITS) + 1)] * (len(HABITS) + 1)   # trust in each habit predictor
        self._previous = "none"          # what the AI concluded about the previous offer
        self.offers_judged = 0
        # Events an outside source (the DeepSeek helper) told us about: label -> (effect, uncertainty).
        # Only used for events the AI has not learned from its own data.
        self.external_events: dict = {}

    # ---- seeing the shop ---------------------------------------------------- #

    def _expected(self, rec: dict) -> float:
        if self.model is None:                      # no past data: fall back to the shop's forecast
            return max(1.0, float(rec["forecast"]))
        base = max(1.0, self.model.expected(rec))
        ext = self.external_events.get(rec.get("event"))
        if ext is not None and rec["event"] not in self.model.event_labels:
            base = max(1.0, base * (1 + ext[0]))
        return base

    def expected_customers(self, record: HourRecord) -> float:
        """How many customers the AI expects in this hour with no offer, events included."""
        return self._expected(record.ai_view())

    def event_effect(self, label: str):
        """How much the AI has learned this kind of event changes sales (None: never seen it)."""
        if label in self.external_events and (self.model is None or label not in self.model.event_labels):
            return self.external_events[label][0]
        return self.model.event_effect(label) if self.model is not None else None

    def observe(self, record: HourRecord) -> None:
        """Called for every hour. No-offer hours are clean examples of a normal hour, so the
        baseline is refitted on them as they arrive."""
        rec = record.ai_view()
        if rec["action"] != "none":
            return
        self._quiet.append(rec)
        self._fresh_quiet += 1
        if self._fresh_quiet >= BASELINE_REFIT_EVERY and len(self._quiet) >= 50:
            self._fresh_quiet = 0
            try:
                self.model = BaselineModel(self._quiet)
            except Exception:                      # keep the old baseline if the refit fails
                pass

    # ---- the verdict ---------------------------------------------------------- #

    def judge_window(self, records: List[HourRecord]) -> dict:
        """ONE verdict on a whole offer period."""
        views = [r.ai_view() for r in records]
        exp = [self._expected(v) for v in views]
        expected_total, seen = sum(exp), sum(v["customers"] for v in views)

        # How much to trust the comparison: noise beyond Poisson luck, plus the error in the
        # baseline itself (it is shared by every hour, so it does NOT average out over the
        # period), plus extra room for events the AI has never seen.
        infl, unseen = 1.0, []
        if self.model is not None:
            a = sum(e * self.model.x(v) for e, v in zip(exp, views))
            unseen = [(e, v["event"]) for e, v in zip(exp, views)
                      if v["event"] and v["event"] not in self.model.event_labels
                      and v["event"] not in self.external_events]
            told = [(e, self.external_events[v["event"]][1]) for e, v in zip(exp, views)
                    if v["event"] in self.external_events and v["event"] not in self.model.event_labels]
            extra = (UNKNOWN_EVENT_SD * sum(e for e, _ in unseen)) ** 2 + sum((sd * e) ** 2 for e, sd in told)
            infl = (self.model.dispersion * expected_total + float(a @ self.model.cov @ a) + extra) / expected_total
        L = _log_lik_ratios(seen, expected_total, infl)

        first = views[0]
        ctx = {"weekend": WEEKDAYS.index(first["weekday"]) >= 5,
               "event": any(v["event"] for v in views),
               "block": (first["hour"] - 9) // 3,
               "previous": self._previous}

        # Each habit predictor guesses BEFORE the evidence is looked at; trust follows success.
        ratio = self.memory.good_ratio(L)
        priors = self.memory.priors(ctx)
        posts = []
        for i, pr in enumerate(priors):
            predicted = pr * ratio + (1 - pr)
            self._weights[i] *= predicted
            posts.append(pr * ratio / predicted)
        total, k = sum(self._weights), len(self._weights)
        self._weights = [(1 - SHARE) * w / total + SHARE / k for w in self._weights]
        p = sum(w * b for w, b in zip(self._weights, posts))

        # Learn from it.
        self.memory.add(L, ctx)
        self.memory.refit()
        self.offers_judged += 1
        self._previous = "good" if p > REAL_BAR else "bad"

        # THE DECISION uses the evidence alone: an e-value, how many times likelier the customers
        # seen are if the offer works (averaged over plausible lift sizes, weights fixed in advance)
        # than if it does nothing. For a useless offer its average is at most 1, so it reaches 20
        # at most 5% of the time (Markov's inequality). Habits never decide; they are commentary.
        e_value = _e_value(L)
        verdict = "REAL" if e_value >= E_BAR else "FAKE"
        label = "IT WORKED!" if verdict == "REAL" else "NO REAL LIFT"   # always a yes or a no
        confidence = p if verdict == "REAL" else 1 - p
        lift = seen / expected_total - 1
        events = self._event_summary(views)
        event_text = (" I allowed for: " + "; ".join(e["text"] for e in events) + ".") if events else ""
        if verdict == "REAL":
            judged = (f" That is {_fmt_e(e_value)} times likelier if the offer works than if it does nothing, "
                      f"past the {E_BAR:.0f} times I need. It worked.")
        elif e_value < 1:
            judged = (" The customers fit 'the offer does nothing' better than 'it works'. "
                      "My answer: no real lift.")
        else:
            judged = (f" The evidence is only {_fmt_e(e_value)} times likelier if it works, short of the "
                      f"{E_BAR:.0f} times I need. My answer: no real lift.")
        text = (f"Over {len(views)} hours I expected about {expected_total:.0f} customers and saw {seen} "
                f"({lift:+.0%}).{event_text}{judged} (Gut feeling from your habits: {p:.0%} chance it is good.)"
                f"{self._habit_note()}")
        return {"verdict": verdict, "label": label, "text": text,
                "evidence": round(e_value, 3), "evidenceNeeded": E_BAR,
                "probability": round(p, 3),             # habit-based chance the offer is good (commentary)
                "confidence": round(confidence, 3),     # chance the verdict above is right
                "expected": round(expected_total), "seen": seen, "lift": round(lift, 3),
                "hours": len(views), "events": events, "learned": self.what_i_learned()}

    # ---- explaining itself ---------------------------------------------------- #

    def _event_summary(self, views: List[dict]) -> List[dict]:
        out, order = {}, []
        for v in views:
            if v["event"]:
                if v["event"] not in out:
                    out[v["event"]] = 0
                    order.append(v["event"])
                out[v["event"]] += 1
        summary = []
        for label in order:
            eff = self.event_effect(label)
            hours = out[label]
            if label in self.external_events and (self.model is None or label not in self.model.event_labels):
                text = f"{label} ({hours} h, new to me, but I was told it changes sales by about {eff:+.0%})"
            elif eff is None:
                text = f"{label} ({hours} h, new to me, so I left extra room for error)"
            else:
                text = f"{label} ({hours} h, which I have seen change sales by about {eff:+.0%})"
            summary.append({"label": label, "hours": hours, "effect": None if eff is None else round(eff, 3),
                            "text": text})
        return summary

    def what_i_learned(self) -> dict:
        m = self.memory
        return {"offersJudged": self.offers_judged,
                "liftEstimate": round(m.lift_estimate(), 3),
                "goodShareOverall": round(m.share_good, 3),
                "habits": {h: {k: round(v, 3) for k, v in m.habits[h].items()} for h in HABITS},
                "habitCounts": m.counts}

    def _habit_note(self) -> str:
        m, best = self.memory, None
        for h, label in (("weekend", "starting on a weekend"), ("event", "adding an event")):
            yes, no = m.habits[h].get("True"), m.habits[h].get("False")
            if yes is None or no is None or min(m.counts[h]["True"], m.counts[h]["False"]) < 2:
                continue
            if abs(yes - no) >= 0.4 and (best is None or abs(yes - no) > best[0]):
                best = (abs(yes - no), label, yes, no)
        if best:
            return (f" I have noticed that when you launch an offer {best[1]}, it is good about {best[2]:.0%} "
                    f"of the time, against {best[3]:.0%} otherwise.")
        return ""