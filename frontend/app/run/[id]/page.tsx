export default function RunPage({ params }: { params: { id: string } }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold">Run {params.id}</h1>
      <p className="text-sm text-zinc-400">
        TODO Phase 4 — live log stream, status, cancel button.
      </p>
    </div>
  );
}
