"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  healthCheck,
  listRuns,
  type RunListItem,
} from "@/lib/api";

const navCards = [
  { href: "/workload", label: "Workload", desc: "Pick or generate .et traces via STG." },
  { href: "/model", label: "Model Presets", desc: "LLaMA-7B, LLaMA-70B, GPT-3-175B." },
  { href: "/system", label: "System / Network", desc: "Configure topology, collectives, memory." },
  { href: "/validate", label: "Validate & Run", desc: "Pre-flight checks, then start a simulation." },
];

const statusColors: Record<string, string> = {
  queued: "text-zinc-400",
  building: "text-amber-300",
  running: "text-blue-300",
  succeeded: "text-emerald-300",
  failed: "text-red-300",
  cancelled: "text-zinc-500",
};

export default function Page() {
  const [backend, setBackend] = useState<string>("checking...");
  const [runs, setRuns] = useState<RunListItem[]>([]);

  useEffect(() => {
    healthCheck()
      .then((r) => setBackend(r.status === "ok" ? "online" : `unexpected: ${JSON.stringify(r)}`))
      .catch((e) => setBackend(`offline (${(e as Error).message})`));
    listRuns()
      .then(setRuns)
      .catch(() => {});
  }, []);

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-semibold">Simulation Interface</h1>
        <p className="mt-2 text-sm text-zinc-400">
          Orchestrate STG, Chakra, and ASTRA-sim from one dashboard.{" "}
          Backend: <span className="font-mono">{backend}</span>
        </p>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {navCards.map((c) => (
          <Link
            key={c.href}
            href={c.href}
            className="block rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition hover:border-zinc-600"
          >
            <div className="text-lg font-medium">{c.label}</div>
            <div className="mt-2 text-sm text-zinc-400">{c.desc}</div>
          </Link>
        ))}
      </section>

      {runs.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-400">
            Recent runs
          </h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="py-2 pr-4">Run ID</th>
                <th className="py-2 pr-4">Status</th>
                <th className="py-2 pr-4">Created</th>
                <th className="py-2 pr-4"></th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 10).map((r) => (
                <tr key={r.run_id} className="border-t border-zinc-900">
                  <td className="py-2 pr-4 font-mono text-xs">{r.run_id}</td>
                  <td className={`py-2 pr-4 font-mono text-xs ${statusColors[r.status] ?? "text-zinc-400"}`}>
                    {r.status}
                  </td>
                  <td className="py-2 pr-4 text-xs text-zinc-500">
                    {formatDate(r.created_at)}
                  </td>
                  <td className="py-2 pr-4 text-right">
                    <Link
                      href={r.status === "succeeded" ? `/results/${r.run_id}` : `/run/${r.run_id}`}
                      className="text-xs text-blue-400 underline"
                    >
                      {r.status === "succeeded" ? "results" : "view"}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
