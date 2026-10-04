import { useEffect, useState } from "react";
import { CircleAlert, FlaskConical, Hourglass } from "lucide-react";
import { getJson } from "../api";
import { ar } from "../format";
import { Disclosure, ICON, InfoCallout, MetricCard } from "../components/ui";
import { useHealth } from "../health";

type Metric = { n: number; "recall@1": number; "recall@5": number; mrr: number };
type Retr = {
  seed: number; cases: number; generated_at: string; case_source: string;
  overall: Record<string, Metric>;
  quote_matching_production: Record<string, Record<string, number>> | null;
  not_found_synthetic: { n: number; status_counts: Record<string, number>; false_positive_rate: number };
} | null;
type Rate = { passed: number; total: number; rate: number };
type Stage = { n: number; avg_ms: number; p50_ms: number; p95_ms: number };
type Multi = {
  generated_at: string; cases_per_category: number; case_source: string;
  hadith_retrieval_bm25: Record<string, Metric>;
  hadith_matching_full_pipeline: Record<string, Record<string, number>>;
  quran_cases_full_pipeline_by_resolved_source: Record<string, number>;
  not_found_synthetic_full_pipeline: { n: number; status_counts: Record<string, number> };
  not_measured: string[];
} | null;
type EvalData = {
  multi_source: Multi;
  retrieval: { development: Retr; held_out: Retr };
  guard_rails: { label: string; generated_at: string; cases: number; metrics: Record<string, unknown> } | null;
  llm: { status?: string; [k: string]: unknown };
  classification: { status: string; reviewed_cases: number; reason: string };
  performance: { generated_at: string; environment: Record<string, string>; stages: Record<string, Stage> } | null;
  load_test: {
    generated_at: string; concurrency: number; requests: number; succeeded: number; failed: number;
    latency_ms: { avg: number; p50: number; p95: number }; throughput_rps: number;
    rss_mb: { before: number; after: number }; note?: string;
  } | null;
  test_suite: { generated_at: string; suites: Record<string, { passed: number; failed: number; skipped?: number }> } | null;
};

const POOL_LABEL: Record<string, string> = {
  bm25_only: "BM25 وحده",
  semantic_only: "المتجهي (LSA) وحده",
  hybrid_rrf: "دمج RRF",
  hybrid_rrf_exact_priority: "RRF مع أولوية المطابقة",
  hybrid_lexical_first: "النصي أولًا (المعتمد)",
};
const OUTCOME_LABEL: Record<string, string> = {
  correct_resolved: "نُسب إلى الموضع الصحيح",
  correct_ambiguous_repeated_text: "متكرر في المصحف فلم يُنسب (صحيح)",
  near_match_not_attributed_source_listed: "قريب غير مطابق: لم يُنسب، والمصدر ضمن الأقرب",
  conservative_ambiguous_source_in_alternatives: "لم يُنسب، والمصدر ضمن المواضع المحتملة",
  WRONG_resolved: "نُسب إلى موضع خاطئ",
  missed: "لم يُعثر عليه",
};
const HCAT: Record<string, string> = {
  partial_verbatim: "مقطع حرفي من حديث",
  word_substitution: "مقطع بكلمة مستبدلة",
  word_deletion: "مقطع بكلمتين محذوفتين",
  honorific_symbol: "«صلى الله عليه وسلم» مكتوبة بالرمز ﷺ",
  honorific_omitted: "«صلى الله عليه وسلم» محذوفة",
};
const HOUT: Record<string, string> = {
  correct_resolved: "نُسب إلى الحديث الصحيح",
  correct_ambiguous_repeated_text: "متكرر بلفظه في أكثر من حديث فلم يُنسب (صحيح)",
  resolved_to_quran_query_is_verbatim_ayah_text: "المقطع آية مقتبسة داخل الحديث فنُسب إلى القرآن",
  resolved_to_other_hadith_containing_query_verbatim: "نُسب إلى حديث آخر يحتوي النص بلفظه",
  near_match_not_attributed_source_listed: "قريب غير مطابق: لم يُنسب، والمصدر ضمن الأقرب",
  near_match_not_attributed_source_not_listed: "قريب غير مطابق: لم يُنسب، والمصدر ليس ضمن الأقرب",
  missed: "لم يُعثر عليه",
  WRONG_resolved: "نُسب خطأً",
};
const GUARD_LABEL: Record<string, string> = {
  critical_safety_case_pass_rate: "الحالات الحرجة",
  required_abstention_recall: "الامتناع حين يجب",
  specialist_routing_pass_rate: "الإحالة إلى مختص",
  prompt_injection_defense_pass_rate_structural: "مقاومة حقن التعليمات (بنيويًا)",
  hallucination_rejection_rate: "رفض الاستشهادات المختلقة",
  llm_failure_degradation_pass_rate: "التدهور الآمن عند فشل النموذج",
  all_technical_cases: "جميع الحالات التقنية",
};
const NOT_MEASURED_AR: Record<string, string> = {
  "tafsir, aqeedah, fiqh, history, dawah and shubuhat retrieval (sources not ingested)":
    "الاسترجاع في التفسير والعقيدة والفقه والسيرة والمحتوى الدعوي والشبهات (مصادرها لم تُستورد).",
  "real user hadith quotations, paraphrased hadith, grading questions":
    "اقتباسات المستخدمين الحقيقية للأحاديث، والأحاديث المنقولة بالمعنى، وأسئلة درجة الحديث.",
  "claim analysis on hadith (disabled)": "تحليل الادعاء على الأحاديث (غير مفعّل).",
};

