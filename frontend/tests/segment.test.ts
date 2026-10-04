/* Unit tests for the screenshot text segmentation (src/ocr/segment.ts). Run: npm run test:unit
   Religious text comes from src/examples.json (generated from the verified corpus); nothing is typed from memory. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { cleanText, segment, MAX_CANDIDATES } from "../src/ocr/segment.ts";

const ex = Object.fromEntries(
  (JSON.parse(readFileSync(new URL("../src/examples.json", import.meta.url), "utf8")).examples as { id: string; quote: string; claim: string }[])
    .map((e) => [e.id, e]),
);
const HADITH = ex.hadith.quote;            // a hadith fragment
const PARTIAL = ex.partial.quote;          // a Quran fragment (imla'i)
const EXACT = ex.exact.quote;              // a whole verse (imla'i)

test("quote in guillemets with the claim around it", () => {
  const s = segment(`يقول بعضهم إن هذا النص يدل على قبول كل عمل\n«${HADITH}» رواه البخاري`);
  assert.deepEqual(s.candidates, [{ quote: HADITH, marker: "quotation_marks" }]);
  assert.equal(s.claim, "يقول بعضهم إن هذا النص يدل على قبول كل عمل");
});

test("Quran brackets in either orientation; reference and verse number removed", () => {
  for (const [o, c] of [["﴿", "﴾"], ["﴾", "﴿"]]) {
    const s = segment(`${o}${PARTIAL} (١٩١)${c} [البقرة: ١٩١]`);
    assert.equal(s.candidates.length, 1);
    assert.equal(s.candidates[0].quote, PARTIAL);
    assert.equal(s.candidates[0].marker, "quran_brackets");
    assert.equal(s.claim, "");
  }
});

test("text after an attribution formula, without quotation marks", () => {
  const s = segment(`الإسلام يأمر بالقتال دائما بدليل قوله تعالى: ${PARTIAL}`);
  assert.deepEqual(s.candidates, [{ quote: PARTIAL, marker: "formula" }]);
  assert.equal(s.claim, "الإسلام يأمر بالقتال دائما");
});

test("a formula that introduces a quoted span gives one candidate, not two", () => {
  const s = segment(`قال رسول الله ﷺ: «${HADITH}»`);
  assert.equal(s.candidates.length, 1);
  assert.equal(s.candidates[0].quote, HADITH);
  assert.equal(s.claim, "");
});

test("several quotes are all offered, in reading order, without duplicates", () => {
  const s = segment(`«${EXACT}»\nثم «${PARTIAL}»\nو«${HADITH}»\nو«${EXACT}»`);
  assert.deepEqual(s.candidates.map((c) => c.quote), [EXACT, PARTIAL, HADITH]);
});

test("never more than the candidate limit", () => {
  const many = Array.from({ length: 9 }, (_, i) => `«${EXACT} ${"و".repeat(i + 1)}كلمة»`).join("\n");
  assert.equal(segment(many).candidates.length, MAX_CANDIDATES);
});

test("lines of one paragraph are joined; paragraphs stay apart", () => {
  const words = HADITH.split(" ");
  const raw = `«${words.slice(0, 2).join(" ")}\n${words.slice(2).join(" ")}»\n\nفقرة أخرى هنا`;
  assert.equal(cleanText(raw), `«${HADITH}»\nفقرة أخرى هنا`);
  assert.equal(segment(raw).candidates[0].quote, HADITH);
});

test("no markers: all Arabic text is one candidate and no claim is invented", () => {
  const s = segment(`${EXACT}\n\n@someone · 2h`);
  assert.deepEqual(s.candidates, [{ quote: EXACT, marker: "whole_text" }]);
  assert.equal(s.claim, "");
});

test("social-media noise is not part of the suggested claim", () => {
  const s = segment(`Ali @ali_99 · 3h\nهذا الحديث يعني أن النية تكفي وحدها https://t.co/x\n«${HADITH}»\n12 Retweets 40 Likes`);
  assert.equal(s.claim, "هذا الحديث يعني أن النية تكفي وحدها");
});

test("no Arabic text: no candidates", () => {
  assert.deepEqual(segment("").candidates, []);
  assert.deepEqual(segment("Hello world 123\n\n---").candidates, []);
});

test("RTL reading order of the extracted text is preserved", () => {
  const s = segment(`«${HADITH}»`);
  assert.equal(s.candidates[0].quote.split(" ")[0], HADITH.split(" ")[0]);
});

test("attribution suffixes are removed", () => {
  for (const suffix of ["(رواه البخاري)", "رواه البخاري ومسلم", "متفق عليه", "[رواه مسلم]"]) {
    const s = segment(`قال النبي ﷺ: ${HADITH} ${suffix}`);
    assert.equal(s.candidates[0].quote, HADITH, suffix);
  }
});

test("output is deterministic", () => {
  const raw = `الادعاء هنا واضح جدا لقوله تعالى ﴿${PARTIAL}﴾ و«${HADITH}»`;
  assert.deepEqual(segment(raw), segment(raw));
});

test("ornate brackets read as parentheses still give the quote; references and honorifics in parentheses do not", () => {
  const s = segment(`يقول بعضهم إن هذه الآية تأمر بكذا لقوله تعالى: .(${PARTIAL}) (البقرة: ١٩١)\nعن عمر (رضي الله عنه) عن النبي (صلى الله عليه وسلم)`);
  assert.deepEqual(s.candidates.map((c) => c.quote), [PARTIAL]);
  assert.equal(s.candidates[0].marker, "parentheses");
});
