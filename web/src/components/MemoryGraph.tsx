"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import type { GraphLink, GraphNode, Snapshot } from "@/lib/api";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const KIND_COLOR: Record<string, string> = {
  identity: "#34d399",
  preference: "#60a5fa",
  goal: "#f472b6",
  state: "#fbbf24",
};

function nodeColor(n: GraphNode) {
  if (n.type === "entity") return "#a78bfa";
  const f = n.fact!;
  if (f.status === "pending") return "#f59e0b";
  if (f.status === "superseded") return "#6b7280";
  return KIND_COLOR[f.kind] ?? "#94a3b8";
}

function linkColor(l: GraphLink) {
  if (l.type === "CONTRADICTS") return l.status === "pending" ? "#ef4444" : "#7f1d1d";
  if (l.type === "SUPERSEDES") return "#9ca3af";
  return "rgba(148,163,184,0.35)";
}

export default function MemoryGraph({
  data,
  highlight,
  onSelect,
}: {
  data: Snapshot | null;
  highlight: Set<string>;
  onSelect: (n: GraphNode | null) => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 600, h: 400 });

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={box} className="absolute inset-0">
      {data && (
        <ForceGraph2D
          width={size.w}
          height={size.h}
          graphData={{ nodes: data.nodes, links: data.links }}
          backgroundColor="rgba(0,0,0,0)"
          nodeId="id"
          cooldownTicks={120}
          linkColor={(l) => linkColor(l as GraphLink)}
          linkWidth={(l) => ((l as GraphLink).type === "CONTRADICTS" ? 2.5 : (l as GraphLink).type === "SUPERSEDES" ? 1.8 : 1)}
          linkLineDash={(l) => ((l as GraphLink).type === "SUPERSEDES" ? [4, 3] : null)}
          linkDirectionalArrowLength={(l) => ((l as GraphLink).type === "HAS_FACT" ? 0 : 4)}
          linkDirectionalArrowRelPos={1}
          linkDirectionalParticles={(l) => ((l as GraphLink).type === "CONTRADICTS" && (l as GraphLink).status === "pending" ? 3 : 0)}
          linkDirectionalParticleColor={() => "#ef4444"}
          onNodeClick={(n) => onSelect(n as GraphNode)}
          onBackgroundClick={() => onSelect(null)}
          nodeCanvasObject={(raw, ctx, scale) => {
            const n = raw as GraphNode;
            const isEntity = n.type === "entity";
            const strength = n.fact?.strength ?? 1;
            const r = isEntity ? 7 : 3.5 + 3 * strength;
            const hl = highlight.has(n.id);
            ctx.globalAlpha = isEntity ? 1 : 0.35 + 0.65 * strength;
            if (hl) {
              ctx.beginPath();
              ctx.arc(n.x!, n.y!, r + 5, 0, 2 * Math.PI);
              ctx.fillStyle = "rgba(250,204,21,0.35)";
              ctx.fill();
            }
            ctx.beginPath();
            if (isEntity) ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
            else ctx.rect(n.x! - r, n.y! - r, 2 * r, 2 * r);
            ctx.fillStyle = nodeColor(n);
            ctx.fill();
            ctx.globalAlpha = 1;
            const fontSize = Math.max(10 / scale, 2.5);
            if (isEntity || scale > 1.4 || hl) {
              ctx.font = `${isEntity ? 600 : 400} ${fontSize}px ui-sans-serif, system-ui`;
              ctx.textAlign = "center";
              ctx.textBaseline = "top";
              ctx.fillStyle = isEntity ? "#e5e7eb" : "#9ca3af";
              ctx.fillText(n.label, n.x!, n.y! + r + 1.5);
            }
          }}
          nodePointerAreaPaint={(raw, color, ctx) => {
            const n = raw as GraphNode;
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(n.x!, n.y!, 9, 0, 2 * Math.PI);
            ctx.fill();
          }}
          nodeLabel={(raw) => {
            const n = raw as GraphNode;
            if (!n.fact) return n.label;
            const f = n.fact;
            return `${f.subject} — ${f.predicate} → ${f.object}<br/>${f.kind} · ${f.status} · strength ${f.strength ?? "-"}`;
          }}
        />
      )}
    </div>
  );
}

export const LEGEND = [
  ["Entity", "#a78bfa", "circle"],
  ["Identity fact", KIND_COLOR.identity, "square"],
  ["Preference", KIND_COLOR.preference, "square"],
  ["Goal", KIND_COLOR.goal, "square"],
  ["State", KIND_COLOR.state, "square"],
  ["Pending conflict", "#f59e0b", "square"],
  ["Superseded", "#6b7280", "square"],
] as const;
