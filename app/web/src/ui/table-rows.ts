// Table rows for the current view: the same values the map colors, formatted for a column.

import type { AreaValue, MetricContext } from "../metrics";
import { LOW_VOTE_THRESHOLD } from "../metrics";
import type { MeasureStats } from "../measures/model";
import { LOW_PARCEL_THRESHOLD, baseLabel, formatMoe, formatValue, isLow } from "../measures/model";
import { METRIC_LABELS } from "../state";
import type { AreaCollection, Results } from "../types";
import { STATUS_TEXT, percent, votes } from "./format";
import type { TableRow, TableSpec } from "./table";

const DASH = "—";

function cell(ctx: MetricContext, a: AreaValue, results: Results): string {
  if (a.value === null) return DASH;
  const name = (i: number | undefined): string => (i === undefined ? "?" : results.choices[i]?.name ?? "?");
  switch (ctx.metric) {
    case "total":
      return votes(a.value);
    case "margin": {
      if (a.value === 0) return "Tied";
      const side = a.value > 0 ? name(ctx.topTwo?.[0]) : name(ctx.topTwo?.[1]);
      return `${side} +${(Math.abs(a.value) * 100).toFixed(1)}`;
    }
    case "leader":
      return `${name(Number(a.leader))} ${percent(a.value)}`;
    default:
      return percent(a.value);
  }
}

function resultNote(a: AreaValue, method: string | null | undefined): string {
  if (a.status === "not_on_ballot" || a.status === "no_ballots" || a.status === "no_data") return STATUS_TEXT[a.status];
  const notes: string[] = [];
  if (a.status === "low") notes.push(`Fewer than ${LOW_VOTE_THRESHOLD} votes`);
  if (method === "allocated" || method === "mixed") notes.push("Includes estimates from split precincts");
  return notes.join("; ");
}

function valueLabel(ctx: MetricContext, results: Results): string {
  if (ctx.metric === "share" && ctx.choiceIndex !== null) return `${results.choices[ctx.choiceIndex]?.name ?? "Candidate"} share`;
  if (ctx.metric === "margin") return "Margin (points)";
  return METRIC_LABELS[ctx.metric];
}

export function resultsTable(
  areas: AreaCollection, values: Map<string, AreaValue>, ctx: MetricContext, results: Results, contestName: string,
): TableSpec {
  const turnout = ctx.metric === "turnout";
  const rows = areas.features.map((f): TableRow => {
    const id = f.properties.feature_id;
    const a = values.get(id) ?? { status: "no_data" as const, value: null, valid: 0, leader: null };
    const counted = a.status === "value" || a.status === "low";
    return {
      id,
      name: f.properties.name,
      value: a.value,
      display: cell(ctx, a, results),
      count: counted ? a.valid : null,
      countDisplay: counted ? votes(a.valid) : DASH,
      note: resultNote(a, results.features[id]?.method),
    };
  });
  return { caption: `${contestName} · ${results.geography_label}`, valueLabel: valueLabel(ctx, results), countLabel: turnout ? "Ballots" : "Valid votes", rows };
}

function measureNote(stats: MeasureStats, has: boolean, low: boolean): string {
  if (!has) return stats.dataset === "census" ? "No estimate" : "No residential parcels with this value";
  if (!low) return "";
  return stats.dataset === "census" ? "Large margin of error" : `Fewer than ${LOW_PARCEL_THRESHOLD} parcels`;
}

export function measureTable(areas: AreaCollection, stats: MeasureStats): TableSpec {
  const rows = areas.features.map((f): TableRow => {
    const id = f.properties.feature_id;
    const v = stats.features[id];
    const value = v !== undefined && v.n > 0 ? v.value : null;
    const moe = value !== null && v?.moe !== null && v?.moe !== undefined ? ` ${formatMoe(stats.kind, v.moe)}` : "";
    return {
      id,
      name: f.properties.name,
      value,
      display: value !== null ? `${formatValue(stats.kind, value, stats.dataset)}${moe}` : DASH,
      count: v?.n ?? null,
      countDisplay: v ? votes(v.n) : DASH,
      note: measureNote(stats, value !== null, v !== undefined && isLow(stats, v)),
    };
  });
  const what = baseLabel(stats);
  return { caption: `${stats.label} · ${stats.geography_label}`, valueLabel: stats.label, countLabel: what.charAt(0).toUpperCase() + what.slice(1), rows };
}
