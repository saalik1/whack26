"""api.py: the server the game screen talks to."""
import pytest
from fastapi.testclient import TestClient

from api import app


@pytest.fixture
def client():
    return TestClient(app)


def test_start_then_rounds_share_one_game(client):
    assert client.post("/api/start").status_code == 200
    for i, offer in enumerate(["bad", "good", "random"], start=1):
        r = client.post("/api/round", json={"offer": offer})
        assert r.status_code == 200
        assert r.json()["scores"]["rounds"] == i


def test_round_without_start_creates_a_game(client):
    r = client.post("/api/round", json={"offer": "good"})
    assert r.status_code == 200 and r.json()["scores"]["rounds"] == 1


def test_fast_forward_through_the_api(client):
    client.post("/api/start")
    r = client.post("/api/round", json={"offer": "good", "hours": 12})
    assert r.status_code == 200
    assert r.json()["careful"]["hours"] == 12


def test_invalid_offer_rejected(client):
    assert client.post("/api/round", json={"offer": "bribe"}).status_code == 422


def test_round_response_shape(client):
    client.post("/api/start")
    body = client.post("/api/round", json={"offer": "bad"}).json()
    for key in ("customers", "nextPrediction", "weather", "careful", "naive", "scores"):
        assert key in body
    assert body["careful"]["verdict"] in {"REAL", "FAKE", "NOT SURE YET", "NO OFFER"}


def test_raw_simulator_endpoints_hide_the_truth(client):
    assert client.post("/api/new_game", json={"game_id": "t", "seed": 1}).status_code == 200
    rec = client.post("/api/step", json={"game_id": "t", "action": "bad"}).json()["record"]
    assert not {"true_effect", "offer_is_real", "expected_customers"} & set(rec)
    assert len(client.get("/api/history", params={"game_id": "t"}).json()) == 1


def test_unknown_raw_game_is_404(client):
    assert client.get("/api/state", params={"game_id": "nope"}).status_code == 404


def test_events_listed(client):
    assert "tourist_bus" in client.get("/api/events").json()


@pytest.mark.parametrize("page", ["/", "/game.html", "/evidence.html", "/evidence.png",
                                  "/evidence_game.png", "/app.js", "/api.js"])
def test_frontend_pages_served(client, page):
    assert client.get(page).status_code == 200
