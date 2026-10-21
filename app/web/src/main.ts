import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";
import "./ui/table.css";

import { App } from "./app";
import { createHeader } from "./header";
import { el } from "./ui/dom";

window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled promise rejection in precinctmap web client:", event.reason);
});

function mount(root: HTMLElement): void {
  const sidebar = el("aside", { class: "sidebar", "aria-label": "Choose what to map" });
  const mapEl = el("div", { id: "map", role: "region", "aria-label": "Results map" });
  const bar = el("div", { class: "stage-bar" });
  const body = el("div", { class: "stage-body" }, el("div", { class: "map-pane" }, mapEl));
  const stage = el("main", { class: "stage" }, bar, body);
  root.append(createHeader("Election, property and census map"), el("div", { class: "body" }, sidebar, stage));
  const app = new App(sidebar, { stage, bar, body, mapEl });
  app.start().catch((err: unknown) => {
    console.error("precinctmap failed to start", err);
    sidebar.append(el("p", { class: "error" }, "The map could not load its data. Check that the API is running, then reload."));
  });
}

const root = document.getElementById("app");
if (!root) throw new Error("precinctmap: #app element missing from index.html");
mount(root);
