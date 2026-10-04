import { useState } from "react";
import {
  BookOpen, BookText, ChevronDown, CircleCheck, CircleCheckBig, CircleHelp, CircleSlash, Cpu, Info, Layers,
  ListChecks, Pencil, Scale, ScrollText, SearchX, Split, Text, TriangleAlert, UserRound, Wrench, Eraser, type LucideIcon,
} from "lucide-react";
import type { AnalyzeResponse, AssertionLabel, EvidenceItem, Relation, TextUnit, Verdict } from "../types";
import {
  LEVEL, OVERRIDE, ROLE, STRENGTH, WARNING, ar, cleanTafsir, clipText, hadithRef, quranRef, sourceTypeLabel, unitRef,
} from "../format";
import {
  Badge, CopyButton, Disclosure, Fold, ICON, InfoCallout, ReportSection, StatusBanner, SubSection, type Tone,
} from "../components/ui";
import { CandidateComparison, ComparisonSection } from "./Comparison";
import EvidenceMapSection from "./EvidenceMap";

/* Layout: one summary card (quote status, claim verdict, AI analysis with the claim-parts table), then three
   collapsed groups: text & context, evidence, caveats & references. Nothing is dropped; detail is one click away.

   Visual separation of content kinds:
   Quran text      -> .scripture / .quran (publisher's Uthmanic font, framed field, no AI marks)
   Hadith text     -> .hadith (Naskh, warm paper, collection rule; never the Quran font)
   AI analysis     -> .ai-box / .relation (cool grey-blue panel, labelled; only when a real model produced it)
   system messages -> neutral callouts, labelled as fixed system text */

export const NO_LLM_MESSAGE = "تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً";
const NOT_ENABLED_MESSAGE = "تحليل الادعاء غير مفعّل لهذا النوع من المصادر بعد";

const SEARCHED = "يشمل البحث حاليًا القرآن الكريم (رواية حفص) والأحاديث المرقّمة في صحيحي البخاري ومسلم. "
  + "عدم العثور لا يعني أن النص غير موجود في مصدر آخر.";

const isHadith = (u?: TextUnit | null) => !!u && (u.source_type === "hadith" || !!u.metadata.collection_ar);

type StatusUI = { tone: Tone; icon: LucideIcon; title: string; line: string };
const QUOTE_STATUS: Record<string, StatusUI> = {
  EXACT: { tone: "success", icon: CircleCheckBig, title: "مطابق", line: "النص موجود بلفظه في المصدر." },
  PARTIAL: { tone: "success", icon: CircleCheck, title: "مطابق جزئيًا", line: "النص مقتطع من نص أطول في المصدر." },
  PARAPHRASED: { tone: "warning", icon: CircleHelp, title: "قريب من المصدر", line: "النص قريب من نص في المصدر لكنه لا يطابقه حرفيًا." },
  AMBIGUOUS: { tone: "warning", icon: Split, title: "غير محسوم", line: "وجدنا أكثر من موضع محتمل." },
  NEAR_MATCH_UNCONFIRMED: { tone: "warning", icon: CircleHelp, title: "قريب غير مطابق", line: "لا يطابق الاقتباس أي نص في المصادر حرفيًا." },
  QUOTE_TOO_SHORT: { tone: "warning", icon: Split, title: "غير محسوم", line: "الاقتباس أقصر من أن يُنسب إلى موضع بعينه." },
  NOT_FOUND: { tone: "neutral", icon: SearchX, title: "لم نعثر على مصدر كافٍ", line: "لم نجد تطابقاً يمكن اعتماده في المصادر المتاحة حالياً." },
};

export const RELATION_UI: Record<Relation, StatusUI> = {
  SUPPORTED: { tone: "success", icon: CircleCheck, title: "متسق مع النص", line: "الادعاء متسق مع النص في سياقه." },
  OVERSTATED: { tone: "warning", icon: TriangleAlert, title: "أوسع من النص", line: "الادعاء أوسع مما يدل عليه النص." },
  CONTRADICTED: { tone: "error", icon: CircleSlash, title: "يخالف السياق", line: "السياق يخالف الادعاء." },
  INSUFFICIENT_EVIDENCE: { tone: "neutral", icon: Scale, title: "الأدلة غير كافية", line: "لا تكفي الأدلة المتاحة للحكم." },
  REQUIRES_SPECIALIST: { tone: "info", icon: UserRound, title: "يحتاج مراجعة مختص", line: "المسألة تحتاج إلى نظر عالم مؤهل." },
};

