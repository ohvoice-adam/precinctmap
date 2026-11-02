// Phone layout helpers. Below FLOATING_SHEET_QUERY the sheet sits under a pinned map, so the
// detail panel moves into the sheet (under the map, not over it) and taps don't show the hover card.

/** Matches the phone breakpoint in styles.css: below it the sheet sits under the map. */
export const FLOATING_SHEET_QUERY = "(min-width: 761px)";

/** Keep `panel` over the map while the sheet floats; otherwise put it in the sheet right after `after`. */
export function placeDetail(panel: HTMLElement, overMap: HTMLElement, after: Element): void {
  const media = window.matchMedia(FLOATING_SHEET_QUERY);
  const place = (): void => {
    if (media.matches) overMap.append(panel);
    else after.after(panel);
  };
  media.addEventListener("change", place);
  place();
}

/** On phones, scroll an opened panel into view below the pinned map (scroll-margin in styles.css). */
export function revealDetail(panel: HTMLElement): void {
  if (panel.hidden || window.matchMedia(FLOATING_SHEET_QUERY).matches) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  panel.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
}

/** Whether the last pointer over `target` was a finger, so the mouse events a tap fires aren't read as hovers. */
export function touchTracker(target: HTMLElement): () => boolean {
  let touch = false;
  const track = (e: PointerEvent): void => { touch = e.pointerType === "touch"; };
  target.addEventListener("pointerdown", track);
  target.addEventListener("pointermove", track);
  return () => touch;
}
