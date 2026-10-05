import { useEffect, useState } from "react";
import {
  BookOpen, CircleSlash, Columns2, DoorClosed, Fingerprint, ImageUp, ListChecks, Quote, Search, ShieldCheck, TriangleAlert,
  Waypoints,
} from "lucide-react";
import { getJson } from "../api";
import { ar } from "../format";
import { RELATION_UI } from "../result/Result";
import { IMAGE_MODE_ENABLED } from "../features";
import { Disclosure, ICON } from "../components/ui";
import type { Relation } from "../types";

type Meth = {
  llm_is_a_source: boolean;
  counts: { by_source_type: Record<string, number> };
  versions: Record<string, string | null>;
  llm: { configured: boolean; provider: string | null; model: string | null };
};

const PIPELINE: { t: string; d: string; optional?: boolean }[] = [
  { t: "النص", d: IMAGE_MODE_ENABLED ? "تلصق الاقتباس والادعاء، أو تختار لقطة شاشة وتراجع النص المستخرج منها. لا يُحفظ ما تكتبه." : "تلصق الاقتباس والادعاء. لا يُحفظ ما تكتبه." },
  { t: "البحث", d: "بحث في القرآن الكريم أولًا، ثم في صحيحي البخاري ومسلم." },
  { t: "مطابقة المصدر", d: "مطابقة حرفية بعد توحيد الإملاء. لا يُنسب نص قريب غير مطابق." },
  { t: "استرجاع السياق", d: "الآية مع ما قبلها وما بعدها، أو الحديث كاملًا برقمه وكتابه وبابه." },
  { t: "بناء الأدلة", d: "كل نص دليل له معرّف (E1، E2…) ومصدره قاعدة المصادر." },
  { t: "التحليل", d: "يصنّف نموذج لغوي علاقة الادعاء بالأدلة، إن توفر وسمحت البوابة.", optional: true },
  { t: "التحقق من الإسناد", d: "تُرفض أي مخرجات تستشهد بما ليس في الأدلة." },
];

const CONCEPTS = [
  { icon: Search, t: "البحث النصي (BM25)", d: "طريقة ترتيب معروفة تقدّم النصوص التي تشترك مع الاقتباس في كلماته النادرة. تحدد المرشحين فقط، ولا تقرر النسبة." },
  { icon: Quote, t: "مطابقة المصدر", d: "لا يُنسب الاقتباس إلا إذا وُجد بلفظه كاملًا أو مقتطعًا. العبارة المتكررة في أكثر من موضع لا تُنسب إلى موضع بعينه." },
  { icon: ListChecks, t: "كائنات الأدلة", d: "كل آية أو حديث يُعرض دليلًا بمعرّف ونص وموضع، مقروء من قاعدة المصادر لا من النموذج." },
  { icon: DoorClosed, t: "بوابة الأدلة", d: "لا يُستدعى التحليل الآلي إلا إذا نُسب الاقتباس إلى آية بعينها ولم تكن المسألة حالة شخصية." },
  { icon: Fingerprint, t: "التحقق من الاستشهاد", d: "يُقبل من النموذج فقط ما يستشهد بمعرّفات الأدلة المعروضة، ولا نص ديني خارجها. أي إخفاق يُسقط المخرجات كلها." },
  { icon: CircleSlash, t: "الامتناع", d: "عند غياب المصدر أو قصور الأدلة يقول تِبيان «لا تكفي الأدلة»، ويحيل المسائل الشخصية والخلافية إلى مختص." },
];

