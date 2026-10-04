import { useState } from "react";
import { BookOpen, Cpu, Info, Library, MessageSquareQuote, ScrollText, Scale, Waypoints } from "lucide-react";
import type { AnalyzeResponse, EvidenceMap as EMap } from "../types";
import { ar, ROLE } from "../format";
import { ChevronDown } from "lucide-react";
import { Badge, ICON, reveal } from "../components/ui";
import { RELATION_UI } from "./Result";

/* Evidence & context map. Everything shown is the response's own data (backend app/services/evidence_map.py):
   stored text split into segments, evidence ids, and the claim-analysis outcome already decided by the pipeline.
   Omitted text is stated as a fact; whether it matters is shown only when a verified AI analysis cited it. */

const NODE_LABEL: Record<string, string> = {
  preceding_context: "السياق السابق",
  matched: "الموضع المطابق",
  following_context: "السياق اللاحق",
};

const RELEVANCE: Record<string, { label: string; tone: "neutral" | "info" | "warning" | "success" }> = {
  UNDETERMINED: { label: "غير محدد", tone: "neutral" },
  LIMITED: { label: "محدودة", tone: "info" },
  RELEVANT: { label: "ذات صلة", tone: "warning" },
  NEEDS_REVIEW: { label: "تحتاج مراجعة", tone: "info" },
};

const ids = (xs: string[]) => xs.map((x) => `⁦${x}⁩`).join("، ");

function relevanceText(m: EMap): string {
  const r = m.result.context_relevance;
  switch (r.basis) {
    case "NO_ANALYSIS":
      return "لم يُحلَّل الادعاء، فلا يحكم تِبيان على أثر ما لم يُقتبس. عرض السياق هنا حقيقة نصية، لا حكم.";
    case "NOT_ENABLED_FOR_SOURCE":
      return "تحليل الادعاء غير مفعّل للأحاديث بعد. يُعرض الحديث كاملًا دون حكم على أثر ما لم يُقتبس منه.";
    case "AI_CITED_MATCHED_ONLY":
      return `استند التحليل الآلي المتحقَّق منه إلى النص المطابق وحده (${ids(r.cited_evidence_ids)})، ولم يستشهد بالسياق.`;
    case "AI_CITED_CONTEXT":
      return `استشهد التحليل الآلي المتحقَّق منه بأدلة من السياق: ${ids(r.cited_evidence_ids)}.`;
    case "SPECIALIST_OR_RESTRICTED":
      return "المسألة محالة إلى مختص أو مقيّدة، فتقدير أثر السياق متروك للمراجعة.";
  }
}

function claimOutcome(m: EMap): { text: string; ai: boolean } {
  const r = m.result;
  if (r.summary_source === "ai" && r.relation) return { text: RELATION_UI[r.relation].title, ai: true };
  switch (r.claim_status) {
    case "ANALYSIS_UNAVAILABLE": return { text: "لم يُحلَّل الادعاء: التحليل بالذكاء الاصطناعي غير متاح لهذه النتيجة", ai: false };
    case "REFERRED": return { text: "محال إلى مختص", ai: false };
    case "AI_OUTPUT_REJECTED": return { text: "رُفضت مخرجات التحليل الآلي لأنها لم تجتز التحقق", ai: false };
    default: return { text: "لم يُحلَّل الادعاء", ai: false };
  }
}

function goToEvidence(id: string, nodeId: string) {
  const el = document.getElementById(nodeId === "source" ? "h-src" : `ev-${id}`);
  if (!el) return;
  reveal(el);
  el.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
  el.classList.add("flash");
  window.setTimeout(() => el.classList.remove("flash"), 1600);
  if (nodeId !== "source") (el as HTMLElement).focus({ preventScroll: true });
}

function Chip({ id, nodeId, active, onHover }: { id: string; nodeId: string; active: boolean; onHover: (v: string | null) => void }) {
  return (
    <button type="button" className={`ev-chip${active ? " is-active" : ""}`} dir="ltr" data-map-evidence={id}
      aria-label={`الدليل ${id}: انتقل إلى نصه`} onClick={() => goToEvidence(id, nodeId)}
      onMouseEnter={() => onHover(nodeId)} onMouseLeave={() => onHover(null)} onFocus={() => onHover(nodeId)} onBlur={() => onHover(null)}>
      {id}
    </button>
  );
}

