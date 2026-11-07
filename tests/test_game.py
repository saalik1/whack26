"""backend/game.py: one player's game, as the screen uses it."""
from backend.game import PAST_HOURS, Game
from backend.simulator2 import RUSH_THRESHOLD

CONTRACT = {"customers", "weather", "temperature", "time", "event", "offer", "expected",
            "careful", "naive", "scores", "nextPrediction", "nextIsRush"}


def test_start_payload():
    p = Game(seed=1).start_payload()
    assert {"customers", "weather", "time", "scores", "nextPrediction", "nextIsRush"} <= set(p)
    assert p["scores"] == {"rounds": 0, "carefulFooled": 0, "naiveFooled": 0}


def test_game_starts_with_8_weeks_of_history():
    g = Game(seed=2)
    assert len(g.shop.history) == PAST_HOURS + 1
    assert g.careful.model is not None


def test_play_returns_what_the_screen_needs():
    out = Game(seed=3).play("good")
    assert CONTRACT <= set(out)
    assert {"verdict", "label", "text", "fooled"} <= set(out["careful"])
    assert {"verdict", "label", "text", "tag", "fooled"} <= set(out["naive"])


def test_scores_count_rounds_and_fools():
    g = Game(seed=4)
    for offer in ("bad", "good", "random"):
        out = g.play(offer)
    assert out["scores"]["rounds"] == 3


def test_fast_forward_runs_many_hours_but_is_capped():
    g = Game(seed=5)
    before = len(g.shop.history)
    g.play("good", hours=12)
    assert len(g.shop.history) == before + 12
    before = len(g.shop.history)
    g.play("bad", hours=10_000)
    assert len(g.shop.history) == before + 84


def test_rush_hour_cheat_fools_naive_not_careful():
    naive_games = careful_games = 0
    for seed in range(20):
        g = Game(seed=90000 + seed)
        n = c = False
        for _ in range(40):
            rush = g.shop.forecast_next_hour()["expected"] >= RUSH_THRESHOLD
            out = g.play("bad" if rush else "good")
            if out["offer"] == "bad":
                n |= out["naive"]["fooled"]
                c |= out["careful"]["fooled"]
        naive_games += n
        careful_games += c
    assert naive_games >= 18
    assert careful_games <= 1


def test_good_offer_eventually_confirmed_with_fast_forward():
    confirmed = 0
    for seed in range(20):
        g = Game(seed=91000 + seed)
        for _ in range(8):                       # up to 96 hours of the good offer
            if g.play("good", hours=12)["careful"]["verdict"] == "REAL":
                confirmed += 1
                break
    assert confirmed >= 16