const TOOLS = [
  { icon: Columns2, t: "مقارنة النص", d: "مقارنة آلية كلمةً بكلمة بين ما أدخلته والنص المعتمد: مطابق حرفيًا، أو اختلاف في التشكيل أو الترقيم فقط، أو كلمة مفقودة أو مختلفة. تبيّن الفرق ولا تحكم على سببه، ولا تُعدِّل النص المعتمد." },
  { icon: Waypoints, t: "خريطة الدليل والسياق", d: "ترسم الطريق من المصدر إلى النص المقتبس وسياقه ثم الأدلة ونتيجة الادعاء، من بيانات التقرير نفسه. «أهمية السياق للادعاء» تبقى «غير محدد» ما لم يستشهد تحليل آلي متحقَّق منه بالسياق." },
  ...(!IMAGE_MODE_ENABLED ? [] : [{ icon: ImageUp, t: "التحقق من صورة", d: "يُستخرج النص من لقطة الشاشة داخل متصفحك، ولا تُرفع الصورة ولا تُحفظ. تراجع النص المستخرج وتعدّله، ثم يمرّ بالتحقق نفسه. الصورة ليست دليلًا، وجودة الاستخراج لا تعني صحة النص." }]),
];

const STEPS: { t: string; d: string }[] = [
  { t: "التحقق من المدخلات", d: "يُقبل نص عربي محدود الطول، ولا يُحفظ ما يُدخَل." },
  { t: "البحث في القرآن الكريم أولًا", d: "بحث نصي (BM25) أولًا، يُساعده بحث متجهي بسيط على مستوى الحروف. البحث يحدد المرشحين فقط ولا يقرر النسبة." },
  { t: "ثم في الحديث", d: "إن لم يوجد الاقتباس بلفظه في القرآن، يُبحث في صحيحي البخاري ومسلم بفهرس مستقل. النص الموجود بلفظه في القرآن لا يُنسب إلى حديث أبدًا." },
  { t: "مطابقة الاقتباس", d: "مطابقة حتمية بعد توحيد الإملاء: كاملة أو جزئية، أو تعدد مواضع، أو غير موجود. لا يُنسب نص قريب غير مطابق." },
  { t: "قراءة المصدر والسياق", d: "يُقرأ النص من قاعدة المصادر مباشرة: الآية بالرسم العثماني مع آيتين قبلها وآيتين بعدها، والحديث كاملًا برقمه وكتابه وبابه، دون أحاديث مجاورة." },
  { t: "بناء الأدلة", d: "كل آية دليل له معرّف (E1، E2…) ونص من قاعدة المصادر، لا من النموذج." },
  { t: "تصنيف نوع المسألة", d: "تصنيف آلي بالكلمات المفتاحية: نصي مستقر، شرح، خلافي أو حساس، حالة شخصية." },
  { t: "بوابة الأدلة", d: "لا يُستدعى التحليل الآلي إلا إذا نُسب الاقتباس إلى آية أو آيات بعينها ولم تكن المسألة حالة شخصية. تحليل الادعاء على الأحاديث غير مفعّل بعد." },
  { t: "تحليل الادعاء (عند توفّر نموذج)", d: "يصنّف النموذج علاقة الادعاء بالأدلة المعروضة فقط، بصيغة منظَّمة صارمة." },
  { t: "التحقق من المخرجات", d: "فحص البنية، ثم صحة الاستشهادات، ثم الإسناد إلى نص الأدلة، ثم ضوابط اللغة. أي إخفاق يُسقط المخرجات كلها." },
  { t: "ضوابط النتيجة", d: "المسائل الخلافية لا يُقطع فيها، والحالات الشخصية تُحال إلى مختص." },
];

