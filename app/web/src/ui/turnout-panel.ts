// Click detail for the Turnout entry: registered voters, ballots, turnout, and each party's
// ballots as a share of registered voters and of all ballots cast.

import type { TurnoutDetail } from "../types";
import { compact, el } from "./dom";
import { METHOD_TEXT, percent, votes } from "./format";

const pct = (x: number | null): string => (x === null ? "—" : percent(x));

function partyTable(d: TurnoutDetail): HTMLElement {
  const head = el("tr", {}, el("th", {}, "Ballot"), el("th", { class: "num" }, "Ballots"),
    el("th", { class: "num" }, "% of registered"), el("th", { class: "num" }, "% of ballots"));
  const all = el("tr", {}, el("th", { scope: "row" }, "All ballots"), el("td", { class: "num" }, d.ballots_cast === null ? "—" : votes(d.ballots_cast)),
    el("td", { class: "num" }, pct(d.turnout)), el("td", { class: "num" }, d.ballots_cast ? "100%" : "—"));
  const rows = d.parties.map((p) =>
    el("tr", {}, el("th", { scope: "row" }, p.label), el("td", { class: "num" }, p.ballots === null ? "—" : votes(p.ballots)),
      el("td", { class: "num" }, pct(p.of_registered)), el("td", { class: "num" }, pct(p.of_ballots))));
  return el("table", { class: "choices" }, el("thead", {}, head), el("tbody", {}, all, ...rows));
}

function contributions(d: TurnoutDetail): HTMLElement | null {
  if (d.contributions.length === 0) return null;
  const items = d.contributions.map((c) =>
    el("li", {}, `${c.precinct}: ${c.split_share >= 0.9999 ? "whole precinct" : `${percent(c.split_share)} of precinct (${c.weight_basis})`}`,
      c.precinct_ballots === null ? "" : `, ${votes(c.precinct_ballots)} ballots`));
  return el("details", {}, el("summary", {}, `${d.contributions.length} precincts`), el("ul", { class: "precincts" }, ...items));
}

export function renderTurnoutDetail(target: HTMLElement, d: TurnoutDetail, onClose: () => void): void {
  const close = el("button", { type: "button", class: "close", "aria-label": "Close details" }, "×");
  close.addEventListener("click", onClose);
  const summary = d.registered === null || d.ballots_cast === null ? null
    : el("p", { class: "small" }, `Turnout ${pct(d.turnout)}: ${votes(d.ballots_cast)} ballots from ${votes(d.registered)} registered voters.`);
  target.replaceChildren(
    ...compact(
      close,
      el("h2", {}, d.name),
      summary,
      partyTable(d),
      d.method ? el("p", { class: "small" }, METHOD_TEXT[d.method] ?? d.method) : null,
      contributions(d),
      d.retroactive ? el("p", { class: "small" }, "Boundaries are applied to this earlier election.") : null,
      el("p", { class: "source" }, `Source: ${d.source_file}`, el("br"), el("span", { class: "sha" }, `sha256 ${d.source_sha256.slice(0, 16)}…`)),
    ),
  );
  target.hidden = false;
}
