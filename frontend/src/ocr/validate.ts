/* Image checks for screenshot verification. Everything runs in the visitor's browser: the file is never uploaded.
   The file is trusted for nothing - not its name, not its extension, not the type the browser guessed from the
   extension. Order: size, actual signature (magic bytes), declared type vs signature, dimensions read from the
   header BEFORE any decoding (decompression-bomb limit), then a real decode. */

import { ar } from "../format";

export type ImgType = "image/png" | "image/jpeg" | "image/webp";

export const MAX_BYTES = 8 * 1024 * 1024;      // 8 MB: room for a full-height phone screenshot saved as PNG
export const MAX_SIDE = 8000;                  // px, either side
export const MAX_PIXELS = 24_000_000;          // 24 MP (~96 MB as RGBA once decoded)
export const MIN_SIDE = 16;                    // px: smaller than this cannot hold readable text
export const ACCEPT = "image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp";

export type ValidationCode =
  | "EMPTY" | "TOO_LARGE" | "UNSUPPORTED_TYPE" | "NOT_AN_IMAGE" | "TYPE_MISMATCH"
  | "DIMENSIONS_TOO_LARGE" | "DIMENSIONS_TOO_SMALL" | "CORRUPT";

export const VALIDATION_TEXT: Record<ValidationCode, { title: string; next: string }> = {
  EMPTY: { title: "الملف فارغ.", next: "اختر صورة تحتوي على النص." },
  TOO_LARGE: { title: "حجم الصورة أكبر من ٨ ميغابايت.", next: "قصّ الصورة على النص المطلوب أو احفظها بحجم أصغر، ثم أعد المحاولة." },
  UNSUPPORTED_TYPE: { title: "نوع الملف غير مدعوم.", next: "الأنواع المدعومة: PNG وJPG وWEBP. التقط لقطة شاشة واحفظها بأحد هذه الأنواع." },
  NOT_AN_IMAGE: { title: "الملف ليس صورة صالحة.", next: "محتوى الملف لا يطابق أي نوع صورة مدعوم، مهما كان امتداد اسمه." },
  TYPE_MISMATCH: { title: "نوع الملف لا يطابق محتواه.", next: "امتداد الملف يدل على نوع، ومحتواه من نوع آخر. احفظ الصورة من جديد بامتدادها الصحيح." },
  DIMENSIONS_TOO_LARGE: { title: "أبعاد الصورة كبيرة جدًا.", next: "الحد الأقصى ٨٠٠٠ بكسل لكل ضلع و٢٤ مليون بكسل إجمالًا. قصّ الصورة على النص المطلوب." },
  DIMENSIONS_TOO_SMALL: { title: "الصورة صغيرة جدًا لاستخراج نص منها.", next: "استخدم لقطة شاشة أوضح للنص." },
  CORRUPT: { title: "تعذّرت قراءة الصورة.", next: "قد يكون الملف تالفًا أو غير مكتمل. جرّب حفظ لقطة الشاشة من جديد." },
};

export type ValidImage = { type: ImgType; width: number; height: number; bitmap: ImageBitmap };
export type Validation = { ok: true; image: ValidImage } | { ok: false; code: ValidationCode };

const startsWith = (b: Uint8Array, sig: number[], at = 0) => sig.every((v, i) => b[at + i] === v);
const ascii = (b: Uint8Array, at: number, n: number) => String.fromCharCode(...b.subarray(at, at + n));

