// Sortable table of the mapped statistic, one row per area of the current geography.
// Click a column header to sort (again to reverse); areas without a value always sort last.
// Clicking an area name opens its detail panel; hovering a row highlights the area on the map.

import { el } from "./dom";

export interface TableRow {
  id: string;
  name: string;
  value: number | null; // sort key for the statistic column
  display: string; // formatted statistic ("—" when there is none)
  count: number | null;
  countDisplay: string;
  note: string;
  moe?: number | null; // census: 90% margin of error, in the value's units
}

export interface TableSpec {
  caption: string;
  valueLabel: string;
  countLabel: string;
  source: string; // source file the values trace back to
  rows: TableRow[];
}

export type SortKey = "name" | "value" | "count";
export interface Sort {
  key: SortKey;
  desc: boolean;
}

const collator = new Intl.Collator("en-US", { numeric: true, sensitivity: "base" });

/** Rows sorted by `sort`; nulls last in both directions; ties fall back to area name. */
export function sortRows(rows: TableRow[], sort: Sort): TableRow[] {
  const dir = sort.desc ? -1 : 1;
  const byName = (a: TableRow, b: TableRow): number => collator.compare(a.name, b.name);
  return [...rows].sort((a, b) => {
    if (sort.key === "name") return dir * byName(a, b);
    const x = a[sort.key];
    const y = b[sort.key];
    if (x === null || y === null) return x === y ? byName(a, b) : x === null ? 1 : -1;
    return x === y ? byName(a, b) : dir * (x - y);
  });
}

export class AreaTable {
  readonly root = el("section", { class: "table-pane", "aria-label": "Table of the mapped statistic" });
  private spec: TableSpec | null = null;
  private sort: Sort = { key: "value", desc: true };
  private selected: string | null = null;
  private body = el("tbody");

  constructor(
    private readonly onOpen: (id: string) => void,
    private readonly onHover: (id: string | null) => void,
  ) {
    this.root.addEventListener("mouseleave", () => { this.onHover(null); });
  }

  /** The statistic on display (for the "this measure only" export). */
  get current(): TableSpec | null {
    return this.spec;
  }

  render(spec: TableSpec): void {
    this.spec = spec;
    this.draw();
  }

  /** Highlight a row (and scroll it into view when the selection came from the map). */
  select(id: string | null, scroll = false): void {
    this.selected = id;
    for (const tr of this.body.rows) tr.classList.toggle("selected", tr.dataset.id === id);
    if (scroll && id) [...this.body.rows].find((tr) => tr.dataset.id === id)?.scrollIntoView({ block: "nearest" });
  }

  private header(key: SortKey, label: string, numeric: boolean): HTMLTableCellElement {
    const active = this.sort.key === key;
    const button = el("button", { type: "button", class: "sort" }, label, el("span", { class: "arrow", "aria-hidden": "true" }, active ? (this.sort.desc ? "▼" : "▲") : ""));
    button.addEventListener("click", () => {
      this.sort = active ? { key, desc: !this.sort.desc } : { key, desc: key !== "name" };
      this.draw();
    });
    const sort = active ? (this.sort.desc ? "descending" : "ascending") : undefined;
    return el("th", { scope: "col", class: numeric ? "num" : undefined, "aria-sort": sort }, button);
  }

  private row(r: TableRow): HTMLTableRowElement {
    const name = el("button", { type: "button", class: "area-link" }, r.name);
    name.addEventListener("click", () => { this.onOpen(r.id); });
    const tr = el("tr", { class: r.id === this.selected ? "selected" : undefined },
      el("th", { scope: "row" }, name),
      el("td", { class: "num" }, r.display),
      el("td", { class: "num" }, r.countDisplay),
      el("td", { class: "note" }, r.note));
    tr.dataset.id = r.id;
    tr.addEventListener("mouseenter", () => { this.onHover(r.id); });
    return tr;
  }

  private draw(): void {
    const spec = this.spec;
    if (!spec) return;
    this.body = el("tbody", {}, ...sortRows(spec.rows, this.sort).map((r) => this.row(r)));
    const withValue = spec.rows.filter((r) => r.value !== null).length;
    this.root.replaceChildren(
      el("div", { class: "table-scroll" },
        el("table", { class: "areas" },
          el("caption", {}, spec.caption, el("span", { class: "small" }, ` · ${withValue.toLocaleString("en-US")} of ${spec.rows.length.toLocaleString("en-US")} areas with a value`)),
          el("thead", {}, el("tr", {},
            this.header("name", "Area", false),
            this.header("value", spec.valueLabel, true),
            this.header("count", spec.countLabel, true),
            el("th", { scope: "col" }, "Notes"))),
          this.body)),
    );
  }
}
