/* Text extraction from a screenshot, entirely in the visitor's browser (tesseract.js, Arabic LSTM model).
   The engine, its WebAssembly core and the Arabic model are served by this site under /ocr/ (see vite.config.ts);
   nothing is fetched from a third party and the image is never sent anywhere. A fresh worker is started for each
   image and terminated afterwards; the working canvas is released. The model is not cached in IndexedDB.

   The OCR confidence describes how clearly the engine read the pixels. It says nothing about whether the text is
   authentic or where it comes from; the UI shows it only as "text extraction quality". */

import type { LoggerMessage, Worker } from "tesseract.js";

export type OcrPhase = "engine" | "model" | "recognize";
export type OcrProgress = { phase: OcrPhase; progress: number | null };
export type OcrQuality = "good" | "fair" | "poor";
export type OcrResult = {
  text: string;
  confidence: number;          // tesseract mean word confidence, 0-100 (pixel legibility only)
  quality: OcrQuality;
  unclearWords: string[];      // words the engine read with low confidence, for the visitor to check
  inverted: boolean;           // light text on a dark background was inverted before recognition
  scale: number;
  ms: { engine: number; recognize: number };
};
export type OcrFailure = "ENGINE" | "TIMEOUT" | "ABORTED";
export class OcrError extends Error {
  constructor(public code: OcrFailure) { super(code); }
}

const BASE = import.meta.env.BASE_URL || "/";
const asset = (p: string) => new URL(`${BASE}ocr/${p}`, window.location.href).href;
const TIMEOUT_MS = 120_000;
const MAX_OCR_PIXELS = 16_000_000;
const UNCLEAR_BELOW = 60;

export function qualityOf(confidence: number): OcrQuality {
  return confidence >= 85 ? "good" : confidence >= 65 ? "fair" : "poor";
}

/** Grey-scale copy for recognition: small screenshots are upscaled (small text reads better), dark-mode
 *  screenshots are inverted (the model expects dark text on a light background). Pixels only: metadata such as
 *  EXIF is never read or passed on. */
export function prepare(bitmap: ImageBitmap): { canvas: HTMLCanvasElement; inverted: boolean; scale: number } {
  let scale = bitmap.width < 1000 ? Math.min(2, 2000 / bitmap.width) : 1;
  if (bitmap.width * bitmap.height * scale * scale > MAX_OCR_PIXELS) {
    scale = Math.sqrt(MAX_OCR_PIXELS / (bitmap.width * bitmap.height));
  }
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new OcrError("ENGINE");
  ctx.fillStyle = "#ffffff";                  // transparent areas read as white paper
  ctx.fillRect(0, 0, w, h);
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(bitmap, 0, 0, w, h);
  const img = ctx.getImageData(0, 0, w, h);
  const d = img.data;
  let sum = 0;
  for (let i = 0; i < d.length; i += 4) {
    const y = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
    d[i] = d[i + 1] = d[i + 2] = y;
    sum += y;
  }
  const inverted = sum / (w * h) < 110;
  if (inverted) for (let i = 0; i < d.length; i += 4) d[i] = d[i + 1] = d[i + 2] = 255 - d[i];
  ctx.putImageData(img, 0, 0);
  return { canvas, inverted, scale };
}

function phaseOf(m: LoggerMessage): OcrProgress | null {
  switch (m.status) {
    case "loading tesseract core":
    case "initializing tesseract":
    case "initializing api":
      return { phase: "engine", progress: null };
    case "loading language traineddata":
      return { phase: "model", progress: typeof m.progress === "number" ? m.progress : null };
    case "recognizing text":
      return { phase: "recognize", progress: typeof m.progress === "number" ? m.progress : null };
    default:
      return null;
  }
}

type Block = { paragraphs?: { lines?: { words?: { text: string; confidence: number }[] }[] }[] };

export async function extractText(bitmap: ImageBitmap, onProgress: (p: OcrProgress) => void,
  signal: AbortSignal): Promise<OcrResult> {
  if (signal.aborted) throw new OcrError("ABORTED");
  let fail!: (e: OcrError) => void;
  const failed = new Promise<never>((_, reject) => { fail = reject; });
  failed.catch(() => {});                              // observed through Promise.race below
  const onAbort = () => fail(new OcrError("ABORTED"));
  signal.addEventListener("abort", onAbort, { once: true });
  const timer = window.setTimeout(() => fail(new OcrError("TIMEOUT")), TIMEOUT_MS);

  let worker: Worker | null = null;
  let pending: Promise<Worker> | null = null;
  let prepared: ReturnType<typeof prepare> | null = null;
  const t0 = performance.now();
  try {
    onProgress({ phase: "engine", progress: null });
    const { createWorker } = await Promise.race([import("tesseract.js"), failed]);
    pending = createWorker("ara", 1, {
      workerPath: asset("worker.min.js"),
      corePath: asset("core"),
      langPath: asset("lang"),
      gzip: true,
      cacheMethod: "none",
      workerBlobURL: false,
      logger: (m: LoggerMessage) => { const p = phaseOf(m); if (p) onProgress(p); },
      errorHandler: () => fail(new OcrError("ENGINE")),
    });
    worker = await Promise.race([pending, failed]);
    const t1 = performance.now();
    prepared = prepare(bitmap);
    const { data } = await Promise.race([
      worker.recognize(prepared.canvas, {}, { text: true, blocks: true }),
      failed,
    ]);
    const words = ((data.blocks ?? []) as Block[])
      .flatMap((b) => b.paragraphs ?? []).flatMap((p) => p.lines ?? []).flatMap((l) => l.words ?? []);
    const unclear = words.filter((w) => w.confidence < UNCLEAR_BELOW && /[؀-ۿ]/.test(w.text)).map((w) => w.text.trim().replace(/^[^\u0621-\u06d3]+|[^\u0621-\u06d3]+$/g, ""))
      .filter(Boolean);
    const confidence = Math.round(data.confidence ?? 0);
    return {
      text: data.text ?? "",
      confidence,
      quality: qualityOf(confidence),
      unclearWords: [...new Set(unclear)].slice(0, 12),
      inverted: prepared.inverted,
      scale: prepared.scale,
      ms: { engine: Math.round(t1 - t0), recognize: Math.round(performance.now() - t1) },
    };
  } catch (e) {
    throw e instanceof OcrError ? e : new OcrError("ENGINE");
  } finally {
    window.clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
    if (worker) void worker.terminate().catch(() => {});
    else if (pending) void pending.then((w) => w.terminate()).catch(() => {});   // finished loading after we gave up
    if (prepared) { prepared.canvas.width = 0; prepared.canvas.height = 0; }
  }
}
