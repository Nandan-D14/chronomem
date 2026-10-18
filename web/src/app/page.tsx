"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import MemoryGraph, { LEGEND } from "@/components/MemoryGraph";
import { api, fmt, type Contradiction, type Fact, type GraphNode, type Snapshot, type TraceStep } from "@/lib/api";

type Tab = "trace" | "conflicts" | "history" | "recall" | "profile";
type Msg = { role: "user" | "assistant"; content: string; tools?: string[] };

const KIND_BADGE: Record<string, string> = {
  identity: "bg-emerald-500/15 text-emerald-300",
  preference: "bg-sky-500/15 text-sky-300",
  goal: "bg-pink-500/15 text-pink-300",
  state: "bg-amber-500/15 text-amber-300",
};

export default function Home() {
  const [users, setUsers] = useState<string[]>([]);
  const [user, setUser] = useState("nandan");
  const [chatOn, setChatOn] = useState(false);
  const [model, setModel] = useState<string | null>(null);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [asOf, setAsOf] = useState<number | null>(null);
  const [stats, setStats] = useState<{ facts: Record<string, number>; session: number } | null>(null);
  const [trace, setTrace] = useState<{ label: string; steps: TraceStep[] } | null>(null);
  const [highlight, setHighlight] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [conflicts, setConflicts] = useState<Contradiction[]>([]);
  const [tab, setTab] = useState<Tab>("trace");
  const [left, setLeft] = useState<"chat" | "playground">("playground");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);
  const refresh = useCallback(
    async (u = user, t = asOf) => {
      try {
        const [g, s, c] = await Promise.all([api.graph(u, t ?? undefined), api.stats(u), api.contradictions(u)]);
        setSnap(g);
        setStats(s);
        setConflicts(c.pending);
        setError(null);
      } catch (e) {
        setError(String((e as Error).message));
      }
    },
    [user, asOf],
  );

  useEffect(() => {
    api.config().then((c) => {
      setChatOn(c.chat_enabled);
      setModel(c.model);
      if (c.chat_enabled) setLeft("chat");
    }).catch((e) => setError("API offline: " + e.message));
    api.users().then((r) => setUsers(r.users)).catch(() => {});
  }, []);

  useEffect(() => {
    refresh(user, asOf);
  }, [user, asOf, refresh]);

  const run = async <T,>(label: string, fn: () => Promise<T & { trace?: TraceStep[] }>, hl?: (r: T) => string[]) => {
    setBusy(true);
    try {
      const r = await fn();
      if (r.trace) setTrace({ label, steps: r.trace });
      if (hl) setHighlight(new Set(hl(r)));
      await refresh();
      return r;
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const seed = async (s: "personal" | "team") => {
    setBusy(true);
    const r = await api.seed(s);
    setUsers((await api.users()).users);
    setAsOf(null);
    setNow(Date.now());
    setUser(r.user);
    await refresh(r.user, null);
    setBusy(false);
  };

  const range = snap?.time_range ?? [null, null];
  const hi = now ?? 0;
  const lo = range[0] ?? hi - 86400000;

  return (
    <div className="flex h-screen min-w-[1180px] flex-col bg-[#0b0d12] text-slate-200">
      {/* header */}
      <header className="flex items-center gap-4 border-b border-white/10 px-5 py-3">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-violet-500 to-emerald-400 font-bold text-black">C</div>
          <div>
            <div className="font-semibold leading-tight">ChronoMem</div>
            <div className="text-[11px] text-slate-400">time-aware graph memory for AI agents · FalkorDB</div>
          </div>
        </div>
        <div className="ml-6 flex items-center gap-2 text-sm">
          <span className="text-slate-400">memory graph</span>
          <select
            value={user}
            onChange={(e) => { setAsOf(null); setUser(e.target.value); setSelected(null); setHighlight(new Set()); }}
            className="rounded-md border border-white/10 bg-white/5 px-2 py-1"
          >
            {[...new Set([user, ...users])].map((u) => <option key={u} value={u} className="bg-slate-900">mem_{u}</option>)}
          </select>
          <button
            className="rounded-md border border-white/10 px-2 py-1 hover:bg-white/5"
            onClick={() => { const n = prompt("New user / tenant id"); if (n) { setUser(n.trim().toLowerCase()); setAsOf(null); } }}
          >+ tenant</button>
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs">
          {stats && (
            <span className="text-slate-400">
              session #{stats.session} · {stats.facts.active ?? 0} active · {stats.facts.superseded ?? 0} superseded · {stats.facts.pending ?? 0} pending
            </span>
          )}
          <button disabled={busy} onClick={() => run("new session", () => api.session(user))} className="rounded-md bg-white/10 px-2.5 py-1 hover:bg-white/15">New session</button>
          <button disabled={busy} onClick={() => run("decay sweep", () => api.sweep(user))} className="rounded-md bg-white/10 px-2.5 py-1 hover:bg-white/15">Decay sweep</button>
          <button disabled={busy} onClick={() => seed("personal")} className="rounded-md bg-violet-600/80 px-2.5 py-1 hover:bg-violet-600">Demo: personal</button>
          <button disabled={busy} onClick={() => seed("team")} className="rounded-md bg-emerald-600/80 px-2.5 py-1 hover:bg-emerald-600">Demo: team brain</button>
        </div>
      </header>

      {error && <div className="bg-red-500/15 px-5 py-1.5 text-xs text-red-300">{error}</div>}

      <div className="flex min-h-0 flex-1">
        {/* left: chat / playground */}
        <aside className="flex w-[340px] shrink-0 flex-col border-r border-white/10">
          <div className="flex border-b border-white/10 text-sm">
            {(["chat", "playground"] as const).map((t) => (
              <button key={t} onClick={() => setLeft(t)}
                className={`flex-1 py-2 capitalize ${left === t ? "border-b-2 border-violet-400 text-white" : "text-slate-400"}`}>
                {t === "chat" ? "Agent chat" : "Tool playground"}
              </button>
            ))}
          </div>
          {left === "chat" ? (
            <Chat user={user} enabled={chatOn} model={model} onStep={(label, steps, hl) => { setTrace({ label, steps }); setHighlight(new Set(hl)); setTab("trace"); refresh(); }} />
          ) : (
            <Playground user={user} busy={busy} run={run} onConflict={() => setTab("conflicts")} />
          )}
        </aside>

        {/* center: graph */}
        <main className="relative flex min-w-[420px] flex-1 flex-col">
          <div className="relative flex-1">
            <MemoryGraph data={snap} highlight={highlight} onSelect={setSelected} />
            <div className="pointer-events-none absolute left-3 top-3 flex flex-wrap gap-x-3 gap-y-1 rounded-md bg-black/40 px-2 py-1.5 text-[10px] text-slate-300">
              {LEGEND.map(([l, c, s]) => (
                <span key={l} className="flex items-center gap-1">
                  <span className={s === "circle" ? "h-2 w-2 rounded-full" : "h-2 w-2"} style={{ background: c }} />{l}
                </span>
              ))}
              <span className="flex items-center gap-1"><span className="h-0.5 w-3 bg-red-500" />contradicts</span>
              <span className="flex items-center gap-1"><span className="h-0.5 w-3 border-t border-dashed border-slate-400" />supersedes</span>
            </div>
            {asOf && (
              <div className="absolute right-3 top-3 rounded-md bg-amber-500/20 px-2 py-1 text-xs text-amber-200">
                Time travel: memory as of {fmt(asOf)}
              </div>
            )}
          </div>
          {/* time travel */}
          <div className="flex items-center gap-3 border-t border-white/10 px-4 py-2.5 text-xs">
            <span className="text-slate-400">Time travel</span>
            {now !== null && <span className="text-slate-500">{fmt(lo)}</span>}
            {now !== null && <input
              type="range" min={lo} max={hi} step={60000}
              value={asOf ?? hi}
              onChange={(e) => { const v = Number(e.target.value); setAsOf(v >= hi - 60000 ? null : v); }}
              className="flex-1 accent-violet-400"
            />}
            {now === null && <div className="flex-1" />}
            <span className="w-32 text-right text-slate-300">{asOf ? fmt(asOf) : "now (live)"}</span>
            <button onClick={() => setAsOf(null)} className="rounded bg-white/10 px-2 py-0.5 hover:bg-white/15">Live</button>
          </div>
        </main>

        {/* right: inspector */}
        <aside className="flex w-[400px] shrink-0 flex-col border-l border-white/10">
          {selected?.fact && <FactCard f={selected.fact} onForget={() => run("forget", () => api.forget(user, selected.fact!.id)).then(() => setSelected(null))} />}
          <div className="flex border-b border-white/10 text-xs">
            {(["trace", "conflicts", "history", "recall", "profile"] as Tab[]).map((t) => (
              <button key={t} onClick={() => setTab(t)}
                className={`flex-1 py-2 capitalize ${tab === t ? "border-b-2 border-emerald-400 text-white" : "text-slate-400"}`}>
                {t}{t === "conflicts" && conflicts.length ? <span className="ml-1 rounded-full bg-red-500 px-1.5 text-[10px] text-white">{conflicts.length}</span> : null}
              </button>
            ))}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-3 text-sm">
            {tab === "trace" && <TracePanel trace={trace} />}
            {tab === "conflicts" && (
              <Conflicts items={conflicts} onResolve={(id, keep) => run(`resolve: keep ${keep}`, () => api.resolve(user, id, keep), () => ["f:" + id])} />
            )}
            {tab === "history" && <History user={user} run={run} />}
            {tab === "recall" && <Recall user={user} asOf={asOf} run={run} />}
            {tab === "profile" && <Profile user={user} run={run} />}
          </div>
        </aside>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- panels */

type Runner = <T>(label: string, fn: () => Promise<T & { trace?: TraceStep[] }>, hl?: (r: T) => string[]) => Promise<(T & { trace?: TraceStep[] }) | undefined>;

function TracePanel({ trace }: { trace: { label: string; steps: TraceStep[] } | null }) {
  if (!trace) return <Empty text="Every memory operation shows the exact Cypher it ran on FalkorDB here." />;
  return (
    <div className="space-y-2">
      <div className="text-xs uppercase tracking-wide text-slate-400">Why the agent knows this · {trace.label}</div>
      {trace.steps.map((s, i) => (
        <div key={i} className="rounded-md border border-white/10 bg-white/[0.03]">
          <div className="flex items-center gap-2 border-b border-white/10 px-2 py-1 text-xs">
            <span className="grid h-4 w-4 place-items-center rounded-full bg-emerald-500/20 text-[10px] text-emerald-300">{i + 1}</span>
            <span className="text-slate-300">{s.step}</span>
          </div>
          <pre className="whitespace-pre-wrap break-words px-2 py-1.5 font-mono text-[11px] leading-relaxed text-sky-200">{s.cypher}</pre>
          {Object.keys(s.params).length > 0 && (
            <pre className="whitespace-pre-wrap break-words px-2 pb-1.5 font-mono text-[10px] text-slate-500">{JSON.stringify(s.params)}</pre>
          )}
        </div>
      ))}
    </div>
  );
}

function FactCard({ f, onForget }: { f: Fact; onForget: () => void }) {
  return (
    <div className="border-b border-white/10 bg-white/[0.03] p-3 text-sm">
      <div className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[10px] ${KIND_BADGE[f.kind]}`}>{f.kind}</span>
        <span className="text-[10px] text-slate-400">{f.status} · by {f.asserted_by} · seen {f.hits}×</span>
        <button onClick={onForget} className="ml-auto text-[10px] text-red-300 hover:underline">forget</button>
      </div>
      <div className="mt-1.5 font-medium">{f.subject} <span className="text-slate-400">{f.predicate}</span> {f.object}</div>
      <div className="mt-1 text-[11px] text-slate-400">valid {fmt(f.valid_from)} → {f.valid_to ? fmt(f.valid_to) : "now"}</div>
      {f.strength !== undefined && <Strength v={f.strength} />}
      {f.sources?.map((s, i) => <div key={i} className="mt-1 border-l-2 border-violet-400/60 pl-2 text-xs italic text-slate-300">“{s}”</div>)}
    </div>
  );
}

function Strength({ v }: { v: number }) {
  return (
    <div className="mt-1.5 flex items-center gap-2 text-[10px] text-slate-400">
      strength
      <div className="h-1.5 flex-1 rounded bg-white/10"><div className="h-1.5 rounded bg-emerald-400" style={{ width: `${v * 100}%` }} /></div>
      {v.toFixed(2)}
    </div>
  );
}

function Conflicts({ items, onResolve }: { items: Contradiction[]; onResolve: (id: string, keep: "new" | "old" | "both") => void }) {
  if (!items.length) return <Empty text="No pending contradictions. ChronoMem never silently overwrites — conflicts land here." />;
  return (
    <div className="space-y-3">
      {items.map((c) => (
        <div key={c.fact_id} className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <div className="text-xs font-medium text-red-300">Contradiction · {c.old.subject} / {c.old.predicate}</div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
            {([["Earlier", c.old], ["Now", c.new]] as const).map(([l, f]) => (
              <div key={l} className="rounded bg-black/30 p-2">
                <div className="text-[10px] uppercase text-slate-500">{l} · {fmt(f.valid_from)} · {f.asserted_by}</div>
                <div className="mt-0.5 font-medium">{f.object}</div>
                {f.sources?.slice(0, 2).map((s, i) => <div key={i} className="mt-1 italic text-slate-400">“{s}”</div>)}
              </div>
            ))}
          </div>
          <div className="mt-2 flex gap-2 text-xs">
            <button onClick={() => onResolve(c.fact_id, "new")} className="rounded bg-emerald-600/80 px-2 py-1 hover:bg-emerald-600">Keep new</button>
            <button onClick={() => onResolve(c.fact_id, "old")} className="rounded bg-white/10 px-2 py-1 hover:bg-white/15">Keep old</button>
            <button onClick={() => onResolve(c.fact_id, "both")} className="rounded bg-white/10 px-2 py-1 hover:bg-white/15">Both true</button>
          </div>
        </div>
      ))}
    </div>
  );
}

function History({ user, run }: { user: string; run: Runner }) {
  const [q, setQ] = useState("lives");
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.why>> | null>(null);
  const go = async () => { const r = await run(`why_changed("${q}")`, () => api.why(user, q), (r) => r.timelines.flatMap((t) => t.versions.map((v) => "f:" + v.id))); if (r) setRes(r); };
  return (
    <div>
      <SearchBox value={q} onChange={setQ} onGo={go} placeholder="When/why did … change? (diet, lives, owned)" />
      {res?.timelines.map((t) => (
        <div key={t.key} className="mt-3">
          <div className="text-xs text-slate-400">{t.key.replace("|", " · ")} {t.changed && <span className="text-amber-300">· changed</span>}</div>
          <ol className="mt-1 border-l border-white/15 pl-3">
            {t.versions.map((v) => (
              <li key={v.id} className="relative mb-2">
                <span className={`absolute -left-[17px] top-1.5 h-2 w-2 rounded-full ${v.status === "active" ? "bg-emerald-400" : v.status === "pending" ? "bg-amber-400" : "bg-slate-500"}`} />
                <div className="text-xs"><b>{v.object}</b> <span className="text-slate-500">({v.status}, {v.asserted_by})</span></div>
                <div className="text-[10px] text-slate-500">{fmt(v.valid_from)} → {v.valid_to ? fmt(v.valid_to) : "now"}{v.replaced && ` · replaced “${v.replaced}”`}</div>
                {v.sources?.slice(0, 1).map((s, i) => <div key={i} className="text-[11px] italic text-slate-400">“{s}”</div>)}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </div>
  );
}

function Recall({ user, asOf, run }: { user: string; asOf: number | null; run: Runner }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.recall>> | null>(null);
  const go = async () => { const r = await run(`recall("${q}")`, () => api.recall(user, q, asOf ?? undefined), (r) => r.facts.map((f) => "f:" + f.id)); if (r) setRes(r); };
  return (
    <div>
      <SearchBox value={q} onChange={setQ} onGo={go} placeholder="Multi-hop recall (empty = everything)" />
      {res && <div className="mt-2 text-[11px] text-slate-500">{res.facts.length} facts{res.decayed_hidden ? ` · ${res.decayed_hidden} faded by decay` : ""}{asOf ? ` · as of ${fmt(asOf)}` : ""}</div>}
      <div className="mt-2 space-y-1.5">
        {res?.facts.map((f) => (
          <div key={f.id} className="rounded border border-white/10 p-2 text-xs">
            <div className="flex items-center gap-1.5">
              <span className={`rounded px-1 text-[10px] ${KIND_BADGE[f.kind]}`}>{f.kind}</span>
              <span className="text-[10px] text-slate-500">{f.match}</span>
            </div>
            <div className="mt-1">{f.subject} <span className="text-slate-400">{f.predicate}</span> <b>{f.object}</b></div>
            {f.strength !== undefined && <Strength v={f.strength} />}
          </div>
        ))}
      </div>
    </div>
  );
}

function Profile({ user, run }: { user: string; run: Runner }) {
  const [res, setRes] = useState<Awaited<ReturnType<typeof api.profile>> | null>(null);
  useEffect(() => { run("core_profile (PageRank)", () => api.profile(user)).then((r) => r && setRes(r)); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  const max = Math.max(...(res?.entities.map((e) => e.score) ?? [1]));
  return (
    <div>
      <div className="text-xs text-slate-400">What matters most — <code>algo.pageRank(&apos;Entity&apos;,&apos;RELATED&apos;)</code></div>
      <div className="mt-3 space-y-1.5">
        {res?.entities.map((e) => (
          <div key={e.name} className="text-xs">
            <div className="flex justify-between"><span>{e.name}</span><span className="text-slate-500">{e.score}</span></div>
            <div className="h-1.5 rounded bg-white/10"><div className="h-1.5 rounded bg-violet-400" style={{ width: `${(e.score / max) * 100}%` }} /></div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Playground({ user, busy, run, onConflict }: { user: string; busy: boolean; run: Runner; onConflict: () => void }) {
  const [f, setF] = useState({ subject: "user", predicate: "", object: "", kind: "preference", source: "", single_valued: true, mode: "ask", asserted_by: "user" });
  const [last, setLast] = useState<Record<string, unknown> | null>(null);
  const examples = useMemo(() => [
    { subject: "user", predicate: "diet", object: "vegan", kind: "identity", source: "I went vegan last week" },
    { subject: "user", predicate: "mood", object: "excited", kind: "state", source: "So excited for the demo!" },
    { subject: "user", predicate: "likes", object: "Graph databases", kind: "preference", source: "graphs are awesome", single_valued: false },
    { subject: "billing-service", predicate: "owned by", object: "Anita", kind: "identity", source: "Anita took over billing", asserted_by: "slack-agent" },
  ], []);
  const submit = async () => {
    const r = await run(`remember(${f.subject}, ${f.predicate}, ${f.object})`, () => api.remember(user, f), (r) => ["f:" + String((r as { fact_id?: string }).fact_id)]);
    if (r) { setLast(Object.fromEntries(Object.entries(r).filter(([k]) => k !== "trace"))); if (r.status === "contradiction") onConflict(); }
  };
  const inp = "w-full rounded-md border border-white/10 bg-white/5 px-2 py-1.5 text-sm outline-none focus:border-violet-400";
  return (
    <div className="flex-1 space-y-2 overflow-y-auto p-3 text-sm">
      <p className="text-xs text-slate-400">Call ChronoMem&apos;s <code>remember</code> tool exactly like an MCP agent would.</p>
      <div className="grid grid-cols-3 gap-1.5">
        <input className={inp} placeholder="subject" value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} />
        <input className={inp} placeholder="predicate" value={f.predicate} onChange={(e) => setF({ ...f, predicate: e.target.value })} />
        <input className={inp} placeholder="object" value={f.object} onChange={(e) => setF({ ...f, object: e.target.value })} />
      </div>
      <input className={inp} placeholder="source — the user's exact words" value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} />
      <div className="grid grid-cols-3 gap-1.5">
        <select className={inp} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          {["identity", "preference", "goal", "state"].map((k) => <option key={k} className="bg-slate-900">{k}</option>)}
        </select>
        <select className={inp} value={f.mode} onChange={(e) => setF({ ...f, mode: e.target.value })}>
          <option value="ask" className="bg-slate-900">ask on conflict</option>
          <option value="replace" className="bg-slate-900">replace</option>
        </select>
        <input className={inp} placeholder="asserted by" value={f.asserted_by} onChange={(e) => setF({ ...f, asserted_by: e.target.value })} />
      </div>
      <label className="flex items-center gap-2 text-xs text-slate-400">
        <input type="checkbox" checked={f.single_valued} onChange={(e) => setF({ ...f, single_valued: e.target.checked })} /> single-valued (only one value allowed)
      </label>
      <button disabled={busy || !f.predicate || !f.object} onClick={submit} className="w-full rounded-md bg-violet-600 py-1.5 font-medium hover:bg-violet-500 disabled:opacity-40">remember()</button>
      <div className="pt-1 text-[11px] text-slate-500">Examples</div>
      <div className="flex flex-wrap gap-1.5">
        {examples.map((e) => (
          <button key={e.object} onClick={() => setF({ ...f, single_valued: true, asserted_by: "user", ...e })} className="rounded-full border border-white/10 px-2 py-0.5 text-[11px] hover:bg-white/5">
            {e.predicate} → {e.object}
          </button>
        ))}
      </div>
      {last && (
        <pre className={`mt-2 whitespace-pre-wrap break-words rounded-md p-2 font-mono text-[11px] ${last.status === "contradiction" ? "bg-red-500/10 text-red-200" : "bg-emerald-500/10 text-emerald-200"}`}>
          {JSON.stringify(last, null, 1)}
        </pre>
      )}
    </div>
  );
}

function Chat({ user, enabled, model, onStep }: { user: string; enabled: boolean; model: string | null; onStep: (label: string, steps: TraceStep[], hl: string[]) => void }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setMsgs([]), [user]);
  if (!enabled)
    return (
      <div className="space-y-2 p-4 text-sm text-slate-400">
        <p>ChronoMem is an <b className="text-slate-200">MCP memory plugin</b> — your agent (Claude Desktop, Cursor, Cortex Code…) brings the LLM.</p>
        <p>To chat here too, set <code>LLM_API_KEY</code> (+ optional <code>LLM_BASE_URL</code>, <code>LLM_MODEL</code>) for any OpenAI-compatible provider and restart the API.</p>
        <p>Meanwhile use the <b className="text-slate-200">Tool playground</b> tab.</p>
      </div>
    );
  const send = async () => {
    if (!text.trim()) return;
    const next = [...msgs, { role: "user" as const, content: text }];
    setMsgs(next);
    setText("");
    setBusy(true);
    try {
      const r = await api.chat(user, next.map(({ role, content }) => ({ role, content })));
      setMsgs([...next, { role: "assistant", content: r.reply, tools: r.steps.map((s) => s.tool) }]);
      const steps = r.steps.flatMap((s) => (s.result.trace ?? []).map((t) => ({ ...t, step: `${s.tool}: ${t.step}` })));
      const hl = r.steps.flatMap((s) => {
        const res = s.result as { facts?: Fact[]; fact_id?: string };
        return [...(res.facts?.map((f) => "f:" + f.id) ?? []), ...(res.fact_id ? ["f:" + res.fact_id] : [])];
      });
      onStep(r.steps.map((s) => s.tool).join(" → ") || "chat", steps, hl);
    } catch (e) {
      setMsgs([...next, { role: "assistant", content: "⚠ " + (e as Error).message }]);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-3 text-sm">
        {!msgs.length && <div className="text-xs text-slate-500">Chatting as <b>{user}</b> via {model}. Try: “what do you know about me?”, “I had chicken today”, “when did I move?”</div>}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "ml-8 rounded-lg bg-violet-600/25 px-3 py-2" : "mr-4 rounded-lg bg-white/5 px-3 py-2"}>
            <div className="whitespace-pre-wrap">{m.content}</div>
            {m.tools?.length ? <div className="mt-1 text-[10px] text-emerald-300">tools: {m.tools.join(" → ")}</div> : null}
          </div>
        ))}
        {busy && <div className="text-xs text-slate-500">thinking · querying graph…</div>}
      </div>
      <div className="border-t border-white/10 p-2">
        <input
          value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && !busy && send()}
          placeholder="Message the agent…" className="w-full rounded-md border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-violet-400"
        />
      </div>
    </div>
  );
}

function SearchBox({ value, onChange, onGo, placeholder }: { value: string; onChange: (v: string) => void; onGo: () => void; placeholder: string }) {
  return (
    <div className="flex gap-1.5">
      <input value={value} onChange={(e) => onChange(e.target.value)} onKeyDown={(e) => e.key === "Enter" && onGo()} placeholder={placeholder}
        className="flex-1 rounded-md border border-white/10 bg-white/5 px-2 py-1.5 text-xs outline-none focus:border-emerald-400" />
      <button onClick={onGo} className="rounded-md bg-emerald-600/80 px-3 text-xs hover:bg-emerald-600">Go</button>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="mt-6 text-center text-xs text-slate-500">{text}</div>;
}
