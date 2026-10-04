import { Fragment } from "react";
import { ArrowLeftRight, CircleCheck, Columns2, Info, Minus, Plus, Scissors, SpellCheck } from "lucide-react";
import type { ComparisonToken, QuoteComparison } from "../types";
import { ar } from "../format";
import { Badge, ICON, InfoCallout, SubSection } from "../components/ui";

/* Deterministic text comparison (backend app/services/text_diff.py). Neutral wording only: it states WHAT differs,
   never why. Meaning is never carried by colour alone: every non-identical token has a visible symbol and a
   screen-reader label. */

const REASON: Record<string, string> = {
  diacritics: "علامات التشكيل",
  tatweel: "حرف التطويل (ـ)",
  punctuation: "علامات الترقيم والأقواس",
  alef_forms: "صور الألف والهمزة",
  presentation_forms: "أشكال عرض الحروف",
  honorific: "صيغة الصلاة أو الترضي",
  orthography: "الرسم الإملائي",
  formatting: "تنسيق الحروف",
};
const reasonList = (rs: string[]) => rs.map((r) => REASON[r] ?? r).join("، ");

type Tone = "success" | "info" | "warning" | "neutral";
function summaryItem(s: QuoteComparison["summary"][number]): { tone: Tone; icon: typeof Info; text: string } {
  const n = s.count ?? 0;
  switch (s.code) {
    case "VERBATIM": return { tone: "success", icon: CircleCheck, text: "مطابق حرفيًا" };
    case "NORMALIZATION_ONLY": return { tone: "info", icon: SpellCheck, text: `اختلاف في ${reasonList(s.reasons)} فقط` };
    case "PARTIAL_QUOTE": return { tone: "neutral", icon: Scissors, text: "الاقتباس يحتوي على جزء من النص فقط" };
    case "MISSING_WORDS": return { tone: "warning", icon: Minus, text: n > 1 ? `${ar(n)} كلمات مفقودة من الاقتباس` : "كلمة مفقودة من الاقتباس" };
    case "ADDED_WORDS": return { tone: "warning", icon: Plus, text: n > 1 ? `${ar(n)} كلمات ليست في النص المعتمد` : "كلمة ليست في النص المعتمد" };
    case "SUBSTITUTED_WORDS": return { tone: "warning", icon: ArrowLeftRight, text: n > 1 ? `${ar(n)} كلمات مختلفة عن النص المعتمد` : "كلمة مختلفة عن النص المعتمد" };
  }
}

export function SummaryChips({ c }: { c: QuoteComparison }) {
  return (
    <ul className="diff-summary" aria-label="خلاصة المقارنة">
      {c.summary.map((s) => {
        const it = summaryItem(s);
        return <li key={s.code} data-diff-summary={s.code}><Badge tone={it.tone} icon={it.icon}>{it.text}</Badge></li>;
      })}
    </ul>
  );
}

const SR: Partial<Record<ComparisonToken["status"], string>> = {
  NORMALIZATION_ONLY: "فرق في الكتابة فقط: ",
  SUBSTITUTED: "كلمة مختلفة: ",
  ADDED_BY_USER: "كلمة ليست في النص المعتمد: ",
  DELETED_FROM_USER_QUOTE: "كلمة مفقودة من الاقتباس: ",
  OUTSIDE_QUOTE: "خارج الاقتباس: ",
};
const MARK: Partial<Record<ComparisonToken["status"], string>> = {
  SUBSTITUTED: "≠", ADDED_BY_USER: "+", DELETED_FROM_USER_QUOTE: "−",
};

function Tok({ t }: { t: ComparisonToken }) {
  const mark = MARK[t.status];
  return (
    <span className={`tok tok-${t.status.toLowerCase()}`} data-tok={t.status}
      title={t.status === "NORMALIZATION_ONLY" ? `فرق في ${reasonList(t.reasons)} فقط` : undefined}>
      {SR[t.status] && <span className="sr-only">{SR[t.status]}</span>}
      {mark && <span className="tok-mark" aria-hidden="true">{mark}</span>}
      {t.text}
    </span>
  );
}

/** Canonical tokens to show: the quoted range with a little context; long texts are elided, never altered. */
function canonicalWindow(c: QuoteComparison, pad = 4): { toks: ComparisonToken[]; before: boolean; after: boolean } {
  const all = c.canonical_tokens;
  if (!c.quoted_range) return { toks: all, before: false, after: false };
  const lo = Math.max(0, c.quoted_range[0] - pad), hi = Math.min(all.length - 1, c.quoted_range[1] + pad);
  return { toks: all.slice(lo, hi + 1), before: lo > 0, after: hi < all.length - 1 };
}

