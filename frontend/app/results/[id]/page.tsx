"use client";

import { useEffect, useMemo, useState } from "react";

import {
  compareRuns,
  getStats,
  getSummary,
  logUrl,
  timelineUrl,
  type CompareResult,
  type PerCollectiveRow,
  type PerNpuRow,
  type RunSummary,
} from "@/lib/api";

type Tab = "summary" | "per_npu" | "per_collective" | "timeline" | "logs" | "compare";

export default function ResultsPage({
  params,
  searchParams,
}: {
  params: { id: string };
  searchParams: { compare?: string };
}) {
  const runId = params.id;
  const compareWith = searchParams.compare ?? null;
  const [tab, setTab] = useState<Tab>(compareWith ? "compare" : "summary");
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSummary(runId)
      .then(setSummary)
      .catch((e) => setError((e as Error).message));
  }, [runId]);

  const tabs: { id: Tab; label: string }[] = [
    { id: "summary", label: "Summary" },
    { id: "per_npu", label: "Per-NPU" },
    { id: "per_collective", label: "Per-collective" },
    { id: "timeline", label: "Timeline" },
    { id: "logs", label: "Logs" },
    { id: "compare", label: "Compare" },
  ];

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            Results <span className="font-mono text-zinc-400">{runId}</span>
          </h1>
          {summary && (
            <p className="text-xs text-zinc-500">
              {summary.npu_count} NPUs · {summary.end_to_end_cycles.toLocaleString()} cycles
              end-to-end
            </p>
          )}
        </div>
        <a
          href={`/run/${runId}`}
          className="rounded border border-zinc-800 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-zinc-600"
        >
          ← Run page
        </a>
      </div>

      {error && (
        <div className="rounded border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="flex gap-1 border-b border-zinc-800 text-sm">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`-mb-px border-b-2 px-3 py-2 transition ${
              tab === t.id
                ? "border-zinc-100 text-zinc-100"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "summary" && summary && <SummaryTab s={summary} />}
      {tab === "per_npu" && <PerNpuTab runId={runId} />}
      {tab === "per_collective" && <PerCollectiveTab runId={runId} />}
      {tab === "timeline" && <TimelineTab runId={runId} />}
      {tab === "logs" && <LogsTab runId={runId} />}
      {tab === "compare" && <CompareTab runId={runId} initialOther={compareWith} />}
    </div>
  );
}

