import { useRef, useState } from "react";
import {
  BookOpen, CircleAlert, FileSearch, Image as ImageIcon, LoaderCircle, Lock, Quote, ScrollText, Search, ShieldCheck, Scale,
  Type, Waypoints, BookText,
} from "lucide-react";
import { analyze, ERROR_TEXT, type ErrorCode } from "../api";
import Result from "../result/Result";
import examplesFile from "../examples.json";
import type { AnalyzeResponse } from "../types";
import { ar } from "../format";
import { Button, EmptyState, ICON, InfoCallout, LinkButton } from "../components/ui";
import { useHealth } from "../health";
import { navigate } from "../nav";
import { checkInput, MAX, type FieldErrors } from "../input";
import ImageVerify from "../ocr/ImageVerify";
import { IMAGE_MODE_ENABLED } from "../features";

type Mode = "text" | "image";

type Ex = { id: string; label: string; quote: string; claim: string };
const EXAMPLES = (examplesFile as { examples: Ex[] }).examples;

/** Faint lattice of eight-pointed stars: the only ornament on the site. */
function Lattice() {
  return (
    <svg className="hero-pattern" aria-hidden="true" focusable="false">
      <defs>
        <pattern id="khatam" width="56" height="56" patternUnits="userSpaceOnUse">
          <g fill="none" stroke="currentColor" strokeWidth="1">
            <rect x="16" y="16" width="24" height="24" />
            <rect x="16" y="16" width="24" height="24" transform="rotate(45 28 28)" />
            <path d="M0 28h11M45 28h11M28 0v11M28 45v11" />
          </g>
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#khatam)" />
    </svg>
  );
}

function Progress({ llm }: { llm: boolean | undefined }) {
  const steps = [
    { t: "البحث عن المصدر", on: true },
    { t: "مطابقة النص", on: true },
    { t: "استرجاع السياق", on: true },
    { t: "بناء الأدلة", on: true },
    { t: llm ? "تحليل الادعاء (إن سمحت الأدلة)" : "تحليل الادعاء: غير متاح حاليًا", on: !!llm },
  ];
  return (
    <div className="loading progress panel" role="status">
      <p className="progress-title"><LoaderCircle {...ICON} />جارٍ البحث في المصادر والتحقق من السياق…</p>
      <div className="progress-bar" aria-hidden="true" />
      <ol className="steps-live" aria-label="مراحل التحقق">
        {steps.map((s, i) => (
          <li key={s.t} data-state={s.on ? "run" : "off"}>
            <span className="dot" aria-hidden="true">{ar(i + 1)}</span>{s.t}
          </li>
        ))}
      </ol>
      <p className="progress-note">تجري هذه المراحل على الخادم في طلب واحد، وتظهر النتيجة كاملة عند انتهائها.</p>
    </div>
  );
}

