"""
game.py - one player's game: a Shop, the two AIs, the clock and the score.

api.py keeps one Game per browser (cookie), so several judges can play at the same time.

HOW THE GAME RUNS
  - Time only moves when the screen calls tick(): one shop hour per call. The screen decides
    how often (pause / play / double play) using the speeds in config(), so the speed is
    changed in ONE place: SECONDS_PER_HOUR below.
  - launch_offer("good" | "bad") starts an offer. It then LOCKS the offer button for
    OFFER_LOCK_HOURS shop hours (until the same time tomorrow). No new offer until then.
  - When the lock ends both AIs give ONE verdict on the whole offer period. It comes back as
    a "verdict" pop-up.
  - trigger_event("random" or a key) adds an event (football match, tourist bus ...). It
    changes sales from the next hour on, and the AI takes it into account. When an event
    is over an "event_ended" pop-up shows what the AI made of it.
  - While any pop-up is open the game is PAUSED: tick() refuses until dismiss_popup().

Every method returns the same kind of dict (see _response): the latest hour, the clock, what
the player can do now, any open pop-ups, and the scores.
"""
from __future__ import annotations

import functools
import threading
from typing import Optional

from .agents import CarefulAgent, naive_window
from .simulator2 import EVENTS, OPEN_HOURS, RUSH_THRESHOLD, WEEKDAYS, Shop, label_time

# ---- the knobs ------------------------------------------------------------- #
SECONDS_PER_HOUR = 2.0        # Play: one shop hour passes every this many real seconds
DOUBLE_SPEED_FACTOR = 2.0     # Double play: this many times faster (2 s -> 1 s per hour)
OFFER_LOCK_HOURS = len(OPEN_HOURS)   # 12 shop hours = until the same time tomorrow (the shop is shut overnight)
LIVE_GOOD_EFFECT = 0.20       # the real lift of a Good Offer. The brief's example is +8%: harder for the AI
PAST_DAYS = 182               # about six months of ordinary trading the AI learns from
PAST_HOURS = PAST_DAYS * len(OPEN_HOURS)
PAST_EVENT_CHANCE = 0.03      # extra events scheduled into the past, so the AI has seen every kind


