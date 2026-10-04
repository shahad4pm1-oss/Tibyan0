import type { MatchStatus, Relation, SourceType, TextUnit } from "./types";

const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";
export const ar = (n: number | string) => String(n).replace(/\d/g, (d) => AR_DIGITS[Number(d)]);

export const SOURCE_TYPE: Record<string, string> = {
  quran: "القرآن الكريم",
  hadith: "الحديث النبوي",
  tafsir: "التفسير",
  aqeedah: "العقيدة",
  fiqh: "الفقه",
  seerah: "السيرة والتاريخ",
  history: "السيرة والتاريخ",
  dawah: "المحتوى الدعوي",
  shubuhat: "الأسئلة والشبهات",
  dictionary: "المصطلحات",
};
export const sourceTypeLabel = (t?: SourceType | null) => (t && SOURCE_TYPE[t]) || "مصدر";

export function hadithRef(u: TextUnit): string {
  const m = u.metadata;
  if (m.hadith_number == null || m.hadith_number === "") {
    // unnumbered in the source file: cite by book and chapter, never by an invented number
    return `${m.collection_ar ?? "حديث"}، ${m.book ?? ""}، ${m.chapter ?? ""} (رواية غير مرقّمة في الملف المصدر)`;
  }
  const nums = (m.numbers_covered && m.numbers_covered.length > 1 ? m.numbers_covered : [m.hadith_number ?? u.reference])
    .map((n) => ar(n as number | string)).join("، ");
  return `${m.collection_ar ?? "حديث"}، رقم ${nums}`;
}

/** Reference for any unit: Quran -> surah/ayah; hadith -> collection/number. */
export function unitRef(units: TextUnit[]): string {
  if (!units.length) return "";
  if (units[0].source_type === "hadith" || units[0].metadata.collection_ar) return hadithRef(units[0]);
  return quranRef(units);
}

export function quranRef(units: TextUnit[]): string {
  if (!units.length) return "";
  const first = units[0].metadata;
  const last = units[units.length - 1].metadata;
  const surah = first.surah_name ? `سورة ${first.surah_name}` : "";
  if (units.length === 1) return `${surah}، الآية ${ar(first.ayah_number ?? "")}`;
  return `${surah}، الآيات ${ar(first.ayah_number ?? "")}–${ar(last.ayah_number ?? "")}`;
}

/** Display-only clean-up of imported tafsir text: drops print page markers ("&; 3-565 &;"), "* * *" separator
 *  lines and stray HTML entities. The wording itself is never changed; the copy action keeps the stored text. */
export function cleanTafsir(text: string): string {
  return text
    .replace(/&(?:amp;)*;\s*[\d٠-٩]+\s*[-–]\s*[\d٠-٩]+\s*&(?:amp;)*;/g, " ")
    .replace(/^[ \t]*\*(?:[ \t]*\*)+[ \t]*$/gm, "")
    .replace(/&amp;/g, "&")
    .replace(/[ \t]{2,}/g, " ")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** First part of a long text, cut at a paragraph or word boundary (never mid-word). */
export function clipText(text: string, max: number): string {
  if (text.length <= max) return text;
  const head = text.slice(0, max);
  const para = head.lastIndexOf("\n");
  const cut = para > max * 0.6 ? para : head.lastIndexOf(" ");
  return head.slice(0, cut > 0 ? cut : max).trimEnd();
}

export const STATUS: Record<MatchStatus, { title: string; tone: "ok" | "warn" | "none" }> = {
  EXACT: { title: "النص موجود بلفظه في المصدر", tone: "ok" },
  PARTIAL: { title: "النص مقتطع من نص أطول في المصدر", tone: "ok" },
  PARAPHRASED: { title: "النص قريب من نص في المصدر لكنه لا يطابقه حرفيًا", tone: "warn" },
  AMBIGUOUS: { title: "النص يطابق أكثر من موضع في المصدر", tone: "warn" },
  NOT_FOUND: { title: "لم يُعثر على النص في المصادر المتاحة", tone: "none" },
};

export const ROLE: Record<string, string> = {
  matched_source: "النص المطابق",
  hadith_evidence: "نص الحديث",
  preceding_context: "سياق سابق",
  following_context: "سياق لاحق",
  source_commentary: "مادة شارحة",
  metadata: "بيانات المصدر",
};

export const RELATION: Record<Relation, { title: string; tone: "ok" | "warn" | "none" | "neutral" | "refer" }> = {
  SUPPORTED: { title: "الادعاء متسق مع النص في سياقه", tone: "ok" },
  OVERSTATED: { title: "الادعاء أوسع مما يدل عليه النص", tone: "warn" },
  CONTRADICTED: { title: "السياق يخالف الادعاء", tone: "none" },
  INSUFFICIENT_EVIDENCE: { title: "لا تكفي الأدلة المتاحة للحكم", tone: "neutral" },
  REQUIRES_SPECIALIST: { title: "يحتاج إلى مراجعة مختص", tone: "refer" },
};

export const STRENGTH: Record<string, { title: string; detail: string }> = {
  SUFFICIENT: { title: "كافٍ", detail: "الاقتباس مطابق لنص المصدر، والنص وسياقه متاحان من قاعدة المصادر المعتمدة." },
  LIMITED: { title: "محدود", detail: "الاقتباس مطابق لنص المصدر لكنه مقطع قصير، فالأدلة أضيق من أن تحسم ادعاءً واسعًا." },
  INSUFFICIENT: { title: "غير كافٍ", detail: "لم يُنسب الاقتباس إلى موضع بعينه في المصادر المعتمدة." },
};

export const LEVEL: Record<string, string> = {
  A: "معلومة نصية مستقرة",
  B: "شرح واستدلال",
  C: "مسألة خلافية أو حساسة",
  D: "حالة شخصية تحتاج إلى فتوى",
};

export const OVERRIDE: Record<string, string> = {
  VERDICT_RECONCILED:
    "عُدِّل الحكم العام ليتوافق مع أحكام أجزاء الادعاء كما صنّفها التحليل نفسه.",
  LEVEL_C_SCOPED_TO_TEXT:
    "تتعلق المسألة بأمر خلافي أو حساس، فاقتصر التحليل على ما يقوله النص وسياقه، دون إصدار حكم أو فتوى؛ ويُرجى عرض المسألة على مختص.",
  LEVEL_C_CERTAINTY_RESTRICTED:
    "قُيِّدت النتيجة لأن الادعاء يتعلق بمسألة خلافية أو حساسة، فلا يقطع فيها تبيان مهما كانت مخرجات التحليل الآلي.",
};

export const WARNING: Record<string, string> = {
  HADITH_LIMITED_PRODUCTION:
    "البحث في الحديث في مرحلة تشغيل محدودة: لم يُقابَل نص الملفات بالمكتبة الشاملة أو الدرر بعد، وحقوق الطبعة المطبوعة قيد التحقق، وقيس الاسترجاع على حالات مولَّدة لا على اقتباسات مستخدمين حقيقية. لا يُنسب إلا ما طابق بلفظه.",
  SEMANTIC_SEARCH_UNAVAILABLE:
    "البحث الدلالي غير متاح حاليًا، فاستُخدم البحث النصي وحده. لا يتأثر بذلك التحقق من المطابقة الحرفية.",
};
