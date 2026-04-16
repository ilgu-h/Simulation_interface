export default function ResultsPage({ params }: { params: { id: string } }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-semibold">Results {params.id}</h1>
      <p className="text-sm text-zinc-400">
        TODO Phase 5 — per-NPU stats, timeline, topology heatmap, comparison.
      </p>
    </div>
  );
}
