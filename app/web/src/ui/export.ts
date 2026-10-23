// "This measure only" CSV: the rows of the table on display (one statistic per area, the same
// values the map colors), built in the browser. The API's exports carry every choice or measure.

import { el } from "./dom";
import type { TableSpec } from "./table";

// A text cell starting with one of these could run as a formula in a spreadsheet; a leading
// minus is allowed before a number ("-$12,500").
const FORMULA = /^(?:[=+@\t\r]|-(?![\d$.]))/;

function field(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "";
  let s = String(v);
  if (typeof v === "string" && FORMULA.test(s)) s = `'${s}`;
  return /[",\r\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s;
}

/** CSV text for the table's statistic; shares are fractions in `value`, as displayed in `value_formatted`. */
export function tableCsv(spec: TableSpec): string {
  const moe = spec.rows.some((r) => r.moe !== undefined && r.moe !== null);
  const header = ["feature_id", "area", "measure", "value", "value_formatted", ...(moe ? ["moe_90"] : []), "count_label", "count", "notes", "view", "source_file"];
  const lines = spec.rows.map((r) =>
    [r.id, r.name, spec.valueLabel, r.value, r.value === null ? "" : r.display, ...(moe ? [r.moe] : []), spec.countLabel, r.count, r.note, spec.caption, spec.source]
      .map(field).join(","));
  return [header.join(","), ...lines].join("\r\n") + "\r\n";
}

export function csvFilename(spec: TableSpec): string {
  const slug = spec.caption.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);
  return `${slug || "export"}.csv`;
}

/** Button that downloads the current table as CSV (with a BOM so Excel reads UTF-8). */
export function measureOnlyButton(current: () => TableSpec | null): HTMLButtonElement {
  const button = el("button", { type: "button", class: "link" }, "CSV (this measure only)");
  button.addEventListener("click", () => {
    const spec = current();
    if (!spec) return;
    const url = URL.createObjectURL(new Blob(["﻿", tableCsv(spec)], { type: "text/csv;charset=utf-8" }));
    const a = el("a", { href: url, download: csvFilename(spec) });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => { URL.revokeObjectURL(url); }, 0);
  });
  return button;
}
