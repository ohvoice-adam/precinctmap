// Draw one area statistic on the shared map: fetch, classify each area, return what was drawn.

import { fetchGeo, fetchMeasure } from "../api";
import type { AreaState } from "../map/view";
import type { Scale } from "../scales";
import { binOf } from "../scales";
import type { AreaCollection } from "../types";
import type { Dataset, MeasureSelection, MeasureStats } from "./model";
import { isLow } from "./model";
import { measureScale } from "./scales";

export interface MeasureDraw {
  stats: MeasureStats;
  scale: Scale;
  states: Map<string, AreaState>;
  areas: AreaCollection;
  context: AreaCollection | null;
  county: AreaCollection;
}

export async function loadMeasure(dataset: Dataset, sel: MeasureSelection, asOf: string): Promise<MeasureDraw> {
  const council = sel.geography === "council_district";
  const [areas, county, context, stats] = await Promise.all([
    fetchGeo(sel.geography, asOf),
    fetchGeo("county", asOf),
    council ? fetchGeo("precinct", asOf) : Promise.resolve(null),
    fetchMeasure(dataset, sel.metric, sel.geography),
  ]);
  const scale = measureScale(stats.kind, stats.label, dataset);
  const states = new Map<string, AreaState>();
  for (const f of areas.features) {
    const id = f.properties.feature_id;
    const v = stats.features[id];
    if (!v || v.value === null || v.n === 0) {
      states.set(id, { status: "not_on_ballot", bin: -1 }); // white: nothing to measure here
      continue;
    }
    states.set(id, { status: isLow(stats, v) ? "low" : "value", bin: binOf(scale, v.value, null) });
  }
  return { stats, scale, states, areas, context, county };
}
