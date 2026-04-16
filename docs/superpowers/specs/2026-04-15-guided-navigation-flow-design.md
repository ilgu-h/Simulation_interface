# Guided Navigation Flow: Workload → System → Validate

**Date**: 2026-04-15
**Status**: Approved

## Problem

After generating workload traces, users have no clear direction to the next step. The three pipeline pages (Workload, System, Validate) are disconnected — users must manually navigate, re-enter NPU counts, and remember their workload prefix.

## Solution

Connect the pages into a guided pipeline using URL query params. Each page works standalone but gains context when navigated to from the previous step.

## Approach

**URL query params only** — consistent with the existing Workload → Validate flow (`?workload=<prefix>`). No shared state library, no localStorage, no new dependencies. Pages remain fully functional when accessed directly.

## Flow

```
Workload (Generate new)
  │  success
  ▼
  "Configure System →" button in result panel
  │  navigates to /system?npus=4&dp=2&tp=2&sp=1&pp=1&workload=<prefix>
  ▼
System page
  │  shows blue context banner, auto-sets npus_count + expected_npus
  │  user configures → materializes
  ▼
  "Continue to Validate →" button in materialize success box
  │  navigates to /validate?workload=<prefix>
  ▼
Validate page (existing — already reads ?workload= param)
```

## Changes by Page

### 1. Workload Page (`/workload`) — Generate Tab Result Panel

**Trigger**: Successful trace generation (result panel is visible).

Add a footer section inside the green result box:

- **Context line**: "Next: configure system for **N NPUs** (DP=X × TP=Y × SP=Z × PP=W)" — computed from the StgSpec that was just submitted.
- **Button**: "Configure System →"
- **Link target**: `/system?npus=<total>&dp=<dp>&tp=<tp>&sp=<sp>&pp=<pp>&ep=<ep>&workload=<prefix>`
  - `npus` = total NPU count (already computed as `totalNpus` in the component)
  - `dp`, `tp`, `sp`, `pp`, `ep` = parallelism dimensions from the submitted spec
  - `workload` = the generated workload prefix, derived from `result.trace_files[0]` by stripping the `.N.et` suffix
- Only appears when `result` is non-null (generation succeeded).

### 2. System Page (`/system`) — Workload Context Banner

**Trigger**: URL contains `?npus=` query param.

#### Blue info banner

- Positioned at the top of the left column, before the Backend picker.
- Content: "**N NPUs** — DP=X × TP=Y × SP=Z × PP=W" with workload prefix if present.
- Dismissible with × button (sets a local `dismissed` state — banner disappears, auto-filled values remain).

#### Auto-configuration

When query params are present on initial render:

- Set `network.npus_count[0]` to the `npus` param value.
- Set `expected_npus` to the `npus` param value (enables cross-validation).
- Do NOT override if the user has already modified these fields (params only apply on mount).

#### Standalone behavior

Without query params: no banner, no auto-fill. Page works exactly as today.

### 3. System Page (`/system`) — Post-Materialize Navigation

**Trigger**: Successful materialization (`materialized` state is non-null).

Add inside the green success box (below the file list):

- A subtle separator line.
- **Button**: "Continue to Validate →"
- **Link target**: `/validate?workload=<prefix>` — the prefix comes from the URL params if present.
- If no workload param was passed (standalone usage), button links to `/validate` without params.

### 4. Validate Page (`/validate`)

No changes. Already reads `?workload=<prefix>` and pre-fills the workload field (implemented previously).

## URL Parameters

### Workload → System

| Param | Type | Example | Purpose |
|-------|------|---------|---------|
| `npus` | int | `4` | Total NPU count for auto-fill |
| `dp` | int | `2` | Data parallel degree (display) |
| `tp` | int | `2` | Tensor parallel degree (display) |
| `sp` | int | `1` | Sequence parallel degree (display) |
| `pp` | int | `1` | Pipeline parallel degree (display) |
| `ep` | int | `1` | Expert parallel degree (display) |
| `workload` | string | `runs/abc123/traces/workload` | Workload prefix to pass through to Validate |

### System → Validate

| Param | Type | Example | Purpose |
|-------|------|---------|---------|
| `workload` | string | `runs/abc123/traces/workload` | Pre-fill workload prefix |

## UI Component Details

### Context banner (System page)

- Background: `bg-blue-950/40`, border: `border-blue-900/50`
- Icon/label: "WORKLOAD CONTEXT" in small uppercase
- Body: bold NPU count + parallelism breakdown
- Dismiss button: × in `text-zinc-500`
- No persistence — refreshing the page without params removes it

### "Configure System →" button (Workload page)

- Lives inside the existing green result box (`border-emerald-900/50 bg-emerald-950/30`)
- Separated from trace list by a top border line (`border-emerald-900/50`)
- Context text above the button in emerald tones
- Button style: primary (`bg-zinc-100 text-zinc-900`) — same as other primary actions

### "Continue to Validate →" button (System page)

- Lives inside the existing green materialized success box
- Separated by a top border line
- Button style: primary (`bg-zinc-100 text-zinc-900`)

## What Does NOT Change

- No new API endpoints.
- No new npm dependencies.
- No global state store.
- Materialize button enable/disable logic (already tied to `hasError`).
- Validate page implementation (already reads `?workload=`).
- Pages accessed directly (without params) behave identically to today.

## Testing

- Frontend build (`pnpm build`) must pass.
- Backend tests (`pytest`) must pass (no backend changes expected).
- Manual verification:
  1. Generate traces → result shows "Configure System →" with correct NPU summary
  2. Click through → System page shows blue banner with correct parallelism dims
  3. Verify npus_count and expected_npus are auto-filled
  4. Dismiss banner → values remain
  5. Materialize → green box shows "Continue to Validate →"
  6. Click through → Validate page has workload pre-filled
  7. Direct navigation to `/system` (no params) → no banner, no auto-fill
  8. Direct navigation to `/system?npus=8` → banner appears with 8 NPUs
