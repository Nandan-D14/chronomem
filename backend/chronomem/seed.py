"""Demo data: a personal memory with 30 days of history, and a shared team graph
where several agents write (and disagree)."""
from .db import delete_user
from .memory import Memory, now_ms

DAY = 24 * 3600 * 1000


def _at(days_ago: float) -> int:
    return now_ms() - int(days_ago * DAY)


PERSONAL = [
    # days_ago, subject, predicate, object, kind, source, single_valued, mode
    (30, "user", "name", "Nandan", "identity", "Hi, I'm Nandan", True, "ask"),
    (30, "user", "studies at", "PES University", "identity", "I'm a student at PES University", True, "ask"),
    (30, "PES University", "located in", "Bengaluru", "identity", "PES is in Bengaluru", True, "ask"),
    (30, "user", "lives in", "Bengaluru", "identity", "I live in Bengaluru", True, "ask"),
    (29, "user", "diet", "vegetarian", "identity", "I'm vegetarian", True, "ask"),
    (25, "user", "likes", "Python", "preference", "I love Python", False, "ask"),
    (20, "user", "working on", "chat app", "goal", "This week I'm building a chat app", True, "ask"),
    (15, "user", "learning", "Rust", "preference", "I've started learning Rust", False, "ask"),
    (10, "user", "lives in", "Mysuru", "identity", "I moved to Mysuru for my internship", True, "replace"),
    (10, "user", "works at", "Acme Labs", "identity", "I'm interning at Acme Labs", True, "ask"),
    (10, "Acme Labs", "located in", "Mysuru", "identity", "Acme Labs is in Mysuru", True, "ask"),
    (6, "user", "likes", "FalkorDB", "preference", "I'm really into graph databases now, FalkorDB especially", False, "ask"),
    (3, "user", "working on", "ChronoMem", "goal", "Now I'm building ChronoMem for Graph Hacks", True, "replace"),
    (2, "user", "mood", "stressed about exams", "state", "Feeling stressed about exams", True, "replace"),
    (0.01, "user", "diet", "eats chicken", "identity", "Had chicken biryani today, loved it!", True, "ask"),
]

DECISIONS = [
    (14, "Recommended Cult.fit gym in Koramangala", "closest gym to where the user lives"),
    (13, "Planned a daily metro commute to PES University", "user lives in Bengaluru and studies there"),
    (12, "Suggested veg-friendly cafes near campus (Hosur Rd)", "user is vegetarian and lives in Bengaluru"),
]

TEAM = [
    # days_ago, subject, predicate, object, kind, source, single_valued, mode, agent
    (14, "billing-service", "owned by", "Priya", "identity", "#eng: Priya owns billing-service", True, "ask", "slack-agent"),
    (14, "billing-service", "depends on", "postgres-main", "identity", "billing-service reads from postgres-main", False, "ask", "code-agent"),
    (13, "auth-service", "depends on", "postgres-main", "identity", "auth-service uses postgres-main", False, "ask", "code-agent"),
    (13, "checkout-web", "depends on", "billing-service", "identity", "checkout-web calls billing-service", False, "ask", "code-agent"),
    (12, "checkout-web", "depends on", "auth-service", "identity", "checkout-web calls auth-service", False, "ask", "code-agent"),
    (12, "Priya", "member of", "Payments team", "identity", "Priya is on Payments", True, "ask", "hr-agent"),
    (11, "Rahul", "member of", "Platform team", "identity", "Rahul is on Platform", True, "ask", "hr-agent"),
    (11, "postgres-main", "owned by", "Rahul", "identity", "Rahul is DBA for postgres-main", True, "ask", "slack-agent"),
    (9, "billing-service", "decision", "use idempotency keys", "identity", "ADR-12: billing uses idempotency keys after double-charge incident", False, "ask", "docs-agent"),
    (9, "INC-42 double charge", "caused by", "billing-service", "identity", "INC-42: double charge caused by billing retries", False, "ask", "incident-agent"),
    (4, "billing-service", "owned by", "Rahul", "identity", "JIRA PAY-77 assigned billing-service ownership to Rahul", True, "ask", "jira-agent"),
]


def seed(scenario: str = "personal") -> dict:
    if scenario == "personal":
        user = "nandan"
        delete_user(user)
        m = Memory(user)
        for d, s, p, o, k, src, sv, mode in PERSONAL:
            if d == 10 and p == "lives in":
                for days, text, why in DECISIONS:
                    m.record_decision(text, ["user|lives_in", "user|diet"], reason=why, ts=_at(days))
            m.remember(s, p, o, kind=k, source=src, single_valued=sv, mode=mode, ts=_at(d))
        return {"user": user, "facts": len(PERSONAL), "decisions": len(DECISIONS)}
    if scenario == "team":
        user = "team_acme"
        delete_user(user)
        m = Memory(user)
        for d, s, p, o, k, src, sv, mode, agent in TEAM:
            m.remember(s, p, o, kind=k, source=src, single_valued=sv, mode=mode, asserted_by=agent, ts=_at(d))
        return {"user": user, "facts": len(TEAM)}
    raise ValueError("scenario must be personal|team")
