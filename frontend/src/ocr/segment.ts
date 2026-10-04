/* Finds the quote(s) and a suggested claim in text extracted from a screenshot. Deterministic text rules only - no
   model, no lookup, no religious judgement. Its output is a SUGGESTION shown to the visitor, who must review and edit
   it before anything is verified. It never decides what the text is or where it comes from.

   Quote candidates, in order of appearance:
     1. text between quotation marks or Quran brackets:  «…»  “…”  "…"  ﴿…﴾  ((…))   (either orientation)
     2. text after an attribution formula, to the end of its paragraph:
          قال الله تعالى / قال تعالى / قوله تعالى / قال رسول الله ﷺ / قال النبي ﷺ …
     3. otherwise, all the Arabic text as one candidate.
   Attribution suffixes (رواه البخاري، [البقرة: ١٩١] …), verse numbers and the isti'adha are removed from candidates.
   The suggested claim is whatever Arabic text remains outside the quote(s). */

export type Marker = "quotation_marks" | "quran_brackets" | "parentheses" | "formula" | "whole_text";
export type Candidate = { quote: string; marker: Marker };
export type Segmentation = { text: string; candidates: Candidate[]; claim: string };

export const MAX_CANDIDATES = 5;
const MAX_LEN = 2000;

const AR_LETTER = /[ء-غف-يٱ-ۓ]/g;
const AR_WORD = /[ء-غف-يٱ-ۓ][ء-ْٰ-ۓۥۦـ]*/g;
export const arabicLetters = (s: string) => (s.match(AR_LETTER) ?? []).length;
export const arabicWords = (s: string) => (s.match(AR_WORD) ?? []).length;

const SPANS: { re: RegExp; marker: Marker }[] = [
  { re: /[﴿﴾]([^﴿﴾]{2,1500})[﴿﴾]/g, marker: "quran_brackets" },
  { re: /[«»]([^«»]{2,1500})[«»]/g, marker: "quotation_marks" },
  { re: /[“”]([^“”]{2,1500})[“”]/g, marker: "quotation_marks" },
  { re: /"([^"]{2,1500})"/g, marker: "quotation_marks" },
  { re: /\(\(([^()]{2,1500})\)\)/g, marker: "quotation_marks" },
  // OCR often reads the ornate Quran brackets as plain parentheses; references in parentheses are excluded below
  { re: /\(([^()]{2,1500})\)/g, marker: "parentheses" },
];
const REFERENCE = /^\s*(?:رواه|أخرجه|اخرجه|متفق عليه|صحيح|سورة|الآية|الاية|آية|[0-9٠-٩]|[\u0621-\u064a]{2,12}\s*[:،,]\s*[0-9٠-٩])|^\s*(?:صلى الله|رضي الله|عليه السلام|عليه الصلاة|رحمه الله|رحمهم الله|عز وجل|جل جلاله|سبحانه|تعالى)/;

const HONORIFIC = "(?:\\s*(?:ﷺ|صلى الله عليه وسلم|صلى الله عليه وآله وسلم|عليه الصلاة والسلام|عليه السلام))?";
const FORMULA = new RegExp(
  "(?:(?:و|ف)?(?:قال|يقول|لقوله|قوله|كقوله)\\s+(?:الله\\s+)?(?:تعالى|تبارك وتعالى|عز وجل|جل وعلا|سبحانه(?:\\s+وتعالى)?)" +
  "|(?:و|ف)?(?:قال|يقول|لقول|قول)\\s+(?:رسول الله|النبي|الرسول)" + HONORIFIC + ")\\s*[:：]?\\s*",
  "g",
);

const ATTRIBUTION = [
  /[(\[]\s*(?:رواه|أخرجه|اخرجه|متفق عليه|صحيح البخاري|صحيح مسلم|البخاري|مسلم)[^)\]]*[)\]]/g,
  /[-–—،.]?\s*(?:رواه|أخرجه|اخرجه)\s+(?:الإمام\s+|الامام\s+)?(?:البخاري|مسلم|الشيخان)[^.\n]*$/g,
  /[-–—،.]?\s*متفق عليه\.?/g,
  /[(\[]\s*(?:سورة\s+)?[ء-ي ]{2,24}\s*[:،,\-–]?\s*(?:الآية|الاية|آية|اية)?\s*[0-9٠-٩]{1,3}\s*[)\]]/g,
  /[(\[]\s*[0-9٠-٩]{1,3}\s*[)\]]/g,
  /۝\s*[0-9٠-٩]{0,3}/g,
  /صدق الله العظيم/g,
  /^\s*(?:أعوذ|اعوذ) بالله من الشيطان الرجيم\s*/g,
];

/** OCR output with consistent whitespace; paragraph breaks kept, lines inside a paragraph joined. */
export function cleanText(raw: string): string {
  return raw
    .replace(/\r/g, "")
    .replace(/[ \t ​‌‍]+/g, " ")
    .split(/\n\s*\n/)
    .map((p) => p.split("\n").map((l) => l.trim()).filter(Boolean).join(" "))
    .filter(Boolean)
    .join("\n");
}