def _locked(method):
    """One request at a time per game (the web server handles requests in threads)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


class Game:
    def __init__(self, seed: Optional[int] = None, good_effect: float = LIVE_GOOD_EFFECT):
        self._lock = threading.RLock()
        self.shop = Shop(seed=seed, good_effect=good_effect)
        self._run_past()
        self.shop.step("none")                    # the opening hour shown on screen
        self.careful = CarefulAgent(self.shop.history)
        self.offer: Optional[dict] = None         # {"kind", "hoursDone", "unlocksAt"}
        self.window: list = []                    # the hours of the running offer
        self.popups: list = []                    # open pop-ups; time is frozen while there are any
        self._event_hours: list = []              # hours of the event that is running
        self.scores = {"offersJudged": 0, "carefulRight": 0, "naiveRight": 0,
                       "carefulFooled": 0, "naiveFooled": 0}

    def _run_past(self) -> None:
        """Six months of ordinary trading (no offers). Every kind of event happens many times,
        so the AI learns from the data how much each one changes sales."""
        order: list = []
        for _ in range(PAST_HOURS):
            if self.shop.active_event is None and self.shop.rng.random() < PAST_EVENT_CHANCE:
                if not order:
                    order = list(EVENTS)
                    self.shop.rng.shuffle(order)
                self.shop.trigger_event(order.pop())
            self.shop.step("none")

    # ---- what the screen needs to know ------------------------------------------ #

    def config(self) -> dict:
        return {
            "secondsPerHour": SECONDS_PER_HOUR,
            "speeds": {"pause": 0, "play": SECONDS_PER_HOUR, "double": SECONDS_PER_HOUR / DOUBLE_SPEED_FACTOR},
            "offerLockHours": OFFER_LOCK_HOURS,
            "events": [{"key": k, "label": v["label"], "hours": v["hours"],
                        "effect": f"{v['mult'] - 1:+.0%} customers"} for k, v in EVENTS.items()],
        }

    def _scores(self) -> dict:
        return {**self.scores, "rounds": self.scores["offersJudged"]}

    def _response(self, ok: bool = True, error: Optional[str] = None) -> dict:
        last = self.shop.history[-1]
        forecast = self.shop.forecast_next_hour()
        offer = None
        if self.offer:
            offer = {"kind": self.offer["kind"], "hoursDone": self.offer["hoursDone"],
                     "hoursLeft": OFFER_LOCK_HOURS - self.offer["hoursDone"],
                     "unlocksAt": self.offer["unlocksAt"]}
        busy = bool(self.popups)
        active = self.shop.active_event
        event_running = active is not None
        key_of = {spec["label"]: key for key, spec in EVENTS.items()}
        return {
            "ok": ok, "error": error,
            # the latest hour
            "customers": last.customers, "weather": last.weather, "temperature": last.temperature_c,
            "time": f"{last.weekday} {last.time_label}", "event": last.event,
            "expected": round(last.forecast),               # what the shop's forecast said for that hour
            "eventKey": key_of.get(last.event),             # event during the latest hour (for the picture)
            # the next hour
            "nextTime": f"{self.shop.weekday} {label_time(self.shop.hour)}",
            "nextPrediction": round(forecast["expected"]),
            "nextIsRush": forecast["expected"] >= RUSH_THRESHOLD,
            "activeEvent": active["label"] if event_running else None,
            "activeEventKey": active["key"] if event_running else None,
            "eventHoursLeft": active["hours_left"] if event_running else 0,
            # what the player can do right now
            "offer": offer,
            "canLaunchOffer": offer is None and not busy,
            "canTriggerEvent": not event_running and not busy,
            "paused": busy,                       # True while a pop-up is open
            "popups": list(self.popups),
            "scores": self._scores(),
        }

    def start_payload(self) -> dict:
        return {**self._response(), "config": self.config()}

    # ---- the clock ----------------------------------------------------------------- #

    @_locked
    def tick(self) -> dict:
        """One shop hour passes. Call it every SECONDS_PER_HOUR (or half that) while playing."""
        if self.popups:
            return self._response(False, "A pop-up is open. Dismiss it to carry on.")
        record = self.shop.step(self.offer["kind"] if self.offer else "none")
        self.careful.observe(record)
        self._track_event(record)
        if self.offer:
            self.window.append(record)
            self.offer["hoursDone"] += 1
            if self.offer["hoursDone"] >= OFFER_LOCK_HOURS:
                self._finish_offer()
        return self._response()

    # ---- the player's three actions ---------------------------------------------------- #

    @_locked
    def launch_offer(self, kind: str) -> dict:
        if kind not in ("good", "bad"):
            return self._response(False, "kind must be 'good' or 'bad'")
        if self.popups:
            return self._response(False, "A pop-up is open. Dismiss it first.")
        if self.offer:
            left = OFFER_LOCK_HOURS - self.offer["hoursDone"]
            return self._response(False, f"An offer is already running. You can launch another at "
                                         f"{self.offer['unlocksAt']} ({left} hours left).")
        tomorrow = WEEKDAYS[(self.shop.weekday_idx + 1) % 7]
        self.offer = {"kind": kind, "hoursDone": 0, "unlocksAt": f"{tomorrow} {label_time(self.shop.hour)}"}
        self.window = []
        return self._response()

    @_locked
    def trigger_event(self, which: str = "random") -> dict:
        if self.popups:
            return self._response(False, "A pop-up is open. Dismiss it first.")
        if self.shop.active_event is not None:
            return self._response(False, f"{self.shop.active_event['label']} is still going on.")
        try:
            self.shop.trigger_event(which)
        except ValueError as e:
            return self._response(False, str(e))
        return self._response()

    @_locked
    def dismiss_popup(self) -> dict:
        if self.popups:
            self.popups.pop(0)
        return self._response()

    # ---- the pop-ups ----------------------------------------------------------------------- #

    def _track_event(self, record) -> None:
        """When an event is over, open a pop-up with what the AI made of it."""
        if record.event is None:
            return
        self._event_hours.append(record)
        if self.shop.active_event is not None:        # still going on
            return
        hours, self._event_hours = self._event_hours, []
        label = record.event
        expected = sum(self.careful.expected_customers(r) for r in hours)
        seen = sum(r.customers for r in hours)
        effect = self.careful.event_effect(label)
        if effect is None:
            text = (f"{label} is over. I had never seen this kind of event, so I could not tell how much "
                    f"it should change sales and I left extra room for error.")
        else:
            text = (f"{label} is over. From past events like it I had allowed for about {effect:+.0%} "
                    f"customers. I expected about {expected:.0f} over its {len(hours)} hour"
                    f"{'s' if len(hours) != 1 else ''} and counted {seen}.")
        self.popups.append({"type": "event_ended", "title": f"{label} is over", "label": label,
                            "hours": len(hours), "aiExpected": round(expected), "seen": seen,
                            "aiEffect": None if effect is None else round(effect, 3), "text": text})

    def _finish_offer(self) -> None:
        """The lock has ended: both AIs judge the whole offer period."""
        window, kind = self.window, self.offer["kind"]
        past = self.shop.history[: len(self.shop.history) - len(window)]
        careful = self.careful.judge_window(window)
        naive = naive_window(window, past)
        is_good = kind == "good"
        careful_right = (careful["verdict"] == "REAL") == is_good
        naive_right = (naive["verdict"] == "REAL") == is_good
        careful["fooled"] = (not is_good) and careful["verdict"] == "REAL"
        naive["fooled"] = (not is_good) and naive["verdict"] == "REAL"
        naive["tag"] = "Fooled!" if naive["fooled"] else ("Got it right" if naive_right else "Missed it")
        careful["tag"] = "Fooled!" if careful["fooled"] else ("Got it right" if careful_right else "Missed it")

        s = self.scores
        s["offersJudged"] += 1
        s["carefulRight"] += int(careful_right)
        s["naiveRight"] += int(naive_right)
        s["carefulFooled"] += int(careful["fooled"])
        s["naiveFooled"] += int(naive["fooled"])
        self.popups.append({"type": "verdict", "title": "The AI's verdict is in", "offer": kind,
                            "careful": careful, "naive": naive,
                            "carefulRight": careful_right, "naiveRight": naive_right,
                            "scores": self._scores()})
        self.offer, self.window = None, []