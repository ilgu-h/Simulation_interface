"use client";

import { CC_MODE_OPTIONS, type CCMode } from "@/lib/api";

export function CCModeDropdown({
  value,
  onChange,
}: {
  value: CCMode;
  onChange: (v: CCMode) => void;
}) {
  const current = CC_MODE_OPTIONS.find((o) => o.value === value);
  return (
    <div>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value) as CCMode)}
        className="w-full rounded border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-sm"
      >
        {CC_MODE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {current?.experimental && (
        <p className="mt-1 text-xs text-amber-300">
          Experimental — no code path in ns-3 rdma-hw.cc. May silently
          fall through to a default implementation.
        </p>
      )}
    </div>
  );
}
