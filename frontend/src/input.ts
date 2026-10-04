/* Input rules shared by both ways of entering a quote (typed text, or text confirmed from a screenshot): one set of
   rules, one request, one pipeline. */
import { ar } from "./format";

export const MIN = 2;
export const MAX = 2000;
const ARABIC = /[ء-يٱ-ۓ]/;

export type FieldErrors = { quote?: string; claim?: string };

export function checkInput(quote: string, claim: string): FieldErrors {
  const fe: FieldErrors = {};
  const q = quote.trim(), c = claim.trim();
  if (q.length < MIN) fe.quote = "أدخل الاقتباس.";
  else if (!ARABIC.test(q)) fe.quote = "يجب أن يحتوي الاقتباس على نص عربي.";
  else if (q.length > MAX) fe.quote = `الاقتباس أطول من ${ar(MAX)} حرف. اختصره إلى الجزء الذي تريد التحقق منه.`;
  if (c.length < MIN) fe.claim = "أدخل الادعاء الذي قُدِّم مع الاقتباس.";
  else if (c.length > MAX) fe.claim = `الادعاء أطول من ${ar(MAX)} حرف.`;
  return fe;
}
