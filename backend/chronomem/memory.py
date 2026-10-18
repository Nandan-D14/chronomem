"""ChronoMem memory engine.

Every fact is a node with a validity window, a source message, a decay class and a
version chain. Contradictions are surfaced (never silently overwritten), and every
call returns a `trace` with the Cypher it ran so answers are explainable.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from .db import graph

# Decay is measured in *sessions*, not wall-clock time, so memory doesn't rot while
# the user is on vacation. None = never decays.
HALF_LIFE_SESSIONS: dict[str, float | None] = {
    "identity": None,   # name, job, allergies, diet...
    "preference": 30,   # likes, tools, style
    "goal": 5,          # this week's plans, current tasks
    "state": 1,         # mood, what they're doing right now
}
FORGET_BELOW = 0.15     # hidden from recall
ARCHIVE_BELOW = 0.05    # archived by sweep
SESSION_GAP_MS = 30 * 60 * 1000

SELF_WORDS = {"i", "me", "my", "myself", "user", "the user"}
STOP = {"the", "and", "for", "what", "who", "when", "why", "how", "does", "did", "was", "are",
        "is", "my", "me", "you", "your", "about", "with", "that", "this", "have", "has", "do"}


def now_ms() -> int:
    return int(time.time() * 1000)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def norm_subject(s: str) -> str:
    n = norm(s)
    return "user" if n in SELF_WORDS else n


def norm_pred(p: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", norm(p)).strip("_")


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", norm(text)) if len(t) > 2 and t not in STOP]


class Trace:
    """Collects every Cypher query a memory operation ran."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def add(self, label: str, cypher: str, params: dict | None = None) -> None:
        clean = {k: v for k, v in (params or {}).items() if k not in ("text",)}
        self.steps.append({"step": label, "cypher": " ".join(cypher.split()), "params": clean})


def strength(fact: dict, current_session: int) -> float:
    hl = HALF_LIFE_SESSIONS.get(fact.get("kind", "preference"))
    if hl is None:
        return 1.0
    age = max(0, current_session - int(fact.get("last_session", current_session)))
    # Each reinforcement (hit) slows decay a little.
    hl = hl * (1 + 0.25 * (int(fact.get("hits", 1)) - 1))
    return round(0.5 ** (age / hl), 3)


def props(node) -> dict:
    return dict(node.properties) if node is not None else {}


