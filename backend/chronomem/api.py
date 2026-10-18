"""REST API for the ChronoMem dashboard (same engine the MCP tools use)."""
import os
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import agent, db
from .memory import Memory

app = FastAPI(title="ChronoMem", version="0.1.0")


@app.middleware("http")
async def errors_as_json(request, call_next):
    # Registered before CORS so error responses still carry CORS headers.
    try:
        return await call_next(request)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"detail": f"{type(e).__name__}: {e}"}, status_code=500)


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


class RememberIn(BaseModel):
    subject: str
    predicate: str
    object: str
    kind: Literal["identity", "preference", "goal", "state"] = "preference"
    source: str = ""
    single_valued: bool = True
    mode: Literal["ask", "replace"] = "ask"
    asserted_by: str = "user"


class ResolveIn(BaseModel):
    fact_id: str
    keep: Literal["new", "old", "both"]


class DecisionIn(BaseModel):
    decision: str
    based_on: list[str]
    reason: str = ""
    alternatives: str = ""
    asserted_by: str = "assistant"


class DecisionActionIn(BaseModel):
    decision_id: str
    action: Literal["reaffirm", "revise", "drop"]


class ChatIn(BaseModel):
    messages: list[dict]


def mem(user: str) -> Memory:
    try:
        return Memory(user)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/health")
def health():
    db.client().list_graphs()
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"chat_enabled": agent.enabled(), "model": agent.MODEL if agent.enabled() else None}


@app.post("/api/{user}/chat")
def chat(user: str, body: ChatIn):
    if not agent.enabled():
        raise HTTPException(400, "Set LLM_API_KEY to enable the built-in chat agent")
    try:
        return agent.chat(user, body.messages)
    except Exception as e:
        raise HTTPException(502, f"LLM error: {e}")


@app.post("/api/seed/{scenario}")
def seed_demo(scenario: str):
    from .seed import seed
    try:
        return seed(scenario)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/users")
def users():
    return {"users": db.list_users()}


@app.delete("/api/users/{user}")
def delete_user(user: str):
    db.delete_user(user)
    return {"deleted": user}


@app.post("/api/{user}/session")
def begin_session(user: str):
    return mem(user).begin_session()


@app.post("/api/{user}/remember")
def remember(user: str, body: RememberIn):
    try:
        return mem(user).remember(body.subject, body.predicate, body.object, kind=body.kind,
                                  source=body.source, single_valued=body.single_valued,
                                  mode=body.mode, asserted_by=body.asserted_by)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/{user}/recall")
def recall(user: str, q: str = "", as_of: int | None = None, limit: int = 15):
    return mem(user).recall(q, as_of=as_of, limit=limit)


@app.post("/api/{user}/resolve")
def resolve(user: str, body: ResolveIn):
    return mem(user).resolve(body.fact_id, body.keep)


@app.post("/api/{user}/forget/{fact_id}")
def forget(user: str, fact_id: str):
    return mem(user).forget(fact_id)


@app.get("/api/{user}/why")
def why(user: str, topic: str):
    return mem(user).why_changed(topic)


@app.get("/api/{user}/contradictions")
def contradictions(user: str):
    return mem(user).contradictions()


@app.get("/api/{user}/profile")
def profile(user: str):
    return mem(user).core_profile()


@app.post("/api/{user}/sweep")
def sweep(user: str):
    return mem(user).sweep()


@app.get("/api/{user}/graph")
def snapshot(user: str, as_of: int | None = None):
    return mem(user).snapshot(as_of)


@app.post("/api/{user}/decisions")
def record_decision(user: str, body: DecisionIn):
    return mem(user).record_decision(body.decision, body.based_on, body.reason, body.alternatives, body.asserted_by)


@app.get("/api/{user}/decisions")
def decisions(user: str):
    return mem(user).decisions()


@app.get("/api/{user}/decisions/stale")
def stale(user: str):
    return mem(user).stale_decisions()


@app.post("/api/{user}/decisions/resolve")
def resolve_decision(user: str, body: DecisionActionIn):
    return mem(user).resolve_decision(body.decision_id, body.action)


@app.get("/api/{user}/stats")
def stats(user: str):
    return mem(user).stats()


def run():
    uvicorn.run("chronomem.api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=False)


if __name__ == "__main__":
    run()
