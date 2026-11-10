// Fitted color scales: bins sized to the selected item's own spread across the mapped areas,
// instead of the fixed bins. A minor candidate at 1-4% (or a census group at 2-6%) is one flat
// color on a 0-100% scale; fitted, the same map separates strong and weak areas.

import type { Bin } from "./scales";

/** The fixed scales have this many bins; a fitted one matches so palettes carry over. */
export const FIT_BINS = 8;
/** Edges are placed to cover up to this quantile; the top bin is open-ended for the rest. */
export const FIT_QUANTILE = 0.98;

/** How a fitted edge is written. */
export type FitFormat = "percent" | "count" | "money" | "decimal";

/** Smallest "nice" step (1, 2, 2.5 or 5 times a power of ten) that is at least `raw`. */
export function niceStep(raw: number): number {
  if (!(raw > 0) || !Number.isFinite(raw)) return 1;
  const pow = 10 ** Math.floor(Math.log10(raw));
  const unit = [1, 2, 2.5, 5, 10].find((m) => m * pow >= raw * (1 - 1e-9)) ?? 10;
  return unit * pow;
}

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return (sorted[lo] ?? 0) + ((sorted[hi] ?? 0) - (sorted[lo] ?? 0)) * (pos - lo);
}

const clean = (x: number): number => Number(x.toPrecision(12)); // no 0.30000000000000004

/** Equal-width bin edges sized to the values' spread: `FIT_BINS` bins, the last open
 * (`Infinity`). They start at 0 when `anchorZero` (shares and counts, where zero means
 * something), otherwise at the nice step at or below the smallest value (dollars, densities,
 * ratios). Returns null when there is nothing to fit, so the caller keeps the fixed scale. */
export function fitEdges(values: number[], anchorZero = true): number[] | null {
  const sorted = values.filter((v) => Number.isFinite(v) && (anchorZero ? v >= 0 : true)).sort((a, b) => a - b);
  const top = quantile(sorted, FIT_QUANTILE);
  const low = anchorZero ? 0 : (sorted[0] ?? 0);
  if (sorted.length === 0 || top <= low) return null;
  const step = niceStep((top - low) / FIT_BINS);
  const start = anchorZero ? 0 : Math.floor(low / step) * step;
  const edges = Array.from({ length: FIT_BINS }, (_, i) => clean(start + i * step));
  return [...edges, Number.POSITIVE_INFINITY];
}

function decimals(step: number): number {
  return step >= 1 ? 0 : step >= 0.1 ? 1 : 2;
}

/** Percent label with just enough decimals to tell neighboring edges apart. */
export function fitPercent(step: number): (x: number) => string {
  const d = step >= 0.01 ? 0 : step >= 0.001 ? 1 : 2;
  return (x) => `${(x * 100).toFixed(d)}%`;
}

function formatter(format: FitFormat, step: number): (x: number) => string {
  switch (format) {
    case "percent":
      return fitPercent(step);
    case "money":
      return (x) => (step >= 1000 ? `$${(x / 1000).toFixed(step % 1000 ? 1 : 0)}k` : `$${x.toFixed(0)}`);
    case "decimal":
      return (x) => x.toFixed(decimals(step));
    default:
      return (x) => Math.round(x).toLocaleString("en-US");
  }
}

/** Fitted bins for `colors` (one per bin), or null when there is nothing to fit. */
export function fitBins(values: number[], colors: string[], format: FitFormat, anchorZero = true): Bin[] | null {
  const edges = fitEdges(values, anchorZero);
  if (!edges) return null;
  const fmt = formatter(format, (edges[1] ?? 1) - (edges[0] ?? 0));
  return colors.map((color, i) => {
    const from = edges[i] ?? 0;
    const to = edges[i + 1] ?? Number.POSITIVE_INFINITY;
    return { from, to, color, label: to === Number.POSITIVE_INFINITY ? `${fmt(from)}+` : `${fmt(from)}–${fmt(to)}` };
  });
}