export default function EvidenceMapSection({ r }: { r: AnalyzeResponse }) {
  const m = r.evidence_map;
  const [hot, setHot] = useState<string | null>(null);
  if (!m) return null;
  const quran = m.source.source_type === "quran";
  const rel = RELEVANCE[m.result.context_relevance.value];
  const outcome = claimOutcome(m);
  const cited = new Set(m.result.context_relevance.cited_evidence_ids);
  const total = m.facts.quoted_words + m.facts.omitted_words_in_matched;

  return (
    <section className="rsub" aria-labelledby="h-map">
      <details className="disclosure" data-map-disclosure>
        <summary>
          <span className="rsub-head"><Waypoints {...ICON} /><h3 id="h-map">خريطة الدليل والسياق</h3></span>
          <ChevronDown {...ICON} />
        </summary>
        <div className="disclosure-body">
      <p className="rsub-desc">توضح الخريطة موضع الاقتباس داخل المصدر وكيف ترتبط الأدلة بالادعاء.</p>
      <ol className="emap" aria-label="خريطة الدليل والسياق">
        <li className="emap-station" data-step="source">
          <p className="emap-step"><Library {...ICON} size={16} />المصدر</p>
          <p className="emap-source">
            <Badge tone={quran ? "primary" : "accent"} icon={quran ? BookOpen : ScrollText}>{quran ? "القرآن الكريم" : "الحديث النبوي"}</Badge>
            <span>{m.source.title}</span>
          </p>
        </li>

        <li className="emap-station" data-step="text">
          <p className="emap-step"><BookOpen {...ICON} size={16} />النص الأصلي والجزء المقتبس والسياق</p>
          <div className="emap-lanes">
            {m.nodes.map((n) => (
              <div key={n.id} className={`emap-row${hot === n.id ? " is-hot" : ""}`} data-node-kind={n.kind}
                data-map-node={n.passage_id}>
                <div className="emap-links" aria-label="الأدلة المرتبطة بهذا النص">
                  {n.evidence_ids.map((id) => <Chip key={id} id={id} nodeId={n.id} active={cited.has(id)} onHover={setHot} />)}
                </div>
                <div className="emap-text">
                  <p className="emap-node-label">
                    <span>{n.kind === "matched" && !quran ? "نص الحديث" : NODE_LABEL[n.kind]}</span>
                  </p>
                  <p className={`emap-body${quran ? " quran" : " hadith-text"}`} lang="ar">
                    {n.segments.map((s, i) => (
                      <span key={i} className={`seg seg-${s.kind}`}>
                        {s.kind === "quoted" && <span className="sr-only">في اقتباسك: </span>}
                        {s.kind === "near_context" && <span className="sr-only">غير موجود في الاقتباس: </span>}
                        {s.text}{" "}
                      </span>
                    ))}
                  </p>
                </div>
              </div>
            ))}
          </div>
          <ul className="emap-legend" aria-label="مفتاح الألوان">
            <li><span className="swatch seg-quoted" aria-hidden="true" />النص الموجود في اقتباسك والمطابق للمصدر</li>
            <li><span className="swatch seg-near_context" aria-hidden="true" />{quran ? "بقية الموضع المطابق، غير موجودة في الاقتباس" : "بقية نص الحديث (ومنه الإسناد)، غير موجودة في الاقتباس"}</li>
            {!quran ? null : <li><span className="swatch seg-context" aria-hidden="true" />سياق إضافي من السورة نفسها</li>}
          </ul>
          <ul className="emap-facts">
            <li data-map-fact="coverage">يغطي اقتباسك {ar(m.facts.quoted_words)} من {ar(total)} كلمة في {quran ? "الموضع المطابق" : "نص الحديث"}.</li>
            {m.facts.omitted_words_in_matched > 0 && (
              <li data-map-fact="omitted">{ar(m.facts.omitted_words_in_matched)} كلمة من الموضع نفسه غير موجودة في الاقتباس المقدم. هذه حقيقة نصية، لا حكم على المعنى.</li>
            )}
            {quran
              ? <li>يُعرض {ar(m.facts.preceding_units)} من الآيات قبله و{ar(m.facts.following_units)} بعده من السورة نفسها.</li>
              : <li>لا تُعرض الأحاديث المجاورة على أنها سياق لهذا الحديث.</li>}
          </ul>
        </li>

        <li className="emap-station" data-step="claim">
          <p className="emap-step"><MessageSquareQuote {...ICON} size={16} />الادعاء المصاحب</p>
          <blockquote className="claim-quote">{m.claim.text}</blockquote>
        </li>

        <li className="emap-station" data-step="evidence">
          <p className="emap-step"><Scale {...ICON} size={16} />الأدلة</p>
          <ul className="emap-ev">
            {m.evidence.map((e) => (
              <li key={e.id}>
                <Chip id={e.id} nodeId={e.node_id} active={cited.has(e.id)} onHover={setHot} />
                <span>{ROLE[e.role] ?? e.role}</span>
              </li>
            ))}
          </ul>
        </li>

        <li className="emap-station" data-step="result">
          <p className="emap-step"><Cpu {...ICON} size={16} />نتيجة العلاقة بين الادعاء والدليل</p>
          <p className="emap-outcome" data-map-outcome={m.result.claim_status}>
            {outcome.ai && <Badge tone="info" icon={Cpu}>مدعوم بالذكاء الاصطناعي</Badge>} {outcome.text}
          </p>
          <div className="emap-relevance" data-context-relevance={m.result.context_relevance.value}>
            <p><span>أهمية السياق للادعاء:</span> <Badge tone={rel.tone}>{rel.label}</Badge></p>
            <p className="small muted"><Info {...ICON} size={14} /> {relevanceText(m)}</p>
          </div>
        </li>
      </ol>
        </div>
      </details>
    </section>
  );
}
