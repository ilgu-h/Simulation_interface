"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { TopologyView } from "@/components/topology/TopologyView";
import {
  defaultMemoryConfig,
  defaultNetworkConfig,
  defaultSystemConfig,
  listWorkloadLibrary,
  startRun,
  validateRun,
  type ConfigBundle,
  type LibraryEntry,
  type RunValidateResponse,
  type WorkloadRef,
} from "@/lib/api";

const REFERENCE_4NPU_PREFIX =
  "frameworks/astra-sim/examples/workload/microbenchmarks/reduce_scatter/4npus_1MB/reduce_scatter";

export default function ValidatePage() {
  return (
    <Suspense fallback={<p className="text-sm text-zinc-500">Loading...</p>}>
      <ValidateContent />
    </Suspense>
  );
}

function ValidateContent() {
  const searchParams = useSearchParams();
  const initialPrefix = searchParams.get("workload") ?? REFERENCE_4NPU_PREFIX;

  const [library, setLibrary] = useState<LibraryEntry[]>([]);
  const [workload, setWorkload] = useState<WorkloadRef>({
    kind: "existing",
    value: initialPrefix,
  });
  const [bundle, setBundle] = useState<ConfigBundle>({
    backend: "analytical_cu",
    system: defaultSystemConfig(),
    network: defaultNetworkConfig(),
    memory: defaultMemoryConfig(),
  });
  const [result, setResult] = useState<RunValidateResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [smokeBusy, setSmokeBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Hint: Ring_4 reference matches the 4-NPU microbenchmark.
  useEffect(() => {
    setBundle((b) => ({
      ...b,
      network: {
        topology: ["Ring"],
        npus_count: [4],
        bandwidth: [50.0],
        latency: [500.0],
      },
    }));
  }, []);

  useEffect(() => {
    listWorkloadLibrary().then(setLibrary).catch((e) => setError((e as Error).message));
  }, []);

  // Auto-validate on workload + bundle changes (excluding smoke).
  useEffect(() => {
    setBusy(true);
    const t = setTimeout(async () => {
      try {
        const r = await validateRun({ workload, bundle, smoke_run: false });
        setResult(r);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBusy(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [workload, bundle]);

  const onSmoke = async () => {
    setSmokeBusy(true);
    setError(null);
    try {
      const r = await validateRun({ workload, bundle, smoke_run: true });
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSmokeBusy(false);
    }
  };

  const router = useRouter();
  const [starting, setStarting] = useState(false);
  const onStartRun = async () => {
    setStarting(true);
    setError(null);
    try {
      const r = await startRun({ workload, bundle });
      router.push(`/run/${r.run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(false);
    }
  };

  // Workload selector helper: distinct prefixes from the library.
  const prefixOptions = useMemo(() => {
    const set = new Set<string>();
    for (const e of library) {
      // Strip ".N.et" suffix to get prefix.
      const m = e.name.match(/^(.+)\.\d+\.et$/);
      const localPrefix = m ? m[1] : e.name;
      const fullPrefix =
        e.source === "examples"
          ? `frameworks/astra-sim/examples/workload/${localPrefix}`
          : `runs/${e.run_id}/traces/${localPrefix}`;
      set.add(fullPrefix);
    }
    return Array.from(set).sort();
  }, [library]);

  const errorDimIdx = useMemo(() => {
    for (const issue of result?.issues ?? []) {
      if (issue.severity === "error" && issue.field.startsWith("network.npus_count")) {
        const m = issue.field.match(/\[(\d+)\]/);
        return m ? Number(m[1]) : 0;
      }
    }
    return null;
  }, [result]);

  const errors = (result?.issues ?? []).filter((i) => i.severity === "error");
  const warnings = (result?.issues ?? []).filter((i) => i.severity === "warning");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Validate</h1>
        <p className="text-sm text-zinc-400">
          Pre-flight: schema, NPU consistency, binary, collectives, and an
          optional 4-NPU smoke run on the bundled microbenchmark.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <section className="space-y-5">
          <div className="space-y-2">
            <label className="block text-xs uppercase tracking-wide text-zinc-500">
              Workload (.et prefix)
            </label>
            <input
              value={workload.value}
              onChange={(e) => setWorkload({ ...workload, value: e.target.value })}
              className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 font-mono text-xs"
            />
            {prefixOptions.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {prefixOptions.slice(0, 8).map((p) => (
                  <button
                    key={p}
                    onClick={() => setWorkload({ kind: "existing", value: p })}
                    className="rounded border border-zinc-800 px-2 py-0.5 font-mono text-[10px] text-zinc-400 transition hover:border-zinc-600 hover:text-zinc-100"
                  >
                    {p.replace("frameworks/astra-sim/examples/workload/", "")}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <NumField
              label="dim0 NPUs"
              value={bundle.network.npus_count[0]}
              onChange={(v) =>
                setBundle({
                  ...bundle,
                  network: {
                    ...bundle.network,
                    npus_count: [v, ...bundle.network.npus_count.slice(1)],
                  },
                })
              }
            />
            <NumField
              label="bandwidth"
              value={bundle.network.bandwidth[0]}
              step="0.1"
              onChange={(v) =>
                setBundle({
                  ...bundle,
                  network: {
                    ...bundle.network,
                    bandwidth: [v, ...bundle.network.bandwidth.slice(1)],
                  },
                })
              }
            />
            <NumField
              label="latency"
              value={bundle.network.latency[0]}
              onChange={(v) =>
                setBundle({
                  ...bundle,
                  network: {
                    ...bundle.network,
                    latency: [v, ...bundle.network.latency.slice(1)],
                  },
                })
              }
            />
            <SelectField
              label="all-reduce impl"
              value={bundle.system["all-reduce-implementation"][0]}
              options={["ring", "direct", "halvingDoubling", "doubleBinaryTree"]}
              onChange={(v) =>
                setBundle({
                  ...bundle,
                  system: { ...bundle.system, "all-reduce-implementation": [v] },
                })
              }
            />
          </div>

          <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
            <div className="mb-1 flex items-baseline justify-between text-xs uppercase tracking-wide text-zinc-500">
              <span>Topology preview</span>
              <span>{busy ? "validating..." : ""}</span>
            </div>
            <TopologyView network={bundle.network} errorDimIdx={errorDimIdx} />
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <SummaryCard
              title="Traces"
              value={result?.workload?.trace_count ?? "—"}
              hint={result?.workload ? prettyBytes(result.workload.total_size_bytes) : ""}
            />
            <SummaryCard
              title="prod(npus_count)"
              value={bundle.network.npus_count.reduce((a, b) => a * b, 1)}
              hint={
                result?.workload
                  ? result.workload.trace_count ===
                    bundle.network.npus_count.reduce((a, b) => a * b, 1)
                    ? "matches"
                    : "mismatch"
                  : ""
              }
            />
            <SummaryCard
              title="Binary"
              value={result?.binary_present ? "ready" : "missing"}
              hint={bundle.backend}
            />
            <SummaryCard
              title="Est. wall"
              value={
                result?.estimated_run_seconds != null
                  ? `${(result.estimated_run_seconds * 1000).toFixed(1)}ms`
                  : "—"
              }
              hint="rough"
            />
          </div>

          <div className="flex gap-2">
            <button
              onClick={onSmoke}
              disabled={smokeBusy || errors.length > 0}
              className="flex-1 rounded border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm text-zinc-200 transition hover:border-zinc-500 disabled:opacity-50"
            >
              {smokeBusy ? "Running smoke..." : "Smoke (4-NPU bundled)"}
            </button>
            <button
              onClick={onStartRun}
              disabled={starting || errors.length > 0}
              className="flex-1 rounded bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
            >
              {starting ? "Starting..." : "Start run →"}
            </button>
          </div>

          {result?.smoke && (
            <div
              className={`rounded border p-3 text-sm ${
                result.smoke.returncode === 0
                  ? "border-emerald-900/50 bg-emerald-950/30 text-emerald-100"
                  : "border-red-900/60 bg-red-950/40 text-red-100"
              }`}
            >
              <div className="font-mono text-xs">
                returncode={result.smoke.returncode} ·{" "}
                {result.smoke.duration_sec?.toFixed(3)}s
              </div>
              {result.smoke.stderr_tail && (
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer">stderr</summary>
                  <pre className="mt-1 whitespace-pre-wrap font-mono">
                    {result.smoke.stderr_tail}
                  </pre>
                </details>
              )}
              <details className="mt-2 text-xs opacity-80">
                <summary className="cursor-pointer">stdout tail</summary>
                <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap font-mono">
                  {result.smoke.stdout_tail}
                </pre>
              </details>
            </div>
          )}
        </section>

        <section className="space-y-3">
          <Banner ok={!!result?.ok} />
          {error && (
            <div className="rounded border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
              {error}
            </div>
          )}
          <IssueList title="Errors" issues={errors} tone="error" />
          <IssueList title="Warnings" issues={warnings} tone="warning" />
        </section>
      </div>
    </div>
  );
}

function Banner({ ok }: { ok: boolean }) {
  return (
    <div
      className={`rounded border p-3 text-sm font-medium ${
        ok
          ? "border-emerald-900/50 bg-emerald-950/30 text-emerald-100"
          : "border-amber-900/50 bg-amber-950/30 text-amber-100"
      }`}
    >
      {ok ? "Pre-flight OK — ready to run." : "Pre-flight blocked — fix errors below."}
    </div>
  );
}

function IssueList({
  title,
  issues,
  tone,
}: {
  title: string;
  issues: { severity: string; field: string; message: string }[];
  tone: "error" | "warning";
}) {
  if (issues.length === 0) return null;
  const cls =
    tone === "error"
      ? "border-red-900/60 bg-red-950/30 text-red-100"
      : "border-amber-900/60 bg-amber-950/30 text-amber-100";
  return (
    <div className={`rounded border ${cls} p-3 text-sm`}>
      <div className="mb-2 text-xs uppercase tracking-wide opacity-70">{title}</div>
      <ul className="space-y-1">
        {issues.map((iss, i) => (
          <li key={i} className="text-xs">
            <span className="font-mono opacity-80">{iss.field}</span> · {iss.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  hint,
}: {
  title: string;
  value: number | string;
  hint?: string;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="text-xs uppercase tracking-wide text-zinc-500">{title}</div>
      <div className="mt-1 font-mono text-lg text-zinc-100">{value}</div>
      {hint && <div className="text-[10px] text-zinc-500">{hint}</div>}
    </div>
  );
}

function NumField({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step?: string;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block">
      <span className="block text-xs uppercase tracking-wide text-zinc-500">{label}</span>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 font-mono text-sm"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <label className="block">
      <span className="block text-xs uppercase tracking-wide text-zinc-500">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function prettyBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}
