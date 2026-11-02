import { describe, expect, it } from "vitest";

import { renderLegend } from "../ui/legend";
import type { PatternImage } from "./style";
import { STATUS_COLORS, dotsImage, hatchImage, patternBackground } from "./style";

function lit(img: PatternImage): [number, number][] {
  const out: [number, number][] = [];
  for (let y = 0; y < img.height; y++) {
    for (let x = 0; x < img.width; x++) if ((img.data[(y * img.width + x) * 4 + 3] ?? 0) > 0) out.push([x, y]);
  }
  return out;
}

describe("map patterns", () => {
  it("draws the low-count hatch rising left to right (\"/\" on screen, rows run top to bottom)", () => {
    const px = lit(hatchImage());
    expect(px.length).toBeGreaterThan(0);
    for (const [x, y] of px) expect([0, 7]).toContain((x + y) % 8); // x + y constant: up and to the right
    expect(px.some(([x, y]) => x === 7 && y === 0)).toBe(true); // reaches the top-right corner
  });

  it("uses dots, not a second diagonal, for areas outside Columbus", () => {
    const px = lit(dotsImage());
    expect(px).toHaveLength(8); // two 2 x 2 dots per tile
    const onHatch = px.filter(([x, y]) => (x + y) % 8 === 0 || (x + y) % 8 === 7);
    expect(onHatch.length).toBeLessThan(px.length); // not the hatch's lines
  });

  it("builds legend swatches from the exact tiles the map uses", () => {
    const css = patternBackground(hatchImage(), "#ffffff");
    const svg = decodeURIComponent(/data:image\/svg\+xml,([^"]+)"/.exec(css)?.[1] ?? "");
    const rects = [...svg.matchAll(/<rect x='(\d+)' y='(\d+)'/g)].map((m) => [Number(m[1]), Number(m[2])]);
    expect(rects).toEqual(lit(hatchImage()));
    expect(css).toMatch(/0 0 \/ 8px 8px repeat #ffffff$/);
  });

  it("shows each pattern once in the council legend: hatch for low counts, dots for not in Columbus", () => {
    const target = document.createElement("section");
    renderLegend(target, { kind: "sequential", title: "x", bins: [] }, "council_district", new Map());
    const items = [...target.querySelectorAll(".legend-states li")];
    const style = (text: RegExp): string =>
      items.find((li) => text.test(li.textContent))?.querySelector(".swatch")?.getAttribute("style") ?? "";
    expect(style(/votes \(hatched\)/)).toMatch(new RegExp(`^background:${escape(patternBackground(hatchImage(), "#ffffff"))}(;|$)`));
    expect(style(/Not in Columbus/)).toBe(`background:${patternBackground(dotsImage(), STATUS_COLORS.not_in_columbus)}`);
  });

  it("counts areas per bin from the painted states, high bins first", () => {
    const target = document.createElement("section");
    const bins = [
      { from: 0, to: 0.5, color: "#d3eee7", label: "0–50%" },
      { from: 0.5, to: 1, color: "#0c4037", label: "50–100%" },
    ];
    const states = new Map([
      ["a", { status: "value", bin: 1 }],
      ["b", { status: "value", bin: 1 }],
      ["c", { status: "low", bin: 0 }],
      ["d", { status: "not_on_ballot", bin: -1 }],
    ]);
    renderLegend(target, { kind: "sequential", title: "Share", bins }, "precinct", states);
    const rows = [...target.querySelectorAll(".legend-bins li")].map((li) => [li.querySelector(".r")?.textContent, li.querySelector(".c")?.textContent]);
    expect(rows).toEqual([["50–100%", "2"], ["0–50%", "1"]]);
    const states_ = [...target.querySelectorAll(".legend-states li")].map((li) => li.querySelector(".c")?.textContent);
    expect(states_.slice(0, 2)).toEqual(["1", "1"]); // one hatched, one with nothing to map
    expect(target.querySelector(".legend-unit")?.textContent).toBe("precincts");
  });
});

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
}
