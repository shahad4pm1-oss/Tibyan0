import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, ChevronDown, Copy, type LucideIcon } from "lucide-react";

/* Shared UI primitives. Every visual value comes from the tokens in index.css. */

export type Tone = "success" | "warning" | "error" | "info" | "neutral";

export const ICON = { size: 18, strokeWidth: 1.75, "aria-hidden": true } as const;

export function Badge({ tone, icon: I, children, outline = false, ...rest }:
  { tone?: "primary" | "accent" | Tone; icon?: LucideIcon; children: ReactNode; outline?: boolean } & Record<string, unknown>) {
  const cls = `badge${tone && tone !== "neutral" ? ` badge-${tone}` : ""}${outline ? " badge-outline" : ""}`;
  return <span className={cls} {...rest}>{I && <I {...ICON} />}{children}</span>;
}

export function Button({ variant = "primary", size, icon: I, children, ...rest }:
  { variant?: "primary" | "secondary"; size?: "lg"; icon?: LucideIcon; children: ReactNode }
  & React.ComponentProps<"button">) {
  return (
    <button className={`btn btn-${variant}${size ? ` btn-${size}` : ""}`} {...rest}>
      {I && <I {...ICON} />}{children}
    </button>
  );
}

export function LinkButton({ variant = "primary", size, icon: I, children, ...rest }:
  { variant?: "primary" | "secondary"; size?: "lg"; icon?: LucideIcon; children: ReactNode }
  & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a className={`btn btn-${variant}${size ? ` btn-${size}` : ""}`} {...rest}>
      {I && <I {...ICON} />}{children}
    </a>
  );
}

export function Card({ as: As = "div", className = "", children, ...rest }:
  { as?: "div" | "section" | "article"; className?: string; children: ReactNode } & Record<string, unknown>) {
  return <As className={`panel ${className}`} {...rest}>{children}</As>;
}

/** A report section: heading in the margin column, content in the main column (stacked on small screens). */
export function SectionHeader({ id, title, icon: I, desc }: { id: string; title: string; icon?: LucideIcon; desc?: ReactNode }) {
  return (
    <div className="rsec-side">
      <div className="rsec-head">
        {I && <I {...ICON} size={20} />}
        <h2 id={id}>{title}</h2>
      </div>
      {desc && <p className="rsec-desc">{desc}</p>}
    </div>
  );
}

export function ReportSection({ id, title, icon, desc, children, className = "" }:
  { id: string; title: string; icon?: LucideIcon; desc?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rsec ${className}`} aria-labelledby={id}>
      <SectionHeader id={id} title={title} icon={icon} desc={desc} />
      <div className="rsec-body">{children}</div>
    </section>
  );
}

/** A collapsed group of the report: the heading is the toggle; the body holds SubSections. */
export function Fold({ id, title, icon: I, hint, children, className = "" }:
  { id: string; title: string; icon?: LucideIcon; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`fold ${className}`} aria-labelledby={id}>
      <details>
        <summary>
          {I && <I {...ICON} size={20} />}
          <h2 id={id}>{title}</h2>
          {hint && <span className="fold-hint">{hint}</span>}
          <ChevronDown {...ICON} className="fold-chevron" />
        </summary>
        <div className="fold-body">{children}</div>
      </details>
    </section>
  );
}

/** A titled block inside a Fold (stacked: heading, optional description, content). */
export function SubSection({ id, title, icon: I, desc, children, className = "" }:
  { id: string; title: string; icon?: LucideIcon; desc?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`rsub ${className}`} aria-labelledby={id}>
      <div className="rsub-head">
        {I && <I {...ICON} />}
        <h3 id={id}>{title}</h3>
      </div>
      {desc && <p className="rsub-desc">{desc}</p>}
      <div className="rsub-body">{children}</div>
    </section>
  );
}

/** Opens every collapsed ancestor (and the element itself when it is a <details>) so it can be scrolled to. */
export function reveal(el: Element) {
  for (let n: Element | null = el; n; n = n.parentElement) {
    if (n instanceof HTMLDetailsElement) n.open = true;
  }
}

export function StatusBanner({ tone, icon: I, title, line, status, children }:
  { tone: Tone; icon: LucideIcon; title: string; line: string; status: string; children?: ReactNode }) {
  return (
    <div className={`status tone-${tone}`} data-status={status}>
      <span className="status-icon"><I {...ICON} size={24} /></span>
      <div>
        <p className="status-title">{title}</p>
        <p className="status-line">{line}</p>
        {children}
      </div>
    </div>
  );
}

export function InfoCallout({ tone = "neutral", icon: I, title, children, role = "note", ...rest }:
  { tone?: "info" | "warning" | "error" | "neutral" | "quiet"; icon: LucideIcon; title?: ReactNode; children?: ReactNode; role?: string }
  & Record<string, unknown>) {
  return (
    <div className={`callout${tone !== "neutral" ? ` callout-${tone}` : ""}`} role={role} {...rest}>
      <I {...ICON} />
      <div>
        {title && <p className="callout-title">{title}</p>}
        {children}
      </div>
    </div>
  );
}

export function EmptyState({ icon: I, title, children, level = 2 }:
  { icon: LucideIcon; title: string; children?: ReactNode; level?: 2 | 3 }) {
  const H = level === 2 ? "h2" : "h3";
  return (
    <div className="empty">
      <I {...ICON} size={28} />
      <H>{title}</H>
      {children}
    </div>
  );
}

export function MetricCard({ label, value, sub, ratio, ...rest }:
  { label: string; value: ReactNode; sub?: ReactNode; ratio?: number } & Record<string, unknown>) {
  return (
    <div className="metric" {...rest}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
      {ratio !== undefined && (
        <div className="meter" aria-hidden="true"><span style={{ width: `${Math.max(0, Math.min(1, ratio)) * 100}%` }} /></div>
      )}
      {sub && <p className="metric-sub">{sub}</p>}
    </div>
  );
}

export function Disclosure({ summary, children, ...rest }: { summary: ReactNode; children: ReactNode } & Record<string, unknown>) {
  return (
    <details className="disclosure" {...rest}>
      <summary>{summary}<ChevronDown {...ICON} /></summary>
      <div className="disclosure-body">{children}</div>
    </details>
  );
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch {
      return false;
    }
  }
}

/** Copies text; the label (for screen readers too) changes to "نُسخ" for two seconds. */
export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <button type="button" className="copy-btn" data-copied={copied}
      onClick={async () => {
        if (await copyText(text)) {
          setCopied(true);
          window.clearTimeout(timer.current);
          timer.current = window.setTimeout(() => setCopied(false), 2000);
        }
      }}>
      {copied ? <Check {...ICON} size={15} /> : <Copy {...ICON} size={15} />}
      <span aria-live="polite">{copied ? "نُسخ" : label}</span>
    </button>
  );
}

/** Eight-pointed star built from two overlapping squares: the brand mark. */
export function BrandMark({ className = "brand-mark" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="7" y="7" width="18" height="18" rx="1.5" />
      <rect x="7" y="7" width="18" height="18" rx="1.5" transform="rotate(45 16 16)" />
      <circle cx="16" cy="16" r="3.2" fill="currentColor" stroke="none" />
    </svg>
  );
}
