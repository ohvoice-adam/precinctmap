// Admin upload page: upload -> review report -> commit (enabled only for a ready report).
// The page itself is served behind the admin login; the browser re-sends those credentials.

import "../styles.css";
import "./admin.css";

import { createHeader } from "../header";
import { compact, el, option } from "../ui/dom";
import type { StagedReport } from "./review";
import { canCommit, facts, statusText } from "./review";

window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled promise rejection on admin page:", event.reason);
});

const ADMIN_HEADER = { "X-PRECINCTMAP-Admin": "1" };

async function post<T>(url: string, body?: FormData): Promise<T> {
  const res = await fetch(url, { method: "POST", headers: ADMIN_HEADER, body: body ?? null });
  const data = (await res.json()) as T & { detail?: string };
  if (!res.ok) throw new Error(data.detail ?? res.statusText);
  return data;
}

function field(label: string, control: HTMLElement, hint?: string): HTMLElement {
  return el("label", { class: "field" }, el("span", {}, label), control, hint ? el("small", {}, hint) : null);
}

function build(root: HTMLElement): void {
  const file = el("input", { type: "file", accept: ".xlsx", required: true });
  const date = el("input", { type: "date" });
  const type = el("select", {}, option("", "Detect from the file", true), option("primary", "Primary", false),
    option("general", "General", false), option("special", "Special", false));
  const certified = el("select", {}, option("", "Detect from the file name", true), option("true", "Yes", false), option("false", "No", false));
  const reprocess = el("input", { type: "checkbox" });
  const review = el("button", { type: "submit", class: "primary" }, "Review file");
  const form = el("form", { class: "upload" },
    field("Results spreadsheet (.xlsx)", file),
    field("Election date", date, "Only needed when the file name has no year."),
    field("Election type", type), field("Certified", certified),
    el("label", { class: "check" }, reprocess, " Re-process a file that is already loaded"), review);
  const result = el("section", { class: "result", "aria-live": "polite" });
  root.append(createHeader("Election results map · Admin"),
    el("main", { class: "admin" }, el("h1", {}, "Add an election"),
      el("p", {}, "Upload the Board of Elections precinct results export. Nothing changes on the map until you review the report and choose Add to the map."),
      form, result));

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const fd = new FormData();
    const picked = file.files?.[0];
    if (!picked) return;
    fd.append("file", picked);
    if (date.value) fd.append("election_date", date.value);
    if (type.value) fd.append("election_type", type.value);
    if (certified.value) fd.append("certified", certified.value);
    fd.append("reprocess", reprocess.checked ? "true" : "false");
    review.disabled = true;
    result.replaceChildren(el("p", {}, "Reviewing…"));
    post<StagedReport>("/api/ingest", fd)
      .then((staged) => { showReport(result, staged); })
      .catch((err: unknown) => { result.replaceChildren(el("p", { class: "error" }, String(err))); })
      .finally(() => { review.disabled = false; });
  });
}

function showReport(target: HTMLElement, staged: StagedReport): void {
  const commit = el("button", { type: "button", class: "primary" }, "Add to the map");
  const replaces = staged.report.replaces;
  const confirm = el("input", { type: "checkbox" });
  const confirmRow = replaces
    ? el("label", { class: "check confirm" }, confirm,
        ` Replace the loaded file ${replaces.filename} (${replaces.contests} contests) with this one`)
    : null;
  commit.disabled = !canCommit(staged, confirm.checked);
  confirm.addEventListener("change", () => { commit.disabled = !canCommit(staged, confirm.checked); });
  const outcome = el("div", { "aria-live": "polite" });
  commit.addEventListener("click", () => {
    commit.disabled = true;
    outcome.replaceChildren(el("p", {}, "Adding…"));
    post<{ election_id: string; detail: string; reconciliation: { geography: string; choices: number; failures: number }[] }>(
      `/api/ingest/${encodeURIComponent(staged.staging_id)}/commit${replaces ? "?replace=true" : ""}`,
    )
      .then((done) => {
        const ok = done.reconciliation.every((r) => r.failures === 0);
        outcome.replaceChildren(
          el("p", { class: ok ? "ok" : "error" }, ok ? `Added. ${done.detail}. Totals reconcile for every map view.` : "Added, but some totals did not reconcile. Check the server log."),
          el("a", { href: `/?e=${encodeURIComponent(done.election_id)}` }, "View it on the map"),
        );
      })
      .catch((err: unknown) => {
        outcome.replaceChildren(el("p", { class: "error" }, String(err)));
        commit.disabled = false;
      });
  });
  const list = (title: string, items: string[], cls: string): HTMLElement | null =>
    items.length ? el("div", { class: cls }, el("h3", {}, title), el("ul", {}, ...items.map((i) => el("li", {}, i)))) : null;
  target.replaceChildren(
    ...compact(
    el("h2", {}, staged.report.filename),
    el("p", { class: `status status-${staged.status}` }, statusText(staged)),
    list("Problems", staged.report.blockers, "blockers"),
    list("Check before adding", staged.report.warnings, "warnings"),
    el("dl", { class: "facts" }, ...facts(staged).flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])),
    el("details", {}, el("summary", {}, "Full review report"), el("pre", {}, staged.report_text)),
    confirmRow,
    commit,
    outcome,
    ),
  );
}

const root = document.getElementById("app");
if (!root) throw new Error("admin: #app element missing");
build(root);