export default function Home() {
  const health = useHealth();
  const [quote, setQuote] = useState("");
  const [claim, setClaim] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ code: ErrorCode; requestId?: string } | null>(null);
  const [fieldError, setFieldError] = useState<FieldErrors>({});
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [mode, setMode] = useState<Mode>("text");
  const [resultFrom, setResultFrom] = useState<Mode>("text");
  const resultRef = useRef<HTMLDivElement>(null);
  const submitRef = useRef<HTMLButtonElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const llm = health === undefined ? undefined : health?.llm_mode === "REAL_LLM";

  function validate(): boolean {
    const fe = checkInput(quote, claim);
    setFieldError(fe);
    if (fe.quote) document.getElementById("quote")?.focus();
    else if (fe.claim) document.getElementById("claim")?.focus();
    return !fe.quote && !fe.claim;
  }

  async function run(q: string, c: string, from: Mode = "text") {
    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    setBusy(true);
    setError(null);
    setResult(null);
    setResultFrom(from);
    requestAnimationFrame(() => resultRef.current?.scrollIntoView({ block: "start", behavior: "smooth" }));
    const r = await analyze(q.trim(), c.trim(), ctl.signal);
    if (ctl.signal.aborted) return;
    setBusy(false);
    if (r.ok) setResult(r.data);
    else setError({ code: r.code, requestId: r.requestId });
    requestAnimationFrame(() => resultRef.current?.focus({ preventScroll: true }));
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !validate()) return;
    run(quote, claim);
  }

  /** An example fills the form; the visitor submits it through the real pipeline. */
  function useExample(ex: Ex) {
    setQuote(ex.quote);
    setClaim(ex.claim);
    setFieldError({});
    requestAnimationFrame(() => submitRef.current?.focus());
  }

  function startVerify(e: React.MouseEvent<HTMLAnchorElement>) {
    e.preventDefault();
    document.getElementById("verify")?.scrollIntoView({ behavior: "smooth", block: "start" });
    document.getElementById(mode === "text" ? "quote" : "tab-image")?.focus({ preventScroll: true });
  }

  /** Text confirmed from a screenshot goes through exactly the same request as typed text. */
  function verifyFromImage(q: string, c: string) {
    if (busy) return;
    setQuote(q);
    setClaim(c);
    setFieldError({});
    run(q, c, "image");
  }

  function selectMode(m: Mode, focus = false) {
    setMode(m);
    if (focus) requestAnimationFrame(() => document.getElementById(`tab-${m}`)?.focus());
  }

  function onTabKey(e: React.KeyboardEvent) {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      const next: Mode = e.key === "Home" ? "text" : e.key === "End" ? "image" : mode === "text" ? "image" : "text";
      selectMode(next, true);
    }
  }

  return (
    <>
      <section className="hero" aria-labelledby="hero-h">
        <Lattice />
        <div className="container">
          <div className="hero-copy">
            <span className="badge badge-primary"><ShieldCheck {...ICON} />تحقق من الاقتباسات الإسلامية من مصادر موثقة</span>
            <h1 id="hero-h"><span>تحقق من النص</span><span>وافهم سياقه</span></h1>
            <p className="hero-lede">
              تِبيان يبحث في المصادر المعتمدة ويعرض لك النص الأصلي والسياق والأدلة قبل أي تحليل.
            </p>
            <div className="hero-actions">
              <LinkButton href="#verify" size="lg" icon={Search} onClick={startVerify}>ابدأ التحقق</LinkButton>
              <LinkButton href="/methodology" size="lg" variant="secondary" onClick={(e) => navigate(e, "/methodology")}>
                كيف يعمل تِبيان؟
              </LinkButton>
            </div>
            <ul className="trust" aria-label="المصادر المتاحة">
              <li><BookOpen {...ICON} />القرآن الكريم</li>
              <li><ScrollText {...ICON} />صحيح البخاري</li>
              <li><ScrollText {...ICON} />صحيح مسلم</li>
              <li><Waypoints {...ICON} />نسبة قابلة للتتبع</li>
            </ul>
          </div>
        </div>
      </section>

      <section id="verify" className="verify" aria-labelledby="verify-h">
        <div className="container">
          <div className="verify-panel panel">
            <div className="verify-head">
              <h2 id="verify-h">التحقق من اقتباس</h2>
              <p>{mode === "text" ? "الصق النص كما وصلك، واكتب ما قيل إنه يدل عليه." : "اختر لقطة شاشة للنص، وراجع ما يُستخرج منها قبل التحقق."}</p>
            </div>

            {IMAGE_MODE_ENABLED && (
              <div className="input-tabs" role="tablist" aria-label="طريقة إدخال الاقتباس" onKeyDown={onTabKey}>
                <button type="button" role="tab" id="tab-text" aria-selected={mode === "text"} aria-controls="panel-text"
                  tabIndex={mode === "text" ? 0 : -1} onClick={() => selectMode("text")}>
                  <Type {...ICON} size={17} />نص
                </button>
                <button type="button" role="tab" id="tab-image" aria-selected={mode === "image"} aria-controls="panel-image"
                  tabIndex={mode === "image" ? 0 : -1} onClick={() => selectMode("image")}>
                  <ImageIcon {...ICON} size={17} />صورة
                </button>
              </div>
            )}

            {/* with a single input method there are no tabs, so the form is a plain block, not a tab panel */}
            <div id="panel-text" hidden={mode !== "text"}
              {...(IMAGE_MODE_ENABLED ? { role: "tabpanel", "aria-labelledby": "tab-text" } : {})}>
              <form className="form" onSubmit={onSubmit} noValidate aria-describedby="form-note" aria-label="التحقق من نص">
                <div className="field">
                  <label htmlFor="quote">الاقتباس</label>
                  <textarea id="quote" className="quote-input" rows={4} maxLength={MAX} value={quote}
                    onChange={(e) => setQuote(e.target.value)} aria-invalid={!!fieldError.quote}
                    aria-describedby={`quote-hint${fieldError.quote ? " quote-err" : ""}`}
                    placeholder="ألصق الآية أو الحديث أو النص الذي تريد التحقق منه" />
                  {fieldError.quote && <p id="quote-err" className="field-error"><CircleAlert {...ICON} size={16} />{fieldError.quote}</p>}
                  <p id="quote-hint" className="field-foot">
                    <span>يكفي جزء من النص، ولا يلزم التشكيل.</span>
                    <span className="count">{ar(quote.length)} / {ar(MAX)}</span>
                  </p>
                </div>

                <div className="field">
                  <label htmlFor="claim">الادعاء المصاحب</label>
                  <textarea id="claim" rows={3} maxLength={MAX} value={claim} onChange={(e) => setClaim(e.target.value)}
                    aria-invalid={!!fieldError.claim}
                    aria-describedby={`claim-hint${fieldError.claim ? " claim-err" : ""}`}
                    placeholder="ما الفكرة أو الادعاء الذي قُدِّم معه هذا النص؟" />
                  {fieldError.claim && <p id="claim-err" className="field-error"><CircleAlert {...ICON} size={16} />{fieldError.claim}</p>}
                  <p id="claim-hint" className="field-foot">
                    <span>يظهر المصدر والسياق مهما كان الادعاء؛ الادعاء يحدد ما يُحلَّل.</span>
                    <span className="count">{ar(claim.length)} / {ar(MAX)}</span>
                  </p>
                </div>

                <div className="form-actions">
                  <Button type="submit" size="lg" icon={busy ? undefined : FileSearch} disabled={busy} aria-busy={busy} ref={submitRef}>
                    {busy ? "جارٍ التحقق…" : "تحقق من السياق"}
                  </Button>
                  <span className="privacy"><Lock {...ICON} size={15} />لا يُحفظ ما تكتبه.</span>
                </div>
                <p id="form-note" className="sr-only">النتيجة تظهر أسفل النموذج بعد التحقق.</p>

                <section className="examples" aria-labelledby="ex-h">
                  <h3 id="ex-h">جرّب مثالًا</h3>
                  <p>يملأ المثال النموذج بنص من قاعدة المصادر، ثم اضغط «تحقق من السياق».</p>
                  <ul>
                    {EXAMPLES.map((ex) => (
                      <li key={ex.id}>
                        <button type="button" className="chip" onClick={() => useExample(ex)} disabled={busy}>
                          <Quote {...ICON} size={15} />{ex.label}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              </form>
            </div>

            {IMAGE_MODE_ENABLED && (
              <div role="tabpanel" id="panel-image" aria-labelledby="tab-image" hidden={mode !== "image"}>
                <ImageVerify busy={busy} onVerify={verifyFromImage} onTypeInstead={() => selectMode("text", true)} />
              </div>
            )}
          </div>

          <div ref={resultRef} tabIndex={-1} className="result-anchor" aria-live="polite" aria-busy={busy}>
            {busy && <Progress llm={llm} />}
            {error && (
              <div className="error-box">
                <InfoCallout tone="error" icon={CircleAlert} role="alert" title={ERROR_TEXT[error.code].title}>
                  <p>{ERROR_TEXT[error.code].next}</p>
                  {error.requestId && <p className="meta-line" dir="ltr">request {error.requestId.slice(0, 8)}</p>}
                </InfoCallout>
              </div>
            )}
            {result && resultFrom === "image" && (
              <div className="input-source-note" data-input-source="image">
                <InfoCallout tone="quiet" icon={ImageIcon}>
                  <p className="small">أُدخل هذا النص من صورة بعد مراجعتك له. تحقّق تِبيان من النص الذي أكدته، والصورة نفسها ليست دليلًا.</p>
                </InfoCallout>
              </div>
            )}
            {result && <Result r={result} />}
            {!busy && !error && !result && (
              <EmptyState icon={FileSearch} title="ستظهر نتيجة التحقق هنا">
                <ul>
                  <li><BookText {...ICON} size={16} />حالة الاقتباس ومصدره المعتمد، بالسورة والآية أو بالكتاب ورقم الحديث.</li>
                  <li><BookOpen {...ICON} size={16} />النص الأصلي كما في المصدر، مع ما قبله وما بعده.</li>
                  <li><Scale {...ICON} size={16} />الأدلة التي يُستند إليها، وحدود النتيجة.</li>
                </ul>
              </EmptyState>
            )}
          </div>
        </div>
      </section>

      <section id="about" className="principles" aria-labelledby="why-h" tabIndex={-1}>
        <div className="container">
          <h2 id="why-h">لماذا تِبيان؟</h2>
          <p>لأن الاقتباس قد يكون صحيح اللفظ ومقطوعًا عن سياقه. يضع تِبيان النص في موضعه قبل أي حكم.</p>
          <ul className="principle-list">
            <li>
              <BookOpen {...ICON} size={26} />
              <h3>مصدر قبل الإجابة</h3>
              <p>كل نص ديني يعرضه تِبيان مقروء من قاعدة مصادر معتمدة موثّقة البصمة، لا من ذاكرة نموذج لغوي.</p>
            </li>
            <li>
              <Waypoints {...ICON} size={26} />
              <h3>دليل قابل للتتبع</h3>
              <p>لكل دليل معرّف وموضع: سورة وآية، أو كتاب وباب ورقم حديث، فتراجعه بنفسك.</p>
            </li>
            <li>
              <ShieldCheck {...ICON} size={26} />
              <h3>الامتناع عند عدم كفاية المعلومات</h3>
              <p>إن لم يطابق النص مصدرًا، أو احتاجت المسألة إلى مختص، يقول تِبيان ذلك صراحة ولا يخمّن.</p>
            </li>
          </ul>
        </div>
      </section>
    </>
  );
}