const pct = (x: number) => `${ar((x * 100).toFixed(1))}٪`;
const num = (x: number, d = 1) => ar(Number.isInteger(x) ? x : x.toFixed(d));
const isRate = (v: unknown): v is Rate => !!v && typeof v === "object" && "passed" in v && "total" in v;

function RetrTable({ d, title }: { d: Retr; title: string }) {
  if (!d) return <p className="muted">لا توجد نتائج محفوظة.</p>;
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={`${title}، جدول قابل للتمرير`}>
      <table className="data">
        <caption>{title}: {ar(d.cases)} حالة، البذرة {ar(d.seed)}</caption>
        <thead><tr><th scope="col">طريقة الترتيب</th><th scope="col">Recall@1</th><th scope="col">Recall@5</th><th scope="col">MRR</th></tr></thead>
        <tbody>
          {Object.entries(d.overall).map(([k, m]) => (
            <tr key={k} className={k === "hybrid_lexical_first" ? "row-strong" : ""}>
              <th scope="row">{POOL_LABEL[k] ?? k}</th>
              <td>{pct(m["recall@1"])}</td><td>{pct(m["recall@5"])}</td><td>{num(m.mrr, 3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function sumOutcomes(by: Record<string, Record<string, number>>) {
  const totals: Record<string, number> = {};
  for (const o of Object.values(by)) for (const [k, n] of Object.entries(o)) totals[k] = (totals[k] ?? 0) + n;
  return totals;
}

export default function Evaluation() {
  const health = useHealth();
  const [d, setD] = useState<EvalData | null | undefined>(undefined);
  useEffect(() => { getJson<EvalData>("/api/v1/evaluation").then(setD); }, []);
  const prod = d?.retrieval.held_out?.overall.hybrid_lexical_first;
  const byCol = health?.components.hadith_corpus?.by_collection ?? {};

  return (
    <>
      <header className="page-head">
        <div className="container">
          <h1>التقييم</h1>
          <p>الأرقام المقيسة فعلًا والمحفوظة في المستودع فقط. ما لم يُقَس بعدُ مكتوب بوضوح أنه لم يُقَس.</p>
        </div>
      </header>

      <div className="page-body container">
        {d === undefined && <p role="status" className="muted">جارٍ تحميل النتائج…</p>}
        {d === null && (
          <InfoCallout tone="error" icon={CircleAlert} role="alert" title="تعذّر تحميل نتائج التقييم.">
            <p>تحقّق من تشغيل الخادم ثم أعد تحميل الصفحة.</p>
          </InfoCallout>
        )}

        {d && (
          <>
            <section className="block" aria-labelledby="ev-pending">
              <div className="block-head"><h2 id="ev-pending">حالة التحقق بنموذج حقيقي</h2></div>
              <div className="block-body">
                <InfoCallout tone="warning" icon={Hourglass}
                  title={<span data-llm-status={d.llm.status ?? "MEASURED"}>
                    {d.llm.status === "PENDING_REAL_MODEL_VALIDATION"
                      ? "تحليل الادعاء بنموذج لغوي حقيقي: بانتظار التحقق (Pending real-model validation)"
                      : "نتائج النموذج الحقيقي محفوظة في المستودع."}
                  </span>}>
                  <p>لم يُجرَ بعدُ تقييم منهجي لتحليل الادعاء بنموذج لغوي حقيقي، فلا توجد أرقام محفوظة لدقة تصنيف الادعاءات أو ثباته أو زمنه أو كلفته.</p>
                  <p>
                    دقة التصنيف الشرعي (accuracy / precision / recall / F1) لم تُحسب، لأن عدد الحالات التي راجعها مختص مؤهل{" "}
                    {ar(d.classification.reviewed_cases)}.
                  </p>
                </InfoCallout>
              </div>
            </section>

            <section className="block" aria-labelledby="ev-cov">
              <div className="block-head">
                <h2 id="ev-cov">تغطية المصادر</h2>
                <p>عدد السجلات في قاعدة المصادر التي يعمل عليها الخادم الآن.</p>
              </div>
              <div className="metrics block-body">
                <MetricCard label="القرآن الكريم" value={ar(health?.components.quran_corpus?.passages ?? 0)} sub="آية، رواية حفص (مصحف المدينة النبوية)" />
                <MetricCard label="صحيح البخاري" value={ar(byCol["hadith:bukhari"] ?? 0)} sub="سجل حديث، تشغيل محدود" />
                <MetricCard label="صحيح مسلم" value={ar(byCol["hadith:muslim"] ?? 0)} sub="سجل حديث، منها روايات غير مرقّمة في الملف، تشغيل محدود" />
              </div>
            </section>

            <section className="block" aria-labelledby="ev-retr">
              <div className="block-head">
                <h2 id="ev-retr">استرجاع النص القرآني</h2>
                <p>
                  حالات مولَّدة آليًا من نص المصحف نفسه (اقتباسات كاملة ومقتطعة وبتغيير حرف أو كلمة)، وليست أسئلة مستخدمين
                  حقيقيين. تقيس العثور على الموضع الصحيح، لا فهم المعنى.
                </p>
              </div>
              <div className="block-body">
                {prod && (
                  <div className="metrics">
                    <MetricCard label="Recall@1" value={pct(prod["recall@1"])} ratio={prod["recall@1"]} sub="الموضع الصحيح أولًا، مجموعة مستقلة" />
                    <MetricCard label="Recall@5" value={pct(prod["recall@5"])} ratio={prod["recall@5"]} sub="الموضع الصحيح ضمن أول خمسة" />
                    <MetricCard label="MRR" value={num(prod.mrr, 3)} ratio={prod.mrr} sub="متوسط مقلوب ترتيب الموضع الصحيح" />
                  </div>
                )}
                <div style={{ marginTop: "var(--s-8)" }}>
                  <RetrTable d={d.retrieval.held_out} title="مجموعة مستقلة لم يُضبط عليها النظام" />
                </div>
                <div style={{ marginTop: "var(--s-6)" }}>
                  <Disclosure summary="مجموعة التطوير ونتيجة المطابقة">
                    <RetrTable d={d.retrieval.development} title="مجموعة التطوير" />
                    {d.retrieval.development?.quote_matching_production && (
                      <>
                        <h3 className="sub">نتيجة المطابقة في الإعداد المعتمد (مجموعة التطوير)</h3>
                        <ul className="stat-list">
                          {Object.entries(OUTCOME_LABEL).map(([k, label]) => (
                            <li key={k}><span>{label}</span><strong>{ar(sumOutcomes(d.retrieval.development!.quote_matching_production!)[k] ?? 0)}</strong></li>
                          ))}
                        </ul>
                        <p className="small" style={{ marginTop: "var(--s-3)" }}>
                          نصوص غير قرآنية مصطنعة: {ar(d.retrieval.development.not_found_synthetic.status_counts.NOT_FOUND ?? 0)} من{" "}
                          {ar(d.retrieval.development.not_found_synthetic.n)} أُعيدت «غير موجود».
                        </p>
                      </>
                    )}
                  </Disclosure>
                </div>
              </div>
            </section>

            {d.multi_source && (
              <section className="block" aria-labelledby="ev-hadith">
                <div className="block-head">
                  <h2 id="ev-hadith">الحديث النبوي (صحيحا البخاري ومسلم)</h2>
                  <p>
                    حالات مولَّدة آليًا من نصوص الأحاديث نفسها ({ar(d.multi_source.cases_per_category)} لكل فئة)، وليست أسئلة
                    مستخدمين. تُقاس كل فئة وحدها، ولا يوجد رقم إجمالي.
                  </p>
                </div>
                <div className="block-body">
                  <h3 className="sub" style={{ marginTop: 0 }}>Recall@1 لكل فئة (BM25 وحده على فهرس الحديث)</h3>
                  <ul className="bars" style={{ marginTop: "var(--s-4)" }}>
                    {Object.entries(d.multi_source.hadith_retrieval_bm25).map(([k, m]) => (
                      <li key={k} title={`Recall@5 ${pct(m["recall@5"])}، MRR ${num(m.mrr, 3)}`}>
                        <span>{HCAT[k] ?? k}</span>
                        <span className="bar" aria-hidden="true"><span style={{ width: `${m["recall@1"] * 100}%` }} /></span>
                        <strong>{pct(m["recall@1"])}</strong>
                      </li>
                    ))}
                  </ul>
                  <p className="small muted" style={{ marginTop: "var(--s-3)" }}>
                    هذا أداء الاسترجاع وحده. في النظام كاملًا تُقدَّم المطابقات الحرفية أولًا، والنتيجة أدناه.
                  </p>
                  <div style={{ marginTop: "var(--s-6)" }}>
                    <Disclosure summary="الجدول الكامل ونتيجة النظام كاملًا">
                      <div className="table-wrap" tabIndex={0} role="region" aria-label="استرجاع الحديث، جدول قابل للتمرير">
                        <table className="data">
                          <caption>استرجاع الحديث: BM25 وحده</caption>
                          <thead><tr><th scope="col">الفئة</th><th scope="col">Recall@1</th><th scope="col">Recall@5</th><th scope="col">MRR</th></tr></thead>
                          <tbody>
                            {Object.entries(d.multi_source.hadith_retrieval_bm25).map(([k, m]) => (
                              <tr key={k}><th scope="row">{HCAT[k] ?? k}</th><td>{pct(m["recall@1"])}</td><td>{pct(m["recall@5"])}</td><td>{num(m.mrr, 3)}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                      <h3 className="sub">نتيجة المطابقة في النظام كاملًا</h3>
                      <ul className="stat-list">
                        {Object.entries(sumOutcomes(d.multi_source.hadith_matching_full_pipeline))
                          .map(([k, v]) => <li key={k}><span>{HOUT[k] ?? k}</span><strong>{ar(v)}</strong></li>)}
                        <li>
                          <span>مقاطع قرآنية مرّت بالنظام كاملًا ونُسبت إلى حديث</span>
                          <strong>{ar(Object.entries(d.multi_source.quran_cases_full_pipeline_by_resolved_source)
                            .filter(([k]) => k.includes("hadith")).reduce((a, [, v]) => a + v, 0))}</strong>
                        </li>
                        <li>
                          <span>نصوص غير دينية أعيدت «غير موجود»</span>
                          <strong>{ar(d.multi_source.not_found_synthetic_full_pipeline.status_counts.NOT_FOUND ?? 0)} / {ar(d.multi_source.not_found_synthetic_full_pipeline.n)}</strong>
                        </li>
                      </ul>
                    </Disclosure>
                  </div>
                </div>
              </section>
            )}

            {d.guard_rails && (
              <section className="block" aria-labelledby="ev-guard">
                <div className="block-head">
                  <h2 id="ev-guard">ضوابط الأمان</h2>
                  <p>هل ترفض طبقات التحقق المخرجات الخاطئة، وتمتنع وتحيل حين يجب؟</p>
                </div>
                <div className="block-body">
                  <InfoCallout icon={FlaskConical} tone="info" title="ليست أداء نموذج">
                    <p>
                      نتائج اختبار الضوابط بمخرجات نموذج مُعدّة مسبقًا (test double). تقيس سلوك طبقات التحقق، ولا تقيس جودة أي
                      نموذج لغوي.
                    </p>
                  </InfoCallout>
                  <div className="metrics" style={{ marginTop: "var(--s-6)" }}>
                    {Object.entries(d.guard_rails.metrics).filter(([, v]) => isRate(v)).map(([k, v]) => {
                      const r = v as Rate;
                      return <MetricCard key={k} label={GUARD_LABEL[k] ?? k} value={`${ar(r.passed)} / ${ar(r.total)}`} ratio={r.rate} />;
                    })}
                    {typeof d.guard_rails.metrics.model_outputs_rejected_by_verifiers === "number" && (
                      <MetricCard label="مخرجات رفضتها طبقات التحقق" value={ar(d.guard_rails.metrics.model_outputs_rejected_by_verifiers as number)}
                        sub="مخرجات مختلقة أو غير مستندة رُفضت عمدًا في الاختبار" />
                    )}
                  </div>
                </div>
              </section>
            )}

            <section className="block" aria-labelledby="ev-perf">
              <div className="block-head">
                <h2 id="ev-perf">الأداء (دون نموذج لغوي)</h2>
                <p>على بيئة التطوير، بعامل خادم واحد. ليست ادعاءً لسعة خادم إنتاجي.</p>
              </div>
              <div className="block-body">
                {d.load_test && (
                  <div className="metrics">
                    <MetricCard label="زمن الاستجابة p50" value={`${num(d.load_test.latency_ms.p50)} ms`} sub={`عند ${ar(d.load_test.concurrency)} طلبًا متزامنًا`} />
                    <MetricCard label="زمن الاستجابة p95" value={`${num(d.load_test.latency_ms.p95)} ms`} />
                    <MetricCard label="طلبات ناجحة" value={`${ar(d.load_test.succeeded)} / ${ar(d.load_test.requests)}`} />
                    <MetricCard label="طلبات في الثانية" value={num(d.load_test.throughput_rps)} />
                  </div>
                )}
                {d.performance ? (
                  <div style={{ marginTop: "var(--s-6)" }}>
                    <Disclosure summary="زمن كل مرحلة">
                      <div className="table-wrap" tabIndex={0} role="region" aria-label="زمن المراحل، جدول قابل للتمرير">
                        <table className="data">
                          <caption>زمن كل مرحلة بالملّي ثانية</caption>
                          <thead><tr><th scope="col">المرحلة</th><th scope="col">المتوسط</th><th scope="col">p50</th><th scope="col">p95</th></tr></thead>
                          <tbody>
                            {Object.entries(d.performance.stages).map(([k, s]) => (
                              <tr key={k}><th scope="row" dir="ltr">{k}</th><td>{num(s.avg_ms, 2)}</td><td>{num(s.p50_ms, 2)}</td><td>{num(s.p95_ms, 2)}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </Disclosure>
                  </div>
                ) : <p className="muted">لم يُقَس بعد.</p>}
              </div>
            </section>

            {d.test_suite && (
              <section className="block" aria-labelledby="ev-tests">
                <div className="block-head">
                  <h2 id="ev-tests">الاختبارات الآلية</h2>
                  <p>آخر تشغيل محفوظ في المستودع.</p>
                </div>
                <ul className="stat-list block-body">
                  {Object.entries(d.test_suite.suites).map(([k, s]) => (
                    <li key={k}><span>{k === "backend_pytest" ? "اختبارات الخادم (pytest)" : k === "browser_e2e_playwright" ? "اختبارات المتصفح (Playwright)" : k}</span><strong>{ar(s.passed)} نجح، {ar(s.failed)} فشل</strong></li>
                  ))}
                </ul>
              </section>
            )}

            <section className="block" aria-labelledby="ev-limits">
              <div className="block-head"><h2 id="ev-limits">ما لم يُقَس بعد</h2></div>
              <ul className="limits block-body" style={{ fontSize: "var(--t-base)" }}>
                <li>تحليل الادعاء بنموذج لغوي حقيقي: دقته وثباته وزمنه وكلفته.</li>
                <li>دقة التصنيف الشرعي على حالات راجعها مختص مؤهل.</li>
                {(d.multi_source?.not_measured ?? []).map((x) => <li key={x}>{NOT_MEASURED_AR[x] ?? x}</li>)}
              </ul>
            </section>
          </>
        )}
      </div>
    </>
  );
}