export const VERDICT_UI: Record<Verdict, { tone: Tone; title: string }> = {
  correct: { tone: "success", title: "استدلال صحيح بالنص" },
  manipulated: { tone: "error", title: "استدلال محرَّف أو مُحمَّل ما لا يحتمله النص" },
  unrelated: { tone: "neutral", title: "النص لا يتناول الادعاء" },
};

const LABEL_UI: Record<AssertionLabel, { tone: Tone; title: string }> = {
  supported: { tone: "success", title: "مؤيَّد" },
  overstated: { tone: "warning", title: "مبالغ فيه" },
  contradicted: { tone: "error", title: "مخالف للنص" },
  not_in_evidence: { tone: "neutral", title: "غير وارد في الدليل" },
  requires_specialist: { tone: "info", title: "يحتاج إلى مختص" },
};

const AI_FAILED_TITLE = "AI Analysis Failed · فشل تحليل الذكاء الاصطناعي";

/** True when the AI step was expected but produced nothing to show (not configured, provider error, rejected). */
function aiFailed(r: AnalyzeResponse): boolean {
  const ca = r.claim_analysis;
  if (ca.status === "AI_OUTPUT_REJECTED") return true;
  return ca.status === "ANALYSIS_UNAVAILABLE" && ca.uncertainty_reason !== "CLAIM_ANALYSIS_NOT_ENABLED_FOR_SOURCE_TYPE";
}

function aiFailureReason(r: AnalyzeResponse): string {
  const ca = r.claim_analysis;
  if (ca.status === "AI_OUTPUT_REJECTED") return ca.uncertainty_reason ?? "AI_OUTPUT_REJECTED";
  return r.metadata.llm_unavailable_reason ?? ca.uncertainty_reason ?? "ANALYSIS_UNAVAILABLE";
}

function AiFailedBanner({ r, withStatus = false }: { r: AnalyzeResponse; withStatus?: boolean }) {
  const ca = r.claim_analysis;
  const message = ca.status === "AI_OUTPUT_REJECTED"
    ? "رُفضت مخرجات التحليل الآلي لأنها لم تجتز التحقق، فلم يُعرض أي نص منها."
    : NO_LLM_MESSAGE;
  return (
    <InfoCallout tone="error" icon={TriangleAlert} title={AI_FAILED_TITLE} role="alert" data-ai-failed={ca.status}>
      <p>{withStatus ? <span data-claim-status={ca.status}>{message}</span> : message}</p>
      <p className="small muted">المصدر والنص والسياق المعروضة موثّقة من قاعدة المصادر، ولم يصدر حكم على الادعاء.</p>
      <p className="meta-line" dir="ltr">reason: {aiFailureReason(r)}</p>
    </InfoCallout>
  );
}

