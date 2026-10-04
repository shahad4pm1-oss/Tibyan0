import { useEffect, useState } from "react";
import { BookOpen, BookText, CircleAlert, Clock, ScrollText, type LucideIcon } from "lucide-react";
import { getJson } from "../api";
import { ar } from "../format";
import { Badge, ICON, InfoCallout } from "../components/ui";
import { useHealth } from "../health";

type Src = {
  id: string; source_type: string; title: string; author: string | null; edition: string; publisher: string | null;
  source_url: string | null; verification_status: string; license_note: string; provenance: string | null;
  package_sha256: string | null; file_sha256: string | null; gaps: number | null;
};
type Meth = { sources: Src[]; counts: { by_source_type: Record<string, number>; tafsir_ayahs?: number } };

/* Plain-language description of each integrated source. Facts mirror docs/OFFICIAL_SOURCE_INVENTORY.md. */
const ACTIVE: Record<string, {
  name: string; icon: LucideIcon; type: string; status: { label: string; tone: "success" | "warning" };
  provenance: string; limits: string;
}> = {
  quran: {
    name: "القرآن الكريم", icon: BookOpen, type: "نص قرآني", status: { label: "يعمل", tone: "success" },
    provenance: "ملف مصحف المدينة النبوية من مجمع الملك فهد (الإصدار ٢٫٠)، نُقل عبر مستودع قرآنبيديا وطابقت بصمته ملف المجمع بايتًا ببايت.",
    limits: "رواية حفص عن عاصم فقط. السياق المعروض آيات مجاورة من السورة نفسها، ويُعرض التفسير منفصلًا عن النص القرآني.",
  },
  "hadith:bukhari": {
    name: "صحيح البخاري", icon: ScrollText, type: "حديث نبوي", status: { label: "تشغيل محدود", tone: "warning" },
    provenance: "المصدر العلمي معتمد في الحزمة العلمية للتحدي. مسار البيانات: ملف OpenITI المأخوذ من المكتبة الشاملة (CC BY-NC-SA 4.0).",
    limits: "لم يُقابَل النص بالشاملة أو الدرر بعد، وحقوق الطبعة المطبوعة قيد التحقق. بعض الأرقام ليست مدخلات مستقلة في الملف.",
  },
  "hadith:muslim": {
    name: "صحيح مسلم", icon: ScrollText, type: "حديث نبوي", status: { label: "تشغيل محدود", tone: "warning" },
    provenance: "المصدر العلمي معتمد في الحزمة العلمية للتحدي. مسار البيانات: ملف OpenITI المأخوذ من المكتبة الشاملة (CC BY-NC-SA 4.0).",
    limits: "روايات لا يرقّمها الملف تُنسب بالكتاب والباب دون رقم، ولم يُخترع أي رقم. المقابلة بالشاملة والدرر لم تُجرَ بعد.",
  },
  "tafsir:tabari-15": {
    name: "تفسير الطبري", icon: BookText, type: "تفسير (مادة شارحة)", status: { label: "يعمل", tone: "success" },
    provenance: "يُجلب تفسير الآية المطابقة عند الطلب من واجهة Quran.com (الإصدار ٤)، ولا يُخزَّن في قاعدة المصادر.",
    limits: "يُعرض منفصلًا عن النص القرآني تحت عنوان «تفسير الآية»، ولا يُبحث فيه ولا يُنسب إليه اقتباس. إن تعذّر الوصول إلى الواجهة استُخدم تفسير مجاهد المحلي.",
  },
  "tafsir:269": {
    name: "تفسير مجاهد", icon: BookText, type: "تفسير (مادة شارحة)", status: { label: "يعمل", tone: "success" },
    provenance: "ملفات محلية لكل سورة (data/json-data) مأخوذة من نسخة موقع قرآنبيديا (الإصدار ٢٠٢٦-٠٨-١٠)، تحقيق محمد عبد السلام أبو النيل.",
    limits: "يُعرض منفصلًا عن النص القرآني تحت عنوان «تفسير الآية»، ولا يُعدّ نصًّا قرآنيًا. لا توجد مادة للفاتحة والكافرون، ولبعض الآيات، ولا يُبحث فيه ولا يُنسب إليه اقتباس.",
  },
};

