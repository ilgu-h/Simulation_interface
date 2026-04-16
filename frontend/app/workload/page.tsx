"use client";

import { useEffect, useMemo, useState } from "react";

import {
  defaultStgSpec,
  generateWorkload,
  listPresets,
  listWorkloadLibrary,
  type GenerateResponse,
  type LibraryEntry,
  type Preset,
  type StgSpec,
} from "@/lib/api";

type Tab = "select" | "generate";

export default function WorkloadPage() {
  const [tab, setTab] = useState<Tab>("select");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Workload</h1>
        <p className="text-sm text-zinc-400">
          Pick an existing .et trace, or generate a new one with STG.
        </p>
      </div>

      <div className="flex gap-2 border-b border-zinc-800">
        {(["select", "generate"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm transition ${
              tab === t
                ? "border-zinc-100 text-zinc-100"
                : "border-transparent text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {t === "select" ? "Select existing" : "Generate new"}
          </button>
        ))}
      </div>

      {tab === "select" ? <LibraryView /> : <GenerateView />}
    </div>
  );
}

function LibraryView() {
  const [entries, setEntries] = useState<LibraryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listWorkloadLibrary()
      .then(setEntries)
      .catch((e) => setError((e as Error).message));
  }, []);

  if (error) return <ErrorBox message={error} />;
  if (!entries) return <p className="text-sm text-zinc-500">Loading...</p>;
  if (entries.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        No traces yet. Generate one in the &ldquo;Generate new&rdquo; tab.
      </p>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
        <tr>
          <th className="py-2 pr-4">Source</th>
          <th className="py-2 pr-4">Name</th>
          <th className="py-2 pr-4">Run</th>
          <th className="py-2 pr-4 text-right">Size</th>
        </tr>
      </thead>
      <tbody>
        {entries.map((e) => (
          <tr key={e.path} className="border-t border-zinc-900">
            <td className="py-2 pr-4 font-mono text-xs text-zinc-400">{e.source}</td>
            <td className="py-2 pr-4 font-mono">{e.name}</td>
            <td className="py-2 pr-4 font-mono text-xs text-zinc-500">{e.run_id ?? ""}</td>
            <td className="py-2 pr-4 text-right tabular-nums text-zinc-400">
              {formatBytes(e.size_bytes)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GenerateView() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [spec, setSpec] = useState<StgSpec>(defaultStgSpec());
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPresets()
      .then(setPresets)
      .catch((e) => setError((e as Error).message));
  }, []);

  const totalNpus = useMemo(() => {
    const base = spec.dp * spec.tp * spec.sp * spec.pp;
    return spec.model_type === "moe" ? base * spec.ep : base;
  }, [spec.dp, spec.tp, spec.sp, spec.pp, spec.ep, spec.model_type]);

  const applyPreset = (id: string) => {
    const p = presets.find((p) => p.id === id);
    if (!p) return;
    setSpec((prev) => ({ ...prev, ...(p.spec as Partial<StgSpec>) }));
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await generateWorkload(spec);
      setResult(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_3fr]">
      <section className="space-y-4">
        <div>
          <label className="block text-xs uppercase tracking-wide text-zinc-500">Preset</label>
          <select
            className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
            defaultValue=""
            onChange={(e) => e.target.value && applyPreset(e.target.value)}
          >
            <option value="">— pick a preset —</option>
            {presets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </div>

        <FormGroup label="Model type">
          <select
            className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
            value={spec.model_type}
            onChange={(e) => setSpec({ ...spec, model_type: e.target.value as StgSpec["model_type"] })}
          >
            {(["dense", "llama", "gpt", "moe", "debug"] as const).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </FormGroup>

        <FieldGrid>
          <NumField label="DP" value={spec.dp} min={1} onChange={(v) => setSpec({ ...spec, dp: v })} />
          <NumField label="TP" value={spec.tp} min={1} onChange={(v) => setSpec({ ...spec, tp: v })} />
          <NumField label="SP" value={spec.sp} min={1} onChange={(v) => setSpec({ ...spec, sp: v })} />
          <NumField label="PP" value={spec.pp} min={1} onChange={(v) => setSpec({ ...spec, pp: v })} />
          <NumField
            label="EP"
            value={spec.ep}
            min={1}
            onChange={(v) => setSpec({ ...spec, ep: v })}
            disabled={spec.model_type !== "moe"}
          />
        </FieldGrid>

        <FieldGrid>
          <NumField label="dmodel" value={spec.dmodel} onChange={(v) => setSpec({ ...spec, dmodel: v })} />
          <NumField label="dff" value={spec.dff} onChange={(v) => setSpec({ ...spec, dff: v })} />
          <NumField label="head" value={spec.head} onChange={(v) => setSpec({ ...spec, head: v })} />
          <NumField label="kvhead" value={spec.kvhead} onChange={(v) => setSpec({ ...spec, kvhead: v })} />
          <NumField label="num_stacks" value={spec.num_stacks} onChange={(v) => setSpec({ ...spec, num_stacks: v })} />
          <NumField label="dvocal" value={spec.dvocal} onChange={(v) => setSpec({ ...spec, dvocal: v })} />
        </FieldGrid>

        <FieldGrid>
          <NumField label="batch" value={spec.batch} onChange={(v) => setSpec({ ...spec, batch: v })} />
          <NumField label="seq" value={spec.seq} onChange={(v) => setSpec({ ...spec, seq: v })} />
          <NumField
            label="micro_batch"
            value={spec.micro_batch}
            onChange={(v) => setSpec({ ...spec, micro_batch: v })}
          />
        </FieldGrid>

        <div className="rounded border border-zinc-800 bg-zinc-900/50 p-3 text-sm">
          <div className="flex items-baseline justify-between">
            <span className="text-zinc-400">Total NPUs (= dp × tp × sp × pp{spec.model_type === "moe" ? " × ep" : ""})</span>
            <span className="font-mono text-lg">{totalNpus}</span>
          </div>
        </div>

        <button
          onClick={submit}
          disabled={busy}
          className="w-full rounded bg-zinc-100 px-4 py-2 text-sm font-medium text-zinc-900 transition hover:bg-white disabled:opacity-50"
        >
          {busy ? "Generating..." : `Generate ${totalNpus} traces`}
        </button>
      </section>

      <section className="space-y-3">
        {error && <ErrorBox message={error} />}
        {result && (
          <div className="space-y-3 rounded border border-zinc-800 bg-zinc-900/50 p-4">
            <div className="text-sm text-zinc-400">
              Run <span className="font-mono text-zinc-200">{result.run_id}</span> ·{" "}
              {result.total_npus} traces
            </div>
            <ul className="space-y-1 font-mono text-xs text-zinc-300">
              {result.trace_files.map((p) => (
                <li key={p} className="truncate">{p}</li>
              ))}
            </ul>
            {result.stdout_tail && (
              <details className="text-xs text-zinc-500">
                <summary className="cursor-pointer">stdout tail</summary>
                <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap">{result.stdout_tail}</pre>
              </details>
            )}
          </div>
        )}
        {!result && !error && (
          <p className="text-sm text-zinc-500">
            Output will appear here after generation completes.
          </p>
        )}
      </section>
    </div>
  );
}

function FormGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs uppercase tracking-wide text-zinc-500">{label}</label>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function FieldGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{children}</div>;
}

function NumField({
  label,
  value,
  min,
  onChange,
  disabled = false,
}: {
  label: string;
  value: number;
  min?: number;
  onChange: (v: number) => void;
  disabled?: boolean;
}) {
  return (
    <label className="block">
      <span className="block text-xs uppercase tracking-wide text-zinc-500">{label}</span>
      <input
        type="number"
        min={min}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 font-mono text-sm disabled:opacity-40"
      />
    </label>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
      {message}
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}
