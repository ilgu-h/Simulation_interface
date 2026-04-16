"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import {
  cancelRun,
  eventsUrl,
  getRun,
  type RunStatus,
  type RunStatusValue,
} from "@/lib/api";

type Event =
  | { ts: string; kind: "status"; status: RunStatusValue }
  | { ts: string; kind: "log"; text: string }
  | { ts: string; kind: "done"; ok: boolean; returncode: number | null }
  | { ts: string; kind: "error"; text: string };

export default function RunPage({ params }: { params: { id: string } }) {
  const runId = params.id;
  const [status, setStatus] = useState<RunStatusValue | "unknown">("unknown");
  const [returncode, setReturncode] = useState<number | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [doneAt, setDoneAt] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [meta, setMeta] = useState<RunStatus | null>(null);
  const logRef = useRef<HTMLPreElement | null>(null);
  const sseRef = useRef<EventSource | null>(null);

  // Initial status snapshot.
  useEffect(() => {
    getRun(runId)
      .then((r) => {
        setMeta(r);
        setStatus(r.status);
      })
      .catch((e) => setErr((e as Error).message));
  }, [runId]);

  // SSE stream.
  useEffect(() => {
    const es = new EventSource(eventsUrl(runId));
    sseRef.current = es;
    es.onmessage = (msg) => {
      try {
        const ev = JSON.parse(msg.data) as Event;
        if (ev.kind === "status") {
          setStatus(ev.status);
        } else if (ev.kind === "log") {
          setLines((prev) => prev.concat(ev.text));
        } else if (ev.kind === "done") {
          setReturncode(ev.returncode);
          setDoneAt(ev.ts);
          es.close();
        } else if (ev.kind === "error") {
          setErr(ev.text);
        }
      } catch {
        // ignore malformed line
      }
    };
    es.onerror = () => {
      // Browser will retry by default; treat persistent failure as soft.
      // (We don't want to spam errors during normal close after `done`.)
    };
    return () => {
      es.close();
    };
  }, [runId]);

  // Auto-scroll log on new lines.
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [lines]);

  const onCancel = async () => {
    try {
      await cancelRun(runId);
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const isLive = ["queued", "building", "running"].includes(status);

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold">
            Run <span className="font-mono text-zinc-400">{runId}</span>
          </h1>
          <p className="mt-1 text-xs text-zinc-500">
            {meta?.log_dir && (
              <>
                logs: <span className="font-mono">{meta.log_dir}</span>
              </>
            )}
          </p>
        </div>
        <StatusBadge status={status} returncode={returncode} />
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={onCancel}
          disabled={!isLive}
          className="rounded border border-zinc-800 px-3 py-1.5 text-xs text-zinc-300 transition hover:border-red-800 hover:text-red-300 disabled:opacity-40"
        >
          Cancel
        </button>
        <Link
          href={`/results/${runId}`}
          className={`rounded border border-zinc-800 px-3 py-1.5 text-xs transition ${
            status === "succeeded"
              ? "text-emerald-300 hover:border-emerald-700"
              : "pointer-events-none text-zinc-500 opacity-50"
          }`}
        >
          Results →
        </Link>
        <span className="ml-auto text-xs text-zinc-500">
          {lines.length} log lines · {doneAt ? `done ${formatTime(doneAt)}` : isLive ? "live" : ""}
        </span>
      </div>

      {err && (
        <div className="rounded border border-red-900/60 bg-red-950/40 p-3 text-sm text-red-200">
          {err}
        </div>
      )}

      <pre
        ref={logRef}
        className="max-h-[60vh] overflow-auto rounded border border-zinc-800 bg-black p-3 font-mono text-[11px] leading-relaxed text-zinc-300"
      >
        {lines.length === 0 ? (
          <span className="text-zinc-600">
            {status === "unknown" ? "Loading run..." : "Waiting for first log line..."}
          </span>
        ) : (
          lines.map((l, i) => (
            <div key={i} className={lineClass(l)}>
              {l}
            </div>
          ))
        )}
      </pre>
    </div>
  );
}

function StatusBadge({
  status,
  returncode,
}: {
  status: RunStatusValue | "unknown";
  returncode: number | null;
}) {
  const colors: Record<string, string> = {
    queued: "border-zinc-700 bg-zinc-900 text-zinc-200",
    building: "border-amber-800 bg-amber-950/50 text-amber-200",
    running: "border-blue-800 bg-blue-950/50 text-blue-200",
    succeeded: "border-emerald-800 bg-emerald-950/50 text-emerald-200",
    failed: "border-red-800 bg-red-950/50 text-red-200",
    cancelled: "border-zinc-700 bg-zinc-900 text-zinc-400",
    unknown: "border-zinc-800 bg-zinc-900 text-zinc-500",
  };
  return (
    <span
      className={`rounded border px-2 py-1 font-mono text-xs uppercase tracking-wide ${
        colors[status] ?? colors.unknown
      }`}
    >
      {status}
      {returncode != null && status !== "running" && status !== "building" && (
        <span className="ml-2 opacity-70">rc={returncode}</span>
      )}
    </span>
  );
}

function lineClass(line: string): string {
  if (line.includes("[error]") || line.includes("[build:err]") || line.includes("Error"))
    return "text-red-400";
  if (line.includes("[build]")) return "text-amber-300";
  if (line.includes("[cancel]")) return "text-zinc-500";
  if (line.includes("[run]")) return "text-blue-300";
  return "";
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}
