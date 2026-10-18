"""Optional built-in chat agent for the dashboard demo.

Uses any OpenAI-compatible endpoint (OpenAI, Groq, Gemini, Ollama...) with tool calling.
The real product is the MCP server; this just lets the dashboard show a live agent
using exactly the same memory tools.
"""
import json
import os

import httpx

from .mcp_server import mcp
from .memory import Memory

BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


def enabled() -> bool:
    return bool(API_KEY)


TOOLS = [
    {"type": "function", "function": {
        "name": "remember",
        "description": "Store a durable fact as a triple. Use subject 'user' for the human.",
        "parameters": {"type": "object", "required": ["subject", "predicate", "object", "kind", "source"], "properties": {
            "subject": {"type": "string"}, "predicate": {"type": "string"}, "object": {"type": "string"},
            "kind": {"type": "string", "enum": ["identity", "preference", "goal", "state"]},
            "source": {"type": "string", "description": "user's exact words"},
            "single_valued": {"type": "boolean", "description": "only one value allowed (city, diet, employer)"},
            "mode": {"type": "string", "enum": ["ask", "replace"], "description": "replace only if user explicitly says it changed"}}}}},
    {"type": "function", "function": {
        "name": "recall", "description": "Multi-hop recall of memories relevant to a query ('' = everything).",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "resolve", "description": "Resolve a pending contradiction after the user answers.",
        "parameters": {"type": "object", "required": ["fact_id", "keep"], "properties": {
            "fact_id": {"type": "string"}, "keep": {"type": "string", "enum": ["new", "old", "both"]}}}}},
    {"type": "function", "function": {
        "name": "why_changed", "description": "History of how a fact changed over time, with sources.",
        "parameters": {"type": "object", "required": ["topic"], "properties": {"topic": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "core_profile", "description": "PageRank: what matters most in the user's world.",
        "parameters": {"type": "object", "properties": {}}}},
]


def _call(m: Memory, name: str, args: dict) -> dict:
    if name == "remember":
        return m.remember(args["subject"], args["predicate"], args["object"], kind=args.get("kind", "preference"),
                          source=args.get("source", ""), single_valued=args.get("single_valued", True),
                          mode=args.get("mode", "ask"), asserted_by="chat-agent")
    if name == "recall":
        return m.recall(args.get("query", ""))
    if name == "resolve":
        return m.resolve(args["fact_id"], args["keep"])
    if name == "why_changed":
        return m.why_changed(args["topic"])
    if name == "core_profile":
        return m.core_profile()
    return {"error": f"unknown tool {name}"}


def chat(user_id: str, history: list[dict]) -> dict:
    m = Memory(user_id)
    messages = [{"role": "system", "content": mcp.instructions +
                 "\nBe concise. Always call recall before answering questions about the user."}] + history
    steps = []
    with httpx.Client(timeout=60) as client:
        for _ in range(6):
            r = client.post(f"{BASE_URL}/chat/completions",
                            headers={"Authorization": f"Bearer {API_KEY}"},
                            json={"model": MODEL, "messages": messages, "tools": TOOLS, "temperature": 0.2})
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            messages.append({k: v for k, v in msg.items() if k in ("role", "content", "tool_calls")})
            if not calls:
                return {"reply": msg.get("content") or "", "steps": steps}
            for c in calls:
                args = json.loads(c["function"]["arguments"] or "{}")
                result = _call(m, c["function"]["name"], args)
                steps.append({"tool": c["function"]["name"], "args": args, "result": result})
                slim = {k: v for k, v in result.items() if k != "trace"}
                messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(slim, default=str)})
    return {"reply": "(stopped after too many tool calls)", "steps": steps}
