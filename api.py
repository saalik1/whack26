"""
api.py - FastAPI layer over simulator2.py, agents.py and game.py.

Run:  uvicorn api:app --reload
Play: http://localhost:8000          (serves the frontend in static/)
Docs: http://localhost:8000/docs     (try every endpoint by hand)

The browser only sends the player's choice and draws what comes back.
The simulation, the two AIs and the scoring all stay in Python.

Two groups of endpoints:
  /api/start, /api/round   what the frontend uses. One game per browser (cookie),
                           so several judges can play at the same time.
  /api/new_game, /api/step, /api/event, /api/state, /api/history
                           raw simulator access for testing and for the evidence runs.
"""
import uuid
from pathlib import Path
from typing import Dict, Literal, Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.game import Game
from backend.simulator2 import EVENTS, Shop

app = FastAPI(title="Fool the AI - shop simulator")

# --------------------------------------------------------------------------- #
# Frontend endpoints: one Game per browser, kept in memory (fine for a hackathon)
# --------------------------------------------------------------------------- #

SESSIONS: Dict[str, Game] = {}
MAX_SESSIONS = 500
COOKIE = "shop_session"


def new_session(response: Response) -> Game:
    while len(SESSIONS) >= MAX_SESSIONS:          # forget the oldest player
        SESSIONS.pop(next(iter(SESSIONS)))
    sid = uuid.uuid4().hex
    SESSIONS[sid] = Game()
    response.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=6 * 3600)
    return SESSIONS[sid]


class RoundRequest(BaseModel):
    offer: Literal["good", "bad", "random"]
    state: Optional[dict] = None     # the frontend's own copy; the server does not trust it


@app.post("/api/start")
def start(response: Response):
    """Called when the page loads: a fresh shop and the numbers for the first screen."""
    return new_session(response).start_payload()


@app.post("/api/round")
def play_round(body: RoundRequest, request: Request, response: Response):
    """One button press: good, bad or random. Simulates the next hour and judges it."""
    game = SESSIONS.get(request.cookies.get(COOKIE, ""))
    just_started = (body.state or {}).get("round") == 0
    if game is None or (just_started and game.rounds > 0):   # no game yet, or page was reloaded
        game = new_session(response)
    return game.play(body.offer)


# --------------------------------------------------------------------------- #
# Raw simulator endpoints (no AI verdicts)
# --------------------------------------------------------------------------- #

GAMES: Dict[str, Shop] = {}


class NewGame(BaseModel):
    game_id: str = "demo"
    seed: Optional[int] = None


class StepRequest(BaseModel):
    game_id: str = "demo"
    action: Literal["good", "bad", "none"] = "none"
    event: Optional[str] = None      # "random", an event key, or null


class EventRequest(BaseModel):
    game_id: str = "demo"
    event: str = "random"


def get_game(game_id: str) -> Shop:
    if game_id not in GAMES:
        raise HTTPException(404, f"No game {game_id!r}. Call POST /api/new_game first.")
    return GAMES[game_id]


@app.post("/api/new_game")
def new_game(body: NewGame = NewGame()):
    GAMES[body.game_id] = Shop(seed=body.seed)
    return GAMES[body.game_id].state()


@app.get("/api/state")
def state(game_id: str = "demo"):
    return get_game(game_id).state()


@app.post("/api/event")
def event(body: EventRequest):
    shop = get_game(body.game_id)
    try:
        shop.trigger_event(body.event)
    except ValueError as err:
        raise HTTPException(400, str(err))
    return shop.state()


@app.post("/api/step")
def step(body: StepRequest):
    """Simulate ONE hour with the player's choice: good, bad or none."""
    shop = get_game(body.game_id)
    try:
        record = shop.step(body.action, body.event)
    except ValueError as err:
        raise HTTPException(400, str(err))
    return {"record": record.public(), "state": shop.state()}


@app.get("/api/history")
def history(game_id: str = "demo"):
    return get_game(game_id).public_history()


@app.get("/api/events")
def list_events():
    return {key: spec["label"] for key, spec in EVENTS.items()}


# --------------------------------------------------------------------------- #
# Serve the shop screen (static/index.html). Must stay LAST so it never hides /api.
# --------------------------------------------------------------------------- #

STATIC = Path(__file__).parent / "frontend"
if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
