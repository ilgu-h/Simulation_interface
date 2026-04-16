"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { listPresets, type Preset } from "@/lib/api";

export default function ModelPage() {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPresets()
      .then(setPresets)
      .catch((e) => setError((e as Error).message));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Model Presets</h1>
        <p className="text-sm text-zinc-400">
          Pre-configured model shapes. Select one here and it will pre-fill
          the workload generation form.
        </p>
      </div>

      {error && (
        <div className="rounded border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {presets.map((p) => (
          <div
            key={p.id}
            className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition hover:border-zinc-600"
          >
            <div className="text-lg font-medium">{p.label}</div>
            <div className="mt-1 text-xs uppercase tracking-wide text-zinc-500">
              {p.model_type}
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-xs text-zinc-400">
              {Object.entries(p.spec)
                .filter(([k]) => !["model_type"].includes(k))
                .map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <dt className="text-zinc-500">{k}</dt>
                    <dd className="text-zinc-200">{String(v)}</dd>
                  </div>
                ))}
            </dl>
            <Link
              href="/workload"
              className="mt-4 inline-block rounded border border-zinc-700 px-3 py-1.5 text-xs text-zinc-200 transition hover:border-zinc-500"
            >
              Use in workload →
            </Link>
          </div>
        ))}
      </div>

      {presets.length === 0 && !error && (
        <p className="text-sm text-zinc-500">Loading presets...</p>
      )}

      <div className="rounded border border-dashed border-zinc-800 p-4 text-sm text-zinc-500">
        <p>
          To add a new preset, create a JSON file in{" "}
          <code className="font-mono">backend/app/schemas/presets/</code> with{" "}
          <code className="font-mono">{`{id, label, model_type, spec:{...}}`}</code>. It
          appears here and in the workload preset picker automatically.
        </p>
      </div>
    </div>
  );
}
