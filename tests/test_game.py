"""backend/game.py: the live game loop the screen drives (offers lock for two shop days)."""
from backend.evidence_game import play
from backend.game import OFFER_LOCK_DAYS, OFFER_LOCK_HOURS, PAST_HOURS, Game
from backend.simulator2 import WEEKDAYS


def finish_offer(g):
    for _ in range(OFFER_LOCK_HOURS * 3):
        for pop in list(g.popups):
            if pop["type"] == "verdict":
                return pop
            g.dismiss_popup()
        g.tick()
    raise AssertionError("no verdict")


def test_offer_runs_two_shop_days():
    assert OFFER_LOCK_DAYS == 2 and OFFER_LOCK_HOURS == 24


def test_start_payload():
    p = Game(seed=1).start_payload()
    assert p["ok"] and "config" in p and "scores" in p


def test_game_starts_with_six_months_of_history():
    g = Game(seed=2)
    assert len(g.shop.history) == PAST_HOURS + 1 and g.careful.model is not None


def test_offer_locks_until_two_days_later():
    g = Game(seed=3)
    day = g.shop.weekday_idx
    out = g.launch_offer("bad")
    assert out["ok"]
    assert g.offer["unlocksAt"].startswith(WEEKDAYS[(day + OFFER_LOCK_DAYS) % 7])
    second = g.launch_offer("good")
    assert not second["ok"] and "already running" in second["error"]


def test_verdict_arrives_and_time_pauses_for_popups():
    g = Game(seed=4)
    g.launch_offer("good")
    pop = finish_offer(g)
    assert {"careful", "naive", "offer", "scores"} <= set(pop)
    assert not g.tick()["ok"]                     # paused while the pop-up is open
    g.dismiss_popup()
    assert g.scores["offersJudged"] == 1


def test_call_friends_once_per_day():
    g = Game(seed=5)
    assert g.call_friends()["ok"]
    assert not g.call_friends()["ok"]


def test_invalid_offer_rejected():
    assert not Game(seed=6).launch_offer("bribe")["ok"]


def test_cheater_fools_naive_not_ours():
    rows = [r for s in range(8) for r in play(140000 + s, 0.20, "cheater", offers=8)]
    bad = [r for r in rows if r["kind"] == "bad"]
    assert sum(r["ours"] for r in bad) <= 1
    assert sum(r["naive"] for r in bad) > sum(r["ours"] for r in bad)


def test_switcher_cannot_train_our_ai_into_a_mistake():
    rows = [r for s in range(8) for r in play(141000 + s, 0.20, "switcher", offers=8)]
    late_bad = [r for r in rows if r["kind"] == "bad" and r["offer"] >= 4]
    assert sum(r["ours"] for r in late_bad) <= 1


def test_good_offers_mostly_found():
    rows = [r for s in range(8) for r in play(142000 + s, 0.20, "random", offers=8)]
    good = [r for r in rows if r["kind"] == "good"]
    assert sum(r["ours"] for r in good) / len(good) >= 0.75