function tidy(s: string): string {
  let t = s;
  for (const re of ATTRIBUTION) t = t.replace(re, " ");
  t = t.replace(/(^|\s)[0-9٠-٩]{1,3}(?=\s|$)/g, " ");                    // stray verse numbers
  t = t.replace(/\s+/g, " ").trim();
  t = t.replace(/^[\s.,،:؛;!؟?\-–—*•|«»"“”﴿﴾()[\]]+/, "").replace(/[\s.,،:؛;\-–—*•|«»"“”﴿﴾()[\]]+$/, "");
  return t.slice(0, MAX_LEN).trim();
}

const key = (s: string) => s.replace(/[ً-ْٰـ]/g, "").replace(/[^ء-ي]+/g, " ").trim();

type Hit = { start: number; end: number; quote: string; marker: Marker };

function spanHits(text: string): Hit[] {
  const hits: Hit[] = [];
  for (const { re, marker } of SPANS) {
    re.lastIndex = 0;
    for (let m = re.exec(text); m; m = re.exec(text)) {
      const start = m.index, end = m.index + m[0].length;
      if (hits.some((h) => start < h.end && end > h.start)) continue;    // already inside an earlier span
      if (marker === "parentheses" && (REFERENCE.test(m[1]) || arabicWords(m[1]) < 3)) continue;
      hits.push({ start, end, quote: tidy(m[1]), marker });
    }
  }
  return hits;
}

function formulaHits(text: string, taken: Hit[]): Hit[] {
  const hits: Hit[] = [];
  FORMULA.lastIndex = 0;
  for (let m = FORMULA.exec(text); m; m = FORMULA.exec(text)) {
    const start = m.index, bodyStart = m.index + m[0].length;
    if (taken.some((h) => start >= h.start && start < h.end)) continue;
    if (taken.some((h) => h.start >= start && h.start <= bodyStart + 2)) continue;   // formula introduces a quoted span
    const lineEnd = text.indexOf("\n", bodyStart);
    let end = lineEnd === -1 ? text.length : lineEnd;
    const next = taken.find((h) => h.start > bodyStart && h.start < end);
    if (next) end = next.start;
    hits.push({ start, end, quote: tidy(text.slice(bodyStart, end)), marker: "formula" });
  }
  return hits;
}

const CONNECTORS = /(?:\s|^)(?:بدليل|والدليل|ودليله|ودليل ذلك|لقوله|كقوله|كما في|كما قال|حيث قال|قال|يقول|في قوله|قوله)\s*$/;

function suggestClaim(text: string, hits: Hit[]): string {
  let rest = "";
  let at = 0;
  for (const h of [...hits].sort((a, b) => a.start - b.start)) {
    rest += text.slice(at, h.start) + "\n";
    at = Math.max(at, h.end);
  }
  rest += text.slice(at);
  const lines = rest.split("\n")
    .map((l) => l.replace(FORMULA, " "))
    .map((l) => l.replace(/https?:\/\/\S+|www\.\S+|@\w+|#/g, " "))
    .map((l) => tidy(l))
    .filter((l) => arabicWords(l) >= 2);
  const toks = lines.join(" ").split(/\s+/).filter(Boolean);
  while (toks.length && !arabicLetters(toks[0])) toks.shift();            // names, handles, times, counters
  while (toks.length && !arabicLetters(toks[toks.length - 1])) toks.pop();
  let claim = toks.join(" ");
  for (let i = 0; i < 3 && CONNECTORS.test(claim); i++) claim = claim.replace(CONNECTORS, "").trim();
  claim = claim.replace(/[\s:،,\-–—]+$/, "");
  return arabicWords(claim) >= 3 ? claim.slice(0, MAX_LEN) : "";
}

export function segment(raw: string): Segmentation {
  const text = cleanText(raw);
  const spans = spanHits(text);
  const formulas = formulaHits(text, spans);
  const hits = [...spans, ...formulas]
    .sort((a, b) => a.start - b.start)
    .filter((h) => arabicWords(h.quote) >= 2);

  const seen = new Set<string>();
  const candidates: Candidate[] = [];
  for (const h of hits) {
    const k = key(h.quote);
    if (!k || seen.has(k)) continue;
    seen.add(k);
    candidates.push({ quote: h.quote, marker: h.marker });
    if (candidates.length === MAX_CANDIDATES) break;
  }
  if (!candidates.length) {
    const whole = tidy(text.split("\n").filter((l) => arabicWords(l) >= 1).join(" "));
    return { text, candidates: arabicWords(whole) >= 1 ? [{ quote: whole, marker: "whole_text" }] : [], claim: "" };
  }
  return { text, candidates, claim: suggestClaim(text, hits) };
}
