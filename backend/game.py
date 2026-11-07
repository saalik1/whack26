"""
game.py - one player's game: a Shop, the two AIs and the score.

api.py keeps one Game per browser (cookie), so several judges can play at the same time.
"""
from __future__ import annotations

from typing import Optional

from .agents import CarefulAgent, naive_agent
from .simulator2 import RUSH_THRESHOLD, Shop

# The real lift of a Good Offer in the LIVE game.
# The brief's example is +8%, which takes ~35 offers to confirm. 20% lets the careful AI
# reach a verdict within about six Good Offers, which suits a live demo.
# Set to 0.08 to match the brief exactly (e.g. for the 1,000-game evidence runs).
LIVE_GOOD_EFFECT = 0.20


class Game:
    def __init__(self, seed: Optional[int] = None, good_effect: float = LIVE_GOOD_EFFECT):
        self.shop = Shop.new_game(seed=seed, good_effect=good_effect)
        self.careful = CarefulAgent()
        self.rounds = 0
        self.careful_fooled = 0
        self.naive_fooled = 0

    # ---- shared pieces of the response ------------------------------------ #

    def _scores(self) -> dict:
        return {"rounds": self.rounds, "carefulFooled": self.careful_fooled, "naiveFooled": self.naive_fooled}

    def _look_ahead(self) -> dict:
        forecast = self.shop.forecast_next_hour()
        return {"nextPrediction": round(forecast["expected"]),
                "nextIsRush": forecast["expected"] >= RUSH_THRESHOLD}

    # ---- what the screen shows before the first click --------------------- #

    def start_payload(self) -> dict:
        last = self.shop.history[-1]
        return {
            "customers": last.customers,
            "weather": last.weather,
            "temperature": last.temperature_c,
            "time": f"{last.weekday} {last.time_label}",
            "event": last.event,
            "scores": self._scores(),
            **self._look_ahead(),
        }

    # ---- one button press -------------------------------------------------- #

    def play(self, offer: str) -> dict:
        past = list(self.shop.history)           # hours before this one
        record = self.shop.play_round(offer)
        naive = naive_agent(record, past)
        careful = self.careful.judge(record)

        is_bad = record.action == "bad"
        careful_fooled = is_bad and careful["verdict"] == "REAL"
        naive_fooled = is_bad and naive["verdict"] == "REAL"
        if naive_fooled:
            naive["tag"] = "Fooled!"
        elif record.action == "none":
            naive["tag"] = "No offer"
        elif (naive["verdict"] == "REAL") == (record.action == "good"):
            naive["tag"] = "Got it right"
        else:
            naive["tag"] = "Missed it"
        careful["fooled"], naive["fooled"] = careful_fooled, naive_fooled

        self.rounds += 1
        self.careful_fooled += int(careful_fooled)
        self.naive_fooled += int(naive_fooled)

        return {
            # the original contract the frontend already understands
            "customers": record.customers,
            "weather": record.weather,
            # extras
            "temperature": record.temperature_c,
            "time": f"{record.weekday} {record.time_label}",
            "event": record.event,
            "offer": offer,
            "expected": round(record.forecast),
            "careful": careful,
            "naive": naive,
            "scores": self._scores(),
            **self._look_ahead(),
        }
