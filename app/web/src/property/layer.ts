// Draw one property metric on the shared map: fetch, classify each area, return what was drawn.

import { fetchGeo, fetchProperty } from "../api";
import type { AreaState } from "../map/view";
import type { Scale } from "../scales";
import { binOf } from "../scales";
import type { AreaCollection } from "../types";
import type { PropertySelection, PropertyStats } from "./model";
import { LOW_PARCEL_THRESHOLD, propertyScale } from "./model";

export interface PropertyDraw {
  stats: PropertyStats;
  scale: Scale;
  states: Map<string, AreaState>;
  areas: AreaCollection;
  context: AreaCollection | null;
  county: AreaCollection;
}

export async function loadProperty(sel: PropertySelection, asOf: string): Promise<PropertyDraw> {
  const council = sel.geography === "council_district";
  const [areas, county, context, stats] = await Promise.all([
    fetchGeo(sel.geography, asOf),
    fetchGeo("county", asOf),
    council ? fetchGeo("precinct", asOf) : Promise.resolve(null),
    fetchProperty(sel.metric, sel.geography),
  ]);
  const scale = propertyScale(stats.kind, stats.label);
  const states = new Map<string, AreaState>();
  for (const f of areas.features) {
    const id = f.properties.feature_id;
    const v = stats.features[id];
    if (!v || v.value === null || v.n === 0) {
      states.set(id, { status: "not_on_ballot", bin: -1 }); // white: no residential parcels
      continue;
    }
    states.set(id, { status: v.n < LOW_PARCEL_THRESHOLD ? "low" : "value", bin: binOf(scale, v.value, null) });
  }
  return { stats, scale, states, areas, context, county };
}
