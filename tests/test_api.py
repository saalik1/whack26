"""api.py: the server the game screen talks to."""
import pytest
from fastapi.testclient import TestClient

from api import app


@pytest.fixture
def client():
    c = TestClient(app)
    assert c.post("/api/start").status_code == 200
    return c


def test_offer_then_ticks_until_verdict(client):
    assert client.post("/api/offer", json={"kind": "bad"}).json()["ok"]
    verdict = None
    for _ in range(80):
        body = client.post("/api/tick").json()
        pops = body.get("popups") or []
        verdict = next((p for p in pops if p.get("type") == "verdict"), None)
        if verdict:
            break
        if pops:
            client.post("/api/dismiss")
    assert verdict and verdict["careful"]["verdict"] in {"REAL", "FAKE"}


def test_invalid_offer_rejected(client):
    assert client.post("/api/offer", json={"kind": "bribe"}).status_code == 422


def test_actions_respond(client):
    assert client.post("/api/call_friends").status_code == 200
    assert client.post("/api/trigger_event", json={"event": "random"}).status_code == 200
    assert client.post("/api/dismiss").status_code == 200


def test_raw_simulator_endpoints_hide_the_truth(client):
    assert client.post("/api/new_game", json={"game_id": "t", "seed": 1}).status_code == 200
    rec = client.post("/api/step", json={"game_id": "t", "action": "bad"}).json()["record"]
    assert not {"true_effect", "offer_is_real", "expected_customers", "friends"} & set(rec)


def test_unknown_raw_game_is_404(client):
    assert client.get("/api/state", params={"game_id": "nope"}).status_code == 404


def test_events_listed(client):
    assert "leicester_win" in client.get("/api/events").json()


@pytest.mark.parametrize("page", ["/", "/game.html", "/evidence.html", "/evidence.png",
                                  "/evidence_game.png", "/app.js", "/api.js", "/doodle.css"])
def test_frontend_pages_served(client, page):
    assert client.get(page).status_code == 200
