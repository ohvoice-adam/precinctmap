// The map: one "areas" source (current geography, promoteId feature_id) colored through
// feature-state, a gray "context" precinct layer for areas outside Columbus (council view),
// and a mask for everything outside Franklin County ("no data", not zero).

import { Map as MlMap, NavigationControl, setWorkerUrl } from "maplibre-gl";
// MapLibre 6 runs its worker from a separate module; have Vite emit it and point MapLibre at it.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import type { GeoJSONSource, MapGeoJSONFeature, MapMouseEvent } from "maplibre-gl";

import type { AreaCollection } from "../types";
import { BASEMAP_STYLE_URL, initialView } from "./config";
import {
  FILL_OPACITY, HATCH_OPACITY, LINE_COLOR, LINE_WIDTH, STATUS_COLORS, dotsImage, fillColor, hatchImage, outsideMask,
} from "./style";

export interface AreaState {
  status: string;
  bin: number;
}

export type Hit =
  | { kind: "area"; featureId: string; name: string }
  | { kind: "not_in_columbus"; name: string }
  | { kind: "outside_county" }
  | null;

setWorkerUrl(workerUrl);

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

export class AreaMap {
  readonly map: MlMap;
  private ids: string[] = [];
  private hovered: string | null = null;
  private selected: string | null = null;
  readonly ready: Promise<void>;

  constructor(container: HTMLElement) {
    const view = initialView();
    this.map = new MlMap({
      container,
      style: BASEMAP_STYLE_URL,
      bounds: view.bounds,
      maxBounds: view.maxBounds,
      fitBoundsOptions: { padding: 24 },
      attributionControl: { compact: true },
    });
    this.map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    this.map.on("error", (e) => {
      console.error("Map error:", e.error);
    });
    this.ready = new Promise((resolve) => {
      this.map.on("load", () => {
        this.addLayers();
        resolve();
      });
    });
  }

  private addLayers(): void {
    const m = this.map;
    m.addImage("hatch", hatchImage());
    m.addImage("dots", dotsImage());
    m.addSource("context", { type: "geojson", data: EMPTY });
    m.addSource("areas", { type: "geojson", data: EMPTY, promoteId: "feature_id" });
    m.addSource("mask", { type: "geojson", data: EMPTY });
    // Data layers go under the basemap's labels so place names stay readable.
    const labels = m.getStyle().layers.find((l) => l.type === "symbol")?.id;
    const add = (layer: Parameters<MlMap["addLayer"]>[0]): void => { m.addLayer(layer, labels); };
    add({ id: "context-fill", type: "fill", source: "context",
      paint: { "fill-color": STATUS_COLORS.not_in_columbus, "fill-opacity": 0.95 } });
    add({ id: "context-dots", type: "fill", source: "context", paint: { "fill-pattern": "dots" } });
    add({ id: "context-line", type: "line", source: "context",
      paint: { "line-color": "#ffffff", "line-width": 0.4 } });
    add({ id: "areas-fill", type: "fill", source: "areas",
      paint: { "fill-color": fillColor([]), "fill-opacity": FILL_OPACITY } });
    add({ id: "areas-hatch", type: "fill", source: "areas",
      paint: { "fill-pattern": "hatch", "fill-opacity": HATCH_OPACITY } });
    add({ id: "areas-line", type: "line", source: "areas",
      paint: { "line-color": LINE_COLOR, "line-width": LINE_WIDTH } });
    add({ id: "mask-fill", type: "fill", source: "mask",
      paint: { "fill-color": STATUS_COLORS.outside_county, "fill-opacity": 1 } });
    add({ id: "mask-line", type: "line", source: "mask",
      paint: { "line-color": "#52514e", "line-width": 1.2 } });
  }

  /** Swap boundaries. `context` is the gray not-in-Columbus layer (council view only). */
  async setAreas(areas: AreaCollection, context: AreaCollection | null, county: AreaCollection): Promise<void> {
    this.hovered = null;
    this.selected = null;
    this.map.removeFeatureState({ source: "areas" });
    this.ids = areas.features.map((f) => f.properties.feature_id);
    const outside = context
      ? context.features.filter((f) => f.properties.jurisdiction !== "COLUMBUS")
      : [];
    const outline = county.features[0]?.geometry;
    const source = (id: string): GeoJSONSource => this.map.getSource(id) as GeoJSONSource;
    // Wait for the data to load so feature states land on the new features.
    await Promise.all([
      source("areas").setData(areas),
      source("context").setData({ type: "FeatureCollection", features: outside }),
      source("mask").setData(outline ? { type: "FeatureCollection", features: [outsideMask(outline)] } : EMPTY),
    ]);
  }

  /** Color every area: states keyed by feature_id; areas missing from `states` get no_data. */
  paint(binColors: string[], states: Map<string, AreaState>): void {
    this.map.setPaintProperty("areas-fill", "fill-color", fillColor(binColors));
    for (const id of this.ids) {
      const s = states.get(id) ?? { status: "no_data", bin: -1 };
      this.map.setFeatureState({ source: "areas", id }, { status: s.status, bin: s.bin });
    }
  }

  select(featureId: string | null): void {
    if (this.selected) this.map.setFeatureState({ source: "areas", id: this.selected }, { selected: false });
    this.selected = featureId;
    if (featureId) this.map.setFeatureState({ source: "areas", id: featureId }, { selected: true });
  }

  hitAt(e: MapMouseEvent): Hit {
    const pick = (layer: string): MapGeoJSONFeature | undefined =>
      this.map.queryRenderedFeatures(e.point, { layers: [layer] })[0];
    const area = pick("areas-fill");
    if (pick("mask-fill")) return { kind: "outside_county" };
    if (area) {
      const p = area.properties as { feature_id: string; name: string };
      return { kind: "area", featureId: p.feature_id, name: p.name };
    }
    const ctx = pick("context-fill");
    if (ctx) return { kind: "not_in_columbus", name: (ctx.properties as { name: string }).name };
    return null;
  }

  setHover(featureId: string | null): void {
    if (this.hovered === featureId) return;
    if (this.hovered) this.map.setFeatureState({ source: "areas", id: this.hovered }, { hover: false });
    this.hovered = featureId;
    if (featureId) this.map.setFeatureState({ source: "areas", id: featureId }, { hover: true });
    this.map.getCanvas().style.cursor = featureId ? "pointer" : "";
  }
}