class Memory:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.g = graph(user_id)

    # ------------------------------------------------------------------ helpers
    def _q(self, trace: Trace | None, label: str, cypher: str, params: dict | None = None):
        if trace is not None:
            trace.add(label, cypher, params)
        return self.g.query(cypher, params or {}).result_set

    def _session(self, trace: Trace | None = None, force_new: bool = False, ts: int | None = None) -> int:
        """Current session number; opens a new one after inactivity or when forced."""
        t = ts or now_ms()
        rows = self._q(None, "", "MATCH (u:User {id:$uid}) RETURN u.session_no, u.last_active", {"uid": self.user_id})
        if not rows:
            self._q(trace, "create user", """
                CREATE (u:User {id:$uid, session_no:1, last_active:$t})
                CREATE (:Session {no:1, started_at:$t})-[:OF]->(u)
                MERGE (e:Entity {name_n:'user'}) ON CREATE SET e.name=$uid, e.type='person'
            """, {"uid": self.user_id, "t": t})
            return 1
        no, last = rows[0]
        if force_new or t - (last or 0) > SESSION_GAP_MS:
            no = (no or 0) + 1
            self._q(trace, "open session", """
                MATCH (u:User {id:$uid})
                SET u.session_no=$no, u.last_active=$t
                CREATE (:Session {no:$no, started_at:$t})-[:OF]->(u)
            """, {"uid": self.user_id, "no": no, "t": t})
        else:
            self._q(None, "", "MATCH (u:User {id:$uid}) SET u.last_active=$t", {"uid": self.user_id, "t": t})
        return int(no)

    def begin_session(self) -> dict:
        trace = Trace()
        no = self._session(trace, force_new=True)
        return {"session": no, "trace": trace.steps}

    def _message(self, trace: Trace, text: str, session: int, ts: int, role: str = "user") -> str:
        mid = uuid.uuid4().hex[:12]
        self._q(trace, "store source message", """
            MATCH (s:Session {no:$sess})
            CREATE (m:Message {id:$mid, text:$text, ts:$ts, role:$role, session:$sess})-[:IN]->(s)
        """, {"mid": mid, "text": text, "ts": ts, "role": role, "sess": session})
        return mid

    # ------------------------------------------------------------------ write
    def remember(self, subject: str, predicate: str, obj: str, kind: str = "preference",
                 source: str = "", single_valued: bool = True, mode: str = "ask",
                 asserted_by: str = "user", confidence: float = 0.9, ts: int | None = None) -> dict:
        """Store a fact.

        mode="ask"     -> conflicting single-valued fact becomes a pending contradiction
        mode="replace" -> conflicting fact is superseded immediately (user stated a change)
        """
        if kind not in HALF_LIFE_SESSIONS:
            kind = "preference"
        trace = Trace()
        t = ts or now_ms()
        sess = self._session(trace, ts=t)
        s_n, p_n, o_n = norm_subject(subject), norm_pred(predicate), norm(obj)
        if not (s_n and p_n and o_n):
            raise ValueError("subject, predicate and object are required")
        key = f"{s_n}|{p_n}"
        mid = self._message(trace, source or f"{subject} {predicate} {obj}", sess, t)

        existing = self._q(trace, "find active facts with same subject+predicate", """
            MATCH (f:Fact {key:$key}) WHERE f.status = 'active' RETURN f
        """, {"key": key})
        existing = [props(r[0]) for r in existing]

        same = next((f for f in existing if f["object_n"] == o_n), None)
        if same:
            self._q(trace, "reinforce duplicate (no bloat)", """
                MATCH (f:Fact {id:$id}), (m:Message {id:$mid})
                SET f.last_session=$sess, f.hits=f.hits+1, f.confidence=CASE WHEN f.confidence < 0.99 THEN f.confidence + 0.05 ELSE f.confidence END
                CREATE (f)-[:SOURCED_FROM]->(m)
            """, {"id": same["id"], "mid": mid, "sess": sess})
            return {"status": "reinforced", "fact_id": same["id"], "trace": trace.steps}

        conflicts = [f for f in existing if single_valued and f.get("single_valued", True)]
        status = "pending" if conflicts and mode == "ask" else "active"
        fid = uuid.uuid4().hex[:12]
        self._create_fact(trace, fid, key, subject, s_n, predicate, p_n, obj, o_n, kind,
                          single_valued, status, t, sess, mid, asserted_by, confidence)

        if not conflicts:
            return {"status": "stored", "fact_id": fid, "trace": trace.steps}

        if mode == "replace":
            for old in conflicts:
                self._supersede(trace, fid, old["id"], t)
            return {"status": "superseded", "fact_id": fid,
                    "replaced": [self._fact_view(o) for o in conflicts], "trace": trace.steps}

        for old in conflicts:
            self._q(trace, "flag contradiction", """
                MATCH (n:Fact {id:$new}), (o:Fact {id:$old})
                CREATE (n)-[:CONTRADICTS {status:'pending', ts:$t}]->(o)
            """, {"new": fid, "old": old["id"], "t": t})
        old = conflicts[0]
        old_s = "you" if old["subject_n"] == "user" else old["subject"]
        new_s = "you" if s_n == "user" else subject
        return {
            "status": "contradiction",
            "fact_id": fid,
            "new": f"{new_s} {predicate} {obj}",
            "conflicts_with": [self._fact_view(o) for o in conflicts],
            "ask_user": f"Earlier: '{old_s} {old['predicate']} {old['object']}'. Now: '{new_s} {predicate} {obj}'. "
                        f"Which is true — the new one, the old one, or both?",
            "resolve_with": f"resolve(fact_id='{fid}', keep='new'|'old'|'both')",
            "trace": trace.steps,
        }

    def _create_fact(self, trace, fid, key, s, s_n, p, p_n, o, o_n, kind, single_valued, status,
                     t, sess, mid, by, conf):
        self._q(trace, "create fact + entities + provenance", """
            MERGE (s:Entity {name_n:$s_n}) ON CREATE SET s.name=$s, s.type='thing'
            MERGE (o:Entity {name_n:$o_n}) ON CREATE SET o.name=$o, o.type='thing'
            CREATE (f:Fact {id:$id, key:$key, subject:$s, subject_n:$s_n, predicate:$p, predicate_n:$p_n,
                            object:$o, object_n:$o_n, kind:$kind, single_valued:$sv, status:$status,
                            valid_from:$t, created_session:$sess, last_session:$sess, hits:1,
                            confidence:$conf, asserted_by:$by})
            CREATE (s)-[:HAS_FACT]->(f)-[:ABOUT]->(o)
            WITH s, o, f
            MATCH (m:Message {id:$mid})
            CREATE (f)-[:SOURCED_FROM]->(m)
            MERGE (a:Agent {name:$by})
            CREATE (a)-[:ASSERTED {ts:$t}]->(f)
        """, {"id": fid, "key": key, "s": s if s_n != "user" else self.user_id, "s_n": s_n, "p": p,
              "p_n": p_n, "o": o, "o_n": o_n, "kind": kind, "sv": single_valued, "status": status,
              "t": t, "sess": sess, "conf": conf, "by": by, "mid": mid})
        if status == "active":
            self._link(trace, s_n, p_n, o_n)

    def _link(self, trace, s_n, p_n, o_n):
        self._q(trace, "link entities for graph algorithms", """
            MATCH (s:Entity {name_n:$s_n}), (o:Entity {name_n:$o_n})
            MERGE (s)-[:RELATED {pred:$p}]->(o)
        """, {"s_n": s_n, "o_n": o_n, "p": p_n})

    def _unlink(self, trace, fact_id):
        self._q(trace, "unlink retired fact", """
            MATCH (s:Entity)-[:HAS_FACT]->(f:Fact {id:$id})-[:ABOUT]->(o:Entity)
            MATCH (s)-[r:RELATED]->(o) WHERE r.pred = f.predicate_n
            DELETE r
        """, {"id": fact_id})

    def _supersede(self, trace, new_id, old_id, t):
        self._q(trace, "supersede old fact (close validity window)", """
            MATCH (n:Fact {id:$new}), (o:Fact {id:$old})
            SET o.valid_to=$t, o.status='superseded', n.status='active', n.valid_from=$t
            CREATE (n)-[:SUPERSEDES {ts:$t}]->(o)
        """, {"new": new_id, "old": old_id, "t": t})
        self._unlink(trace, old_id)
        rows = self._q(None, "", "MATCH (f:Fact {id:$id}) RETURN f.subject_n, f.predicate_n, f.object_n", {"id": new_id})
        if rows:
            self._link(trace, *rows[0])

    def resolve(self, fact_id: str, keep: str = "new") -> dict:
        """Resolve a pending contradiction: keep 'new', 'old', or 'both'."""
        trace = Trace()
        t = now_ms()
        rows = self._q(trace, "load contradiction", """
            MATCH (n:Fact {id:$id})-[c:CONTRADICTS {status:'pending'}]->(o:Fact) RETURN o.id
        """, {"id": fact_id})
        if not rows:
            return {"status": "not_found", "trace": trace.steps}
        old_ids = [r[0] for r in rows]
        if keep == "new":
            for oid in old_ids:
                self._supersede(trace, fact_id, oid, t)
        elif keep == "old":
            self._q(trace, "reject new claim", """
                MATCH (n:Fact {id:$id}) SET n.status='rejected', n.valid_to=$t
            """, {"id": fact_id, "t": t})
        elif keep == "both":
            self._q(trace, "both true -> multi-valued", """
                MATCH (n:Fact {id:$id})-[:CONTRADICTS]->(o:Fact)
                SET n.status='active', n.single_valued=false, o.single_valued=false
            """, {"id": fact_id})
            rows = self._q(None, "", "MATCH (f:Fact {id:$id}) RETURN f.subject_n, f.predicate_n, f.object_n", {"id": fact_id})
            self._link(trace, *rows[0])
        else:
            raise ValueError("keep must be new|old|both")
        self._q(trace, "close contradiction", """
            MATCH (n:Fact {id:$id})-[c:CONTRADICTS {status:'pending'}]->() SET c.status=$res, c.resolved_at=$t
        """, {"id": fact_id, "res": f"kept_{keep}", "t": t})
        return {"status": f"kept_{keep}", "fact_id": fact_id, "trace": trace.steps}

    def forget(self, fact_id: str) -> dict:
        trace = Trace()
        self._unlink(trace, fact_id)
        self._q(trace, "user-requested forget", """
            MATCH (f:Fact {id:$id}) SET f.status='forgotten', f.valid_to=$t
        """, {"id": fact_id, "t": now_ms()})
        return {"status": "forgotten", "fact_id": fact_id, "trace": trace.steps}

    # ------------------------------------------------------------------ read
    def _fact_view(self, f: dict, cur: int | None = None, sources: list | None = None) -> dict:
        v = {k: f.get(k) for k in ("id", "subject", "predicate", "object", "kind", "status",
                                   "valid_from", "valid_to", "confidence", "asserted_by", "hits")}
        if cur is not None:
            v["strength"] = strength(f, cur)
        if sources is not None:
            v["sources"] = sources
        return v

    def _validity(self, alias: str, as_of: int | None) -> str:
        if as_of is None:
            return f"{alias}.status = 'active'"
        return (f"{alias}.valid_from <= $as_of AND ({alias}.valid_to IS NULL OR {alias}.valid_to > $as_of) "
                f"AND {alias}.status IN ['active','superseded']")

    def recall(self, query: str = "", as_of: int | None = None, limit: int = 15) -> dict:
        """Multi-hop recall: facts matching the query + facts about the entities they point to."""
        trace = Trace()
        cur = self._session(trace)
        toks = tokens(query)
        params: dict[str, Any] = {"toks": toks, "as_of": as_of, "lim": limit * 3}
        where = self._validity("f", as_of)
        if toks:
            cypher = f"""
                MATCH (f:Fact) WHERE {where}
                  AND any(t IN $toks WHERE f.subject_n CONTAINS t OR f.predicate_n CONTAINS t OR f.object_n CONTAINS t)
                OPTIONAL MATCH (f)-[:ABOUT]->(:Entity)-[:HAS_FACT]->(h:Fact) WHERE {self._validity('h', as_of)}
                OPTIONAL MATCH (f)-[:SOURCED_FROM]->(m:Message)
                RETURN f, collect(DISTINCT h) AS hops, collect(DISTINCT m.text) AS src
                LIMIT $lim
            """
        else:
            cypher = f"""
                MATCH (f:Fact) WHERE {where}
                OPTIONAL MATCH (f)-[:SOURCED_FROM]->(m:Message)
                RETURN f, [] AS hops, collect(DISTINCT m.text) AS src
                LIMIT $lim
            """
        rows = self._q(trace, "multi-hop recall (1..2 hops)", cypher, params)

        facts: dict[str, dict] = {}
        hidden = 0
        for f_node, hops, src in rows:
            f = props(f_node)
            items = [(f, src, "direct")] + [(props(h), None, f"via {f['object']}") for h in hops]
            for item, s, why in items:
                if item["id"] in facts:
                    continue
                st = strength(item, cur)
                if as_of is None and st < FORGET_BELOW:
                    hidden += 1
                    continue
                view = self._fact_view(item, cur, s)
                view["match"] = why
                facts[item["id"]] = view

        ranked = sorted(facts.values(), key=lambda v: (v["match"] != "direct", -v["strength"]))[:limit]
        if as_of is None and ranked:
            self._q(trace, "reinforce recalled facts", """
                MATCH (f:Fact) WHERE f.id IN $ids SET f.last_session=$sess, f.hits=f.hits+1
            """, {"ids": [r["id"] for r in ranked], "sess": cur})
        pending = self.contradictions()["pending"]
        return {"facts": ranked, "decayed_hidden": hidden, "pending_contradictions": pending,
                "as_of": as_of, "trace": trace.steps}

    def why_changed(self, topic: str) -> dict:
        """Version history for facts about a topic: what it was, what replaced it, and the source quotes."""
        trace = Trace()
        toks = tokens(topic)
        rows = self._q(trace, "find fact keys about topic", """
            MATCH (f:Fact) WHERE any(t IN $toks WHERE f.predicate_n CONTAINS t OR f.object_n CONTAINS t OR f.subject_n CONTAINS t)
            RETURN DISTINCT f.key
        """, {"toks": toks})
        keys = [r[0] for r in rows]
        if not keys:
            return {"timelines": [], "trace": trace.steps}
        rows = self._q(trace, "walk SUPERSEDES chain with provenance", """
            MATCH (f:Fact) WHERE f.key IN $keys
            OPTIONAL MATCH (f)-[:SOURCED_FROM]->(m:Message)
            OPTIONAL MATCH (f)-[:SUPERSEDES]->(prev:Fact)
            RETURN f, collect(DISTINCT m.text) AS src, prev.object AS replaced
            ORDER BY f.valid_from
        """, {"keys": keys})
        timelines: dict[str, list] = {}
        for f_node, src, replaced in rows:
            f = props(f_node)
            v = self._fact_view(f, sources=src)
            v["replaced"] = replaced
            timelines.setdefault(f["key"], []).append(v)
        out = [{"key": k, "versions": v, "changed": len(v) > 1} for k, v in timelines.items()]
        out.sort(key=lambda x: not x["changed"])
        return {"timelines": out, "trace": trace.steps}

    def contradictions(self) -> dict:
        rows = self.g.query("""
            MATCH (n:Fact)-[c:CONTRADICTS {status:'pending'}]->(o:Fact)
            OPTIONAL MATCH (n)-[:SOURCED_FROM]->(mn:Message)
            OPTIONAL MATCH (o)-[:SOURCED_FROM]->(mo:Message)
            RETURN n, o, collect(DISTINCT mn.text), collect(DISTINCT mo.text)
        """).result_set
        return {"pending": [{
            "fact_id": props(n)["id"],
            "new": self._fact_view(props(n), sources=sn),
            "old": self._fact_view(props(o), sources=so),
        } for n, o, sn, so in rows]}

    def core_profile(self, limit: int = 10) -> dict:
        """PageRank over the entity graph: what matters most in this user's world."""
        trace = Trace()
        rows = self._q(trace, "PageRank over entities", """
            CALL algo.pageRank('Entity', 'RELATED') YIELD node, score
            WITH node, score WHERE node.name_n <> 'user'
            MATCH (node)-[:RELATED]-()
            WITH DISTINCT node, score
            RETURN node.name, score ORDER BY score DESC LIMIT $lim
        """, {"lim": limit})
        return {"entities": [{"name": n, "score": round(s, 4)} for n, s in rows], "trace": trace.steps}

    def sweep(self) -> dict:
        """Archive facts whose strength decayed below threshold."""
        trace = Trace()
        cur = self._session(trace)
        rows = self._q(trace, "load active facts", "MATCH (f:Fact {status:'active'}) RETURN f")
        dead = [props(r[0])["id"] for r in rows if strength(props(r[0]), cur) < ARCHIVE_BELOW]
        if dead:
            for fid in dead:
                self._unlink(trace, fid)
            self._q(trace, "archive decayed facts", """
                MATCH (f:Fact) WHERE f.id IN $ids SET f.status='archived', f.valid_to=$t
            """, {"ids": dead, "t": now_ms()})
        return {"archived": len(dead), "trace": trace.steps}

    # ------------------------------------------------------------------ dashboard
    def snapshot(self, as_of: int | None = None) -> dict:
        """Graph for visualisation (optionally as it was at a point in time)."""
        cur = self._session(None)
        fwhere = ("f.status IN ['active','pending']" if as_of is None else self._validity("f", as_of))
        rows = self.g.query(f"""
            MATCH (s:Entity)-[:HAS_FACT]->(f:Fact)-[:ABOUT]->(o:Entity) WHERE {fwhere}
            OPTIONAL MATCH (f)-[:SOURCED_FROM]->(m:Message)
            RETURN s, f, o, collect(DISTINCT m.text)
        """, {"as_of": as_of}).result_set
        nodes, links = {}, []
        for s, f, o, src in rows:
            fp = props(f)
            for e in (s, o):
                ep = props(e)
                nodes.setdefault("e:" + ep["name_n"], {"id": "e:" + ep["name_n"], "label": ep["name"], "type": "entity"})
            fid = "f:" + fp["id"]
            nodes[fid] = {"id": fid, "label": fp["predicate"], "type": "fact", "fact": self._fact_view(fp, cur, src)}
            links.append({"source": "e:" + props(s)["name_n"], "target": fid, "type": "HAS_FACT"})
            links.append({"source": fid, "target": "e:" + props(o)["name_n"], "type": "ABOUT"})
        rel = self.g.query("""
            MATCH (a:Fact)-[r:SUPERSEDES|CONTRADICTS]->(b:Fact) RETURN a.id, type(r), b.id, r.status
        """).result_set
        for a, t, b, st in rel:
            if "f:" + a in nodes and "f:" + b in nodes:
                links.append({"source": "f:" + a, "target": "f:" + b, "type": t, "status": st})
        bounds = self.g.query("MATCH (f:Fact) RETURN min(f.valid_from), max(f.valid_from)").result_set
        lo, hi = bounds[0] if bounds else (None, None)
        return {"nodes": list(nodes.values()), "links": links, "time_range": [lo, hi], "session": cur}

    def stats(self) -> dict:
        rows = self.g.query("""
            MATCH (f:Fact) RETURN f.status, count(f)
        """).result_set
        by = {s: c for s, c in rows}
        sess = self.g.query("MATCH (u:User) RETURN u.session_no").result_set
        return {"facts": by, "session": sess[0][0] if sess else 0}
