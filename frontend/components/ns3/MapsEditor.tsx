"use client";

import { useState } from "react";

import { NumInput } from "./primitives";

/**
 * Editor for ns-3's per-bandwidth threshold maps (KMAX_MAP, KMIN_MAP,
 * PMAX_MAP). Each row is ``(bandwidth_bps, value)``; the `valueKind`
 * prop controls whether `value` is a byte-count threshold or a drop
 * probability.
 *
 * Stable React keys are assigned once per row via crypto.randomUUID()
 * so add/remove doesn't scramble focus or input drafts.
 */

type ThresholdRow = { bandwidth_bps: number; threshold: number };
type ProbabilityRow = { bandwidth_bps: number; probability: number };

type Row = ThresholdRow | ProbabilityRow;

type Props<R extends Row> = {
  title: string;
  hint?: string;
  valueKind: "threshold" | "probability";
  rows: R[];
  onChange: (rows: R[]) => void;
};

const newRowId = () => crypto.randomUUID();

function valueOf<R extends Row>(row: R, kind: "threshold" | "probability"): number {
  return kind === "threshold"
    ? (row as ThresholdRow).threshold
    : (row as ProbabilityRow).probability;
}

function withValue<R extends Row>(
  row: R,
  kind: "threshold" | "probability",
  v: number,
): R {
  return kind === "threshold"
    ? ({ ...(row as ThresholdRow), threshold: v } as unknown as R)
    : ({ ...(row as ProbabilityRow), probability: v } as unknown as R);
}

export function MapsEditor<R extends Row>({
  title,
  hint,
  valueKind,
  rows,
  onChange,
}: Props<R>) {
  // React keys parallel to `rows`; stable across edits.
  const [ids, setIds] = useState<string[]>(() => rows.map(() => newRowId()));
  // Defensive: rows might lengthen via default-object changes.
  if (ids.length !== rows.length) {
    setIds(rows.map((_, i) => ids[i] ?? newRowId()));
  }

  const setRow = (i: number, next: Partial<R>) => {
    const out = rows.map((r, idx) => (idx === i ? { ...r, ...next } : r));
    onChange(out);
  };

  const addRow = () => {
    const template = (rows.at(-1) ?? null) as R | null;
    const newRow = template
      ? ({ ...template } as R)
      : valueKind === "threshold"
        ? ({ bandwidth_bps: 100_000_000_000, threshold: 400 } as unknown as R)
        : ({ bandwidth_bps: 100_000_000_000, probability: 0.2 } as unknown as R);
    onChange([...rows, newRow]);
    setIds([...ids, newRowId()]);
  };

  const removeRow = (i: number) => {
    onChange(rows.filter((_, idx) => idx !== i));
    setIds(ids.filter((_, idx) => idx !== i));
  };

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs uppercase tracking-wide text-zinc-400">{title}</h3>
        {hint && <span className="text-xs text-zinc-500">{hint}</span>}
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-zinc-500">No entries; ns-3 ECN will fall back to defaults.</p>
      ) : (
        <div className="space-y-1">
          {rows.map((row, i) => (
            <div
              key={ids[i] ?? `fallback-${i}`}
              className="grid grid-cols-[1.3fr_1fr_auto] items-end gap-2"
            >
              <label className="block">
                <span className="block text-[10px] uppercase tracking-wide text-zinc-500">
                  bandwidth (bps)
                </span>
                <NumInput
                  value={row.bandwidth_bps}
                  min={0}
                  onChange={(v) => setRow(i, { bandwidth_bps: v } as Partial<R>)}
                />
              </label>
              <label className="block">
                <span className="block text-[10px] uppercase tracking-wide text-zinc-500">
                  {valueKind === "threshold" ? "threshold (bytes)" : "probability (0-1)"}
                </span>
                <NumInput
                  value={valueOf(row, valueKind)}
                  min={0}
                  max={valueKind === "probability" ? 1 : undefined}
                  step={valueKind === "probability" ? "0.01" : undefined}
                  onChange={(v) => {
                    const next = withValue(row, valueKind, v);
                    onChange(rows.map((r, idx) => (idx === i ? next : r)));
                  }}
                />
              </label>
              <button
                onClick={() => removeRow(i)}
                disabled={rows.length <= 1}
                className="rounded border border-zinc-800 px-2 py-1.5 text-xs text-zinc-400 transition hover:border-red-800 hover:text-red-400 disabled:opacity-40"
                aria-label="Remove row"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      <button
        onClick={addRow}
        className="rounded border border-dashed border-zinc-700 px-3 py-1 text-xs text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200"
      >
        + add row
      </button>
    </div>
  );
}