export default function Methodology() {
  const [m, setM] = useState<Meth | null | undefined>(undefined);
  useEffect(() => { getJson<Meth>("/api/v1/methodology").then(setM); }, []);

  return (
    <>
      <header className="page-head">
        <div className="container">
          <h1>المنهجية والحدود</h1>
          <p>كيف يصل تِبيان من نص ملصوق إلى مصدر وسياق وأدلة، ومتى يمتنع عن الحكم.</p>
          <div className="panel principle-statement" role="note">
            <ShieldCheck {...ICON} size={26} />
            <div>
              <h2>النموذج اللغوي ليس مصدرًا للمعلومة الشرعية.</h2>
              <p>
                كل نص ديني يعرضه تِبيان مقروء من قاعدة مصادر معتمدة موثّقة البصمة. دور النموذج، حين يتوفر، مقصور على
                تصنيف علاقة الادعاء بالأدلة المعروضة، ولا يُقبل منه أي نص أو نسبة لا توجد في تلك الأدلة.
              </p>
            </div>
          </div>
        </div>
      </header>

      <div className="page-body container">
        <section className="block" aria-labelledby="m-flow">
          <div className="block-head">
            <h2 id="m-flow">من النص إلى النتيجة</h2>
            <p>سبع مراحل بالترتيب. التحليل وحده اختياري، ولا يجري إلا بعد ثبوت المصدر.</p>
          </div>
          <ol className="pipeline block-body">
            {PIPELINE.map((s) => (
              <li key={s.t} data-optional={s.optional ? "true" : undefined}>
                <div><h3>{s.t}</h3><p>{s.d}</p></div>
              </li>
            ))}
          </ol>
        </section>

        <section className="block" aria-labelledby="m-concepts">
          <div className="block-head">
            <h2 id="m-concepts">المفاهيم الأساسية</h2>
            <p>ستة أفكار تكفي لفهم ما يعرضه تقرير التحقق.</p>
          </div>
          <ul className="concepts block-body">
            {CONCEPTS.map((c) => (
              <li key={c.t}><c.icon {...ICON} size={22} /><div><h3>{c.t}</h3><p>{c.d}</p></div></li>
            ))}
          </ul>
        </section>

        <section className="block" aria-labelledby="m-tools">
          <div className="block-head">
            <h2 id="m-tools">أدوات العرض والإدخال</h2>
            <p>تُبنى بعد قرارات التحقق ولا تغيّر شيئًا منها.</p>
          </div>
          <ul className="tools-list block-body">
            {TOOLS.map((c) => (
              <li key={c.t}><c.icon {...ICON} size={22} /><div><h3>{c.t}</h3><p>{c.d}</p></div></li>
            ))}
          </ul>
        </section>

        <section className="block" aria-labelledby="m-rel">
          <div className="block-head">
            <h2 id="m-rel">تصنيفات علاقة الادعاء</h2>
            <p>تظهر فقط حين يحلّل نموذج حقيقي الادعاء وتجتاز مخرجاته التحقق.</p>
          </div>
          <ul className="rel-list block-body">
            {(Object.keys(RELATION_UI) as Relation[]).map((k) => {
              const u = RELATION_UI[k];
              return (
                <li key={k} className={`tone-${u.tone}`}>
                  <span style={{ display: "inline-flex", gap: "var(--s-2)", alignItems: "center" }}>
                    <u.icon {...ICON} style={{ color: "var(--tone)" }} /><strong>{u.title}</strong>
                    <span className="muted small">{u.line}</span>
                  </span>
                  <span className="latin" dir="ltr">{k}</span>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="block" aria-labelledby="m-llm">
          <div className="block-head"><h2 id="m-llm">حالة التحليل الآلي</h2></div>
          <div className="block-body">
            {m === undefined && <p role="status" className="muted">جارٍ التحميل…</p>}
            {m === null && <p className="muted">تعذّر تحميل حالة التحليل من الخادم.</p>}
            {m && (
              <p data-llm-configured={String(m.llm.configured)} data-analysis-types="quran">
                {m.llm.configured
                  ? `مفعّل (${m.llm.provider} / ${m.llm.model}) لنتائج القرآن الكريم. لم يُتحقَّق من جودته على حالات راجعها مختص بعد.`
                  : "تحليل الادعاء بالذكاء الاصطناعي غير متاح حالياً. يعرض تِبيان المصدر والنص والسياق الموثّقة فقط، دون حكم على الادعاء."}
              </p>
            )}
          </div>
        </section>

        <section className="block" aria-labelledby="m-lim" id="limits" tabIndex={-1}>
          <div className="block-head">
            <h2 id="m-lim">حدود النظام</h2>
            <p>ما لا يفعله تِبيان، مكتوبًا بوضوح.</p>
          </div>
          <ul className="limits block-body" style={{ fontSize: "var(--t-base)" }}>
            <li>تِبيان أداة تحقق، وليس مفتيًا ولا بديلًا عن العالم المختص.</li>
            <li>المصادر الحالية: القرآن الكريم برواية حفص، وأحاديث صحيحي البخاري ومسلم (روايات من صحيح مسلم غير مرقّمة في الملف تُنسب بالكتاب والباب دون رقم). عدم العثور على نص لا يعني أنه غير موجود في مصدر آخر.</li>
            <li>درجة الحديث مأخوذة من قاعدة الحزمة العلمية «الأحاديث الصحيحة من الصحيحين»، ولا يولّد تِبيان ولا النموذج اللغوي أي حكم على حديث.</li>
            <li>لا يُنسب اقتباس إلا عند المطابقة الحرفية الكاملة أو الجزئية؛ الاقتباس المنقول بتصرّف يُعرض معه أقرب النصوص دون نسبة.</li>
            <li>العبارات المتكررة في المصحف لا تُنسب إلى موضع بعينه.</li>
            <li>السياق المعروض هو الآيات المجاورة في السورة نفسها، وليس السياق العلمي الكامل (أسباب النزول، الناسخ والمنسوخ، أقوال المفسرين).</li>
            <li>تصنيف نوع المسألة يعتمد على كلمات مفتاحية، وقد يخطئ.</li>
            <li>تصنيفات علاقة الادعاء لم تُقَيَّم على حالات راجعها مختص مؤهل، ولم يُقَس أداء التحليل بنموذج لغوي حقيقي قياسًا منهجيًا بعد.</li>
            <li>البحث المتجهي تقنية بسيطة على مستوى الحروف، وليس نموذجًا لغويًا عصبيًا، ولا يفهم المعنى.</li>
            {IMAGE_MODE_ENABLED && <li>استخراج النص من الصور قد يخطئ، خاصة مع الخطوط الزخرفية والنص المشكول بالرسم العثماني والصور غير الواضحة؛ لذلك لا يُتحقَّق إلا من النص الذي تراجعه وتؤكده.</li>}
            <li>مقارنة النص آلية على مستوى الكلمات، تذكر ما اختلف ولا تفسّر سببه.</li>
          </ul>
        </section>

        <section className="block" aria-labelledby="m-tech">
          <div className="block-head">
            <h2 id="m-tech">للمحكّمين والمختصين</h2>
            <p>الخطوات الكاملة وأرقام الإصدارات.</p>
          </div>
          <div className="block-body">
            <Disclosure summary="تفاصيل تقنية">
              <ol className="steps-full">
                {STEPS.map((s) => <li key={s.t}><strong>{s.t}.</strong> {s.d}</li>)}
              </ol>
              {m && (
                <>
                  <p className="small" style={{ marginTop: "var(--s-5)" }}>
                    حجم القاعدة: {ar(m.counts.by_source_type.quran ?? 0)} آية، و{ar(m.counts.by_source_type.hadith ?? 0)} سجل حديث.
                  </p>
                  <p className="meta-line" dir="ltr" style={{ marginTop: "var(--s-3)" }}>
                    {Object.entries(m.versions).map(([k, v]) => `${k} ${v ?? "—"}`).join(" / ")}
                  </p>
                </>
              )}
              <p className="small muted" style={{ marginTop: "var(--s-3)", display: "flex", gap: "var(--s-2)", alignItems: "center" }}>
                <BookOpen {...ICON} size={15} />بصمات الملفات ومسار كل مصدر في صفحة المصادر.
              </p>
            </Disclosure>
          </div>
        </section>

        <p className="small muted" style={{ marginTop: "var(--s-12)", display: "flex", gap: "var(--s-2)", alignItems: "center" }}>
          <TriangleAlert {...ICON} size={15} />لا يصدر تِبيان فتاوى شخصية.
        </p>
      </div>
    </>
  );
}
