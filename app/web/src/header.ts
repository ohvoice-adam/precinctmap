/** Header: dark bar with an optional organization name (VITE_ORG_NAME at build time) and the app title. */
export function createHeader(title: string, orgName: string = import.meta.env.VITE_ORG_NAME ?? ""): HTMLElement {
  const header = document.createElement("header");
  header.className = "app-header";

  if (orgName.trim()) {
    const org = document.createElement("span");
    org.className = "app-org";
    org.textContent = orgName.trim();
    header.append(org);
  }

  const heading = document.createElement("h1");
  heading.className = "app-title";
  heading.textContent = title;

  header.append(heading);
  return header;
}
