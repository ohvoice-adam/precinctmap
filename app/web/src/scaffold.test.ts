import { describe, expect, it } from "vitest";

import { ApiError, startupError } from "./api";
import { createHeader } from "./header";
import { BASEMAP_STYLE_URL, FRANKLIN_BOUNDS, FRANKLIN_CENTER, initialView } from "./map/config";

describe("map config", () => {
  it("centers inside the Franklin County bounds", () => {
    const [w, s, e, n] = FRANKLIN_BOUNDS;
    const [lng, lat] = FRANKLIN_CENTER;
    expect(lng).toBeGreaterThan(w);
    expect(lng).toBeLessThan(e);
    expect(lat).toBeGreaterThan(s);
    expect(lat).toBeLessThan(n);
  });

  it("max bounds strictly contain the county", () => {
    const [w, s, e, n] = FRANKLIN_BOUNDS;
    const [mw, ms, me, mn] = initialView().maxBounds as [number, number, number, number];
    expect(mw).toBeLessThan(w);
    expect(ms).toBeLessThan(s);
    expect(me).toBeGreaterThan(e);
    expect(mn).toBeGreaterThan(n);
  });

  it("uses a keyless, no-tracking basemap", () => {
    expect(BASEMAP_STYLE_URL).toMatch(/^https:\/\/tiles\.openfreemap\.org\//);
    expect(BASEMAP_STYLE_URL).not.toMatch(/mapbox|google|access_token|key=/i);
  });
});

describe("header", () => {
  it("renders a sentence-case title and no organization name by default", () => {
    const h = createHeader("Election results map", "");
    expect(h.tagName).toBe("HEADER");
    expect(h.querySelector(".app-org")).toBeNull();
    expect(h.querySelector("h1")?.textContent).toBe("Election results map");
  });

  it("shows the organization name when one is configured", () => {
    const h = createHeader("Election results map", "  Example civic group ");
    expect(h.querySelector(".app-org")?.textContent).toBe("Example civic group");
  });
});

describe("startup error", () => {
  it("passes on the server's reason when the store is unavailable", () => {
    const err = new ApiError("/api/catalog: cannot open the data store", 503, "cannot open the data store data/x.duckdb: permission denied");
    expect(startupError(err)).toBe("The map's data store isn't available: cannot open the data store data/x.duckdb: permission denied");
  });

  it("falls back to a reachability hint when there is no response", () => {
    expect(startupError(new TypeError("Failed to fetch"))).toMatch(/could not reach its server/);
    expect(startupError(new ApiError("/api/catalog: Internal Server Error", 500))).toMatch(/\(\/api\/catalog: Internal Server Error\)/);
  });
});
