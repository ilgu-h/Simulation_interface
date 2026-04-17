"use client";

import { useState } from "react";

import type { Ns3NetworkConfig } from "@/lib/api";

import { Accordion } from "./Accordion";
import { CCModeDropdown } from "./CCModeDropdown";
import { KeyValueTable } from "./KeyValueTable";
import { MapsEditor } from "./MapsEditor";
import { Checkbox, Field, NumInput, TextInput } from "./primitives";

/**
 * Full ns-3 advanced configuration UI.
 *
 * Layout:
 *   • Logical topology (always visible — drives per-NPU allocation)
 *   • File paths (always visible — points at topology + base config.txt)
 *   • Essentials (always open — CC_MODE, packet size, buffer, rates, etc.)
 *   • 8 collapsed accordions for advanced knobs
 *   • Escape hatch for any key not modeled above
 *
 * Field updates flow through a single ``patch`` helper so the immutable
 * update pattern stays consistent; each sub-section extracts the props
 * it needs from the ``network`` prop via narrow destructuring to keep
 * re-renders cheap.
 */

const newDimId = () => crypto.randomUUID();

export function Ns3AdvancedSection({
  network,
  onChange,
}: {
  network: Ns3NetworkConfig;
  onChange: (n: Ns3NetworkConfig) => void;
}) {
  const patch = <K extends keyof Ns3NetworkConfig>(
    key: K,
    value: Ns3NetworkConfig[K],
  ) => onChange({ ...network, [key]: value });

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-300">
        Network (ns-3)
      </h2>
      <div className="rounded border border-blue-900/50 bg-blue-950/40 p-3 text-xs text-blue-200">
        ns-3 combines these <span className="font-mono">logical_dims</span>{" "}
        with a packet-level physical topology defined in the ns-3 submodule.
        Essentials are open by default; advanced knobs are in the accordions
        below. Any key not covered has an escape hatch at the bottom.
      </div>

      <LogicalDimsEditor
        logical_dims={network.logical_dims}
        onChange={(v) => patch("logical_dims", v)}
      />

      <FilePathsEditor
        physical_topology_path={network.physical_topology_path}
        mix_config_path={network.mix_config_path}
        onPhysicalChange={(v) => patch("physical_topology_path", v)}
        onMixChange={(v) => patch("mix_config_path", v)}
      />

      <EssentialsSection network={network} patch={patch} />

      <Accordion title="Rates" hint="4 rate-string fields">
        <div className="grid grid-cols-2 gap-3">
          <Field label="RATE_AI" hint="additive-increase rate">
            <TextInput value={network.rate_ai} onChange={(v) => patch("rate_ai", v)} />
          </Field>
          <Field label="RATE_HAI" hint="hyper-additive-increase rate">
            <TextInput value={network.rate_hai} onChange={(v) => patch("rate_hai", v)} />
          </Field>
          <Field label="MIN_RATE" hint="rate floor">
            <TextInput value={network.min_rate} onChange={(v) => patch("min_rate", v)} />
          </Field>
          <Field label="DCTCP_RATE_AI">
            <TextInput
              value={network.dctcp_rate_ai}
              onChange={(v) => patch("dctcp_rate_ai", v)}
            />
          </Field>
        </div>
      </Accordion>

      <Accordion title="Congestion control tuning" hint="6 CC knobs">
        <div className="grid grid-cols-2 gap-3">
          <Field label="ALPHA_RESUME_INTERVAL">
            <NumInput
              value={network.alpha_resume_interval}
              min={0}
              onChange={(v) => patch("alpha_resume_interval", v)}
            />
          </Field>
          <Field label="RATE_DECREASE_INTERVAL">
            <NumInput
              value={network.rate_decrease_interval}
              min={0}
              onChange={(v) => patch("rate_decrease_interval", v)}
            />
          </Field>
          <Field label="RP_TIMER">
            <NumInput
              value={network.rp_timer}
              min={0}
              onChange={(v) => patch("rp_timer", v)}
            />
          </Field>
          <Field label="EWMA_GAIN">
            <NumInput
              value={network.ewma_gain}
              min={0}
              max={1}
              step="0.001"
              onChange={(v) => patch("ewma_gain", v)}
            />
          </Field>
          <Field label="FAST_RECOVERY_TIMES">
            <NumInput
              value={network.fast_recovery_times}
              min={0}
              onChange={(v) => patch("fast_recovery_times", v)}
            />
          </Field>
          <div className="flex items-end">
            <Checkbox
              checked={network.clamp_target_rate}
              onChange={(v) => patch("clamp_target_rate", v)}
              label="CLAMP_TARGET_RATE"
            />
          </div>
        </div>
      </Accordion>

      <Accordion title="Window / HPCC advanced" hint="12 HPCC-specific knobs">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-end">
            <Checkbox
              checked={network.has_win}
              onChange={(v) => patch("has_win", v)}
              label="HAS_WIN"
            />
          </div>
          <Field label="GLOBAL_T">
            <NumInput
              value={network.global_t}
              onChange={(v) => patch("global_t", v)}
            />
          </Field>
          <div className="flex items-end">
            <Checkbox
              checked={network.var_win}
              onChange={(v) => patch("var_win", v)}
              label="VAR_WIN"
            />
          </div>
          <div className="flex items-end">
            <Checkbox
              checked={network.fast_react}
              onChange={(v) => patch("fast_react", v)}
              label="FAST_REACT"
            />
          </div>
          <Field label="U_TARGET">
            <NumInput
              value={network.u_target}
              min={0}
              max={1}
              step="0.01"
              onChange={(v) => patch("u_target", v)}
            />
          </Field>
          <Field label="MI_THRESH">
            <NumInput
              value={network.mi_thresh}
              min={0}
              onChange={(v) => patch("mi_thresh", v)}
            />
          </Field>
          <Field label="INT_MULTI">
            <NumInput
              value={network.int_multi}
              min={0}
              onChange={(v) => patch("int_multi", v)}
            />
          </Field>
          <Field label="PINT_LOG_BASE">
            <NumInput
              value={network.pint_log_base}
              step="0.01"
              onChange={(v) => patch("pint_log_base", v)}
            />
          </Field>
          <Field label="PINT_PROB">
            <NumInput
              value={network.pint_prob}
              min={0}
              max={1}
              step="0.01"
              onChange={(v) => patch("pint_prob", v)}
            />
          </Field>
          <div className="flex items-end">
            <Checkbox
              checked={network.multi_rate}
              onChange={(v) => patch("multi_rate", v)}
              label="MULTI_RATE"
            />
          </div>
          <div className="flex items-end">
            <Checkbox
              checked={network.sample_feedback}
              onChange={(v) => patch("sample_feedback", v)}
              label="SAMPLE_FEEDBACK"
            />
          </div>
          <div className="flex items-end">
            <Checkbox
              checked={network.rate_bound}
              onChange={(v) => patch("rate_bound", v)}
              label="RATE_BOUND"
            />
          </div>
        </div>
      </Accordion>

      <Accordion title="ECN threshold maps" hint="KMAX / KMIN / PMAX per-bandwidth">
        <div className="space-y-4">
          <MapsEditor
            title="KMAX_MAP (bytes)"
            valueKind="threshold"
            rows={network.kmax_map}
            onChange={(v) => patch("kmax_map", v)}
          />
          <MapsEditor
            title="KMIN_MAP (bytes)"
            valueKind="threshold"
            rows={network.kmin_map}
            onChange={(v) => patch("kmin_map", v)}
          />
          <MapsEditor
            title="PMAX_MAP (drop probability)"
            valueKind="probability"
            rows={network.pmax_map}
            onChange={(v) => patch("pmax_map", v)}
          />
          <p className="text-xs text-amber-300">
            All three maps must have the same length and matching
            bandwidths per row; KMIN ≤ KMAX required.
          </p>
        </div>
      </Accordion>

      <Accordion title="Global switches" hint="4 boolean flags">
        <div className="grid grid-cols-2 gap-3">
          <Checkbox
            checked={network.use_dynamic_pfc_threshold}
            onChange={(v) => patch("use_dynamic_pfc_threshold", v)}
            label="USE_DYNAMIC_PFC_THRESHOLD"
          />
          <Checkbox
            checked={network.enable_trace}
            onChange={(v) => patch("enable_trace", v)}
            label="ENABLE_TRACE"
          />
          <Checkbox
            checked={network.ack_high_prio}
            onChange={(v) => patch("ack_high_prio", v)}
            label="ACK_HIGH_PRIO"
          />
          <Checkbox
            checked={network.l2_back_to_zero}
            onChange={(v) => patch("l2_back_to_zero", v)}
            label="L2_BACK_TO_ZERO"
          />
        </div>
      </Accordion>

      <Accordion title="Packet / link layer" hint="3 L2 knobs">
        <div className="grid grid-cols-3 gap-3">
          <Field label="L2_CHUNK_SIZE">
            <NumInput
              value={network.l2_chunk_size}
              min={0}
              onChange={(v) => patch("l2_chunk_size", v)}
            />
          </Field>
          <Field label="L2_ACK_INTERVAL">
            <NumInput
              value={network.l2_ack_interval}
              min={0}
              onChange={(v) => patch("l2_ack_interval", v)}
            />
          </Field>
          <Field label="NIC_TOTAL_PAUSE_TIME">
            <NumInput
              value={network.nic_total_pause_time}
              min={0}
              onChange={(v) => patch("nic_total_pause_time", v)}
            />
          </Field>
        </div>
      </Accordion>

      <Accordion
        title="Timing"
        hint="SIMULATOR_STOP_TIME in picoseconds"
      >
        <div className="grid grid-cols-3 gap-3">
          <Field label="SIMULATOR_STOP_TIME" hint={`${(network.simulator_stop_time / 1e12).toFixed(1)}s`}>
            <NumInput
              value={network.simulator_stop_time}
              step="1e12"
              onChange={(v) => patch("simulator_stop_time", v)}
            />
          </Field>
          <Field label="QLEN_MON_START">
            <NumInput
              value={network.qlen_mon_start}
              min={0}
              onChange={(v) => patch("qlen_mon_start", v)}
            />
          </Field>
          <Field label="QLEN_MON_END">
            <NumInput
              value={network.qlen_mon_end}
              min={0}
              onChange={(v) => patch("qlen_mon_end", v)}
            />
          </Field>
        </div>
      </Accordion>

      <Accordion
        title="Link control"
        hint="LINK_DOWN src / dst / time"
      >
        <div className="grid grid-cols-3 gap-3">
          <Field label="src">
            <NumInput
              value={network.link_down.src}
              min={0}
              onChange={(v) => patch("link_down", { ...network.link_down, src: v })}
            />
          </Field>
          <Field label="dst">
            <NumInput
              value={network.link_down.dst}
              min={0}
              onChange={(v) => patch("link_down", { ...network.link_down, dst: v })}
            />
          </Field>
          <Field label="time (ns)">
            <NumInput
              value={network.link_down.time}
              min={0}
              onChange={(v) => patch("link_down", { ...network.link_down, time: v })}
            />
          </Field>
        </div>
        <p className="mt-2 text-xs text-zinc-500">All zeros = disabled.</p>
      </Accordion>

      <Accordion
        title="Raw overrides (advanced)"
        hint="Any config.txt key not modeled above"
      >
        <KeyValueTable
          value={network.extra_overrides}
          onChange={(v) => patch("extra_overrides", v)}
          hint="Keys here are merged last and win over typed fields. Use UPPER_SNAKE names."
        />
      </Accordion>
    </div>
  );
}

