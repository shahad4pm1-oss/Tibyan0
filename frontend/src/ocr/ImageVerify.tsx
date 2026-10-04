import { useEffect, useId, useRef, useState } from "react";
import {
  CircleAlert, FileImage, ImageUp, Info, Keyboard, Lock, RotateCcw, ScanText, ShieldCheck, X,
} from "lucide-react";
import { ar } from "../format";
import { checkInput, MAX, type FieldErrors } from "../input";
import { Badge, Button, Disclosure, ICON, InfoCallout } from "../components/ui";
import { ACCEPT, MAX_BYTES, VALIDATION_TEXT, displayName, formatBytes, validateImage, type ValidationCode } from "./validate";
import { extractText, OcrError, type OcrFailure, type OcrProgress, type OcrQuality, type OcrResult } from "./ocr";
import { arabicLetters, segment, type Candidate, type Segmentation } from "./segment";

/* Screenshot verification: choose an image -> checks -> text extraction in the browser -> the visitor reviews and
   edits the extracted quote and claim -> the SAME verification request as typed text. The image is never uploaded,
   never stored and is not evidence; only the text the visitor confirms is sent. */

type FileInfo = { name: string; size: number; width: number; height: number; preview: string };
type Phase =
  | { k: "idle" }
  | { k: "checking"; name: string }
  | { k: "invalid"; code: ValidationCode; name: string }
  | { k: "extracting"; file: FileInfo; progress: OcrProgress }
  | { k: "failed"; file: FileInfo; code: OcrFailure }
  | { k: "no_text"; file: FileInfo; result: OcrResult }
  | { k: "review"; file: FileInfo; result: OcrResult; seg: Segmentation };

const QUALITY: Record<OcrQuality, { label: string; tone: "success" | "info" | "warning" }> = {
  good: { label: "جيدة", tone: "success" },
  fair: { label: "متوسطة", tone: "info" },
  poor: { label: "ضعيفة", tone: "warning" },
};

const MARKER: Record<Candidate["marker"], string> = {
  quotation_marks: "بين علامتي تنصيص",
  quran_brackets: "بين القوسين ﴿ ﴾",
  parentheses: "بين قوسين",
  formula: "بعد صيغة النسبة",
  whole_text: "كل النص المستخرج",
};

const FAILURE: Record<OcrFailure, { title: string; next: string }> = {
  ENGINE: { title: "تعذّر تشغيل محرك استخراج النص.", next: "قد يكون الاتصال انقطع أثناء تحميل المحرك، أو أن المتصفح لا يدعم WebAssembly. أعد المحاولة، أو اكتب النص يدويًا." },
  TIMEOUT: { title: "استغرق استخراج النص وقتًا أطول من المسموح.", next: "قصّ الصورة على النص المطلوب وأعد المحاولة، أو اكتب النص يدويًا." },
  ABORTED: { title: "أُلغي استخراج النص.", next: "اختر الصورة من جديد." },
};

function foundText(n: number): string {
  if (n === 2) return "وجدنا نصين محتملين";
  return `وجدنا ${ar(n)} نصوص محتملة`;
}

async function thumbnail(bitmap: ImageBitmap): Promise<string> {
  const s = Math.min(1, 900 / Math.max(bitmap.width, bitmap.height));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(bitmap.width * s));
  c.height = Math.max(1, Math.round(bitmap.height * s));
  c.getContext("2d")?.drawImage(bitmap, 0, 0, c.width, c.height);
  const blob = await new Promise<Blob | null>((r) => c.toBlob(r, "image/png"));
  c.width = 0;
  c.height = 0;
  return blob ? URL.createObjectURL(blob) : "";       // a re-encoded copy: pixels only, no metadata
}

function Steps({ progress }: { progress: OcrProgress }) {
  const order = ["check", "engine", "recognize"] as const;
  const at = progress.phase === "recognize" ? 2 : 1;
  const pct = progress.progress === null ? null : Math.round(progress.progress * 100);
  const label = [
    "فحص الصورة",
    progress.phase === "model" ? "تحميل نموذج اللغة العربية" : "تحميل محرك استخراج النص",
    "استخراج النص",
  ];
  return (
    <div className="ocr-progress" role="status" data-ocr-phase={progress.phase}>
      <ol className="ocr-steps" aria-label="مراحل استخراج النص">
        {order.map((s, i) => (
          <li key={s} data-state={i < at ? "done" : i === at ? "run" : "wait"}>
            <span className="dot" aria-hidden="true">{ar(i + 1)}</span>{label[i]}
          </li>
        ))}
      </ol>
      {pct === null ? (
        <progress className="ocr-bar" aria-label={label[at]} />
      ) : (
        <progress className="ocr-bar" max={100} value={pct} aria-label={label[at]} aria-valuetext={`${ar(pct)}٪`} />
      )}
      <p className="small muted">
        {pct === null ? `${label[at]}…` : `${label[at]}: ${ar(pct)}٪`}
        {at === 1 && " يُحمَّل المحرك من موقع تِبيان نفسه، ويعمل داخل متصفحك."}
      </p>
    </div>
  );
}

