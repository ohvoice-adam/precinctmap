// Map fill transparency slider. A display preference like the view switch: remembered in this
// browser, not part of the URL. 100% is the map's normal look; lower lets the basemap show through.

import { el } from "./dom";

export const OPACITY_MIN = 20;
export const OPACITY_MAX = 100;
export const OPACITY_STEP = 5;
const KEY = "precinctmap.fillOpacity";

/** Clamp to the slider's range and snap to its step; anything unusable becomes 100. */
export function clampOpacity(pct: number): number {
  if (!Number.isFinite(pct)) return OPACITY_MAX;
  const snapped = Math.round(pct / OPACITY_STEP) * OPACITY_STEP;
  return Math.min(OPACITY_MAX, Math.max(OPACITY_MIN, snapped));
}

function load(): number {
  try {
    const raw = localStorage.getItem(KEY);
    return raw === null ? OPACITY_MAX : clampOpacity(Number(raw));
  } catch {
    return OPACITY_MAX; // storage blocked: the slider still works for this visit
  }
}

function save(pct: number): void {
  try {
    localStorage.setItem(KEY, String(pct));
  } catch {
    /* not remembered */
  }
}

export class OpacitySlider {
  readonly root = el("label", { class: "opacity-ctl" });
  private readonly input = el("input", {
    type: "range", min: String(OPACITY_MIN), max: String(OPACITY_MAX), step: String(OPACITY_STEP),
  });
  private readonly out = el("output", {});

  constructor(private readonly onChange: (factor: number) => void) {
    this.root.append(el("span", {}, "Map opacity"), this.input, this.out);
    this.input.value = String(load());
    this.input.addEventListener("input", () => {
      const pct = clampOpacity(Number(this.input.value));
      save(pct);
      this.apply();
    });
  }

  /** Show the current value and pass it on as a 0.2-1 factor. */
  apply(): void {
    const pct = clampOpacity(Number(this.input.value));
    this.out.textContent = `${pct}%`;
    this.input.setAttribute("aria-valuetext", `${pct}%`);
    this.onChange(pct / 100);
  }
}
