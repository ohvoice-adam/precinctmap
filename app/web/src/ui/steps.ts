// Sheet building blocks: numbered drill-down steps, pickers (a native select under a wrapping
// label) and chip groups (native radios). All text goes through textContent.

import { el } from "./dom";

/** One numbered step. `labelFor` is a select's id (a real label) or a chip group's id (the group
 * points at the label through aria-labelledby). */
export function step(n: number, label: string, labelFor: string, ...body: HTMLElement[]): HTMLElement {
  const id = `${labelFor}-label`;
  const lab = body[0]?.getAttribute("role") === "radiogroup"
    ? el("span", { class: "step-label", id }, label)
    : el("label", { class: "step-label", id, for: labelFor }, label);
  return el("div", { class: "step" }, el("span", { class: "step-n", "aria-hidden": "true" }, String(n)), lab, ...body);
}

/** A select drawn as a wrapping text field. The select stays on top (transparent), so keyboard,
 * screen readers and the native option list all work as usual. */
export class Picker {
  readonly select = el("select");
  readonly root: HTMLElement;
  private readonly group = el("span", { class: "pick-group" });
  private readonly text = el("span", { class: "pick-value" });

  constructor(id: string, onChange: (value: string) => void, big = false) {
    this.select.id = id;
    this.root = el("div", { class: big ? "pick big" : "pick" },
      el("span", { class: "pick-text", "aria-hidden": "true" }, this.group, this.text), this.select);
    this.select.addEventListener("change", () => { this.sync(); onChange(this.select.value); });
  }

  /** Call after replacing the options. Shows the selected option and its optgroup, if any. */
  sync(showGroup = false): void {
    const opt = this.select.selectedOptions[0];
    this.text.textContent = opt?.textContent ?? "";
    const parent = opt?.parentElement;
    const group = showGroup && parent instanceof HTMLOptGroupElement ? parent.label : "";
    this.group.textContent = group === this.text.textContent ? "" : group;
    this.group.hidden = !this.group.textContent;
  }
}

export interface Chip {
  value: string;
  label: string;
}

/** A single-choice group of native radio buttons styled as chips (or a segmented control). */
export class ChipGroup {
  readonly root: HTMLElement;

  constructor(private readonly name: string, private readonly onChange: (value: string) => void, segmented = false) {
    this.root = el("div", { class: segmented ? "chips seg" : "chips", role: "radiogroup", id: name, "aria-labelledby": `${name}-label` });
  }

  render(chips: Chip[], current: string): void {
    this.root.replaceChildren(
      ...chips.map((c) => {
        const input = el("input", { type: "radio", name: this.name, value: c.value });
        input.checked = c.value === current;
        input.addEventListener("change", () => { if (input.checked) this.onChange(c.value); });
        return el("label", { class: "chip" }, input, el("span", {}, c.label));
      }),
    );
  }
}
