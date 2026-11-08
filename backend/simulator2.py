"""
simulator2.py - the hourly corner-shop simulator.

The shop is open 09:00-20:59 (12 hours a day). Each call to Shop.step() simulates ONE hour.

The player's input each hour is one of:
    "good"  - a genuinely good offer   (hidden truth: +8% customers)
    "bad"   - a useless offer          (hidden truth: +0%)
    "none"  - no offer

Everything else is simulated: day of week, time, weather, temperature, random events,
customer counts and revenue. The hidden ground truth (the real effect of each offer) is
stored on every record so the AI can be scored later, but it is stripped out of
HourRecord.public() so the agents and the browser never see it.

Pure standard library: no numpy needed.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, asdict
from typing import Callable, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Settings (all the "knobs" live here so they are easy to change)
# --------------------------------------------------------------------------- #

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
OPEN_HOURS = list(range(9, 21))  # 9..20 inclusive

# Typical customers per hour on a normal weekday: two rushes (lunch and after work).
HOURLY_CURVE = {
    9: 8, 10: 12, 11: 18, 12: 30, 13: 28, 14: 16,
    15: 14, 16: 18, 17: 30, 18: 26, 19: 14, 20: 8,
}
RUSH_THRESHOLD = 25          # an hour counts as a "rush" above this baseline
WEEKEND_MULT = 1.3
WEATHER_MULT = {"Sunny": 1.10, "Cloudy": 1.00, "Rainy": 0.80}
TREND_PER_DAY = 0.0005       # shop slowly grows 0.05% a day (about 10% over six months)

# Weather is a Markov chain: it tends to stay the same from hour to hour.
WEATHER_TRANSITIONS = {
    "Sunny":  {"Sunny": 0.86, "Cloudy": 0.12, "Rainy": 0.02},
    "Cloudy": {"Sunny": 0.10, "Cloudy": 0.80, "Rainy": 0.10},
    "Rainy":  {"Sunny": 0.02, "Cloudy": 0.18, "Rainy": 0.80},
}
WEATHER_TEMP_ADJ = {"Sunny": 2.0, "Cloudy": 0.0, "Rainy": -2.0}

# The hidden truth. This is what the AI is trying to discover.
TRUE_EFFECTS = {"none": 0.0, "bad": 0.0, "good": 0.08}

# Random events: multiplier on customers, how many hours it lasts. The keys and hours match
# the pictures and banners in the frontend (frontend/app.js).
EVENTS = {
    "leicester_win":   {"label": "LCFC wins a dramatic match!",                  "mult": 1.5, "hours": 3},
    "whack_hackathon": {"label": "WHACK Warwick Hackathon is happening today!",  "mult": 1.3, "hours": 6},
    "wifi_outage":     {"label": "City-wide card machine crash",                 "mult": 0.6, "hours": 2},
    "tiktok_viral":    {"label": "A food reviewer goes viral on TikTok!",        "mult": 1.6, "hours": 1},
    "roadworks":       {"label": "Emergency roadworks outside",                  "mult": 0.8, "hours": 5},
}
SPONTANEOUS_EVENT_CHANCE = 0.03   # per hour, when no event is running
EVENT_MULT_BY_LABEL = {spec["label"]: spec["mult"] for spec in EVENTS.values()}

AVG_BASKET = 6.50   # average spend per customer (GBP)
BASKET_SD = 2.50

ACTIONS = ("good", "bad", "none")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def poisson(rng: random.Random, lam: float) -> int:
    """Sample a Poisson random number (stdlib only)."""
    if lam <= 0:
        return 0
    if lam > 40:  # normal approximation is fine for big rates
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= limit:
            return k - 1


def expected_customers(weekday_idx: int, hour: int, weather: str, temperature_c: float,
                       event_mult: float = 1.0, day_count: int = 0) -> float:
    """The no-offer baseline: how many customers we expect in this hour."""
    value = HOURLY_CURVE[hour]
    if weekday_idx >= 5:
        value *= WEEKEND_MULT
    value *= WEATHER_MULT[weather]
    value *= min(1.10, max(0.90, 1 + 0.01 * (temperature_c - 14)))   # mild days are busier
    value *= (1 + TREND_PER_DAY) ** day_count
    value *= event_mult
    return value


def label_time(hour: int) -> str:
    return f"{hour:02d}:00"


# --------------------------------------------------------------------------- #
# One simulated hour
# --------------------------------------------------------------------------- #

@dataclass
class HourRecord:
    step: int
    day: int                    # 0 = first day
    weekday: str
    hour: int
    time_label: str
    weather: str
    temperature_c: float
    event: Optional[str]        # event label, or None
    action: str                 # "good" | "bad" | "none"
    forecast: float             # what a forecaster predicted BEFORE the hour (no offer)
    customers: int
    revenue: float
    is_rush_hour: bool
    # --- hidden ground truth (never sent to agents or the browser) ---
    expected_customers: float   # true no-offer baseline for the conditions that really happened
    true_effect: float          # real lift caused by the action (0.08 for good, 0 otherwise)
    offer_is_real: bool

    HIDDEN = ("expected_customers", "true_effect", "offer_is_real")

    def public(self) -> dict:
        """The record as the AI and the player are allowed to see it."""
        d = asdict(self)
        for key in self.HIDDEN:
            d.pop(key, None)
        return d

    def ai_view(self) -> dict:
        """What the AI judge is allowed to see: the public record, except that the offer is
        anonymous ("offer" or "none": it is never told whether the player picked good or bad)
        and facts derived from the hidden baseline (is_rush_hour) are removed."""
        d = self.public()
        d["action"] = "none" if self.action == "none" else "offer"
        d.pop("is_rush_hour", None)
        return d

    def full(self) -> dict:
        """Everything, including the truth. For scoring only."""
        return asdict(self)


# --------------------------------------------------------------------------- #
# The shop
# --------------------------------------------------------------------------- #

class Shop:
    def __init__(self, seed: Optional[int] = None, start_day_of_week: int = 5,
                 start_hour: int = 11, start_weather: str = "Sunny",
                 good_effect: float = TRUE_EFFECTS["good"]):
        self.rng = random.Random(seed)
        self.seed = seed
        self.good_effect = good_effect

        self.step_count = 0
        self.day = 0
        self.start_weekday = start_day_of_week
        self.hour = start_hour if start_hour in OPEN_HOURS else OPEN_HOURS[0]
        self.weather = start_weather
        self.daily_mean_temp = 14.0 + self.rng.gauss(0, 2)
        self.temperature_c = self._temperature_for(self.hour, self.weather)

        self.active_event: Optional[dict] = None   # {"key", "label", "mult", "hours_left", "known"}
        self.history: List[HourRecord] = []

    # ---- clock ------------------------------------------------------------ #

    @property
    def weekday_idx(self) -> int:
        return (self.start_weekday + self.day) % 7

    @property
    def weekday(self) -> str:
        return WEEKDAYS[self.weekday_idx]

    def _advance_clock(self) -> None:
        self.hour += 1
        if self.hour > OPEN_HOURS[-1]:
            self.hour = OPEN_HOURS[0]
            self.day += 1
            # Overnight, the daily mean temperature wanders a bit.
            self.daily_mean_temp += self.rng.gauss(0, 1.2)
            self.daily_mean_temp = min(24.0, max(2.0, self.daily_mean_temp))

    # ---- environment ------------------------------------------------------ #

    def _temperature_for(self, hour: int, weather: str) -> float:
        diurnal = 4.0 * math.sin((hour - 9) / 12 * math.pi)   # warmest mid-afternoon
        return round(self.daily_mean_temp + diurnal + WEATHER_TEMP_ADJ[weather] + self.rng.gauss(0, 0.7), 1)

    def _next_weather(self) -> str:
        probs = WEATHER_TRANSITIONS[self.weather]
        return self.rng.choices(list(probs), weights=list(probs.values()))[0]

    # ---- events ----------------------------------------------------------- #

    def trigger_event(self, which: Optional[str] = "random") -> Optional[dict]:
        """Player presses the Random Event button. Known to the forecaster."""
        if which is None:
            return None
        key = self.rng.choice(list(EVENTS)) if which == "random" else which
        if key not in EVENTS:
            raise ValueError(f"unknown event {key!r}; choose from {list(EVENTS)} or 'random'")
        spec = EVENTS[key]
        self.active_event = {"key": key, "label": spec["label"], "mult": spec["mult"],
                             "hours_left": spec["hours"], "known": True}
        return self.active_event

    def _event_mult(self) -> float:
        return self.active_event["mult"] if self.active_event else 1.0

    # ---- forecast (what the AI is allowed to know before the hour) -------- #

    def forecast_next_hour(self) -> dict:
        """Baseline prediction for the coming hour: no offer, weather assumed unchanged,
        and only events the player has triggered (i.e. visible ones) are included."""
        mult = self.active_event["mult"] if (self.active_event and self.active_event["known"]) else 1.0
        expected = expected_customers(self.weekday_idx, self.hour, self.weather,
                                      self.temperature_c, mult, self.day)
        return {
            "expected": round(expected, 1),
            "low": max(0, round(expected - 2 * math.sqrt(expected))),
            "high": round(expected + 2 * math.sqrt(expected)),
            "is_rush_hour": expected >= RUSH_THRESHOLD,
        }

    # ---- the main loop: ONE hour ------------------------------------------ #

    def step(self, action: str = "none", event: Optional[str] = None) -> HourRecord:
        if action not in ACTIONS:
            raise ValueError(f"action must be one of {ACTIONS}, got {action!r}")
        if event is not None:
            self.trigger_event(event)

        # 1. Forecast is made before anything unexpected can happen.
        forecast = self.forecast_next_hour()["expected"]

        # 2. An unannounced event may crash the party.
        if self.active_event is None and self.rng.random() < SPONTANEOUS_EVENT_CHANCE:
            key = self.rng.choice(list(EVENTS))
            spec = EVENTS[key]
            self.active_event = {"key": key, "label": spec["label"], "mult": spec["mult"],
                                 "hours_left": spec["hours"], "known": False}

        # 3. Weather moves on (an event like heavy rain can force it).
        self.weather = self._next_weather()
        if self.active_event and EVENTS[self.active_event["key"]].get("force_weather"):
            self.weather = EVENTS[self.active_event["key"]]["force_weather"]
        self.temperature_c = self._temperature_for(self.hour, self.weather)

        # 4. Customers: Poisson around the baseline, nudged by the real effect of the offer.
        baseline = expected_customers(self.weekday_idx, self.hour, self.weather,
                                      self.temperature_c, self._event_mult(), self.day)
        effect = self.good_effect if action == "good" else TRUE_EFFECTS[action]
        customers = poisson(self.rng, baseline * (1 + effect))
        revenue = max(0.0, customers * AVG_BASKET + self.rng.gauss(0, BASKET_SD * math.sqrt(max(customers, 1))))

        record = HourRecord(
            step=self.step_count, day=self.day, weekday=self.weekday,
            hour=self.hour, time_label=label_time(self.hour),
            weather=self.weather, temperature_c=self.temperature_c,
            event=self.active_event["label"] if self.active_event else None,
            action=action, forecast=forecast, customers=customers,
            revenue=round(revenue, 2), is_rush_hour=baseline >= RUSH_THRESHOLD,
            expected_customers=round(baseline, 2), true_effect=effect,
            offer_is_real=effect > 0,
        )
        self.history.append(record)
        self.step_count += 1

        # 5. Events tick down, clock moves on. A surprise event is visible to everyone
        #    once it has happened, so later forecasts include it.
        if self.active_event:
            self.active_event["hours_left"] -= 1
            self.active_event["known"] = True
            if self.active_event["hours_left"] <= 0:
                self.active_event = None
        self._advance_clock()
        return record

    # ---- frontend helpers ------------------------------------------------- #

    @classmethod
    def new_game(cls, seed: Optional[int] = None, **kwargs) -> "Shop":
        """A shop that has already played its opening hour (Saturday 11:00, no offer),
        so the screen starts with a real 'customers now' number and a forecast."""
        shop = cls(seed=seed, **kwargs)
        shop.step("none")
        return shop

    def play_round(self, offer: str) -> HourRecord:
        """One button press from the screen: 'good', 'bad' or 'random'.
        'random' = no offer, but a random event hits the shop for this hour."""
        if offer == "random":
            self.trigger_event("random")
            return self.step("none")
        return self.step(offer)

    # ---- views ------------------------------------------------------------ #

    def state(self) -> dict:
        """What the screen needs: current clock, weather, last hour's customers and the forecast."""
        last = self.history[-1] if self.history else None
        return {
            "step": self.step_count,
            "day": self.day,
            "weekday": self.weekday,
            "hour": self.hour,
            "time_label": label_time(self.hour),
            "weather": self.weather,
            "temperature_c": self.temperature_c,
            "customers_now": last.customers if last else None,
            "event": self.active_event["label"] if (self.active_event and self.active_event["known"]) else None,
            "forecast": self.forecast_next_hour(),
            "total_customers": sum(r.customers for r in self.history),
            "total_revenue": round(sum(r.revenue for r in self.history), 2),
            "last": last.public() if last else None,
        }

    def public_history(self) -> List[dict]:
        return [r.public() for r in self.history]

    def full_history(self) -> List[dict]:
        return [r.full() for r in self.history]

    # ---- batch mode (for the 1,000-game evidence runs) -------------------- #

    def run(self, hours: int, policy: Optional[Callable[["Shop"], str]] = None) -> List[HourRecord]:
        """Simulate many hours. policy(shop) returns "good" | "bad" | "none" each hour."""
        out = []
        for _ in range(hours):
            out.append(self.step(policy(self) if policy else "none"))
        return out


# --------------------------------------------------------------------------- #
# Quick demo:  python simulator2.py
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    shop = Shop(seed=42)
    plan = ["none", "bad", "good", "none", "bad", "none"]
    print(f"{'when':<14}{'weather':<8}{'temp':>5}  {'action':<6}{'forecast':>9}{'actual':>8}  event")
    for action in plan:
        r = shop.step(action)
        print(f"{r.weekday[:3]} {r.time_label:<9}{r.weather:<8}{r.temperature_c:>5}  "
              f"{r.action:<6}{r.forecast:>9}{r.customers:>8}  {r.event or ''}")