const PENDING: { name: string; source: string; status: string; why: string }[] = [
  { name: "موسوعة التفسير", source: "موسوعة التفسير، الدرر السنية", status: "تعذّر الوصول",
    why: "لم توجد واجهة أو ملفات بيانات. المتاح حاليًا تفسير الطبري وتفسير مجاهد (انظر «متاح الآن»)، وبقية كتب التفسير تحتاج اختيارًا علميًا ومحاذاة موثّقة بالآيات." },
  { name: "العقيدة", source: "الموسوعة العقدية، الدرر السنية", status: "تعذّر الوصول", why: "لا واجهة ولا ملفات بيانات، وشروط إعادة الاستخدام غير موثّقة." },
  { name: "الفقه", source: "الموسوعة الفقهية، الدرر السنية", status: "تعذّر الوصول", why: "لا واجهة ولا ملفات بيانات. اختيار كتب المذاهب قرار يعود إلى المختص." },
  { name: "السيرة والتاريخ", source: "موسوعة التاريخ، الدرر السنية", status: "تعذّر الوصول", why: "لا واجهة ولا ملفات بيانات، وشروط إعادة الاستخدام غير موثّقة." },
  { name: "بيّنات", source: "أسئلة وأجوبة عن الإسلام، مركز أصول", status: "بانتظار الملف والإذن",
    why: "ملف PDF «جميع الحقوق محفوظة» وموقعه غير متاح لبيئة البناء. يمكن إضافته إذا وُفّر الملف وأُكّد جواز استعماله داخل التطبيق." },
  { name: "الجمهرة", source: "معجم المصطلحات، موسوعة الجمهرة", status: "شروط الاستخدام",
    why: "الاستعمال مقصور على الاستخدام الشخصي غير التجاري، ولا توجد واجهة أو ملفات تصدير، فلم يُستورد آليًا." },
  { name: "التحقق الحديثي", source: "الموسوعة الحديثية، الدرر السنية", status: "تعذّر الوصول",
    why: "واجهة بحث لا مجموعة بيانات، وتعذّر اختبارها من بيئة البناء، فلم يُبنَ محوّل لها." },
];

export default function Sources() {
  const health = useHealth();
  const [m, setM] = useState<Meth | null | undefined>(undefined);
  useEffect(() => { getJson<Meth>("/api/v1/methodology").then(setM); }, []);
  const byCol = health?.components.hadith_corpus?.by_collection ?? {};
  const count = (id: string) => id === "quran" ? `${ar(m?.counts.by_source_type.quran ?? 0)} آية`
    : id.startsWith("hadith:") ? `${ar(byCol[id] ?? 0)} سجل حديث`
    : id === "tafsir:tabari-15" ? "يُجلب عند الطلب لكل آية"
    : id.startsWith("tafsir:") ? `${ar(m?.counts.tafsir_ayahs ?? 0)} آية لها تفسير`
    : "—";

  return (
    <>
      <header className="page-head">
        <div className="container">
          <h1>المصادر</h1>
          <p>
            كل نص يعرضه تِبيان يأتي من مصدر في هذه الصفحة، ببصمة ملف مثبتة. ما لم يُضَف بعدُ مذكور مع سببه، ولا يُعرض منه شيء.
          </p>
        </div>
      </header>

      <div className="page-body container">
        <section className="block" aria-labelledby="s-now">
          <div className="block-head">
            <h2 id="s-now">متاح الآن</h2>
            <p>المصادر التي يبحث فيها تِبيان ويُنسب إليها الاقتباس.</p>
          </div>
          <div className="block-body">
            {m === undefined && <p role="status" className="muted">جارٍ التحميل…</p>}
            {m === null && (
              <InfoCallout tone="error" icon={CircleAlert} role="alert" title="تعذّر تحميل بيانات المصادر من الخادم.">
                <p>تحقّق من تشغيل الخادم ثم أعد تحميل الصفحة.</p>
              </InfoCallout>
            )}
            {m && (
              <ul className="src-grid">
                {m.sources.map((s) => {
                  const a = ACTIVE[s.id];
                  const Icon = a?.icon ?? BookText;
                  const hash = s.package_sha256 ?? s.file_sha256;
                  return (
                    <li key={s.id} className="src-card" data-source-id={s.id}>
                      <div className="src-card-head">
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--s-2)" }}>
                          <Icon {...ICON} size={22} style={{ color: "var(--c-primary-text)" }} />
                          <h3>{a?.name ?? s.title}</h3>
                        </span>
                        {a && <Badge tone={a.status.tone}>{a.status.label}</Badge>}
                      </div>
                      <dl className="kv">
                        <div><dt>النوع</dt><dd>{a?.type ?? s.source_type}</dd></div>
                        <div><dt>الحجم</dt><dd className="num">{count(s.id)}</dd></div>
                        <div><dt>العنوان</dt><dd>{s.title}</dd></div>
                        {s.author && <div><dt>المؤلف</dt><dd>{s.author}</dd></div>}
                        <div><dt>الطبعة</dt><dd>{s.edition}</dd></div>
                        {a && <div><dt>مسار البيانات</dt><dd>{a.provenance}</dd></div>}
                        {a && <div><dt>الحدود</dt><dd>{a.limits}</dd></div>}
                      </dl>
                      {hash && <p className="hash" dir="ltr">SHA-256 {hash}</p>}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </section>

        <section className="block" aria-labelledby="s-next">
          <div className="block-head">
            <h2 id="s-next">قيد الإضافة أو التحقق</h2>
            <p>
              مصادر رسمية في الحزمة العلمية لم تُدمج بعد. لا يبحث فيها تِبيان ولا يُنسب إليها شيء، ولم يُكتب شيء من محتواها من
              ذاكرة نموذج.
            </p>
          </div>
          <ul className="blocked-list block-body">
            {PENDING.map((p) => (
              <li key={p.name} data-pending-source={p.name}>
                <span>
                  <strong>{p.name}</strong>
                  <span className="small muted" style={{ display: "block" }}>{p.source}</span>
                </span>
                <span><Badge icon={Clock} outline>{p.status}</Badge></span>
                <p>{p.why}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
