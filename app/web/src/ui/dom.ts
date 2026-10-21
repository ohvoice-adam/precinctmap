// Tiny DOM helpers: no framework, no innerHTML with data (all text goes through textContent).

type Attrs = Record<string, string | boolean | undefined>;

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Attrs = {},
  ...children: (Node | string | null | undefined)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === false) continue;
    if (k === "class") node.className = String(v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const child of children) {
    if (child === null || child === undefined) continue;
    node.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

/** Drop null/undefined so optional pieces can be listed inline. */
export function compact(...nodes: (Node | string | null | undefined)[]): (Node | string)[] {
  return nodes.filter((n): n is Node | string => n !== null && n !== undefined);
}

export function option(value: string, label: string, selected: boolean): HTMLOptionElement {
  const o = el("option", { value }, label);
  o.selected = selected;
  return o;
}

export function labeled(label: string, control: HTMLElement, id: string): HTMLElement {
  control.id = id;
  return el("div", { class: "field" }, el("label", { for: id }, label), control);
}
