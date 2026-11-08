"""
api.py - FastAPI layer over simulator2.py, agents.py and game.py.

Run:  uvicorn api:app --reload
Play: http://localhost:8000          (serves the frontend in static/)
Docs: http://localhost:8000/docs     (try every endpoint by hand)

The browser only sends the player's choice and draws what comes back.
The simulation, the two AIs and the scoring all stay in Python.

The game runs on a clock the BROWSER drives: it calls /api/tick once per shop hour (every
2 seconds on Play, every 1 second on Double Play, never on Pause; see SECONDS_PER_HOUR in
backend/game.py). Everything else happens in Python.

Two groups of endpoints:
  /api/start, /api/tick, /api/offer, /api/trigger_event, /api/call_friends, /api/dismiss
                           what the frontend uses. One game per browser (cookie),
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


class OfferRequest(BaseModel):
    kind: Literal["good", "bad"]


class TriggerEventRequest(BaseModel):
    event: str = "random"            # "random" or an event key (see GET /api/events)


def current_game(request: Request) -> Game:
    game = SESSIONS.get(request.cookies.get(COOKIE, ""))
    if game is None:
        raise HTTPException(404, "No game for this browser. Reload the page to start a new one.")
    return game


@app.post("/api/start")
def start(response: Response):
    """Called when the page loads: a fresh shop and the numbers for the first screen
    (including config: the clock speeds, the offer lock and the list of events)."""
    return new_session(response).start_payload()


@app.post("/api/tick")
def tick(request: Request):
    """ONE shop hour passes. The browser calls this on a timer while the game is playing.
    Refused (ok=false) while a pop-up is open: the game is paused until it is dismissed."""
    return current_game(request).tick()


@app.post("/api/offer")
def launch_offer(body: OfferRequest, request: Request):
    """Start a good or bad offer. It then runs for a full day and locks until tomorrow, same time."""
    return current_game(request).launch_offer(body.kind)


@app.post("/api/call_friends")
def call_friends(request: Request):
    """Roll a die; that many friends visit during the next hour (once per shop day)."""
    return current_game(request).call_friends()


@app.post("/api/trigger_event")
def trigger_event(body: TriggerEventRequest, request: Request):
    """Add an event (or "random"). It changes sales from the next hour on."""
    return current_game(request).trigger_event(body.event)


@app.post("/api/dismiss")
def dismiss(request: Request):
    """Close the pop-up that is open. The game carries on once there are none left."""
    return current_game(request).dismiss_popup()


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