// ---- Sub-sections -----------------------------------------------------------

function LogicalDimsEditor({
  logical_dims,
  onChange,
}: {
  logical_dims: number[];
  onChange: (v: number[]) => void;
}) {
  const [ids, setIds] = useState<string[]>(() => logical_dims.map(() => newDimId()));
  if (ids.length !== logical_dims.length) {
    setIds(logical_dims.map((_, i) => ids[i] ?? newDimId()));
  }

  const setDim = (i: number, v: number) => {
    onChange(logical_dims.map((d, idx) => (idx === i ? v : d)));
  };
  const addDim = () => {
    onChange([...logical_dims, 2]);
    setIds([...ids, newDimId()]);
  };
  const removeDim = (i: number) => {
    onChange(logical_dims.filter((_, idx) => idx !== i));
    setIds(ids.filter((_, idx) => idx !== i));
  };

  return (
    <div>
      <label className="block text-xs uppercase tracking-wide text-zinc-500">
        logical_dims
      </label>
      <div className="mt-2 space-y-2">
        {logical_dims.map((count, i) => (
          <div
            key={ids[i] ?? `fallback-${i}`}
            className="grid grid-cols-[1fr_auto] items-end gap-2"
          >
            <Field label={`dim${i} npus`}>
              <NumInput value={count} min={1} onChange={(v) => setDim(i, v)} />
            </Field>
            <button
              onClick={() => removeDim(i)}
              disabled={logical_dims.length === 1}
              className="rounded border border-zinc-800 px-2 py-1.5 text-xs text-zinc-400 transition hover:border-red-800 hover:text-red-400 disabled:opacity-40"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
      <button
        onClick={addDim}
        className="mt-2 rounded border border-dashed border-zinc-700 px-3 py-1.5 text-xs text-zinc-400 transition hover:border-zinc-500 hover:text-zinc-200"
      >
        + add dim
      </button>
    </div>
  );
}

function FilePathsEditor({
  physical_topology_path,
  mix_config_path,
  onPhysicalChange,
  onMixChange,
}: {
  physical_topology_path: string;
  mix_config_path: string;
  onPhysicalChange: (v: string) => void;
  onMixChange: (v: string) => void;
}) {
  return (
    <div className="space-y-2">
      <Field
        label="physical_topology_path"
        hint="relative to frameworks/astra-sim"
      >
        <TextInput value={physical_topology_path} onChange={onPhysicalChange} />
      </Field>
      <Field
        label="mix_config_path"
        hint="base config.txt; user overrides are overlaid on this"
      >
        <TextInput value={mix_config_path} onChange={onMixChange} />
      </Field>
    </div>
  );
}

function EssentialsSection({
  network,
  patch,
}: {
  network: Ns3NetworkConfig;
  patch: <K extends keyof Ns3NetworkConfig>(key: K, value: Ns3NetworkConfig[K]) => void;
}) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/40 p-3">
      <h3 className="mb-2 text-xs uppercase tracking-wide text-zinc-400">
        Essentials
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <Field label="CC_MODE">
          <CCModeDropdown
            value={network.cc_mode}
            onChange={(v) => patch("cc_mode", v)}
          />
        </Field>
        <Field label="PACKET_PAYLOAD_SIZE" hint="bytes; 64 ≤ x ≤ 9216">
          <NumInput
            value={network.packet_payload_size}
            min={64}
            max={9216}
            onChange={(v) => patch("packet_payload_size", v)}
          />
        </Field>
        <Field label="BUFFER_SIZE" hint="MB; 1 ≤ x ≤ 1024">
          <NumInput
            value={network.buffer_size}
            min={1}
            max={1024}
            onChange={(v) => patch("buffer_size", v)}
          />
        </Field>
        <Field label="ERROR_RATE_PER_LINK" hint="0.0 - 1.0">
          <NumInput
            value={network.error_rate_per_link}
            min={0}
            max={1}
            step="0.0001"
            onChange={(v) => patch("error_rate_per_link", v)}
          />
        </Field>
        <div className="flex items-end">
          <Checkbox
            checked={network.enable_qcn}
            onChange={(v) => patch("enable_qcn", v)}
            label="ENABLE_QCN (ECN)"
          />
        </div>
        <Field label="RATE_AI / HAI / MIN" hint="default 50 / 100 / 100 Mb/s">
          <div className="grid grid-cols-3 gap-1">
            <TextInput value={network.rate_ai} onChange={(v) => patch("rate_ai", v)} />
            <TextInput value={network.rate_hai} onChange={(v) => patch("rate_hai", v)} />
            <TextInput value={network.min_rate} onChange={(v) => patch("min_rate", v)} />
          </div>
        </Field>
      </div>
    </div>
  );
}
