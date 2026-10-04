/** Client-side navigation for links outside the header (the App listens to popstate). */
export function navigate(e: React.MouseEvent<HTMLAnchorElement>, to: string) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  window.history.pushState({}, "", to);
  window.dispatchEvent(new PopStateEvent("popstate"));
  const hash = to.split("#")[1];
  requestAnimationFrame(() => {
    const el = hash ? document.getElementById(hash) : null;
    if (el) el.scrollIntoView();
    else window.scrollTo(0, 0);
    (el ?? document.getElementById("main"))?.focus({ preventScroll: true });
  });
}
