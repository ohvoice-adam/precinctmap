import "maplibre-gl/dist/maplibre-gl.css";
import "@fontsource-variable/bricolage-grotesque/opsz.css";
import "@fontsource-variable/instrument-sans/index.css";
import "./styles.css";
import "./ui/sheet.css";
import "./ui/summary.css";
import "./ui/legend.css";
import "./ui/detail.css";
import "./ui/table.css";

import { startupError } from "./api";
import { App } from "./app";
import { createHeader } from "./header";
import { el } from "./ui/dom";

window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled promise rejection in precinctmap web client:", event.reason);
});

function mount(root: HTMLElement): void {
  // The sheet floats over the map's left edge (desktop) or sits under the map (phones).
  const sidebar = el("aside", { class: "sidebar sheet", "aria-label": "Choose what to map" },
    createHeader("Election, property and census map"));
  const mapEl = el("div", { id: "map", role: "region", "aria-label": "Results map" });
  const bar = el("div", { class: "stage-bar" });
  const body = el("div", { class: "stage-body" }, el("div", { class: "map-pane" }, mapEl));
  const stage = el("main", { class: "stage" }, bar, body);
  root.append(el("div", { class: "body" }, stage, sidebar));
  const app = new App(sidebar, { stage, bar, body, mapEl });
  app.start().catch((err: unknown) => {
    console.error("precinctmap failed to start", err);
    sidebar.append(el("p", { class: "error" }, startupError(err)));
  });
}

const root = document.getElementById("app");
if (!root) throw new Error("precinctmap: #app element missing from index.html");
mount(root);
