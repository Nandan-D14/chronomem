"""End-to-end smoke test against a live FalkorDB: run with `uv run python tests/smoke.py`."""
import json

from chronomem.db import delete_user
from chronomem.memory import Memory

U = "smoke_test"
delete_user(U)
m = Memory(U)

def show(label, r):
    r = {k: v for k, v in r.items() if k != "trace"}
    print(f"\n== {label}\n" + json.dumps(r, indent=1, default=str)[:900])

show("store diet", m.remember("I", "diet", "vegetarian", kind="identity", source="I'm vegetarian"))
show("store job", m.remember("I", "works at", "Acme", kind="identity", source="I work at Acme"))
show("acme city", m.remember("Acme", "located in", "Berlin", kind="identity", source="Acme is in Berlin"))
show("dup -> reinforce", m.remember("user", "diet", "Vegetarian", kind="identity", source="still veg"))
show("contradiction", r := m.remember("I", "diet", "eats steak", kind="identity", source="I just had a great steak"))
show("pending", m.contradictions())
show("resolve new", m.resolve(r["fact_id"], "new"))
show("why diet", m.why_changed("diet"))
show("multi-hop recall 'work'", m.recall("where do I work"))
show("pagerank", m.core_profile())
show("mood", m.remember("I", "mood", "tired", kind="state", source="I'm so tired today"))
for _ in range(4):
    m.begin_session()
show("after 4 sessions recall mood (should decay)", m.recall("mood"))
show("snapshot", {"n": len(m.snapshot()["nodes"]), "links": len(m.snapshot()["links"])})
show("stats", m.stats())
print("\nTRACE SAMPLE:", r["trace"][-1])
delete_user(U)
print("\nOK")
