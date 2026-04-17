"use client";

import type { AnalyticalNetworkConfig, TopologyKind } from "@/lib/api";

type Props = {
  network: AnalyticalNetworkConfig;
  errorDimIdx?: number | null;
};

/**
 * Inline SVG rendering of one or two ASTRA-sim topology dims.
 * - 1D: drawn as a single ring/star/line.
 * - 2D: outer dim is a column of inner-dim groups, with inter-dim links.
 *
 * Kept dependency-free so the Phase-2 page builds with no extra packages.
 * If a richer interactive editor is needed later, swap to react-flow inside
 * this same component boundary.
 */
export function TopologyView({ network, errorDimIdx = null }: Props) {
  if (network.topology.length === 0) {
    return <Empty message="No topology dimensions configured." />;
  }
  if (network.topology.length === 1) {
    return (
      <SingleDim
        kind={network.topology[0]}
        count={network.npus_count[0]}
        bandwidth={network.bandwidth[0]}
        errored={errorDimIdx === 0}
      />
    );
  }
  // Multi-dim: render as nested groups. Outer dim = repeated copies; inner
  // dim = the topology of each group. We support up to 2D in the viz; higher
  // dims fall back to a textual summary (still valid configs).
  if (network.topology.length === 2) {
    const [outer, inner] = network.topology;
    const [outerCount, innerCount] = network.npus_count;
    return (
      <TwoDim
        outerKind={outer}
        innerKind={inner}
        outerCount={outerCount}
        innerCount={innerCount}
        errorOuter={errorDimIdx === 0}
        errorInner={errorDimIdx === 1}
      />
    );
  }
  return (
    <Empty
      message={`${network.topology.length}-D topology — viz only renders up to 2 dims.`}
    />
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="flex h-48 items-center justify-center rounded border border-dashed border-zinc-800 text-sm text-zinc-500">
      {message}
    </div>
  );
}

function SingleDim({
  kind,
  count,
  bandwidth,
  errored,
}: {
  kind: TopologyKind;
  count: number;
  bandwidth: number;
  errored: boolean;
}) {
  const positions = nodePositions(kind, count, 240, 130);
  const links = topologyLinks(kind, count);
  const stroke = errored ? "#ef4444" : "#52525b";

  return (
    <svg viewBox="0 0 480 280" className="h-72 w-full">
      <Annotation kind={kind} count={count} bandwidth={bandwidth} />
      {kind === "Switch" &&
        positions.map((p, i) => (
          <line
            key={`spoke-${i}`}
            x1={p.x}
            y1={p.y}
            x2={240}
            y2={130}
            stroke={stroke}
            strokeWidth={1}
          />
        ))}
      {kind === "Switch" && <SwitchHub cx={240} cy={130} errored={errored} />}
      {links.map(([a, b], i) => (
        <line
          key={i}
          x1={positions[a].x}
          y1={positions[a].y}
          x2={positions[b].x}
          y2={positions[b].y}
          stroke={stroke}
          strokeWidth={1}
        />
      ))}
      {positions.map((p, i) => (
        <Node key={i} x={p.x} y={p.y} label={String(i)} errored={errored} />
      ))}
    </svg>
  );
}

