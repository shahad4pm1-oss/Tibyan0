/* Theme preference: "light" | "dark" chosen by the visitor, or null to follow the system.
   Stored in localStorage when available; the page works the same without storage. */
export type Theme = "light" | "dark";
const KEY = "tibyan-theme";

export function storedTheme(): Theme | null {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

export function systemTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(t: Theme | null) {
  const root = document.documentElement;
  if (t) root.setAttribute("data-theme", t);
  else root.removeAttribute("data-theme");
  try {
    if (t) window.localStorage.setItem(KEY, t);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: preference lasts for this page view only */
  }
}