function SummaryTab({ s }: { s: RunSummary }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Card title="End-to-end" value={s.end_to_end_cycles.toLocaleString()} unit="cycles" />
      <Card title="NPUs" value={s.npu_count} />
      <Card title="Slowest NPU" value={s.slowest_npu ?? "—"} />
      <Card
        title="Comm fraction"
        value={(s.avg_comm_fraction * 100).toFixed(1) + "%"}
        hint="avg across NPUs"
      />
      <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3 sm:col-span-2 lg:col-span-4">
        <div className="text-xs uppercase tracking-wide text-zinc-500">Top collectives</div>
        <table className="mt-2 w-full text-sm">
          <thead className="text-left text-xs text-zinc-500">
            <tr>
              <th className="py-1 pr-4">Type</th>
              <th className="py-1 pr-4 text-right">Count</th>
              <th className="py-1 pr-4 text-right">Total bytes</th>
            </tr>
          </thead>
          <tbody>
            {s.top_collectives.map((c) => (
              <tr key={c.comm_type} className="border-t border-zinc-900">
                <td className="py-1 pr-4 font-mono text-zinc-200">{c.comm_type}</td>
                <td className="py-1 pr-4 text-right tabular-nums">{c.count}</td>
                <td className="py-1 pr-4 text-right tabular-nums">
                  {prettyBytes(c.total_bytes)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PerNpuTab({ runId }: { runId: string }) {
  const [rows, setRows] = useState<PerNpuRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getStats<PerNpuRow>(runId, "per_npu").then(setRows).catch((e) => setError((e as Error).message));
  }, [runId]);
  if (error) return <ErrorBox message={error} />;
  if (!rows) return <p className="text-sm text-zinc-500">Loading...</p>;
  if (rows.length === 0) return <p className="text-sm text-zinc-500">No per-NPU stats parsed.</p>;
  const maxWall = Math.max(...rows.map((r) => r.wall_cycles));
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-zinc-500">
        <tr>
          <th className="py-2 pr-4">NPU</th>
          <th className="py-2 pr-4 text-right">Wall</th>
          <th className="py-2 pr-4 text-right">Comm</th>
          <th className="py-2 pr-4 text-right">Compute</th>
          <th className="py-2 pr-4 text-right">Comm %</th>
          <th className="py-2 pr-4">Bar</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.npu_id} className="border-t border-zinc-900">
            <td className="py-1 pr-4 font-mono">{r.npu_id}</td>
            <td className="py-1 pr-4 text-right tabular-nums">
              {r.wall_cycles.toLocaleString()}
            </td>
            <td className="py-1 pr-4 text-right tabular-nums">
              {r.comm_cycles.toLocaleString()}
            </td>
            <td className="py-1 pr-4 text-right tabular-nums">
              {r.compute_cycles.toLocaleString()}
            </td>
            <td className="py-1 pr-4 text-right tabular-nums">
              {(r.comm_fraction * 100).toFixed(1)}%
            </td>
            <td className="py-1 pr-4">
              <div className="h-2 w-48 overflow-hidden rounded bg-zinc-900">
                <div
                  className="h-full bg-blue-700"
                  style={{ width: `${(r.comm_cycles / maxWall) * 100}%` }}
                  title={`comm ${r.comm_cycles}`}
                />
                <div
                  className="-mt-2 h-full bg-emerald-700"
                  style={{
                    marginLeft: `${(r.comm_cycles / maxWall) * 100}%`,
                    width: `${(r.compute_cycles / maxWall) * 100}%`,
                  }}
                  title={`compute ${r.compute_cycles}`}
                />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PerCollectiveTab({ runId }: { runId: string }) {
  const [rows, setRows] = useState<PerCollectiveRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getStats<PerCollectiveRow>(runId, "per_collective")
      .then(setRows)
      .catch((e) => setError((e as Error).message));
  }, [runId]);
  if (error) return <ErrorBox message={error} />;
  if (!rows) return <p className="text-sm text-zinc-500">Loading...</p>;
  if (rows.length === 0) return <p className="text-sm text-zinc-500">No collectives in trace.</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs text-zinc-500">
        <tr>
          <th className="py-2 pr-4">NPU</th>
          <th className="py-2 pr-4">Type</th>
          <th className="py-2 pr-4">Name</th>
          <th className="py-2 pr-4 text-right">Bytes</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.npu_id}-${r.node_id}-${i}`} className="border-t border-zinc-900">
            <td className="py-1 pr-4 font-mono">{r.npu_id}</td>
            <td className="py-1 pr-4 font-mono text-zinc-200">{r.comm_type}</td>
            <td className="py-1 pr-4 font-mono text-xs text-zinc-400">{r.name}</td>
            <td className="py-1 pr-4 text-right tabular-nums">
              {prettyBytes(r.comm_size_bytes)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function TimelineTab({ runId }: { runId: string }) {
  return (
    <div className="space-y-3 text-sm">
      <p className="text-zinc-400">
        Chrome Tracing JSON — drop into{" "}
        <a
          href="https://ui.perfetto.dev"
          className="text-blue-400 underline"
          target="_blank"
          rel="noreferrer"
        >
          ui.perfetto.dev
        </a>{" "}
        (or chrome://tracing) to inspect per-NPU compute / comm bands and
        per-collective markers.
      </p>
      <a
        href={timelineUrl(runId)}
        download
        className="inline-block rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 transition hover:border-zinc-500"
      >
        Download timeline.json
      </a>
      <p className="text-xs text-zinc-500">
        Note: the analytical backend doesn&apos;t emit per-collective issue
        timestamps, so the timeline is approximate (compute and comm bands
        sized to measured cycles; collectives shown as instant markers).
      </p>
    </div>
  );
}

function LogsTab({ runId }: { runId: string }) {
  const logs = ["log.log", "stdout.log", "err.log", "events.log"];
  return (
    <ul className="space-y-2 text-sm">
      {logs.map((name) => (
        <li key={name} className="flex items-center justify-between rounded border border-zinc-800 bg-zinc-900/40 px-3 py-2">
          <span className="font-mono text-zinc-200">{name}</span>
          <a
            href={logUrl(runId, name)}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-blue-400 underline"
          >
            open
          </a>
        </li>
      ))}
    </ul>
  );
}

function CompareTab({ runId, initialOther }: { runId: string; initialOther: string | null }) {
  const [other, setOther] = useState(initialOther ?? "");
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onCompare = async () => {
    if (!other) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await compareRuns(runId, other));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // Auto-fire when the URL came pre-populated.
  useEffect(() => {
    if (initialOther) onCompare();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <input
          value={other}
          onChange={(e) => setOther(e.target.value)}
          placeholder="other run id"
          className="flex-1 rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 font-mono text-sm"
        />
        <button
          onClick={onCompare}
          disabled={busy || !other}
          className="rounded bg-zinc-100 px-4 py-1.5 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
        >
          {busy ? "Comparing..." : "Compare"}
        </button>
      </div>
      {error && <ErrorBox message={error} />}
      {result && <CompareView r={result} />}
    </div>
  );
}

function CompareView({ r }: { r: CompareResult }) {
  const sign = r.e2e_delta_cycles > 0 ? "+" : "";
  const tone = r.e2e_delta_cycles > 0 ? "text-amber-300" : "text-emerald-300";
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-3">
        <Card title="A wall" value={r.summary_a.end_to_end_cycles.toLocaleString()} unit="cycles" hint={r.a} />
        <Card title="B wall" value={r.summary_b.end_to_end_cycles.toLocaleString()} unit="cycles" hint={r.b} />
        <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
          <div className="text-xs uppercase tracking-wide text-zinc-500">Δ B − A</div>
          <div className={`mt-1 font-mono text-lg ${tone}`}>
            {sign}
            {r.e2e_delta_cycles.toLocaleString()} cycles ({sign}
            {r.e2e_delta_pct.toFixed(1)}%)
          </div>
        </div>
      </div>
      <div>
        <div className="mb-1 text-xs uppercase tracking-wide text-zinc-500">
          Config diffs ({r.config_diffs.length})
        </div>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-zinc-500">
            <tr>
              <th className="py-1 pr-4">Path</th>
              <th className="py-1 pr-4">A</th>
              <th className="py-1 pr-4">B</th>
            </tr>
          </thead>
          <tbody>
            {r.config_diffs.map((d) => (
              <tr key={d.path} className="border-t border-zinc-900">
                <td className="py-1 pr-4 font-mono text-xs text-zinc-300">{d.path}</td>
                <td className="py-1 pr-4 font-mono text-xs text-zinc-400">{stringify(d.a)}</td>
                <td className="py-1 pr-4 font-mono text-xs text-zinc-100">{stringify(d.b)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Card({
  title,
  value,
  unit,
  hint,
}: {
  title: string;
  value: number | string;
  unit?: string;
  hint?: string;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="text-xs uppercase tracking-wide text-zinc-500">{title}</div>
      <div className="mt-1 font-mono text-lg text-zinc-100">
        {value}
        {unit && <span className="ml-1 text-xs text-zinc-500">{unit}</span>}
      </div>
      {hint && <div className="text-[10px] text-zinc-500">{hint}</div>}
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
      {message}
    </div>
  );
}

function prettyBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(2)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function stringify(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
