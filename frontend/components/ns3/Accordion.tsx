"use client";

import type { ReactNode } from "react";

/**
 * Collapsible section using native <details>/<summary> so it works
 * without any client-side toggle state and is keyboard-accessible out
 * of the box. `defaultOpen` maps to the HTML `open` attribute.
 */
export function Accordion({
  title,
  defaultOpen = false,
  hint,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <details
      open={defaultOpen}
      className="rounded border border-zinc-800 bg-zinc-900/30"
    >
      <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-zinc-900/50">
        {title}
        {hint && <span className="ml-2 text-xs font-normal text-zinc-500">— {hint}</span>}
      </summary>
      <div className="border-t border-zinc-800 p-3">{children}</div>
    </details>
  );
}