export function TokenRows({ c, quran }: { c: QuoteComparison; quran: boolean }) {
  const w = canonicalWindow(c);
  return (
    <div className="diff-rows">
      <div className="diff-row">
        <p className="diff-label">النص الذي أدخلته</p>
        <p className="diff-text diff-user" lang="ar">{c.user_tokens.map((t, i) => <Fragment key={i}><Tok t={t} />{" "}</Fragment>)}</p>
      </div>
      <div className="diff-row">
        <p className="diff-label">{quran ? "النص القرآني المعتمد" : "النص المعتمد في المصدر"}</p>
        <p className={`diff-text diff-canonical${quran ? " quran" : ""}`} lang="ar">
          {w.before && <span className="tok tok-elided" aria-label="نص سابق محذوف من العرض">… </span>}
          {w.toks.map((t, i) => <Fragment key={i}><Tok t={t} />{" "}</Fragment>)}
          {w.after && <span className="tok tok-elided" aria-label="نص لاحق محذوف من العرض"> …</span>}
        </p>
      </div>
    </div>
  );
}

export function DifferenceList({ c }: { c: QuoteComparison }) {
  if (!c.differences.length) return null;
  return (
    <ul className="diff-list" aria-label="الفروق في الألفاظ">
      {c.differences.map((d, i) => (
        <li key={i} data-diff-kind={d.kind}>
          {d.kind === "SUBSTITUTED" && (
            <><ArrowLeftRight {...ICON} size={16} /><span>كتبتَ <q className="diff-q">{d.user}</q>، وفي المصدر <q className="diff-q">{d.canonical}</q></span></>
          )}
          {d.kind === "DELETED_FROM_USER_QUOTE" && (
            <><Minus {...ICON} size={16} /><span>في المصدر <q className="diff-q">{d.canonical}</q>، ولا توجد في اقتباسك</span></>
          )}
          {d.kind === "ADDED_BY_USER" && (
            <><Plus {...ICON} size={16} /><span>كتبتَ <q className="diff-q">{d.user}</q>، وليست في النص المعتمد</span></>
          )}
        </li>
      ))}
    </ul>
  );
}

function Legend() {
  return (
    <p className="diff-legend small muted">
      <span><span className="tok tok-normalization_only">مثال</span> فرق في الكتابة فقط</span>
      <span><span className="tok tok-substituted"><span className="tok-mark" aria-hidden="true">≠</span>مختلفة</span></span>
      <span><span className="tok tok-deleted_from_user_quote"><span className="tok-mark" aria-hidden="true">−</span>مفقودة</span></span>
      <span><span className="tok tok-added_by_user"><span className="tok-mark" aria-hidden="true">+</span>إضافية</span></span>
      <span><span className="tok tok-outside_quote">خارج الاقتباس</span></span>
    </p>
  );
}

/** Definitive comparison against the resolved source. */
export function ComparisonSection({ c }: { c: QuoteComparison | null | undefined }) {
  if (!c || !c.definitive) return null;
  const quran = c.source_type === "quran";
  return (
    <SubSection id="h-diff" title="مقارنة النص" icon={Columns2}
      desc="مقارنة آلية لفظًا بلفظ بين ما أدخلته والنص المعتمد. تبيّن الفروق ولا تحكم على سببها.">
      <div className="diff" data-comparison-basis={c.basis}>
        <SummaryChips c={c} />
        <TokenRows c={c} quran={quran} />
        <DifferenceList c={c} />
        <Legend />
        {quran && c.basis === "imlaei" && (
          <InfoCallout icon={Info} tone="quiet">
            <p className="small">
              قورن اقتباسك بالرسم الإملائي للآية كما نشره مجمع الملك فهد في الملف نفسه، فلا يُعدّ اختلاف الرسم العثماني عن
              الإملائي فرقًا. النص القرآني المعروض هو الرسم العثماني كما هو، دون أي تعديل.
            </p>
          </InfoCallout>
        )}
      </div>
    </SubSection>
  );
}

/** Non-definitive comparison inside a candidate card (near matches only). */
export function CandidateComparison({ c }: { c: QuoteComparison }) {
  return (
    <details className="cand-diff" data-candidate-comparison={c.passage_ids.join(",")}>
      <summary>مقارنة اقتباسك بهذا الموضع (للمراجعة، دون نسبة)</summary>
      <div className="cand-diff-body">
        <SummaryChips c={c} />
        <TokenRows c={c} quran={c.source_type === "quran"} />
        <DifferenceList c={c} />
      </div>
    </details>
  );
}
