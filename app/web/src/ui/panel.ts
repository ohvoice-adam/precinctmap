// Click detail panel: every choice's votes and share, method with split shares, source file.

import type { Detail, TurnoutDetail } from "../types";
import { compact, el } from "./dom";
import { METHOD_TEXT, percent, votes } from "./format";
import { renderTurnoutDetail } from "./turnout-panel";


function choicesTable(d: Detail): HTMLElement {
  const rows = d.choices.map((c) =>
    el(
      "tr",
      { class: c.counts ? "" : "muted" },
      el("th", { scope: "row" }, c.party ? `${c.name} (${c.party})` : c.name),
      el("td", { class: "num" }, votes(c.votes)),
      el("td", { class: "num" }, c.share === null ? "—" : percent(c.share)),
    ),
  );
  return el(
    "table",
    { class: "choices" },
    el("thead", {}, el("tr", {}, el("th", {}, "Choice"), el("th", { class: "num" }, "Votes"), el("th", { class: "num" }, "Share"))),
    el("tbody", {}, ...rows),
  );
}

function contributions(d: Detail): HTMLElement | null {
  if (d.contributions.length === 0) return null;
  const items = d.contributions.map((c) =>
    el(
      "li",
      {},
      `${c.precinct}: ${c.split_share >= 0.9999 ? "whole precinct" : `${percent(c.split_share)} of precinct (${c.weight_basis})`}`,
      c.precinct_valid_votes === null ? "" : `, ${votes(c.precinct_valid_votes)} valid votes`,
    ),
  );
  return el("details", {}, el("summary", {}, `${d.contributions.length} precincts`), el("ul", { class: "precincts" }, ...items));
}

export function renderDetail(target: HTMLElement, d: Detail | TurnoutDetail, onClose: () => void): void {
  if ("parties" in d) {
    renderTurnoutDetail(target, d, onClose);
    return;
  }
  const close = el("button", { type: "button", class: "close", "aria-label": "Close details" }, "×");
  close.addEventListener("click", onClose);
  const turnout = d.turnout?.turnout;
  target.replaceChildren(
    ...compact(
    close,
    el("h2", {}, d.name),
    d.on_ballot ? choicesTable(d) : el("p", {}, "This contest was not on the ballot here."),
    d.on_ballot ? el("p", { class: "small" }, `${votes(d.valid_votes)} valid votes (over- and under-votes excluded from shares).`) : null,
    turnout === null || turnout === undefined ? null : el("p", { class: "small" }, `Turnout ${percent(turnout)} (${votes(d.turnout?.ballots_cast ?? 0)} of ${votes(d.turnout?.registered ?? 0)} registered).`),
    d.method ? el("p", { class: "small" }, METHOD_TEXT[d.method] ?? d.method) : null,
    contributions(d),
    d.retroactive ? el("p", { class: "small" }, "Boundaries are from July 2025, applied to this earlier election.") : null,
    el("p", { class: "source" }, `Source: ${d.source_file}`, el("br"), el("span", { class: "sha" }, `sha256 ${d.source_sha256.slice(0, 16)}…`)),
    ),
  );
  target.hidden = false;
}

export function renderDetailError(target: HTMLElement, message: string): void {
  target.replaceChildren(el("p", { class: "error" }, message));
  target.hidden = false;
}