export default function ImageVerify({ busy, onVerify, onTypeInstead }:
  { busy: boolean; onVerify: (quote: string, claim: string) => void; onTypeInstead: () => void }) {
  const [phase, setPhase] = useState<Phase>({ k: "idle" });
  const [drag, setDrag] = useState(false);
  const [pick, setPick] = useState(0);
  const [quote, setQuote] = useState("");
  const [claim, setClaim] = useState("");
  const [fieldError, setFieldError] = useState<FieldErrors>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const reviewRef = useRef<HTMLHeadingElement>(null);
  const bitmapRef = useRef<ImageBitmap | null>(null);
  const previewRef = useRef<string>("");
  const abortRef = useRef<AbortController | null>(null);
  const runRef = useRef(0);
  const uid = useId();

  function release() {
    abortRef.current?.abort();
    abortRef.current = null;
    bitmapRef.current?.close();
    bitmapRef.current = null;
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = "";
  }
  useEffect(() => release, []);
  // move focus to the review step once the extracted text is shown, so it is announced
  useEffect(() => { if (phase.k === "review") reviewRef.current?.focus(); }, [phase.k]);

  function reset() {
    runRef.current += 1;
    release();
    setPhase({ k: "idle" });
    setQuote("");
    setClaim("");
    setFieldError({});
    if (inputRef.current) inputRef.current.value = "";
  }

  async function extract(file: FileInfo) {
    const bitmap = bitmapRef.current;
    if (!bitmap) return;
    const run = runRef.current;
    const ctl = new AbortController();
    abortRef.current = ctl;
    setPhase({ k: "extracting", file, progress: { phase: "engine", progress: null } });
    try {
      const result = await extractText(bitmap, (progress) => {
        if (runRef.current === run) setPhase({ k: "extracting", file, progress });
      }, ctl.signal);
      if (runRef.current !== run) return;
      const seg = segment(result.text);
      if (arabicLetters(result.text) < 4 || !seg.candidates.length) {
        setPhase({ k: "no_text", file, result });
        return;
      }
      setPick(0);
      setQuote(seg.candidates[0].quote);
      setClaim(seg.claim);
      setFieldError({});
      setPhase({ k: "review", file, result, seg });
    } catch (e) {
      if (runRef.current !== run) return;
      setPhase({ k: "failed", file, code: e instanceof OcrError ? e.code : "ENGINE" });
    }
  }

  async function choose(f: File | undefined | null) {
    if (!f || busy) return;
    runRef.current += 1;
    const run = runRef.current;
    release();
    const name = displayName(f.name);
    setPhase({ k: "checking", name });
    const v = await validateImage(f);
    if (runRef.current !== run) { if (v.ok) v.image.bitmap.close(); return; }
    if (!v.ok) {
      setPhase({ k: "invalid", code: v.code, name });
      if (inputRef.current) inputRef.current.value = "";
      return;
    }
    bitmapRef.current = v.image.bitmap;
    const preview = await thumbnail(v.image.bitmap);
    if (runRef.current !== run) { URL.revokeObjectURL(preview); return; }
    previewRef.current = preview;
    await extract({ name, size: f.size, width: v.image.width, height: v.image.height, preview });
  }

  // paste a screenshot straight from the clipboard while this panel is shown
  useEffect(() => {
    function onPaste(e: ClipboardEvent) {
      const panel = document.getElementById("panel-image");
      if (!panel || panel.hidden) return;
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT")) return;
      const img = Array.from(e.clipboardData?.files ?? []).find((x) => x.type.startsWith("image/"));
      if (img) { e.preventDefault(); void choose(img); }
    }
    // a file dropped next to the drop zone must not make the browser leave the page to display it
    function onWindowDrop(e: DragEvent) {
      const panel = document.getElementById("panel-image");
      if (panel && !panel.hidden && e.dataTransfer?.types.includes("Files")) e.preventDefault();
    }
    document.addEventListener("paste", onPaste);
    window.addEventListener("dragover", onWindowDrop);
    window.addEventListener("drop", onWindowDrop);
    return () => {
      document.removeEventListener("paste", onPaste);
      window.removeEventListener("dragover", onWindowDrop);
      window.removeEventListener("drop", onWindowDrop);
    };
  });

  function selectCandidate(i: number, seg: Segmentation) {
    setPick(i);
    setQuote(seg.candidates[i].quote);
    setFieldError({});
  }

  function onContinue() {
    const fe = checkInput(quote, claim);
    setFieldError(fe);
    if (fe.quote) document.getElementById("ocr-quote")?.focus();
    else if (fe.claim) document.getElementById("ocr-claim")?.focus();
    if (fe.quote || fe.claim || busy) return;
    onVerify(quote.trim(), claim.trim());
  }

  const file = "file" in phase ? phase.file : null;
  const working = phase.k === "checking" || phase.k === "extracting";

  return (
    <div className="img-verify" data-image-phase={phase.k}>
      <input ref={inputRef} type="file" accept={ACCEPT} hidden id="image-input" data-testid="image-input"
        onChange={(e) => void choose(e.target.files?.[0])} />

      {!file && (
        <div className={`dropzone${drag ? " is-drag" : ""}`} data-dropzone
          onDragOver={(e) => { e.preventDefault(); if (!working) setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); if (!working) void choose(e.dataTransfer.files?.[0]); }}>
          <ImageUp {...ICON} size={30} />
          <p className="dropzone-title">اسحب لقطة الشاشة إلى هنا</p>
          <p className="dropzone-or">أو</p>
          <Button type="button" variant="secondary" icon={FileImage} onClick={() => inputRef.current?.click()}
            disabled={working || busy} aria-describedby={`${uid}-hint`}>
            اختيار صورة
          </Button>
          <p id={`${uid}-hint`} className="small muted">PNG أو JPG أو WEBP، حتى {formatBytes(MAX_BYTES)}. يمكنك أيضًا لصق لقطة الشاشة.</p>
          {phase.k === "checking" && <p className="small" role="status">جارٍ فحص الصورة…</p>}
        </div>
      )}

      {phase.k === "invalid" && (
        <InfoCallout tone="error" icon={CircleAlert} role="alert" title={VALIDATION_TEXT[phase.code].title}
          data-image-error={phase.code}>
          <p>{VALIDATION_TEXT[phase.code].next}</p>
          <p className="meta-line">الملف: <bdi>{phase.name}</bdi></p>
        </InfoCallout>
      )}

      {file && (
        <div className="file-card" data-file-card>
          {file.preview && <img className="file-preview" src={file.preview} alt="معاينة الصورة المختارة" />}
          <div className="file-meta">
            <p className="file-name"><FileImage {...ICON} size={16} /><bdi data-file-name>{file.name}</bdi></p>
            <p className="small muted">{formatBytes(file.size)} · <span dir="ltr">{ar(file.width)} × {ar(file.height)}</span> بكسل</p>
            <div className="file-actions">
              <Button type="button" variant="secondary" icon={RotateCcw} onClick={() => inputRef.current?.click()} disabled={busy}>
                اختيار صورة أخرى
              </Button>
              <Button type="button" variant="secondary" icon={X} onClick={reset} disabled={busy}>إزالة الصورة</Button>
            </div>
          </div>
        </div>
      )}

      {phase.k === "extracting" && <Steps progress={phase.progress} />}

      {phase.k === "failed" && (
        <InfoCallout tone="error" icon={CircleAlert} role="alert" title={FAILURE[phase.code].title} data-ocr-error={phase.code}>
          <p>{FAILURE[phase.code].next}</p>
          <div className="callout-actions">
            <Button type="button" variant="secondary" icon={RotateCcw} onClick={() => void extract(phase.file)}>إعادة المحاولة</Button>
            <Button type="button" variant="secondary" icon={Keyboard} onClick={onTypeInstead}>اكتب النص يدويًا</Button>
          </div>
        </InfoCallout>
      )}

      {phase.k === "no_text" && (
        <InfoCallout tone="warning" icon={ScanText} role="alert" title="لم نعثر على نص عربي واضح في الصورة." data-ocr-error="NO_TEXT">
          <p>تأكد أن الصورة تُظهر النص بوضوح، أو قصّها على النص المطلوب. يمكنك أيضًا كتابة النص يدويًا.</p>
          <div className="callout-actions">
            <Button type="button" variant="secondary" icon={Keyboard} onClick={onTypeInstead}>اكتب النص يدويًا</Button>
          </div>
        </InfoCallout>
      )}

      {phase.k === "review" && (
        <section className="ocr-review" aria-labelledby="ocr-review-h" data-ocr-review>
          <h3 id="ocr-review-h" ref={reviewRef} tabIndex={-1}>راجع النص المستخرج</h3>
          <p className="small muted">صحّح أي كلمة قُرئت خطأً قبل المتابعة. يُتحقَّق من النص الذي تؤكده هنا فقط.</p>

          <div className="ocr-quality" data-ocr-quality={phase.result.quality}>
            <p>جودة استخراج النص: <Badge tone={QUALITY[phase.result.quality].tone}>{QUALITY[phase.result.quality].label}</Badge></p>
            <p className="small muted">تصف وضوح قراءة الحروف في الصورة فقط، ولا تدل على صحة النص ولا على مصدره.</p>
            {phase.result.unclearWords.length > 0 && (
              <p className="small" data-unclear-words>
                كلمات قرأها المحرك بوضوح أقل، فراجعها:{" "}
                {phase.result.unclearWords.map((w, i) => <bdi key={i} className="unclear-word">{w}</bdi>)}
              </p>
            )}
          </div>

          {phase.seg.candidates.length > 1 && (
            <fieldset className="cand-pick" data-candidates={phase.seg.candidates.length}>
              <legend>{foundText(phase.seg.candidates.length)}</legend>
              <p className="small muted">اختر النص الذي تريد التحقق منه.</p>
              {phase.seg.candidates.map((c, i) => (
                <label key={i} className={`cand-option${pick === i ? " is-picked" : ""}`}>
                  <input type="radio" name={`${uid}-cand`} checked={pick === i} onChange={() => selectCandidate(i, phase.seg)} />
                  <span className="cand-text" lang="ar">{c.quote.length > 160 ? `${c.quote.slice(0, 160)}…` : c.quote}</span>
                  <span className="small muted">{MARKER[c.marker]}</span>
                </label>
              ))}
            </fieldset>
          )}

          <div className="field">
            <label htmlFor="ocr-quote">الاقتباس المستخرج</label>
            <textarea id="ocr-quote" className="quote-input" rows={4} value={quote} maxLength={MAX}
              onChange={(e) => setQuote(e.target.value)} aria-invalid={!!fieldError.quote}
              aria-describedby={`ocr-quote-hint${fieldError.quote ? " ocr-quote-err" : ""}`} />
            {fieldError.quote && <p id="ocr-quote-err" className="field-error"><CircleAlert {...ICON} size={16} />{fieldError.quote}</p>}
            <p id="ocr-quote-hint" className="field-foot">
              <span>{phase.seg.candidates[pick]?.marker === "whole_text" ? "لم تُحدَّد علامات اقتباس، فعُرض كل النص. احذف ما ليس من الاقتباس." : "عدّل النص ليطابق ما في الصورة."}</span>
              <span className="count">{ar(quote.length)} / {ar(MAX)}</span>
            </p>
          </div>

          <div className="field">
            <label htmlFor="ocr-claim">الادعاء المستخرج</label>
            {phase.seg.claim && (
              <p className="field-tag" id="ocr-claim-tag"><Badge tone="info" icon={Info}>الادعاء المقترح من الصورة</Badge></p>
            )}
            <textarea id="ocr-claim" rows={3} value={claim} maxLength={MAX} onChange={(e) => setClaim(e.target.value)}
              aria-invalid={!!fieldError.claim}
              aria-describedby={`${phase.seg.claim ? "ocr-claim-tag " : ""}ocr-claim-hint${fieldError.claim ? " ocr-claim-err" : ""}`}
              placeholder="ما الفكرة أو الادعاء الذي قُدِّم مع هذا النص؟" />
            {fieldError.claim && <p id="ocr-claim-err" className="field-error"><CircleAlert {...ICON} size={16} />{fieldError.claim}</p>}
            <p id="ocr-claim-hint" className="field-foot">
              <span>{phase.seg.claim ? "اقتراح من النص المحيط بالاقتباس في الصورة؛ عدّله أو استبدله." : "لم نجد ادعاءً واضحًا في الصورة؛ اكتب ما قيل إن النص يدل عليه."}</span>
              <span className="count">{ar(claim.length)} / {ar(MAX)}</span>
            </p>
          </div>

          <Disclosure summary="النص المستخرج كاملًا" data-ocr-full>
            <p className="ocr-text" lang="ar" dir="rtl" data-ocr-text>{phase.seg.text}</p>
          </Disclosure>

          <InfoCallout tone="quiet" icon={ShieldCheck}>
            <p className="small">الصورة ليست دليلًا. يقارن تِبيان النص الذي تؤكده بالمصادر المعتمدة، كما لو كتبته بنفسك.</p>
          </InfoCallout>

          <div className="form-actions">
            <Button type="button" size="lg" icon={ScanText} onClick={onContinue} disabled={busy} aria-busy={busy} data-ocr-continue>
              {busy ? "جارٍ التحقق…" : "متابعة التحقق"}
            </Button>
          </div>
        </section>
      )}

      <p className="privacy img-privacy">
        <Lock {...ICON} size={15} />
        يُستخرج النص داخل متصفحك: لا تُرفع الصورة إلى الخادم ولا تُحفظ، ويُرسل للتحقق النص الذي تؤكده فقط.
      </p>
    </div>
  );
}
