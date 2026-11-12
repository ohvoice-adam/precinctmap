import { describe, expect, it } from "vitest";

import { fillOpacity } from "../map/style";
import { OPACITY_MAX, OPACITY_MIN, clampOpacity } from "./opacity";

describe("clampOpacity", () => {
  it("keeps in-range values and snaps to the step", () => {
    expect(clampOpacity(60)).toBe(60);
    expect(clampOpacity(62)).toBe(60);
    expect(clampOpacity(63)).toBe(65);
  });
  it("clamps to the slider range and rejects junk", () => {
    expect(clampOpacity(0)).toBe(OPACITY_MIN);
    expect(clampOpacity(500)).toBe(OPACITY_MAX);
    expect(clampOpacity(Number.NaN)).toBe(OPACITY_MAX);
  });
});

describe("fillOpacity", () => {
  it("is the normal look at 1 and scales both states proportionally", () => {
    expect(fillOpacity()).toEqual(["case", ["==", ["feature-state", "status"], "low"], 0.45, 0.88]);
    expect(fillOpacity(0.5)).toEqual(["case", ["==", ["feature-state", "status"], "low"], 0.225, 0.44]);
  });
});
