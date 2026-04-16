"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { TopologyView } from "@/components/topology/TopologyView";
import {
  defaultMemoryConfig,
  defaultNetworkConfig,
  defaultSystemConfig,
  listBackends,
  materializeConfigs,
  validateConfigs,
  type BackendInfo,
  type ConfigBundle,
  type Issue,
  type MaterializeResponse,
  type MemoryConfig,
  type MemoryType,
  type NetworkConfig,
  type SystemConfig,
  type TopologyKind,
} from "@/lib/api";

export default function SystemPage() {
  return (
    <Suspense fallback={<p className="text-sm text-zinc-500">Loading...</p>}>
      <SystemContent />
    </Suspense>
  );
}

/** Parse workload context from URL search params (if arriving from Workload page). */
type WorkloadContext = {
  npus: number;
  dp: number;
  tp: number;
  sp: number;
  pp: number;
  ep: number;
  workload: string | null;
};

function parseWorkloadContext(params: URLSearchParams): WorkloadContext | null {
  const npus = params.get("npus");
  if (!npus) return null;
  return {
    npus: Number(npus),
    dp: Number(params.get("dp") ?? 1),
    tp: Number(params.get("tp") ?? 1),
    sp: Number(params.get("sp") ?? 1),
    pp: Number(params.get("pp") ?? 1),
    ep: Number(params.get("ep") ?? 1),
    workload: params.get("workload"),
  };
}

