import Link from "next/link";

import { healthCheck } from "@/lib/api";

const phases = [
  { href: "/workload", label: "Workload", phase: "Phase 1", desc: "Pick or generate an .et trace." },
  { href: "/system", label: "System / Network / Memory", phase: "Phase 2", desc: "Configure the simulator." },
  { href: "/model", label: "Model", phase: "Phase 1", desc: "Pick a model preset." },
  { href: "/validate", label: "Validate", phase: "Phase 3", desc: "Pre-flight checks." },
  { href: "/run/test", label: "Run", phase: "Phase 4", desc: "Auto-build and execute." },
  { href: "/results/test", label: "Results", phase: "Phase 5", desc: "Per-NPU drill-down." },
];

export default async function Page() {
  let backend: string;
  try {
    const res = await healthCheck();
    backend = res.status === "ok" ? "online" : `unexpected: ${JSON.stringify(res)}`;
  } catch (err) {
    backend = `offline (${(err as Error).message})`;
  }

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-3xl font-semibold">Phase 0 shell is live.</h1>
        <p className="mt-2 text-sm text-zinc-400">
          Backend status: <span className="font-mono">{backend}</span>
        </p>
      </section>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {phases.map((p) => (
          <Link
            key={p.href}
            href={p.href}
            className="block rounded-lg border border-zinc-800 bg-zinc-900 p-4 transition hover:border-zinc-600"
          >
            <div className="text-xs uppercase tracking-wide text-zinc-500">{p.phase}</div>
            <div className="mt-1 text-lg font-medium">{p.label}</div>
            <div className="mt-2 text-sm text-zinc-400">{p.desc}</div>
          </Link>
        ))}
      </section>
    </div>
  );
}