function TwoDim({
  outerKind,
  innerKind,
  outerCount,
  innerCount,
  errorOuter,
  errorInner,
}: {
  outerKind: TopologyKind;
  innerKind: TopologyKind;
  outerCount: number;
  innerCount: number;
  errorOuter: boolean;
  errorInner: boolean;
}) {
  // Lay out outer copies horizontally; each is a small inner topology.
  const groupW = Math.max(120, 480 / outerCount);
  const r = Math.min(40, groupW * 0.35);
  const cy = 130;

  return (
    <svg viewBox={`0 0 ${groupW * outerCount} 280`} className="h-72 w-full">
      {Array.from({ length: outerCount }).map((_, gi) => {
        const cx = groupW * gi + groupW / 2;
        const innerPositions = nodePositions(innerKind, innerCount, cx, cy, r);
        const innerLinks = topologyLinks(innerKind, innerCount);
        return (
          <g key={gi}>
            <text
              x={cx}
              y={28}
              fill="#a1a1aa"
              fontSize={11}
              textAnchor="middle"
              fontFamily="ui-monospace, monospace"
            >
              dim0[{gi}]
            </text>
            {innerLinks.map(([a, b], i) => (
              <line
                key={i}
                x1={innerPositions[a].x}
                y1={innerPositions[a].y}
                x2={innerPositions[b].x}
                y2={innerPositions[b].y}
                stroke={errorInner ? "#ef4444" : "#52525b"}
                strokeWidth={1}
              />
            ))}
            {innerPositions.map((p, i) => (
              <Node
                key={i}
                x={p.x}
                y={p.y}
                label={`${gi}.${i}`}
                size={10}
                errored={errorOuter || errorInner}
              />
            ))}
          </g>
        );
      })}
      {/* Outer-dim links between corresponding nodes. */}
      {Array.from({ length: outerCount }).map((_, gi) => {
        if (gi === outerCount - 1 && outerKind !== "Ring") return null;
        const next = (gi + 1) % outerCount;
        if (next === gi) return null;
        const x1 = groupW * gi + groupW / 2;
        const x2 = groupW * next + groupW / 2;
        return (
          <line
            key={`outer-${gi}`}
            x1={x1}
            y1={250}
            x2={x2}
            y2={250}
            stroke={errorOuter ? "#ef4444" : "#3f3f46"}
            strokeWidth={1}
            strokeDasharray="3,3"
          />
        );
      })}
      <text
        x={10}
        y={270}
        fill="#71717a"
        fontSize={10}
        fontFamily="ui-monospace, monospace"
      >
        outer dim: {outerKind} × {outerCount} ┊ inner dim: {innerKind} × {innerCount}
      </text>
    </svg>
  );
}

function Node({
  x,
  y,
  label,
  size = 14,
  errored,
}: {
  x: number;
  y: number;
  label: string;
  size?: number;
  errored: boolean;
}) {
  return (
    <g>
      <circle cx={x} cy={y} r={size} fill={errored ? "#7f1d1d" : "#27272a"} stroke={errored ? "#ef4444" : "#71717a"} strokeWidth={1} />
      <text
        x={x}
        y={y + 3}
        fill="#e4e4e7"
        fontSize={9}
        textAnchor="middle"
        fontFamily="ui-monospace, monospace"
      >
        {label}
      </text>
    </g>
  );
}

function SwitchHub({ cx, cy, errored }: { cx: number; cy: number; errored: boolean }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r={22} fill={errored ? "#7f1d1d" : "#1f1f24"} stroke={errored ? "#ef4444" : "#a1a1aa"} strokeWidth={1.5} strokeDasharray="3,3" />
      <text x={cx} y={cy + 3} fill="#e4e4e7" fontSize={9} textAnchor="middle" fontFamily="ui-monospace, monospace">
        switch
      </text>
    </g>
  );
}

function Annotation({
  kind,
  count,
  bandwidth,
}: {
  kind: TopologyKind;
  count: number;
  bandwidth: number;
}) {
  return (
    <text x={10} y={20} fill="#a1a1aa" fontSize={11} fontFamily="ui-monospace, monospace">
      {kind} × {count} NPUs · {bandwidth} GB/s
    </text>
  );
}

function nodePositions(
  kind: TopologyKind,
  count: number,
  cx: number,
  cy: number,
  radius?: number,
): { x: number; y: number }[] {
  const r = radius ?? Math.min(100, 12 + count * 4);
  if (kind === "Ring") {
    return Array.from({ length: count }).map((_, i) => {
      const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
      return { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
    });
  }
  if (kind === "FullyConnected") {
    return Array.from({ length: count }).map((_, i) => {
      const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
      return { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
    });
  }
  // Switch — nodes around a central hub.
  return Array.from({ length: count }).map((_, i) => {
    const angle = (i / count) * Math.PI * 2 - Math.PI / 2;
    return { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r };
  });
}

function topologyLinks(kind: TopologyKind, count: number): [number, number][] {
  if (kind === "Ring") {
    return Array.from({ length: count }).map((_, i) => [i, (i + 1) % count]);
  }
  if (kind === "FullyConnected") {
    const out: [number, number][] = [];
    for (let i = 0; i < count; i++) for (let j = i + 1; j < count; j++) out.push([i, j]);
    return out;
  }
  // Switch — every NPU connects to the hub (synthetic node not in array).
  // We render the hub separately; here we draw each NPU's spoke to center.
  return [];
}
