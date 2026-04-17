"use client";

import { useState } from "react";

import { TextInput } from "./primitives";

/**
 * Editor for ``Record<string, string>`` — used for ns3's
 * ``extra_overrides`` escape hatch. User can add arbitrary
 * ``UPPER_SNAKE`` keys not covered by the typed schema.
 *
 * Stable keys via crypto.randomUUID() so row edits don't shuffle focus.
 */

const newRowId = () => crypto.randomUUID();

type Row = { id: string; key: string; value: string };

function recordToRows(r: Record<string, string>, existingIds: string[]): Row[] {
  const entries = Object.entries(r);
  return entries.map(([key, value], i) => ({
    id: existingIds[i] ?? newRowId(),
    key,
    value,
  }));
}

function rowsToRecord(rows: Row[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const { key, value } of rows) {
    if (key.trim() !== "") out[key] = value;
  }
  return out;
}

export function KeyValueTable({
  value,
  onChange,
  hint,
}: {
  value: Record<string, string>;
  onChange: (v: Record<string, string>) => void;
  hint?: string;
}) {
  // Track local rows (including rows with blank keys that the user is
  // still typing) separately from the committed `value` record.
  const [rows, setRows] = useState<Row[]>(() => recordToRows(value, []));

  const commit = (next: Row[]) => {
    setRows(next);
    onChange(rowsToRecord(next));
  };

  const setField = (i: number, patch: Partial<Omit<Row, "id">>) => {
    commit(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };

  const addRow = () => commit([...rows, { id: newRowId(), key: "", value: "" }]);
  const removeRow = (i: number) => commit(rows.filter((_, idx) => idx !== i));

  return (
    <div className="space-y-2">
      {hint && <p className="text-xs text-zinc-500">{hint}</p>}
      {rows.length === 0 ? (
        <p className="text-xs text-zinc-500">
          No overrides. Use this for upstream ns-3 keys not modeled above.
        </p>
      ) : (
        <div className="space-y-1">
          {rows.map((row, i) => (
            <div key={row.id} className="grid grid-cols-[1fr_1fr_auto] items-center gap-2">
              <TextInput
                value={row.key}
                placeholder="UPPER_SNAKE_KEY"
                onChange={(v) => setField(i, { key: v })}
              />
              <TextInput
                value={row.value}
                placeholder="value"
                onChange={(v) => setField(i, { value: v })}
              />
              <button
                onClick={() => removeRow(i)}
                className="rounded border border-zinc-800 px-2 py-1.5 text-xs text-zinc-400 transition hover:border-red-800 hover:text-red-400"
                aria-label="Remove override"
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
        + add override
      </button>
    </div>
  );
}
