// Fixed bins for area statistics (property and census). Same edges for every area and view,
// so a color always means the same range; never party red or blue.

import type { Bin, Scale } from "../scales";
import { SEQUENTIAL } from "../scales";
import type { Dataset, MeasureKind } from "./model";

const ARM_A = ["#f7c58a", "#e08214", "#a14d07"]; // mean above median
const ARM_B = ["#c9c1e0", "#8d7fbf", "#542788"]; // mean below median
const NEUTRAL = "#e6e5e1";
const INF = Number.POSITIVE_INFINITY;

export const money = (x: number): string => (Math.abs(x) >= 1000 ? `$${Math.round(x / 1000).toLocaleString("en-US")}k` : `$${Math.round(x)}`);
const pct = (x: number): string => `${Math.round(x * 100)}%`;
export const num = (x: number): string => Math.round(x).toLocaleString("en-US");

function ladder(edges: number[], colors: string[], fmt: (x: number) => string): Bin[] {
  return colors.map((color, i) => {
    const from = edges[i] ?? 0;
    const to = edges[i + 1] ?? INF;
    return { from, to, color, label: to === INF ? `${fmt(from)}+` : `${fmt(from)}–${fmt(to)}` };
  });
}

const GRADE_STEPS: [number, string][] = (["A", "B", "C", "D", "E"] as const).flatMap((g, i) => {
  const base = 5 - i;
  return [2, 1, 0, -1, -2].map((s): [number, string] => [base + s * 0.2, s === 0 ? g : `${g}${s > 0 ? "+" : "-"}${Math.abs(s)}`]);
});

/** Nearest auditor grade for a mean score, e.g. 3.19 -> "C+1". */
export function gradeLabel(score: number): string {
  let best = GRADE_STEPS[0] ?? [5, "A"];
  for (const step of GRADE_STEPS) if (Math.abs(step[0] - score) < Math.abs(best[0] - score)) best = step;
  return best[1];
}

// Property shares run the full range; census shares are often small (5-10% can matter), so
// their lower bins are finer.
const SHARE_EDGES: Record<Dataset, number[]> = {
  property: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 1.0001],
  census: [0, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.65, 1.0001],
};
const CURRENCY_EDGES: Record<Dataset, number[]> = {
  property: [0, 100e3, 150e3, 200e3, 250e3, 300e3, 400e3, 600e3, INF], // home values
  census: [0, 35e3, 50e3, 65e3, 80e3, 100e3, 125e3, 150e3, INF], // household income
};

function deltaScale(label: string): Scale {
  const edges = [-INF, -50e3, -20e3, -5e3, 5e3, 20e3, 50e3, INF];
  const colors = [...ARM_B].reverse().concat([NEUTRAL], ARM_A);
  const labels = ["Mean $50k+ below median", "Mean $20k–50k below", "Mean $5k–20k below", "Within $5k",
    "Mean $5k–20k above", "Mean $20k–50k above", "Mean $50k+ above median"];
  return { kind: "diverging", title: label, bins: colors.map((color, i) => ({ from: edges[i] ?? -INF, to: edges[i + 1] ?? INF, color, label: labels[i] ?? "" })) };
}

function scoreScale(label: string): Scale {
  const edges = [0, 2.5, 2.7, 2.9, 3.1, 3.3, 3.5, 3.9, 5.01];
  return { kind: "sequential", title: label, bins: ladder(edges, SEQUENTIAL, (x) => x.toFixed(1)).map((b, i) =>
    ({ ...b, label: i === 0 ? "Below 2.5 (D or lower)" : i === 7 ? "3.9 and up (B+ or higher)" : `${b.label} (≈${gradeLabel((b.from + b.to) / 2)})` })) };
}

export function measureScale(kind: MeasureKind, label: string, dataset: Dataset = "property"): Scale {
  switch (kind) {
    case "share":
      return { kind: "sequential", title: label, bins: ladder(SHARE_EDGES[dataset], SEQUENTIAL, pct) };
    case "currency":
      return { kind: "sequential", title: label, bins: ladder(CURRENCY_EDGES[dataset], SEQUENTIAL, money) };
    case "currency_delta":
      return deltaScale(label);
    case "score":
      return scoreScale(label);
    case "density":
      return { kind: "sequential", title: label, bins: ladder([0, 500, 1000, 2000, 3000, 4000, 5000, 7500, INF], SEQUENTIAL, num) };
    default:
      return { kind: "sequential", title: label, bins: ladder([0, 25, 50, 100, 250, 500, 1000, 2500, INF], SEQUENTIAL, num) };
  }
}
