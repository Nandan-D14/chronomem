"""ChronoMem MCP server: plug time-aware graph memory into any MCP agent
(Claude Desktop, Cursor, Cortex Code, ...). The host agent's own LLM extracts facts;
ChronoMem stores them in FalkorDB, detects contradictions, decays, and explains.
"""
import json
import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

from .memory import Memory

DEFAULT_USER = os.getenv("CHRONOMEM_USER", "default")

mcp = FastMCP(
    "chronomem",
    instructions=(
        "ChronoMem is your long-term memory, stored as a temporal knowledge graph.\n"
        "- At the start of a conversation call begin_session, then recall('') to load what you know.\n"
        "- Whenever the user reveals a durable fact about themselves or their world, call remember with "
        "a short subject/predicate/object triple, the right kind (identity|preference|goal|state), and "
        "their exact words as source. Use subject 'user' for the human.\n"
        "- If remember returns status 'contradiction', ASK the user the 'ask_user' question, then call "
        "resolve. Never silently overwrite.\n"
        "- If the user explicitly says something changed ('I moved to Berlin'), use mode='replace'.\n"
        "- Before answering personal questions call recall. For 'when/why did X change' call why_changed.\n"
        "- When you use a memory, cite its source quote."
    ),
)


def _out(result: dict, include_trace: bool) -> str:
    if not include_trace:
        result = {k: v for k, v in result.items() if k != "trace"}
    return json.dumps(result, default=str)


@mcp.tool()
def begin_session(user_id: str = DEFAULT_USER) -> str:
    """Start a new conversation session. Decay is measured in sessions, so call this once per conversation."""
    return _out(Memory(user_id).begin_session(), False)


@mcp.tool()
def remember(subject: str, predicate: str, object: str,
             kind: Literal["identity", "preference", "goal", "state"] = "preference",
             source: str = "", single_valued: bool = True,
             mode: Literal["ask", "replace"] = "ask",
             asserted_by: str = "assistant", user_id: str = DEFAULT_USER) -> str:
    """Store a fact as a graph triple with provenance.

    kind: identity (never fades: name, job, diet), preference (slow), goal (days), state (mood; next session).
    single_valued: True if a subject can only have one value for this predicate (city, diet, employer).
    mode: 'ask' flags conflicts as contradictions to confirm; 'replace' supersedes immediately.
    source: the user's exact words this fact came from.
    """
    return _out(Memory(user_id).remember(subject, predicate, object, kind=kind, source=source,
                                         single_valued=single_valued, mode=mode,
                                         asserted_by=asserted_by), False)


@mcp.tool()
def recall(query: str = "", as_of: int | None = None, show_trace: bool = False,
           user_id: str = DEFAULT_USER) -> str:
    """Multi-hop recall from the memory graph. Empty query returns everything currently believed.
    as_of: epoch ms to see what was believed at that time. show_trace returns the Cypher used."""
    return _out(Memory(user_id).recall(query, as_of=as_of), show_trace)


@mcp.tool()
def resolve(fact_id: str, keep: Literal["new", "old", "both"], user_id: str = DEFAULT_USER) -> str:
    """Resolve a pending contradiction after asking the user."""
    return _out(Memory(user_id).resolve(fact_id, keep), False)


@mcp.tool()
def why_changed(topic: str, user_id: str = DEFAULT_USER) -> str:
    """Version history of facts about a topic: old values, what replaced them, when, and source quotes."""
    return _out(Memory(user_id).why_changed(topic), False)


@mcp.tool()
def contradictions(user_id: str = DEFAULT_USER) -> str:
    """List pending contradictions that still need the user's confirmation."""
    return json.dumps(Memory(user_id).contradictions(), default=str)


@mcp.tool()
def core_profile(user_id: str = DEFAULT_USER) -> str:
    """PageRank over the user's entity graph: the people, places and things that matter most to them."""
    return _out(Memory(user_id).core_profile(), False)


@mcp.tool()
def forget(fact_id: str, user_id: str = DEFAULT_USER) -> str:
    """Forget a fact when the user asks you to."""
    return _out(Memory(user_id).forget(fact_id), False)


def run():
    mcp.run()


if __name__ == "__main__":
    run()