function SystemContent() {
  const searchParams = useSearchParams();
  const workloadCtx = useMemo(() => parseWorkloadContext(searchParams), [searchParams]);
  const [bannerDismissed, setBannerDismissed] = useState(false);

  const [backends, setBackends] = useState<BackendInfo[]>([]);
  const [bundle, setBundle] = useState<ConfigBundle>({
    backend: "analytical_cu",
    system: defaultSystemConfig(),
    network: defaultNetworkConfig(),
    memory: defaultMemoryConfig(),
    expected_npus: null,
  });
  const [issues, setIssues] = useState<Issue[]>([]);
  const [validating, setValidating] = useState(false);
  const [materialized, setMaterialized] = useState<MaterializeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listBackends().then(setBackends).catch((e) => setError((e as Error).message));
  }, []);

  // Auto-fill NPU count + expected_npus from workload context (on mount only).
  useEffect(() => {
    if (!workloadCtx) return;
    setBundle((prev) => ({
      ...prev,
      network: {
        ...prev.network,
        npus_count: [workloadCtx.npus, ...prev.network.npus_count.slice(1)],
      },
      expected_npus: workloadCtx.npus,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-validate on every change (debounced lightly via setTimeout).
  useEffect(() => {
    setValidating(true);
    const t = setTimeout(async () => {
      try {
        const r = await validateConfigs(bundle);
        setIssues(r.issues);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setValidating(false);
      }
    }, 200);
    return () => clearTimeout(t);
  }, [bundle]);

  const totalNpus = useMemo(
    () => bundle.network.npus_count.reduce((a, b) => a * b, 1),
    [bundle.network.npus_count],
  );

  const errorDimIdx = useMemo(() => {
    for (const issue of issues) {
      if (issue.severity === "error" && issue.field.startsWith("network.npus_count")) {
        const m = issue.field.match(/\[(\d+)\]/);
        return m ? Number(m[1]) : 0;
      }
    }
    return null;
  }, [issues]);

  const setNetwork = (next: NetworkConfig) => setBundle({ ...bundle, network: next });
  const setSystem = (next: SystemConfig) => setBundle({ ...bundle, system: next });
  const setMemory = (next: MemoryConfig) => setBundle({ ...bundle, memory: next });

  const onMaterialize = async () => {
    setError(null);
    setMaterialized(null);
    try {
      const r = await materializeConfigs(bundle);
      setMaterialized(r);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const hasError = issues.some((i) => i.severity === "error");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">System / Network / Memory</h1>
        <p className="text-sm text-zinc-400">
          Configure the simulator. Validation runs live; materialize writes
          three config files into <code>runs/&lt;id&gt;/configs/</code>.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <section className="space-y-6">
          {workloadCtx && !bannerDismissed && (
            <WorkloadContextBanner ctx={workloadCtx} onDismiss={() => setBannerDismissed(true)} />
          )}

          <BackendPicker
            backends={backends}
            value={bundle.backend}
            onChange={(b) => setBundle({ ...bundle, backend: b })}
          />

          <NetworkSection network={bundle.network} onChange={setNetwork} />

          <SystemSection system={bundle.system} onChange={setSystem} />

          <MemorySection memory={bundle.memory} onChange={setMemory} />

          <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3 text-sm">
            <div className="flex items-baseline justify-between">
              <span className="text-zinc-400">prod(npus_count)</span>
              <span className="font-mono text-lg">{totalNpus}</span>
            </div>
          </div>

          <div className="space-y-2">
            <label className="block text-xs uppercase tracking-wide text-zinc-500">
              Expected NPU count (cross-check vs workload)
            </label>
            <input
              type="number"
              min={1}
              value={bundle.expected_npus ?? ""}
              placeholder="leave blank to skip cross-check"
              onChange={(e) =>
                setBundle({
                  ...bundle,
                  expected_npus: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 font-mono text-sm"
            />
          </div>

          <button
            onClick={onMaterialize}
            disabled={hasError}
            className="w-full rounded bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
          >
            Materialize configs
          </button>
        </section>

        <section className="space-y-4">
          <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
            <div className="mb-1 flex items-baseline justify-between text-xs uppercase tracking-wide text-zinc-500">
              <span>Topology</span>
              <span>{validating ? "validating..." : ""}</span>
            </div>
            <TopologyView network={bundle.network} errorDimIdx={errorDimIdx} />
          </div>

          <IssueList issues={issues} />

          {error && <ErrorBox message={error} />}

          {materialized && (
            <div className="rounded border border-emerald-900/50 bg-emerald-950/30 p-3 text-sm">
              <div className="text-emerald-200">
                Materialized run{" "}
                <span className="font-mono">{materialized.run_id}</span>
              </div>
              <ul className="mt-2 space-y-1 font-mono text-xs text-emerald-100/80">
                <li>{materialized.files.network}</li>
                <li>{materialized.files.system}</li>
                <li>{materialized.files.memory}</li>
              </ul>
              <div className="mt-3 border-t border-emerald-900/50 pt-3">
                <Link
                  href={
                    workloadCtx?.workload
                      ? `/validate?workload=${encodeURIComponent(workloadCtx.workload)}`
                      : "/validate"
                  }
                  className="block rounded bg-zinc-100 px-4 py-2 text-center text-sm font-medium text-zinc-900 transition hover:bg-white"
                >
                  Continue to Validate →
                </Link>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function WorkloadContextBanner({
  ctx,
  onDismiss,
}: {
  ctx: WorkloadContext;
  onDismiss: () => void;
}) {
  const dims = [
    `DP=${ctx.dp}`,
    `TP=${ctx.tp}`,
    `SP=${ctx.sp}`,
    `PP=${ctx.pp}`,
    ...(ctx.ep > 1 ? [`EP=${ctx.ep}`] : []),
  ].join(" \u00d7 ");

  return (
    <div className="flex items-start justify-between rounded border border-blue-900/50 bg-blue-950/40 p-3">
      <div>
        <div className="text-[10px] uppercase tracking-wide text-blue-400">
          Workload context
        </div>
        <div className="mt-1 text-sm text-zinc-100">
          <strong>{ctx.npus} NPUs</strong>
          <span className="text-zinc-400"> — {dims}</span>
        </div>
        {ctx.workload && (
          <div className="mt-0.5 truncate font-mono text-xs text-zinc-500">
            {ctx.workload}
          </div>
        )}
      </div>
      <button
        onClick={onDismiss}
        className="ml-3 text-zinc-500 transition hover:text-zinc-300"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}

function BackendPicker({
  backends,
  value,
  onChange,
}: {
  backends: BackendInfo[];
  value: string;
  onChange: (s: string) => void;
}) {
  return (
    <div>
      <label className="block text-xs uppercase tracking-wide text-zinc-500">
        Simulation backend
      </label>
      <select
        className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {backends.map((b) => (
          <option key={b.name} value={b.name}>
            {b.label} {b.built ? "" : "(needs build)"}
          </option>
        ))}
      </select>
    </div>
  );
}

function NetworkSection({
  network,
  onChange,
}: {
  network: NetworkConfig;
  onChange: (n: NetworkConfig) => void;
}) {
  const setDim = (i: number, patch: Partial<{ topology: TopologyKind; npus_count: number; bandwidth: number; latency: number }>) => {
    const next: NetworkConfig = {
      topology: [...network.topology],
      npus_count: [...network.npus_count],
      bandwidth: [...network.bandwidth],
      latency: [...network.latency],
    };
    if (patch.topology !== undefined) next.topology[i] = patch.topology;
    if (patch.npus_count !== undefined) next.npus_count[i] = patch.npus_count;
    if (patch.bandwidth !== undefined) next.bandwidth[i] = patch.bandwidth;
    if (patch.latency !== undefined) next.latency[i] = patch.latency;
    onChange(next);
  };

  const addDim = () =>
    onChange({
      topology: [...network.topology, "Ring"],
      npus_count: [...network.npus_count, 2],
      bandwidth: [...network.bandwidth, 50.0],
      latency: [...network.latency, 500.0],
    });

  const removeDim = (i: number) =>
    onChange({
      topology: network.topology.filter((_, idx) => idx !== i),
      npus_count: network.npus_count.filter((_, idx) => idx !== i),
      bandwidth: network.bandwidth.filter((_, idx) => idx !== i),
      latency: network.latency.filter((_, idx) => idx !== i),
    });

  return (
    <div className="space-y-3">
      <SectionTitle>Network (analytical)</SectionTitle>
      <div className="space-y-2">
        {network.topology.map((t, i) => (
          <div key={i} className="grid grid-cols-[1.4fr_1fr_1fr_1fr_auto] items-end gap-2">
            <Field label={`dim${i} topology`}>
              <select
                value={t}
                onChange={(e) => setDim(i, { topology: e.target.value as TopologyKind })}
                className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
              >
                {(["Ring", "FullyConnected", "Switch"] as const).map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="npus">
              <NumInput
                value={network.npus_count[i]}
                min={1}
                onChange={(v) => setDim(i, { npus_count: v })}
              />
            </Field>
            <Field label="bw GB/s">
              <NumInput
                value={network.bandwidth[i]}
                step="0.1"
                onChange={(v) => setDim(i, { bandwidth: v })}
              />
            </Field>
            <Field label="lat ns">
              <NumInput
                value={network.latency[i]}
                step="0.01"
                onChange={(v) => setDim(i, { latency: v })}
              />
            </Field>
            <button
              onClick={() => removeDim(i)}
              disabled={network.topology.length === 1}
              className="rounded border border-zinc-800 px-2 py-1.5 text-xs text-zinc-400 transition hover:border-red-800 hover:text-red-400 disabled:opacity-40"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <button
        onClick={addDim}
        className="rounded border border-dashed border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200"
      >
        + add dim
      </button>
    </div>
  );
}

function SystemSection({
  system,
  onChange,
}: {
  system: SystemConfig;
  onChange: (s: SystemConfig) => void;
}) {
  const set = <K extends keyof SystemConfig>(k: K, v: SystemConfig[K]) =>
    onChange({ ...system, [k]: v });

  return (
    <div className="space-y-3">
      <SectionTitle>System</SectionTitle>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Field label="scheduling">
          <select
            value={system["scheduling-policy"]}
            onChange={(e) => set("scheduling-policy", e.target.value as "LIFO" | "FIFO")}
            className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
          >
            <option>LIFO</option>
            <option>FIFO</option>
          </select>
        </Field>
        <Field label="endpoint-delay">
          <NumInput value={system["endpoint-delay"]} onChange={(v) => set("endpoint-delay", v)} />
        </Field>
        <Field label="active-chunks">
          <NumInput
            value={system["active-chunks-per-dimension"]}
            min={1}
            onChange={(v) => set("active-chunks-per-dimension", v)}
          />
        </Field>
        <Field label="dataset-splits">
          <NumInput
            value={system["preferred-dataset-splits"]}
            min={1}
            onChange={(v) => set("preferred-dataset-splits", v)}
          />
        </Field>
        <Field label="local-mem-bw">
          <NumInput value={system["local-mem-bw"]} onChange={(v) => set("local-mem-bw", v)} />
        </Field>
        <Field label="boost-mode">
          <select
            value={system["boost-mode"]}
            onChange={(e) => set("boost-mode", Number(e.target.value) as 0 | 1)}
            className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
          >
            <option value={0}>0</option>
            <option value={1}>1</option>
          </select>
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(
          [
            "all-reduce-implementation",
            "all-gather-implementation",
            "reduce-scatter-implementation",
            "all-to-all-implementation",
          ] as const
        ).map((k) => (
          <Field key={k} label={k.replace("-implementation", "")}>
            <input
              value={system[k][0] ?? ""}
              onChange={(e) => set(k, [e.target.value])}
              className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 font-mono text-sm"
            />
          </Field>
        ))}
      </div>
      <Field label="collective-optimization">
        <select
          value={system["collective-optimization"]}
          onChange={(e) =>
            set("collective-optimization", e.target.value as "localBWAware" | "")
          }
          className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
        >
          <option value="localBWAware">localBWAware</option>
          <option value="">(empty)</option>
        </select>
      </Field>
    </div>
  );
}

const MEMORY_TYPES: { value: MemoryType; label: string; hint: string }[] = [
  {
    value: "NO_MEMORY_EXPANSION",
    label: "No memory expansion",
    hint: "No remote memory access",
  },
  {
    value: "PER_NODE_MEMORY_EXPANSION",
    label: "Per-node expansion",
    hint: "Each node has dedicated remote memory; transactions serialized per node",
  },
  {
    value: "PER_NPU_MEMORY_EXPANSION",
    label: "Per-NPU expansion",
    hint: "Each NPU has independent remote memory access",
  },
  {
    value: "MEMORY_POOL",
    label: "Memory pool",
    hint: "Single shared pool; transactions serialized globally",
  },
];

function MemorySection({
  memory,
  onChange,
}: {
  memory: MemoryConfig;
  onChange: (m: MemoryConfig) => void;
}) {
  const isExpansion = memory["memory-type"] !== "NO_MEMORY_EXPANSION";
  const isPerNode = memory["memory-type"] === "PER_NODE_MEMORY_EXPANSION";

  const setType = (t: MemoryType) => {
    const next: MemoryConfig = {
      ...memory,
      "memory-type": t,
    };
    if (t === "NO_MEMORY_EXPANSION") {
      next["remote-mem-latency"] = 0;
      next["remote-mem-bw"] = 0;
      next["num-nodes"] = null;
      next["num-npus-per-node"] = null;
    }
    if (t !== "PER_NODE_MEMORY_EXPANSION") {
      next["num-nodes"] = null;
      next["num-npus-per-node"] = null;
    }
    onChange(next);
  };

  return (
    <div className="space-y-3">
      <SectionTitle>Memory</SectionTitle>
      <Field label="memory type">
        <select
          value={memory["memory-type"]}
          onChange={(e) => setType(e.target.value as MemoryType)}
          className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
        >
          {MEMORY_TYPES.map((mt) => (
            <option key={mt.value} value={mt.value}>
              {mt.label}
            </option>
          ))}
        </select>
      </Field>
      <p className="text-xs text-zinc-500">
        {MEMORY_TYPES.find((mt) => mt.value === memory["memory-type"])?.hint}
      </p>

      {isExpansion && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="latency (ns)">
            <NumInput
              value={memory["remote-mem-latency"]}
              min={0}
              onChange={(v) => onChange({ ...memory, "remote-mem-latency": v })}
            />
          </Field>
          <Field label="bandwidth (GB/s)">
            <NumInput
              value={memory["remote-mem-bw"]}
              min={0}
              onChange={(v) => onChange({ ...memory, "remote-mem-bw": v })}
            />
          </Field>
          {isPerNode && (
            <>
              <Field label="num-nodes">
                <NumInput
                  value={memory["num-nodes"] ?? 0}
                  min={1}
                  onChange={(v) => onChange({ ...memory, "num-nodes": v })}
                />
              </Field>
              <Field label="npus-per-node">
                <NumInput
                  value={memory["num-npus-per-node"] ?? 0}
                  min={1}
                  onChange={(v) => onChange({ ...memory, "num-npus-per-node": v })}
                />
              </Field>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function IssueList({ issues }: { issues: Issue[] }) {
  if (issues.length === 0) {
    return (
      <div className="rounded border border-emerald-900/50 bg-emerald-950/20 p-3 text-sm text-emerald-200">
        No issues.
      </div>
    );
  }
  const colorFor = (s: Issue["severity"]) =>
    s === "error"
      ? "border-red-900/60 bg-red-950/30 text-red-200"
      : s === "warning"
        ? "border-amber-900/60 bg-amber-950/30 text-amber-200"
        : "border-zinc-800 bg-zinc-900 text-zinc-300";
  return (
    <ul className="space-y-2">
      {issues.map((iss, idx) => (
        <li key={idx} className={`rounded border p-2 text-xs ${colorFor(iss.severity)}`}>
          <span className="mr-2 font-mono uppercase">{iss.severity}</span>
          <span className="font-mono">{iss.field}</span>: {iss.message}
        </li>
      ))}
    </ul>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-300">{children}</h2>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs uppercase tracking-wide text-zinc-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function NumInput({
  value,
  min,
  step,
  onChange,
}: {
  value: number;
  min?: number;
  step?: string;
  onChange: (v: number) => void;
}) {
  return (
    <input
      type="number"
      value={value}
      min={min}
      step={step}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 font-mono text-sm"
    />
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
      {message}
    </div>
  );
}
