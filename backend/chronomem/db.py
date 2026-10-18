"""FalkorDB connection + one isolated graph per user/tenant (multigraph)."""
import os
from functools import lru_cache

from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

GRAPH_PREFIX = "mem_"

INDEXES = [
    "CREATE INDEX FOR (e:Entity) ON (e.name_n)",
    "CREATE INDEX FOR (f:Fact) ON (f.key)",
    "CREATE INDEX FOR (f:Fact) ON (f.id)",
    "CREATE INDEX FOR (f:Fact) ON (f.status)",
    "CREATE INDEX FOR (m:Message) ON (m.id)",
    "CREATE INDEX FOR (s:Session) ON (s.no)",
]


@lru_cache
def client() -> FalkorDB:
    return FalkorDB(
        host=os.getenv("FALKORDB_HOST", "localhost"),
        port=int(os.getenv("FALKORDB_PORT", "6379")),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
    )


_ready: set[str] = set()


def graph(user_id: str):
    """Return the isolated graph for a user/tenant, creating indexes on first use."""
    name = GRAPH_PREFIX + safe_id(user_id)
    g = client().select_graph(name)
    if name not in _ready:
        for q in INDEXES:
            try:
                g.query(q)
            except Exception:
                pass  # index already exists
        _ready.add(name)
    return g


def list_users() -> list[str]:
    return sorted(n[len(GRAPH_PREFIX):] for n in client().list_graphs() if n.startswith(GRAPH_PREFIX))


def delete_user(user_id: str) -> None:
    name = GRAPH_PREFIX + safe_id(user_id)
    try:
        client().select_graph(name).delete()
    except Exception:
        pass
    _ready.discard(name)


def safe_id(user_id: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id.strip().lower())
    if not cleaned:
        raise ValueError("user_id required")
    return cleaned
