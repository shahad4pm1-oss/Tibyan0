import { useEffect, useRef, useState } from "react";
import { BookOpen, Gauge, Home as HomeIcon, Library, Menu, Moon, Sun, X } from "lucide-react";
import Home from "./pages/Home";
import Methodology from "./pages/Methodology";
import Evaluation from "./pages/Evaluation";
import Sources from "./pages/Sources";
import { BrandMark, ICON } from "./components/ui";
import { applyTheme, storedTheme, systemTheme, type Theme } from "./theme";
import { HealthContext, useHealthLoader } from "./health";

const PAGES = [
  { path: "/", label: "الرئيسية", icon: HomeIcon },
  { path: "/methodology", label: "المنهجية", icon: BookOpen },
  { path: "/evaluation", label: "التقييم", icon: Gauge },
  { path: "/sources", label: "المصادر", icon: Library },
] as const;

const TITLES: Record<string, string> = {
  "/": "تِبيان — تحقق من النص وافهم سياقه",
  "/methodology": "تِبيان — المنهجية",
  "/evaluation": "تِبيان — التقييم",
  "/sources": "تِبيان — المصادر",
};

function currentPath() {
  const p = window.location.pathname.replace(/\/+$/, "") || "/";
  return p in TITLES ? p : "/";
}

export default function App() {
  const [path, setPath] = useState(currentPath());
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => storedTheme() ?? systemTheme());
  const menuBtn = useRef<HTMLButtonElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const health = useHealthLoader();

  useEffect(() => {
    const onPop = () => setPath(currentPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => { document.title = TITLES[path]; }, [path]);

  // follow system changes while the visitor has not chosen a theme
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const on = () => { if (!storedTheme()) setTheme(mq.matches ? "dark" : "light"); };
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  // mobile sheet: focus the first link, close on Escape, keep Tab inside, restore focus on close
  useEffect(() => {
    if (!menuOpen) return;
    const sheet = sheetRef.current;
    sheet?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setMenuOpen(false); return; }
      if (e.key !== "Tab" || !sheet) return;
      const items = Array.from(sheet.querySelectorAll<HTMLElement>("a, button"));
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      menuBtn.current?.focus();
    };
  }, [menuOpen]);

  function go(e: React.MouseEvent<HTMLAnchorElement>, to: string) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    const [p, hash] = to.split("#");
    const target = p || "/";
    window.history.pushState({}, "", to);
    setPath(target in TITLES ? target : "/");
    setMenuOpen(false);
    requestAnimationFrame(() => {
      const el = hash ? document.getElementById(hash) : null;
      if (el) el.scrollIntoView();
      else window.scrollTo(0, 0);
      (el ?? document.getElementById("main"))?.focus({ preventScroll: true });
    });
  }

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }

  const themeLabel = theme === "dark" ? "التبديل إلى الوضع الفاتح" : "التبديل إلى الوضع الداكن";

  return (
    <HealthContext.Provider value={health}>
      <a className="skip" href="#main">انتقل إلى المحتوى</a>
      <header className="site-header">
        <div className="container">
          <a className="brand" href="/" onClick={(e) => go(e, "/")} aria-label="تِبيان، الصفحة الرئيسية">
            <BrandMark />
            <span className="brand-word">تِبيان</span>
          </a>
          <nav className="nav" aria-label="أقسام الموقع">
            <ul>
              {PAGES.map((p) => (
                <li key={p.path}>
                  <a href={p.path} onClick={(e) => go(e, p.path)} aria-current={path === p.path ? "page" : undefined}>
                    {p.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
          <button type="button" className="icon-btn menu-btn" ref={menuBtn} aria-label="القائمة"
            aria-expanded={menuOpen} aria-controls="mobile-menu" onClick={() => setMenuOpen(true)}>
            <Menu {...ICON} size={20} />
          </button>
          <button type="button" className="icon-btn" onClick={toggleTheme} aria-label={themeLabel} title={themeLabel}>
            {theme === "dark" ? <Sun {...ICON} size={19} /> : <Moon {...ICON} size={19} />}
          </button>
        </div>
      </header>

      {menuOpen && (
        <>
          <div className="sheet-backdrop" onClick={() => setMenuOpen(false)} aria-hidden="true" />
          <div className="sheet" id="mobile-menu" role="dialog" aria-modal="true" aria-label="القائمة" ref={sheetRef}>
            <div className="sheet-head">
              <span className="brand"><BrandMark /><span className="brand-word">تِبيان</span></span>
              <button type="button" className="icon-btn" onClick={() => setMenuOpen(false)} aria-label="إغلاق القائمة">
                <X {...ICON} size={20} />
              </button>
            </div>
            <nav aria-label="أقسام الموقع (الجوال)">
              <ul>
                {PAGES.map((p) => (
                  <li key={p.path}>
                    <a href={p.path} onClick={(e) => go(e, p.path)} aria-current={path === p.path ? "page" : undefined}>
                      <p.icon {...ICON} />{p.label}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
            <p className="sheet-note">لا يصدر تِبيان فتاوى شخصية، ولا يُحفظ ما تكتبه.</p>
          </div>
        </>
      )}

      <main id="main" tabIndex={-1}>
        {path === "/" && <Home />}
        {path === "/methodology" && <Methodology />}
        {path === "/evaluation" && <Evaluation />}
        {path === "/sources" && <Sources />}
      </main>

      <footer className="site-footer">
        <div className="container">
          <div className="footer-grid">
            <div className="footer-brand">
              <span className="brand"><BrandMark /><span className="brand-word">تِبيان</span></span>
              <p>أداة مدعومة بالذكاء الاصطناعي للتحقق من الاقتباسات والسياق. النص الديني يُعرض من المصادر المعتمدة وحدها.</p>
            </div>
            <nav aria-label="روابط التذييل">
              <ul className="footer-links">
                <li><a href="/methodology" onClick={(e) => go(e, "/methodology")}>المنهجية</a></li>
                <li><a href="/sources" onClick={(e) => go(e, "/sources")}>المصادر</a></li>
                <li><a href="/evaluation" onClick={(e) => go(e, "/evaluation")}>التقييم</a></li>
                <li><a href="/methodology#limits" onClick={(e) => go(e, "/methodology#limits")}>القيود</a></li>
              </ul>
            </nav>
          </div>
          <div className="footer-legal">
            <p><strong>لا يصدر تِبيان فتاوى شخصية.</strong> وليس بديلًا عن العالم المختص. لا يُحفظ نص ما تدخله.</p>
            <p>النص القرآني والخط العثماني من مجمع الملك فهد لطباعة المصحف الشريف، عبر قرآنبيديا (quranpedia.net).</p>
          </div>
        </div>
      </footer>
    </HealthContext.Provider>
  );
}