/** The file's real type, from its first bytes. */
export function sniff(b: Uint8Array): ImgType | null {
  if (startsWith(b, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return "image/png";
  if (startsWith(b, [0xff, 0xd8, 0xff])) return "image/jpeg";
  if (ascii(b, 0, 4) === "RIFF" && ascii(b, 8, 4) === "WEBP") return "image/webp";
  return null;
}

/** Recognisable formats that are deliberately not accepted (animated, vector, document or camera formats). */
function knownUnsupported(b: Uint8Array): boolean {
  const head = ascii(b, 0, 16);
  if (head.startsWith("GIF8") || head.startsWith("%PDF") || head.startsWith("BM")) return true;
  if (startsWith(b, [0x49, 0x49, 0x2a, 0x00]) || startsWith(b, [0x4d, 0x4d, 0x00, 0x2a])) return true;   // TIFF
  if (ascii(b, 4, 4) === "ftyp") return true;                                                         // HEIC/AVIF
  const text = new TextDecoder("utf-8", { fatal: false }).decode(b.subarray(0, 512)).trimStart().toLowerCase();
  return text.startsWith("<svg") || (text.startsWith("<?xml") && text.includes("<svg"));
}

const u16be = (b: Uint8Array, i: number) => (b[i] << 8) | b[i + 1];
const u32be = (b: Uint8Array, i: number) => ((b[i] << 24) >>> 0) + (b[i + 1] << 16) + (b[i + 2] << 8) + b[i + 3];
const u24le = (b: Uint8Array, i: number) => b[i] | (b[i + 1] << 8) | (b[i + 2] << 16);

/** Width and height from the file header, without decoding pixels. null if the header is malformed. */
export function headerDimensions(b: Uint8Array, type: ImgType): { width: number; height: number } | null {
  if (type === "image/png") {
    if (b.length < 24 || ascii(b, 12, 4) !== "IHDR") return null;
    return { width: u32be(b, 16), height: u32be(b, 20) };
  }
  if (type === "image/webp") {
    if (b.length < 30) return null;
    const chunk = ascii(b, 12, 4);
    if (chunk === "VP8X") return { width: 1 + u24le(b, 24), height: 1 + u24le(b, 27) };
    if (chunk === "VP8 " && startsWith(b, [0x9d, 0x01, 0x2a], 23)) {
      return { width: (b[26] | (b[27] << 8)) & 0x3fff, height: (b[28] | (b[29] << 8)) & 0x3fff };
    }
    if (chunk === "VP8L" && b[20] === 0x2f) {
      const bits = b[21] | (b[22] << 8) | (b[23] << 16) | (b[24] << 24);
      return { width: (bits & 0x3fff) + 1, height: ((bits >>> 14) & 0x3fff) + 1 };
    }
    return null;
  }
  // JPEG: walk the segments to the first start-of-frame marker
  let i = 2;
  while (i + 9 < b.length) {
    if (b[i] !== 0xff) return null;
    const marker = b[i + 1];
    if (marker === 0xff) { i += 1; continue; }                       // fill byte
    if (marker === 0xd8 || (marker >= 0xd0 && marker <= 0xd7) || marker === 0x01) { i += 2; continue; }
    if (marker === 0xd9 || marker === 0xda) return null;              // end of image / scan before any frame
    const len = u16be(b, i + 2);
    if (len < 2) return null;
    const sof = marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc;
    if (sof) return { width: u16be(b, i + 7), height: u16be(b, i + 5) };
    i += 2 + len;
  }
  return null;
}

function declaredType(file: File): string {
  const t = (file.type || "").toLowerCase();
  return t === "image/jpg" || t === "image/pjpeg" ? "image/jpeg" : t;
}

export async function validateImage(file: File): Promise<Validation> {
  if (file.size === 0) return { ok: false, code: "EMPTY" };
  if (file.size > MAX_BYTES) return { ok: false, code: "TOO_LARGE" };
  let bytes: Uint8Array;
  try {
    bytes = new Uint8Array(await file.arrayBuffer());
  } catch {
    return { ok: false, code: "CORRUPT" };
  }
  const type = sniff(bytes);
  if (!type) return { ok: false, code: knownUnsupported(bytes) ? "UNSUPPORTED_TYPE" : "NOT_AN_IMAGE" };
  const declared = declaredType(file);
  if (declared && declared !== type) {
    const declaredSupported = ["image/png", "image/jpeg", "image/webp"].includes(declared);
    return { ok: false, code: declaredSupported ? "TYPE_MISMATCH" : "UNSUPPORTED_TYPE" };
  }
  const dims = headerDimensions(bytes, type);
  if (!dims || !dims.width || !dims.height) return { ok: false, code: "CORRUPT" };
  if (dims.width > MAX_SIDE || dims.height > MAX_SIDE || dims.width * dims.height > MAX_PIXELS) {
    return { ok: false, code: "DIMENSIONS_TOO_LARGE" };
  }
  if (dims.width < MIN_SIDE || dims.height < MIN_SIDE) return { ok: false, code: "DIMENSIONS_TOO_SMALL" };

  let bitmap: ImageBitmap;
  try {
    // decoded from the bytes already checked, labelled with the sniffed type (never the file's own label)
    bitmap = await createImageBitmap(new Blob([bytes as BlobPart], { type }));
  } catch {
    return { ok: false, code: "CORRUPT" };
  }
  const same = bitmap.width === dims.width && bitmap.height === dims.height;
  const rotated = bitmap.width === dims.height && bitmap.height === dims.width;   // EXIF orientation applied
  if (!same && !rotated) {
    bitmap.close();
    return { ok: false, code: "CORRUPT" };
  }
  return { ok: true, image: { type, width: bitmap.width, height: bitmap.height, bitmap } };
}

/** A file name safe to show: base name only, no control or bidirectional-override characters, length-capped.
 *  It is only ever rendered as text (never as HTML) and never sent anywhere. */
export function displayName(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? "";
  // eslint-disable-next-line no-control-regex
  const clean = base.replace(/[\u0000-\u001f\u007f-\u009f‎‏‪-‮⁦-⁩]/g, "").trim();
  if (!clean) return "صورة";
  return clean.length > 48 ? `${clean.slice(0, 22)}…${clean.slice(-22)}` : clean;
}

export function formatBytes(n: number): string {
  const f = (x: number) => ar(String(Math.round(x * 10) / 10).replace(".", "٫"));
  if (n < 1024) return `${ar(n)} بايت`;
  if (n < 1024 * 1024) return `${f(n / 1024)} كيلوبايت`;
  return `${f(n / (1024 * 1024))} ميغابايت`;
}
