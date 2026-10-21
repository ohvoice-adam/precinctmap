// Hover tooltip that follows the pointer. Text only (no innerHTML).

import { el } from "./dom";

export class Tooltip {
  readonly root = el("div", { class: "tooltip", role: "status", "aria-live": "polite" });

  constructor(container: HTMLElement) {
    this.root.hidden = true;
    container.append(this.root);
  }

  show(lines: string[], x: number, y: number): void {
    const [title, ...rest] = lines;
    this.root.replaceChildren(el("strong", {}, title ?? ""), ...rest.map((l) => el("div", {}, l)));
    this.root.style.transform = `translate(${x + 14}px, ${y + 14}px)`;
    this.root.hidden = false;
  }

  hide(): void {
    this.root.hidden = true;
  }
}
