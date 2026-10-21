import type { PropertyDetail, PropertyStats } from "./property/model";
import type { AreaCollection, Catalog, Detail, Results } from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function getJson<T>(path: string, params: Record<string, string> = {}): Promise<T> {
  const url = `${path}?${new URLSearchParams(params).toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      // non-JSON error body: keep the status text
    }
    throw new ApiError(`${path}: ${detail}`, res.status);
  }
  return (await res.json()) as T;
}

const geoCache = new Map<string, Promise<AreaCollection>>();
const resultsCache = new Map<string, Promise<Results>>();

export function fetchCatalog(): Promise<Catalog> {
  return getJson<Catalog>("/api/catalog");
}

/** Boundaries for a geography on a date; cached so switching contests never refetches. */
export function fetchGeo(geography: string, date: string): Promise<AreaCollection> {
  const key = `${geography}|${date}`;
  let hit = geoCache.get(key);
  if (!hit) {
    hit = getJson<AreaCollection>(`/api/geo/${geography}`, { date });
    hit.catch(() => geoCache.delete(key));
    geoCache.set(key, hit);
  }
  return hit;
}

export function fetchResults(election: string, contest: string, geography: string): Promise<Results> {
  const key = `${election}|${contest}|${geography}`;
  let hit = resultsCache.get(key);
  if (!hit) {
    hit = getJson<Results>("/api/results", { election, contest, geography });
    hit.catch(() => resultsCache.delete(key));
    resultsCache.set(key, hit);
  }
  return hit;
}

export function fetchDetail(
  election: string,
  contest: string,
  geography: string,
  feature: string,
): Promise<Detail> {
  return getJson<Detail>("/api/results/detail", { election, contest, geography, feature });
}

export function exportUrl(kind: "csv" | "geojson", election: string, contest: string, geography: string): string {
  return `/api/export.${kind}?${new URLSearchParams({ election, contest, geography }).toString()}`;
}

const propertyCache = new Map<string, Promise<PropertyStats>>();

export function fetchProperty(metric: string, geography: string): Promise<PropertyStats> {
  const key = `${metric}|${geography}`;
  let hit = propertyCache.get(key);
  if (!hit) {
    hit = getJson<PropertyStats>("/api/property", { metric, geography });
    hit.catch(() => propertyCache.delete(key));
    propertyCache.set(key, hit);
  }
  return hit;
}

export function fetchPropertyDetail(geography: string, feature: string): Promise<PropertyDetail> {
  return getJson<PropertyDetail>("/api/property/detail", { geography, feature });
}
