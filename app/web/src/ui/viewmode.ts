// Map / table / side-by-side switch. Side by side is offered (and is the default) only when the
// viewport is wide enough; on narrower screens a "both" choice falls back to the map.

import { el } from "./dom";

export type ViewMode = "map" | "table" | "both";

/** Narrowest viewport with room for the sidebar, a usable map and the table. */
export const WIDE_QUERY = "(min-width: 1180px)";

const LABELS: Record<ViewMode, string> = { map: "Map", table: "Table", both: "Map and table" };

/** The layout actually shown for a choice at the current width. */
export function effectiveView(choice: ViewMode | null, wide: boolean): ViewMode {
  if (choice === null) return wide ? "both" : "map";
  return choice === "both" && !wide ? "map" : choice;
}

export class ViewToggle {
  readonly root = el("div", { class: "view-toggle", role: "group", "aria-label": "Show" });
  private choice: ViewMode | null = null;
  private readonly media = window.matchMedia(WIDE_QUERY);
  private readonly buttons = new Map<ViewMode, HTMLButtonElement>();

  constructor(private readonly onChange: (view: ViewMode) => void) {
    for (const mode of ["map", "table", "both"] as const) {
      const b = el("button", { type: "button" }, LABELS[mode]);
      b.addEventListener("click", () => { this.choice = mode; this.apply(); });
      this.buttons.set(mode, b);
      this.root.append(b);
    }
    this.media.addEventListener("change", () => { this.apply(); });
  }

  get view(): ViewMode {
    return effectiveView(this.choice, this.media.matches);
  }

  apply(): void {
    const view = this.view;
    for (const [mode, b] of this.buttons) {
      b.setAttribute("aria-pressed", String(mode === view));
      b.hidden = mode === "both" && !this.media.matches;
    }
    this.onChange(view);
  }
}
