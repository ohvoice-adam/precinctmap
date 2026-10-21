import type { Dataset, MeasureDetail, MeasureStats } from "./measures/model";
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

const measureCache = new Map<string, Promise<MeasureStats>>();

/** One area statistic for a geography: `/api/property` or `/api/census`. */
export function fetchMeasure(dataset: Dataset, metric: string, geography: string): Promise<MeasureStats> {
  const key = `${dataset}|${metric}|${geography}`;
  let hit = measureCache.get(key);
  if (!hit) {
    hit = getJson<MeasureStats>(`/api/${dataset}`, { metric, geography });
    hit.catch(() => measureCache.delete(key));
    measureCache.set(key, hit);
  }
  return hit;
}

export function fetchMeasureDetail(dataset: Dataset, geography: string, feature: string): Promise<MeasureDetail> {
  return getJson<MeasureDetail>(`/api/${dataset}/detail`, { geography, feature });
}
