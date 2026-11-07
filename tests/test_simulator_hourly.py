"""backend/simulator2.py: the hourly shop behind the live game."""
import pytest

from backend.simulator2 import OPEN_HOURS, Shop, TRUE_EFFECTS

HIDDEN = {"expected_customers", "true_effect", "offer_is_real"}


def test_public_record_hides_the_truth():
    rec = Shop(seed=1).step("good").public()
    assert not HIDDEN & set(rec)
    for key in ("weekday", "hour", "weather", "temperature_c", "action", "customers", "forecast"):
        assert key in rec


def test_full_record_keeps_the_truth_for_scoring():
    assert HIDDEN <= set(Shop(seed=1).step("bad").full())


def test_same_seed_same_hours():
    a = [r.customers for r in Shop(seed=9).run(50)]
    b = [r.customers for r in Shop(seed=9).run(50)]
    assert a == b


def test_bad_offer_does_nothing_good_offer_helps():
    shop = Shop(seed=2, good_effect=0.08)
    assert shop.step("bad").true_effect == TRUE_EFFECTS["bad"] == 0
    assert shop.step("good").true_effect == 0.08


def test_invalid_action_rejected():
    with pytest.raises(ValueError):
        Shop(seed=1).step("bribe")


def test_unknown_event_rejected():
    with pytest.raises(ValueError):
        Shop(seed=1).trigger_event("meteor")


def test_clock_stays_in_opening_hours_and_days_roll_over():
    shop = Shop(seed=3)
    records = shop.run(len(OPEN_HOURS) * 3)
    assert all(r.hour in OPEN_HOURS for r in records)
    assert records[-1].day >= 2


def test_rush_hours_are_busier():
    recs = Shop(seed=4).run(12 * 28)
    rush = [r.customers for r in recs if r.is_rush_hour]
    quiet = [r.customers for r in recs if not r.is_rush_hour]
    assert sum(rush) / len(rush) > 1.4 * sum(quiet) / len(quiet)


def test_new_game_starts_with_one_opening_hour():
    shop = Shop.new_game(seed=5)
    assert len(shop.history) == 1 and shop.history[0].action == "none"