function Assertions({ r }: { r: AnalyzeResponse }) {
  const parts = r.claim_analysis.assertions ?? [];
  if (!parts.length) return null;
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label="أجزاء الادعاء، قابل للتمرير"
      style={{ marginTop: "var(--s-4)" }} data-assertions={parts.length}>
      <table className="data">
        <caption>أجزاء الادعاء وحكم كل جزء</caption>
        <thead><tr><th scope="col">جزء الادعاء</th><th scope="col">الحكم</th><th scope="col">ما يقوله الدليل</th></tr></thead>
        <tbody>
          {parts.map((a, i) => (
            <tr key={i} data-assertion-label={a.label}>
              <td>{a.claim_part}</td>
              <td><Badge tone={LABEL_UI[a.label]?.tone ?? "neutral"}>{LABEL_UI[a.label]?.title ?? a.label}</Badge></td>
              <td>{a.evidence_context}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const STRENGTH_TONE: Record<string, "success" | "warning" | "neutral"> = { SUFFICIENT: "success", LIMITED: "warning", INSUFFICIENT: "neutral" };

function statusKey(r: AnalyzeResponse): string {
  const qa = r.quote_analysis;
  if (qa.match_status === "AMBIGUOUS" && qa.ambiguity_reason === "NEAR_MATCH_UNCONFIRMED") return "NEAR_MATCH_UNCONFIRMED";
  if (qa.match_status === "AMBIGUOUS" && qa.ambiguity_reason === "QUOTE_TOO_SHORT") return "QUOTE_TOO_SHORT";
  return qa.match_status;
}

function SourceBadge({ t }: { t?: string | null }) {
  return (
    <Badge tone={t === "quran" ? "primary" : t === "hadith" ? "accent" : "neutral"}
      icon={t === "quran" ? BookOpen : t === "hadith" ? ScrollText : BookText} data-source-type={t ?? ""}>
      {sourceTypeLabel(t)}
    </Badge>
  );
}

function Ayah({ u, cited }: { u: TextUnit; cited: boolean }) {
  return (
    <span className={`ayah${cited ? " ayah-cited" : ""}`}>
      {u.text}
      <span className="ayah-no" aria-label={`الآية ${ar(u.metadata.ayah_number ?? "")}`}>
        {ar(u.metadata.ayah_number ?? u.reference)}
      </span>{" "}
    </span>
  );
}

function HadithText({ u, small = false }: { u: TextUnit; small?: boolean }) {
  return (
    <div className={`hadith${small ? " hadith-small" : ""}`} lang="ar" data-source-type="hadith">
      <p className="hadith-tag"><SourceBadge t="hadith" />{hadithRef(u)}</p>
      {u.text.split("\n").map((para, i) => <p key={i} className="hadith-text">{para}</p>)}
    </div>
  );
}

/* ---------------------------------------------------------------- summary */

function ClaimOutcome({ r }: { r: AnalyzeResponse }) {
  const ca = r.claim_analysis;
  if (aiFailed(r)) return <div style={{ marginTop: "var(--s-4)" }}><AiFailedBanner r={r} withStatus /></div>;
  if (ca.status === "ANALYSIS_UNAVAILABLE") {  // hadith: claim analysis not enabled for this source type (by design)
    return (
      <p className="claim-state"><Info {...ICON} size={16} />
        <span data-claim-status="ANALYSIS_UNAVAILABLE">{NOT_ENABLED_MESSAGE}</span>
      </p>
    );
  }
  if (ca.summary_source === "ai" && ca.relation) {
    const u = RELATION_UI[ca.relation];
    const v = ca.verdict ? VERDICT_UI[ca.verdict] : null;
    const hasParts = (ca.assertions ?? []).length > 0;
    return (
      <div className={`ai-box tone-${u.tone}`} data-relation={ca.relation} data-verdict={ca.verdict ?? ""}>
        <p className="relation-label">علاقة الادعاء بالأدلة <Badge tone="info" icon={Cpu}>مدعوم بالذكاء الاصطناعي</Badge></p>
        <p className="relation-title"><u.icon {...ICON} size={22} />{u.title}</p>
        {v && <p><Badge tone={v.tone}>{v.title}</Badge></p>}
        {ca.summary ? <p className="ai-summary">{ca.summary}</p> : <p className="relation-line">{u.line}</p>}
        {hasParts ? <Assertions r={r} /> : ca.reason && <p className="ai-reason">{ca.reason}</p>}
        {ca.referral && <p className="ai-reason"><strong>{ca.referral}</strong></p>}
        <p className="ai-box-note">هذا التحليل مبني على الأدلة المعروضة أدناه ولا يُعد مصدراً شرعياً مستقلاً. {ca.disclosure}</p>
      </div>
    );
  }
  if (ca.relation === "REQUIRES_SPECIALIST" || ca.needs_specialist) {
    return (
      <div className="specialist" data-relation="REQUIRES_SPECIALIST" role="note" style={{ marginTop: "var(--s-4)" }}>
        <UserRound {...ICON} size={22} />
        <div>
          <h3>هذه المسألة تحتاج مراجعة مختص</h3>
          {ca.summary && <p>{ca.summary}</p>}
          <p>لا يصدر تِبيان فتاوى شخصية ولا أحكامًا مستقلة؛ المصدر والنص والسياق معروضة أدناه للاطلاع فقط.</p>
          {ca.referral && <p className="referral">{ca.referral}</p>}
          <p className="tiny muted">رسالة ثابتة من تِبيان، وليست ناتجة عن نموذج لغوي.</p>
        </div>
      </div>
    );
  }
  // fixed system template: no attributed source, so nothing to analyse the claim against
  return (
    <p className="claim-state"><Info {...ICON} size={16} />
      <span>
        {r.source
          ? "لم يُحلَّل الادعاء، لأن الأدلة المتاحة لا تكفي لتحليله."
          : "لم يُحلَّل الادعاء، لأن التحليل لا يجري إلا بعد نسبة الاقتباس إلى موضع بعينه."}
      </span>
    </p>
  );
}

function Summary({ r }: { r: AnalyzeResponse }) {
  const key = statusKey(r);
  const s = QUOTE_STATUS[key] ?? QUOTE_STATUS.NOT_FOUND;
  const qa = r.quote_analysis;
  const hadith = isHadith(r.context.matched[0]);
  const ca = r.claim_analysis;
  let detail = "";
  if (key === "AMBIGUOUS")
    detail = `يطابق ${ar(qa.alternatives_total)} مواضع، ولم يُنسب إلى موضع بعينه. أضف كلمات أكثر من الاقتباس لتحديد الموضع.`;
  if (key === "NEAR_MATCH_UNCONFIRMED")
    detail = "قد يكون الاقتباس منقولًا بتغيير في بعض الكلمات. لا ينسبه تِبيان إلى موضع بعينه، وأقرب النصوص معروضة بلفظها الصحيح لتراجعها.";
  if (key === "QUOTE_TOO_SHORT") detail = "أضف كلمات أكثر من الاقتباس لتحديد الموضع.";
  if (key === "NOT_FOUND") detail = SEARCHED;
  if (key === "PARTIAL")
    detail = hadith
      ? "الاقتباس جزء من نص الحديث كما في الطبعة، والنص الكامل يشمل الإسناد. اقرأه كاملًا قبل الحكم على معناه."
      : "الاقتباس جزء من نص أطول. اقرأ النص كاملًا مع سياقه قبل الحكم على معناه.";
  const strength = STRENGTH[r.evidence.strength];
  const claimFact = ca.summary_source === "ai" && ca.relation ? "مكتمل (ذكاء اصطناعي)"
    : ca.status === "ANALYSIS_UNAVAILABLE" ? "غير متاح"
    : ca.status === "REFERRED" ? "محال إلى مختص"
    : ca.status === "AI_OUTPUT_REJECTED" ? "مرفوض بعد التحقق" : "لم يُحلَّل";

  return (
    <section className="summary panel" aria-labelledby="h-quote">
      <div className="summary-top">
        <h2 id="h-quote" className="summary-kicker"><ListChecks {...ICON} size={16} />نتيجة التحقق</h2>
        {r.source && <SourceBadge t={r.source.source_type} />}
      </div>
      <StatusBanner tone={s.tone} icon={s.icon} title={s.title} line={s.line} status={key}>
        {r.source && r.context.matched.length > 0 && (
          <p className="status-ref">{unitRef(r.context.matched)}</p>
        )}
        {detail && <p className="status-detail">{detail}</p>}
      </StatusBanner>

      <dl className="facts">
        <div>
          <dt>المصدر</dt>
          <dd>{r.source ? (hadith ? r.context.matched[0].metadata.collection_ar ?? r.source.title : "القرآن الكريم") : "لم يُنسب"}</dd>
        </div>
        <div>
          <dt>قوة الأدلة</dt>
          <dd><Badge tone={STRENGTH_TONE[r.evidence.strength]}>{strength.title}</Badge></dd>
        </div>
        <div>
          <dt>تحليل الادعاء</dt>
          <dd>{claimFact}</dd>
        </div>
      </dl>

      <div className="claim-block">
        <p className="claim-label">الادعاء كما أدخلته</p>
        <blockquote className="claim-quote">{r.claim.text}</blockquote>
        <ClaimOutcome r={r} />
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------- sections */

function SourceSection({ r }: { r: AnalyzeResponse }) {
  const u = r.context.matched[0];
  if (!r.source || !u) return null;
  const ref = unitRef(r.context.matched);
  if (!isHadith(u)) {
    return (
      <SubSection id="h-src" title="المصدر" icon={BookText}>
        <div className="source-card">
          <div className="source-title"><SourceBadge t="quran" /><strong>{r.source.title}</strong></div>
          <p className="source-ref">{quranRef(r.context.matched)}</p>
          <div><CopyButton text={`${r.context.matched.map((x) => x.text).join(" ")}\n— ${ref}`} label="نسخ النص مع الموضع" /></div>
        </div>
      </SubSection>
    );
  }
  const m = u.metadata;
  return (
    <SubSection id="h-src" title="المصدر" icon={BookText}>
      <div className="source-card">
        <div className="source-title"><SourceBadge t="hadith" /><strong>{m.collection_ar ?? r.source.title}</strong></div>
        <p className="source-ref">
          {m.hadith_number ? `الحديث رقم ${ar(String(m.hadith_number))}` : "رواية غير مرقّمة في الملف المصدر"}
        </p>
        <dl className="kv">
          {m.book && <div><dt>الكتاب</dt><dd>{m.book}</dd></div>}
          {m.chapter && <div><dt>الباب</dt><dd>{m.chapter}</dd></div>}
          <div>
            <dt>درجة المصدر</dt>
            <dd data-grading={m.grading_authority}>
              <Badge tone="success">{m.grading_ar}</Badge>{" "}
              أحاديث الصحيحين مقبولة بنص الحزمة العلمية للتحدي («الأحاديث الصحيحة من الصحيحين»). لم يولّد تِبيان ولا أي نموذج لغوي هذا الحكم.
            </dd>
          </div>
          <div><dt>المصدر العلمي</dt><dd>{m.collection_ar}، معتمد في الحزمة العلمية للتحدي</dd></div>
          <div><dt>بيانات الطبعة</dt><dd>{r.source.edition}</dd></div>
          <div><dt>مسار البيانات</dt><dd>ملفات OpenITI المأخوذة من المكتبة الشاملة (رخصة CC BY-NC-SA 4.0)</dd></div>
          <div><dt>المقابلة مع الشاملة والدرر</dt><dd data-crosscheck="PENDING"><span className="pending-tag">لم تُجرَ بعد</span></dd></div>
          <div><dt>حقوق الطبعة المطبوعة</dt><dd data-edition-reuse="PENDING_VERIFICATION"><span className="pending-tag">قيد التحقق</span></dd></div>
        </dl>
        <div><CopyButton text={`${u.text}\n— ${ref}`} label="نسخ الحديث مع موضعه" /></div>
      </div>
    </SubSection>
  );
}

/** Hadith only: the Quran original is shown once, inside its context (see Context). */
function Original({ r }: { r: AnalyzeResponse }) {
  if (!r.source || !isHadith(r.context.matched[0])) return null;
  return (
    <SubSection id="h-orig" title="النص الأصلي" icon={ScrollText} desc="نص الحديث كما في الطبعة، ويشمل الإسناد.">
      {r.context.matched.map((u) => <HadithText key={u.passage_id} u={u} />)}
    </SubSection>
  );
}

function Context({ r, cited }: { r: AnalyzeResponse; cited: Set<string> }) {
  if (!r.source) return null;
  const hadith = isHadith(r.context.matched[0]);
  if (hadith) {
    return (
      <SubSection id="h-ctx" title="السياق المسترجع" icon={Layers}>
        <InfoCallout icon={Info} tone="quiet">
          <p>
            يُعرض الحديث كاملًا كما في الطبعة، مع كتابه وبابه ورقمه. لا تُعرض الأحاديث المجاورة على أنها سياق له،
            ولا تُضاف شروح الحديث لأنها لم تُستورد بعد.
          </p>
        </InfoCallout>
      </SubSection>
    );
  }
  const { before, matched, after } = r.context;
  return (
    <SubSection id="h-ctx" title="النص الأصلي في سياقه" icon={BookOpen}
      desc="بالرسم العثماني من مصحف المدينة النبوية، مع آيات من السورة نفسها قبل الموضع وبعده، وليس السياق العلمي الكامل. المسطّر استند إليه التحليل.">
      <div className="reading">
        {before.length > 0 && (
          <div className="ctx-group">
            <p className="ctx-label">{before.length > 1 ? "الآيات السابقة" : "الآية السابقة"}</p>
            <p className="quran ctx-text" lang="ar">{before.map((u) => <Ayah key={u.passage_id} u={u} cited={cited.has(u.passage_id)} />)}</p>
          </div>
        )}
        <figure className="ctx-group ctx-matched scripture">
          <figcaption className="ctx-label">
            {matched.length > 1 ? "الآيات المطابقة" : "الآية المطابقة"} · {quranRef(matched)}
          </figcaption>
          <p className="quran original" lang="ar">{matched.map((u) => <Ayah key={u.passage_id} u={u} cited={cited.has(u.passage_id)} />)}</p>
        </figure>
        {after.length > 0 && (
          <div className="ctx-group">
            <p className="ctx-label">{after.length > 1 ? "الآيات التالية" : "الآية التالية"}</p>
            <p className="quran ctx-text" lang="ar">{after.map((u) => <Ayah key={u.passage_id} u={u} cited={cited.has(u.passage_id)} />)}</p>
          </div>
        )}
      </div>
      {r.context.supporting_material.length > 0 && (
        <InfoCallout icon={BookText} title="مادة تفسيرية معتمدة" />
      )}
    </SubSection>
  );
}

function Alternatives({ r }: { r: AnalyzeResponse }) {
  const qa = r.quote_analysis;
  if (qa.match_status !== "AMBIGUOUS" || !qa.alternatives.length) return null;
  const near = qa.ambiguity_reason === "NEAR_MATCH_UNCONFIRMED";
  return (
    <ReportSection id="h-alts" title={near ? "أقرب النصوص في المصادر" : "المواضع المحتملة"} icon={Split}
      desc="النصوص معروضة بلفظها من المصدر لتراجعها بنفسك.">
      <InfoCallout icon={Info} tone="warning" title={near ? "لم يُنسب الاقتباس إلى أي من هذه النصوص." : "وجدنا أكثر من موضع محتمل"}>
        <p data-source-none="true">لم يتم اعتماد نسبة نهائية للنص.</p>
      </InfoCallout>
      <ul className={`alts${qa.alternatives.every((u) => !isHadith(u)) ? " alts-quran" : ""}`} style={{ marginTop: "var(--s-4)" }}>
        {qa.alternatives.map((u) => {
          const h = isHadith(u);
          const ref = h ? hadithRef(u) : quranRef([u]);
          const cmp = (r.candidate_comparisons ?? []).find((c) => c.passage_ids.length === 1 && c.passage_ids[0] === u.passage_id);
          return (
            <li key={u.passage_id} className="alt-card">
              {h ? (
                <>
                  <div className="alt-head"><span /><CopyButton text={`${u.text}\n— ${ref}`} label="نسخ" /></div>
                  <HadithText u={u} small />
                </>
              ) : (
                <>
                  <div className="alt-head">
                    <span className="alt-ref"><SourceBadge t="quran" />{ref}</span>
                    <CopyButton text={`${u.text}\n— ${ref}`} label="نسخ" />
                  </div>
                  <span className="quran" lang="ar">{u.text}</span>
                </>
              )}
              {cmp && <CandidateComparison c={cmp} />}
            </li>
          );
        })}
      </ul>
      {qa.alternatives_total > qa.alternatives.length && (
        <p className="small muted" style={{ marginTop: "var(--s-3)" }}>و{ar(qa.alternatives_total - qa.alternatives.length)} مواضع أخرى.</p>
      )}
    </ReportSection>
  );
}

function NextSteps({ r }: { r: AnalyzeResponse }) {
  if (r.quote_analysis.match_status !== "NOT_FOUND") return null;
  return (
    <ReportSection id="h-next" title="ماذا يمكنك أن تجرّب" icon={Pencil}
      desc="عدم العثور ليس حكمًا على النص؛ قد يكون منقولًا بلفظ مختلف أو من مصدر لم يُضَف بعد.">
      <ul className="next-steps">
        <li><Pencil {...ICON} size={16} /><span><strong>تعديل الاقتباس</strong> ليطابق لفظ المصدر كما تعرفه، دون إعادة صياغة.</span></li>
        <li><Eraser {...ICON} size={16} /><span><strong>إزالة ما ليس من النص</strong>: التعليقات والرموز والأرقام، وعبارات مثل «رواه البخاري».</span></li>
        <li><Text {...ICON} size={16} /><span><strong>تجربة جزء أطول من النص</strong>، فالمقاطع القصيرة جدًا لا تكفي لتحديد الموضع.</span></li>
      </ul>
      <p className="small muted" style={{ marginTop: "var(--s-4)" }}>
        المصادر المتاحة حاليًا: القرآن الكريم وصحيحا البخاري ومسلم. تفاصيلها في صفحة المصادر.
      </p>
    </ReportSection>
  );
}

const QURAN_TAG = "[النص القرآني]:";
const TAFSIR_TAG = "[تفسير الآية]:";

/** Commentary evidence: the divine text and the tafsir are shown as two separate, labelled layers. */
function CommentaryText({ text }: { text: string }) {
  const i = text.indexOf(TAFSIR_TAG);
  if (i < 0) return <span lang="ar">{text}</span>;
  const quran = text.slice(0, i).replace(QURAN_TAG, "").trim();
  const tafsir = text.slice(i + TAFSIR_TAG.length).trim();
  return (
    <div className="commentary">
      <p className="commentary-label">{QURAN_TAG.replace(":", "")}</p>
      <span className="quran" lang="ar">{quran}</span>
      <p className="commentary-label">{TAFSIR_TAG.replace(":", "")}</p>
      <Tafsir text={tafsir} />
    </div>
  );
}

const TAFSIR_CLIP = 420;

/** Long commentary starts clipped at a word boundary; "عرض المزيد" shows the whole stored text. */
function Tafsir({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const clean = cleanTafsir(text);
  const long = clean.length > TAFSIR_CLIP + 120;
  return (
    <>
      <p className="tafsir-text" lang="ar" data-tafsir-clipped={long && !open}>
        {long && !open ? `${clipText(clean, TAFSIR_CLIP)} …` : clean}
      </p>
      {long && (
        <button type="button" className="more-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? "عرض أقل" : "عرض المزيد"}
        </button>
      )}
    </>
  );
}

function Evidence({ r }: { r: AnalyzeResponse }) {
  const items = r.evidence.items.filter((e) => e.passage_id || e.role === "source_commentary");
  const isAi = r.claim_analysis.summary_source === "ai";
  const notes = new Map(isAi ? r.claim_analysis.key_evidence.map((k) => [k.evidence_id, k.relevance]) : []);
  if (!items.length) return null;
  const ref = (e: EvidenceItem) => e.source_type === "hadith"
    ? (e.metadata?.hadith_number
      ? `${e.metadata?.collection_ar ?? ""}، رقم ${ar(String(e.metadata.hadith_number))}`
      : `${e.metadata?.collection_ar ?? ""}، ${e.metadata?.book ?? ""} (غير مرقّمة)`)
    : `${e.metadata?.surah_name ? `سورة ${e.metadata.surah_name}، ` : ""}الآية ${ar(e.reference?.split(":")[1] ?? "")}`;
  return (
    <Fold id="h-ev" title="الأدلة" icon={ListChecks} hint={items.length === 1 ? "دليل واحد" : items.length === 2 ? "دليلان" : `${ar(items.length)} ${items.length < 11 ? "أدلة" : "دليلًا"}`}>
      <p className="rsub-desc">كل دليل نص مقروء من قاعدة المصادر بمعرّفه، وهي وحدها ما يُسمح للتحليل بالاستناد إليه. اضغط على الدليل لعرض نصه.</p>
      <ul className="ev-list">
        {items.map((e) => (
          <li key={e.id}>
            <details className="ev-card" data-evidence-id={e.id} id={`ev-${e.id}`} tabIndex={-1}>
              <summary>
                <span className="ev-id" dir="ltr">{e.id}</span>
                <span className="ev-meta-start">
                  <SourceBadge t={e.source_type} />
                  <strong>{ROLE[e.role] ?? e.role}</strong>
                  <span className="muted">{ref(e)}</span>
                  {e.role === "source_commentary" && e.source_title && <span className="muted">· {e.source_title}</span>}
                  {notes.get(e.id) && <Badge tone="info" icon={Cpu}>استند إليه التحليل</Badge>}
                </span>
                <ChevronDown {...ICON} />
              </summary>
              <div className="ev-body">
                <div className="ev-text">
                  {e.role === "source_commentary"
                    ? <CommentaryText text={e.text} />
                    : e.source_type === "hadith"
                      ? <p className="hadith-text hadith-text-small">{e.text}</p>
                      : <span className="quran" lang="ar">{e.text}</span>}
                </div>
                {notes.get(e.id) && (
                  <p className="ai-note"><span className="ai-tag">ملاحظة آلية:</span> {notes.get(e.id)}</p>
                )}
                <div><CopyButton text={`${e.text}\n— ${ref(e)} (${e.id})`} label="نسخ الدليل" /></div>
              </div>
            </details>
          </li>
        ))}
      </ul>
    </Fold>
  );
}

function Limits({ r }: { r: AnalyzeResponse }) {
  const ca = r.claim_analysis;
  const hadith = isHadith(r.context.matched[0]);
  return (
    <SubSection id="h-limits" title="التحفظات وحدود النتيجة" icon={TriangleAlert}>
      <ul className="limits">
        {r.warnings.map((w) => <li key={w.code} data-warning={w.code}>{WARNING[w.code] ?? w.message}</li>)}
        {ca.safety_overrides.map((o) => <li key={o}>{OVERRIDE[o] ?? o}</li>)}
        {aiFailed(r) && <li>{AI_FAILED_TITLE}: لم يُصنَّف الادعاء ({aiFailureReason(r)}).</li>}
        {hadith && (
          <li>
            نص الرقم في الطبعة يشمل الإسناد، وقد يتضمن معلّقًا أو أثرًا أو كلامًا للمصنّف؛ حكم «الصحيحين» قاعدة على مستوى
            الكتاب، وليس حكمًا مستقلًا على كل جزء من النص.
          </li>
        )}
        <li>النموذج اللغوي ليس مصدرًا للمعلومة الشرعية؛ التحليل مقيّد بالأدلة المعروضة فقط.</li>
        <li>لم تُقيَّم تصنيفات علاقة الادعاء بعدُ على حالات راجعها مختص، ولم يُقَس أداء النموذج فيها قياسًا منهجيًا بعد.</li>
        <li>{SEARCHED} لم تُضَف كتب التفسير ولا العقيدة ولا الفقه ولا السيرة بعد.</li>
        <li>لا ينسب تِبيان اقتباسًا إلى مصدر إلا عند المطابقة الحرفية الكاملة أو الجزئية.</li>
        <li>تِبيان أداة تحقق، وليس مفتيًا ولا بديلًا عن المختص.</li>
      </ul>
    </SubSection>
  );
}

function Technical({ r }: { r: AnalyzeResponse }) {
  const u = r.context.matched[0];
  const hadith = isHadith(u);
  const ca = r.claim_analysis;
  const matched = r.context.matched;
  return (
    <SubSection id="h-refs" title="المراجع والتفاصيل التقنية" icon={Wrench}>
      {r.source ? (
        <div className="small">
          <p><strong>{r.source.title}</strong></p>
          {!hadith && u ? (
            <dl className="kv">
              <div><dt>رقم السورة والآية</dt><dd className="num">{ar(u.metadata.surah_number ?? "")}:{ar(u.metadata.ayah_number ?? "")}{matched.length > 1 ? `–${ar(matched[matched.length - 1].metadata.ayah_number ?? "")}` : ""}</dd></div>
              {r.source.publisher && <div><dt>الناشر</dt><dd>{r.source.publisher}</dd></div>}
              <div><dt>الرواية والطبعة</dt><dd>{r.source.edition}</dd></div>
            </dl>
          ) : (
            <p className="muted">{[r.source.publisher, r.source.edition].filter(Boolean).join("، ")}</p>
          )}
          <p className="muted">
            {hadith
              ? "مسار البيانات: ملفات OpenITI المأخوذة من المكتبة الشاملة (CC BY-NC-SA 4.0)، مطابقة للبصمة المثبتة في المستودع. لم تُقابَل بالشاملة أو الدرر بعد."
              : "النص عبر قرآنبيديا (quranpedia.net)، بنسخة مطابقة لملف المجمع بالتحقق من البصمة."}
          </p>
        </div>
      ) : (
        <p className="small muted">لا توجد مصادر منسوبة لهذه النتيجة.</p>
      )}
      <div style={{ marginTop: "var(--s-4)" }}>
        <Disclosure summary="تفاصيل تقنية">
          <p className="small muted">نوع المسألة بحسب التصنيف الآلي للكلمات المفتاحية: {LEVEL[ca.content_level]}</p>
          {r.evidence.items.length > 0 && (
            <div className="table-wrap" tabIndex={0} role="region" aria-label="جدول الأدلة، قابل للتمرير" style={{ marginTop: "var(--s-4)" }}>
              <table className="data">
                <caption>معرّفات الأدلة ومواضعها</caption>
                <thead><tr><th scope="col">المعرّف</th><th scope="col">الدور</th><th scope="col">الموضع</th></tr></thead>
                <tbody>
                  {r.evidence.items.map((e) => (
                    <tr key={e.id}>
                      <td dir="ltr">{e.id}</td>
                      <td>{ROLE[e.role] ?? e.role}</td>
                      <td dir="ltr">{e.passage_id ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="meta-line" dir="ltr" style={{ marginTop: "var(--s-4)" }}>
            corpus {r.metadata.corpus_version} / searched {(r.sources_searched ?? []).join("+") || "quran"} /{" "}
            {r.metadata.search_mode} ({r.metadata.ranking_strategy}) / gate {ca.gate.decision} / llm {r.metadata.llm_provider ?? "none"}
            {r.metadata.llm_model ? ` / ${r.metadata.llm_model}` : ""} / prompt {r.metadata.prompt_version}
            {r.evidence_map ? ` / source ${r.evidence_map.source.source_id}` : ""} / request {r.request_id.slice(0, 8)}
          </p>
        </Disclosure>
      </div>
    </SubSection>
  );
}

export default function Result({ r }: { r: AnalyzeResponse }) {
  const ca = r.claim_analysis;
  const byId = new Map(r.evidence.items.map((e) => [e.id, e]));
  const cited = new Set(ca.evidence_ids.map((i) => byId.get(i)?.passage_id).filter(Boolean) as string[]);
  return (
    <article className="result entering" aria-label="نتيجة التحقق" data-request-id={r.request_id}
      data-source-type={r.source?.source_type ?? ""}>
      <Summary r={r} />
      <div className="report">
        <Alternatives r={r} />
        <NextSteps r={r} />
      </div>
      <div className="folds">
        {r.source && (
          <Fold id="h-text" title="النص والسياق" icon={BookOpen} hint="المصدر، النص الأصلي، المقارنة، السياق">
            <SourceSection r={r} />
            <Original r={r} />
            <Context r={r} cited={cited} />
            <ComparisonSection c={r.quote_comparison} />
            <EvidenceMapSection r={r} />
          </Fold>
        )}
        <Evidence r={r} />
        <Fold id="h-lim" title="التحفظات والمراجع" icon={TriangleAlert} hint="حدود النتيجة، المراجع، تفاصيل تقنية">
          <Limits r={r} />
          <Technical r={r} />
        </Fold>
      </div>
    </article>
  );
}

