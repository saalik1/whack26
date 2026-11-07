"""
api.py - FastAPI layer over simulator2.py.

Run:  uvicorn api:app --reload      then open http://localhost:8000/docs

The browser only sends the player's choice for the next hour and draws what comes back.
All the simulation (and later the AI agents) stay in Python.
"""
from pathlib import Path
from typing import Dict, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from simulator2 import EVENTS, Shop

app = FastAPI(title="Fool the AI - shop simulator")

GAMES: Dict[str, Shop] = {}   # in-memory games, fine for a hackathon


class NewGame(BaseModel):
    game_id: str = "demo"
    seed: Optional[int] = None


class StepRequest(BaseModel):
    game_id: str = "demo"
    action: Literal["good", "bad", "none"] = "none"
    # "random", one of the event keys, or null for no event
    event: Optional[str] = None


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


# Serve the shop screen once static/index.html exists.
STATIC = Path(__file__).parent / "static"
if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")